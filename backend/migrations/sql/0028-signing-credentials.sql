ALTER TABLE public.otm_operation DROP CONSTRAINT ck_operation_kind;

ALTER TABLE public.otm_operation ADD CONSTRAINT ck_operation_kind CHECK (kind IN ('inspect_import','organization_action','configuration_update','configuration_check','cost_collection','required_user_check','recovery_network_repair','recovery_password','signing_key'));

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;

ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry','configuration_check_outcome','cost_collection_outcome','required_user_check_outcome','recovery_network_outcome','recovery_password_outcome','recovery_password_disclosed','signing_key_outcome','signing_key_requested','operation_responsibility_changed','email_delivery') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided','cost_refresh_requested') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK ((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (command_kind='organization_action' AND (step_key='apply_lifecycle' OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap','establish_automation','verify_automation','configure_required','verify_required','retire_temporary','configure_baseline','verify_configured_access','capture_required_users','prepare_automation_signer','prepare_recovery_password')) OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') OR (command_kind='configuration_check' AND step_key ~ '^configuration_check:[0-9a-f-]{36}$') OR (command_kind='cost_collection' AND step_key ~ '^cost:[0-9a-f-]{36}$') OR (command_kind='required_user_check' AND step_key ~ '^required_users:[0-9a-f-]{36}$') OR (command_kind='recovery_network_repair' AND step_key ~ '^recovery_network:[0-9a-f-]{36}$') OR (command_kind='recovery_password' AND step_key ~ '^recovery_password:[0-9a-f-]{36}$') OR (command_kind='signing_key' AND step_key ~ '^signing_key:[0-9a-f-]{36}$'));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_read_only;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_read_only CHECK ((command_kind IN ('inspect_tenancy','configuration_check','cost_collection','required_user_check') AND effect_knowledge='none') OR (command_kind IN ('organization_action','onboarding','configuration_update') AND effect_knowledge IN ('none','known')) OR (command_kind IN ('recovery_network_repair','recovery_password','signing_key') AND effect_knowledge IN ('none','known','unknown')));


CREATE TABLE public.otm_signing_credential (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	tenancy_id UUID NOT NULL, 
	principal_binding_id UUID NOT NULL, 
	connection_id UUID NOT NULL, 
	source_operation_id UUID NOT NULL, 
	source_evidence_event_id UUID NOT NULL, 
	target JSONB NOT NULL, 
	target_hash VARCHAR(64) NOT NULL, 
	current_key JSONB, 
	current_hash VARCHAR(64), 
	generation INTEGER NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	retire_at TIMESTAMP WITH TIME ZONE, 
	rotation_operation_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, id), 
	UNIQUE (workspace_id, tenancy_id, id), 
	UNIQUE (workspace_id, principal_binding_id), 
	FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	FOREIGN KEY(workspace_id, tenancy_id, principal_binding_id) REFERENCES public.otm_managed_object_binding (workspace_id, tenancy_id, id), 
	FOREIGN KEY(workspace_id, tenancy_id, connection_id) REFERENCES public.otm_user_presence_connection (workspace_id, tenancy_id, id), 
	FOREIGN KEY(workspace_id, source_operation_id, source_evidence_event_id) REFERENCES public.audit_event (workspace_id, operation_id, id), 
	FOREIGN KEY(workspace_id, rotation_operation_id) REFERENCES public.otm_operation (workspace_id, id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT ck_signing_credential_state CHECK (state IN ('staging','usable','rotating','attention','retired') AND generation>=0 AND updated_at>=created_at AND target_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(target)='object'), 
	CONSTRAINT ck_signing_credential_current CHECK ((generation=0 AND current_key IS NULL AND current_hash IS NULL AND retire_at IS NULL AND state IN ('staging','attention','retired')) OR (generation>=1 AND jsonb_typeof(current_key)='object' AND current_hash ~ '^[0-9a-f]{64}$' AND retire_at IS NOT NULL))
)

;

CREATE INDEX ix_signing_credential_due ON public.otm_signing_credential (workspace_id, retire_at, id) WHERE state = 'usable';

CREATE UNIQUE INDEX uq_signing_credential_active ON public.otm_signing_credential (workspace_id, tenancy_id) WHERE state != 'retired';

CREATE TRIGGER signing_credential_no_delete BEFORE DELETE ON public.otm_signing_credential FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();

CREATE TRIGGER signing_credential_no_truncate BEFORE TRUNCATE ON public.otm_signing_credential FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();

CREATE FUNCTION public.otm_signing_credential_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE user_row public.otm_managed_object_binding%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (to_jsonb(NEW)-'current_key'-'current_hash'-'generation'-'state'-'retire_at'-'rotation_operation_id'-'updated_at') IS DISTINCT FROM
     (to_jsonb(OLD)-'current_key'-'current_hash'-'generation'-'state'-'retire_at'-'rotation_operation_id'-'updated_at')
     OR OLD.state='retired' OR NEW.updated_at<OLD.updated_at
     OR NEW.generation NOT IN (OLD.generation,OLD.generation+1)
  THEN RAISE EXCEPTION 'SIGNING_CREDENTIAL_ANCHOR_IMMUTABLE'; END IF;
 ELSE
  IF NEW.state<>'staging' OR NEW.generation<>0 OR NEW.created_at<>NEW.updated_at
    OR NOT EXISTS(SELECT 1 FROM public.otm_tenancy t
       JOIN public.otm_operation o ON o.workspace_id=t.workspace_id AND o.id=t.operation_id
       JOIN public.audit_event e ON e.workspace_id=o.workspace_id AND e.operation_id=o.id
         AND e.id=o.current_intent_event_id AND e.kind='operation_intent'
       JOIN public.otm_user_presence_connection c ON c.workspace_id=t.workspace_id AND c.tenancy_id=t.id
         AND c.id=NEW.connection_id AND c.state='active'
       WHERE t.workspace_id=NEW.workspace_id AND t.id=NEW.tenancy_id AND t.status='pending'
         AND t.provider_mode='simulated' AND o.id=NEW.source_operation_id
         AND o.kind='organization_action' AND o.state='queued'
         AND e.data->'intent'->>'signing_key_rotation_contract'='signer-1'
         AND e.data->'intent'->>'action' IN ('create_tenancy','import_tenancy')
         AND c.created_operation_id=o.id AND c.source_evidence_event_id=NEW.source_evidence_event_id
         AND c.automation_binding_id=NEW.principal_binding_id)
  THEN RAISE EXCEPTION 'SIGNING_CREDENTIAL_ENROLLMENT_UNVERIFIED'; END IF;
 END IF;
 SELECT * INTO user_row FROM public.otm_managed_object_binding
  WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id AND id=NEW.principal_binding_id;
 IF NEW.target->>'workspace_id' IS DISTINCT FROM NEW.workspace_id
    OR NEW.target->>'tenancy_id' IS DISTINCT FROM NEW.tenancy_id::text
    OR NEW.target->>'subject_binding_id' IS DISTINCT FROM NEW.principal_binding_id::text
    OR NEW.target->>'purpose' IS DISTINCT FROM 'automation'
    OR NEW.target->>'provider_ocid' IS DISTINCT FROM user_row.provider_ocid
    OR NEW.target->>'scim_resource_id' IS DISTINCT FROM user_row.scim_resource_id
    OR NEW.target->>'user_name' IS DISTINCT FROM user_row.user_name
    OR user_row.logical_key IS DISTINCT FROM 'identity/user/automation'
    OR NEW.generation>0 AND (
       NEW.current_key->'version'->'target' IS DISTINCT FROM NEW.target
       OR NEW.current_key->'version'->>'credential_id' IS DISTINCT FROM NEW.id::text
       OR NEW.current_key->'version'->>'generation' IS DISTINCT FROM NEW.generation::text)
 THEN RAISE EXCEPTION 'SIGNING_CREDENTIAL_SCOPE_INVALID'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.otm_operation o JOIN public.audit_event e
    ON e.workspace_id=o.workspace_id AND e.operation_id=o.id AND e.id=o.current_intent_event_id
    AND e.kind='operation_intent'
    WHERE o.workspace_id=NEW.workspace_id AND o.id=NEW.rotation_operation_id AND o.kind='signing_key'
      AND e.data->'intent'->>'credential_id'=NEW.id::text
      AND e.data->'intent'->'subject'=NEW.target)
 THEN RAISE EXCEPTION 'SIGNING_CREDENTIAL_OPERATION_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER signing_credential_guard BEFORE INSERT OR UPDATE ON public.otm_signing_credential
 FOR EACH ROW EXECUTE FUNCTION public.otm_signing_credential_guard();
CREATE UNIQUE INDEX uq_signing_request ON public.audit_event(workspace_id,actor_subject,(data->>'client_request_key')) WHERE kind='signing_key_requested';
