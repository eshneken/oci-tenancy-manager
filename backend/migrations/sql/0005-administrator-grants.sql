-- Explicit application grants; existing pre-grant sessions cannot be adopted.
DELETE FROM public.otm_admin_session;

CREATE TABLE public.otm_administrator (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	identity_kind VARCHAR(32) NOT NULL, 
	issuer VARCHAR(256) NOT NULL, 
	subject VARCHAR(256) NOT NULL, 
	display_name VARCHAR(256) NOT NULL, 
	email VARCHAR(256), 
	status VARCHAR(16) NOT NULL, 
	authorization_revision UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_administrator_workspace_id UNIQUE (workspace_id, id), 
	CONSTRAINT uq_administrator_identity UNIQUE (workspace_id, issuer, subject), 
	CONSTRAINT ck_administrator_kind CHECK (identity_kind IN ('local_recovery','corporate_sso')), 
	CONSTRAINT ck_administrator_status CHECK (status IN ('active','revoked')), 
	CONSTRAINT ck_administrator_revocation CHECK ((status='active' AND revoked_at IS NULL) OR (status='revoked' AND revoked_at IS NOT NULL)), 
	CONSTRAINT ck_administrator_times CHECK (updated_at>=created_at AND (revoked_at IS NULL OR revoked_at>=created_at)), 
	CONSTRAINT ck_administrator_local CHECK (identity_kind!='local_recovery' OR (subject=id::text AND status='active')), 
	CONSTRAINT ck_administrator_text CHECK (length(btrim(workspace_id))>0 AND length(btrim(issuer))>0 AND length(btrim(subject))>0 AND length(btrim(display_name))>0)
)

;

CREATE TABLE public.otm_local_credential (
	workspace_id VARCHAR(256) NOT NULL, 
	administrator_id UUID NOT NULL, 
	password_hash VARCHAR(2048) NOT NULL, 
	totp_secret_reference VARCHAR(1024) NOT NULL, 
	last_totp_step BIGINT NOT NULL, 
	mfa_enrolled_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	password_changed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	failed_attempts INTEGER NOT NULL, 
	failure_window_started_at TIMESTAMP WITH TIME ZONE, 
	retry_after TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (workspace_id, administrator_id), 
	CONSTRAINT fk_local_credential_administrator FOREIGN KEY(workspace_id, administrator_id) REFERENCES public.otm_administrator (workspace_id, id), 
	CONSTRAINT ck_local_credential_counts CHECK (last_totp_step>=0 AND failed_attempts>=0), 
	CONSTRAINT ck_local_credential_material CHECK (password_hash LIKE '$argon2id$%%' AND length(btrim(totp_secret_reference))>0), 
	CONSTRAINT ck_local_credential_throttle CHECK ((failed_attempts=0 AND failure_window_started_at IS NULL AND retry_after IS NULL) OR (failed_attempts>0 AND failure_window_started_at IS NOT NULL AND (retry_after IS NULL OR retry_after>=failure_window_started_at)))
)

;
CREATE UNIQUE INDEX uq_administrator_recovery ON public.otm_administrator (workspace_id) WHERE identity_kind = 'local_recovery';
ALTER TABLE public.audit_event ALTER COLUMN operation_id DROP NOT NULL;
ALTER TABLE public.audit_event ADD COLUMN administrator_id UUID;
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT fk_audit_administrator FOREIGN KEY(workspace_id, administrator_id) REFERENCES public.otm_administrator (workspace_id, id);
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome') AND intent_revision IS NULL))) OR (kind='administrator_revoked' AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL));
ALTER TABLE public.otm_admin_session ADD CONSTRAINT fk_session_administrator_identity FOREIGN KEY(workspace_id, issuer, subject) REFERENCES public.otm_administrator (workspace_id, issuer, subject);

-- Ordinary application privileges cannot bypass protected local identity custody.
CREATE FUNCTION public.otm_protect_administrator() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE owner_role text;
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'ADMINISTRATOR_HISTORY_PROTECTED';
 END IF;
 IF TG_OP='UPDATE' AND
    (NEW.id,NEW.workspace_id,NEW.identity_kind,NEW.issuer,NEW.subject,NEW.created_at)
    IS DISTINCT FROM
    (OLD.id,OLD.workspace_id,OLD.identity_kind,OLD.issuer,OLD.subject,OLD.created_at) THEN
  RAISE EXCEPTION 'ADMINISTRATOR_IDENTITY_IMMUTABLE';
 END IF;
 IF NEW.identity_kind='local_recovery' THEN
  SELECT pg_catalog.pg_get_userbyid(relowner) INTO owner_role FROM pg_catalog.pg_class
   WHERE oid='public.otm_administrator'::pg_catalog.regclass;
  IF NOT pg_catalog.pg_has_role(current_user,owner_role,'MEMBER') THEN
   RAISE EXCEPTION 'OPERATOR_PRIVILEGES_REQUIRED';
  END IF;
 END IF;
 IF TG_OP='UPDATE' AND
    (NEW.status IS DISTINCT FROM OLD.status OR NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
    AND NEW.authorization_revision=OLD.authorization_revision THEN
  RAISE EXCEPTION 'NEW_AUTHORIZATION_REVISION_REQUIRED';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER otm_administrator_protection BEFORE INSERT OR UPDATE OR DELETE
 ON public.otm_administrator FOR EACH ROW EXECUTE FUNCTION public.otm_protect_administrator();

-- A credential may never be attached to an ordinary corporate grant.
CREATE FUNCTION public.otm_require_local_credential() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM public.otm_administrator
    WHERE workspace_id=NEW.workspace_id AND id=NEW.administrator_id
      AND identity_kind='local_recovery') THEN
  RAISE EXCEPTION 'LOCAL_RECOVERY_CREDENTIAL_REQUIRED';
 END IF;
 IF TG_OP='UPDATE' AND
    (NEW.workspace_id,NEW.administrator_id) IS DISTINCT FROM
    (OLD.workspace_id,OLD.administrator_id) THEN
  RAISE EXCEPTION 'CREDENTIAL_IDENTITY_IMMUTABLE';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER otm_local_credential_protection BEFORE INSERT OR UPDATE
 ON public.otm_local_credential FOR EACH ROW EXECUTE FUNCTION public.otm_require_local_credential();
