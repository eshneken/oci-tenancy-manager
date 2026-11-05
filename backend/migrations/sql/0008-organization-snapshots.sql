-- Organization snapshots are isolated from the preserved prototype and retain existing audit history.


CREATE TABLE public.org_workspace (
	id VARCHAR(256) NOT NULL, 
	configuration_id UUID NOT NULL, 
	configuration JSONB NOT NULL, 
	applied_version_id UUID, 
	proposed_version_id UUID, 
	applied_kind VARCHAR(16) DEFAULT 'applied' NOT NULL, 
	proposed_kind VARCHAR(16) DEFAULT 'proposed' NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_org_head_kinds CHECK (applied_kind='applied' AND proposed_kind='proposed'), 
	CONSTRAINT ck_org_configuration_id CHECK ((configuration->>'id') IS NOT DISTINCT FROM configuration_id::text)
)

;


CREATE TABLE public.org_person (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_person_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_org_person_email UNIQUE (workspace_id, email), 
	CONSTRAINT fk_org_person_workspace FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id)
)

;


CREATE TABLE public.org_feed (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	source_id VARCHAR(256) NOT NULL, 
	population_id VARCHAR(256) NOT NULL, 
	external_id VARCHAR(512) NOT NULL, 
	received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE, 
	digest VARCHAR(64) NOT NULL, 
	raw_digest VARCHAR(64), 
	data JSONB NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	diagnostics JSONB NOT NULL, 
	proposed_version_id UUID, 
	applied_version_id UUID, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_feed_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_org_delivery UNIQUE (workspace_id, source_id, external_id), 
	CONSTRAINT fk_org_feed_workspace FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id), 
	CONSTRAINT ck_org_feed_state CHECK (state IN ('received','staged','published','rejected','superseded')), 
	CONSTRAINT ck_org_feed_digest CHECK (digest ~ '^[0-9a-f]{64}$' AND (raw_digest IS NULL OR raw_digest ~ '^[0-9a-f]{64}$'))
)

;

CREATE INDEX ix_org_feed_received ON public.org_feed (workspace_id, received_at, id);


CREATE TABLE public.org_version (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	base_version_id UUID, 
	feed_id UUID NOT NULL, 
	configuration_id UUID NOT NULL, 
	configuration JSONB NOT NULL, 
	member_count INTEGER NOT NULL, 
	sealed BOOLEAN DEFAULT 'false' NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_version_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_org_version_kind UNIQUE (workspace_id, id, kind), 
	CONSTRAINT ck_org_version_kind CHECK (kind IN ('proposed','applied')), 
	CONSTRAINT ck_org_version_configuration CHECK ((configuration->>'id') IS NOT DISTINCT FROM configuration_id::text), 
	CONSTRAINT fk_org_version_workspace FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id), 
	CONSTRAINT fk_org_version_feed FOREIGN KEY(workspace_id, feed_id) REFERENCES public.org_feed (workspace_id, id), 
	CONSTRAINT fk_org_version_base FOREIGN KEY(workspace_id, base_version_id) REFERENCES public.org_version (workspace_id, id)
)

;


CREATE TABLE public.org_member (
	workspace_id VARCHAR(256) NOT NULL, 
	version_id UUID NOT NULL, 
	person_id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	full_name VARCHAR, 
	manager_person_id UUID, 
	manager_email VARCHAR(320), 
	profile VARCHAR(16) NOT NULL, 
	evidence VARCHAR(16) NOT NULL, 
	lob_id VARCHAR, 
	accountable_leader_email VARCHAR(320), 
	designee_emails JSONB NOT NULL, 
	ancestry VARCHAR(16) NOT NULL, 
	absence_review BOOLEAN NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (workspace_id, version_id, person_id), 
	CONSTRAINT uq_org_member_email UNIQUE (workspace_id, version_id, email), 
	CONSTRAINT fk_org_member_version FOREIGN KEY(workspace_id, version_id) REFERENCES public.org_version (workspace_id, id), 
	CONSTRAINT fk_org_member_person FOREIGN KEY(workspace_id, person_id) REFERENCES public.org_person (workspace_id, id), 
	CONSTRAINT fk_org_member_manager FOREIGN KEY(workspace_id, version_id, manager_person_id) REFERENCES public.org_member (workspace_id, version_id, person_id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT ck_org_member_profile CHECK (profile IN ('employee','reference','configured')), 
	CONSTRAINT ck_org_member_evidence CHECK (evidence IN ('feed_row','retained','reference','configured')), 
	CONSTRAINT ck_org_member_ancestry CHECK (ancestry IN ('root','resolved','incomplete')), 
	CONSTRAINT ck_org_member_not_self CHECK (person_id<>manager_person_id)
)

;

CREATE INDEX ix_org_manager_children ON public.org_member (workspace_id, version_id, manager_person_id);

ALTER TABLE public.org_workspace ADD CONSTRAINT fk_org_workspace_applied_kind FOREIGN KEY(id, applied_version_id, applied_kind) REFERENCES public.org_version (workspace_id, id, kind) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.org_workspace ADD CONSTRAINT fk_org_workspace_proposed_kind FOREIGN KEY(id, proposed_version_id, proposed_kind) REFERENCES public.org_version (workspace_id, id, kind) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.org_feed ADD CONSTRAINT fk_org_feed_applied_version_id FOREIGN KEY(workspace_id, applied_version_id) REFERENCES public.org_version (workspace_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.org_feed ADD CONSTRAINT fk_org_feed_proposed_version_id FOREIGN KEY(workspace_id, proposed_version_id) REFERENCES public.org_version (workspace_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;

ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

-- Protect historical identities and every snapshot table from destructive runtime operations.
CREATE FUNCTION public.org_deny_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'organization history is immutable'; END $$;
CREATE TRIGGER org_person_immutable BEFORE UPDATE OR DELETE ON public.org_person FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_workspace_no_delete BEFORE DELETE ON public.org_workspace FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_workspace_no_truncate BEFORE TRUNCATE ON public.org_workspace FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_person_no_truncate BEFORE TRUNCATE ON public.org_person FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_feed_no_truncate BEFORE TRUNCATE ON public.org_feed FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_version_no_truncate BEFORE TRUNCATE ON public.org_version FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_member_no_truncate BEFORE TRUNCATE ON public.org_member FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();

CREATE FUNCTION public.org_guard_feed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.state<>'received' OR NEW.proposed_version_id IS NOT NULL OR NEW.applied_version_id IS NOT NULL THEN RAISE EXCEPTION 'organization feed must begin received'; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'organization feed is immutable'; END IF;
  IF OLD.state IN ('published','rejected','superseded') OR
     ROW(NEW.id,NEW.workspace_id,NEW.source_id,NEW.population_id,NEW.external_id,NEW.received_at,NEW.captured_at,NEW.digest,NEW.raw_digest,NEW.data)
     IS DISTINCT FROM ROW(OLD.id,OLD.workspace_id,OLD.source_id,OLD.population_id,OLD.external_id,OLD.received_at,OLD.captured_at,OLD.digest,OLD.raw_digest,OLD.data) OR
     (OLD.state='staged' AND NEW.state NOT IN ('staged','published','rejected','superseded')) THEN
    RAISE EXCEPTION 'organization feed source/status is immutable';
  END IF;
  IF NEW.proposed_version_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM public.org_version v WHERE v.id=NEW.proposed_version_id AND v.workspace_id=NEW.workspace_id AND v.feed_id=NEW.id AND v.kind='proposed' AND v.sealed) THEN
    RAISE EXCEPTION 'organization proposed feed pointer is invalid';
  END IF;
  IF NEW.applied_version_id IS NOT NULL AND NOT EXISTS(
      SELECT 1 FROM public.org_version v WHERE v.id=NEW.applied_version_id AND v.workspace_id=NEW.workspace_id AND v.feed_id=NEW.id AND v.kind='applied' AND v.sealed) THEN
    RAISE EXCEPTION 'organization applied feed pointer is invalid';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER org_feed_guard BEFORE INSERT OR UPDATE OR DELETE ON public.org_feed FOR EACH ROW EXECUTE FUNCTION public.org_guard_feed();

CREATE FUNCTION public.org_guard_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.sealed OR NEW.member_count<1 OR NEW.member_count>10000 THEN RAISE EXCEPTION 'organization version must begin unsealed with bounded members'; END IF;
    IF NEW.base_version_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.org_version WHERE workspace_id=NEW.workspace_id AND id=NEW.base_version_id AND kind='applied' AND sealed) THEN RAISE EXCEPTION 'organization base must be a sealed applied version'; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'organization version is immutable'; END IF;
  IF OLD.sealed OR NOT NEW.sealed OR (to_jsonb(NEW)-'sealed') IS DISTINCT FROM (to_jsonb(OLD)-'sealed') THEN
    RAISE EXCEPTION 'organization version is immutable';
  END IF;
  IF NEW.member_count<1 OR NEW.member_count<>(SELECT count(*) FROM public.org_member m WHERE m.workspace_id=NEW.workspace_id AND m.version_id=NEW.id) THEN
    RAISE EXCEPTION 'organization version member count is invalid';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM public.org_member m WHERE m.workspace_id=NEW.workspace_id AND m.version_id=NEW.id AND m.email=NEW.configuration->'policy'->>'root_email' AND m.ancestry='root') THEN
    RAISE EXCEPTION 'organization root profile missing';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER org_version_guard BEFORE INSERT OR UPDATE OR DELETE ON public.org_version FOR EACH ROW EXECUTE FUNCTION public.org_guard_version();

CREATE FUNCTION public.org_guard_member() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE frozen boolean;
BEGIN
  IF TG_OP IN ('UPDATE','DELETE') THEN RAISE EXCEPTION 'organization member is immutable'; END IF;
  SELECT sealed INTO frozen FROM public.org_version WHERE workspace_id=NEW.workspace_id AND id=NEW.version_id FOR UPDATE;
  IF frozen IS DISTINCT FROM false THEN RAISE EXCEPTION 'organization version is sealed or missing'; END IF;
  IF NEW.data->>'id' IS DISTINCT FROM NEW.person_id::text OR NEW.data->>'email' IS DISTINCT FROM NEW.email OR
     NEW.data->>'full_name' IS DISTINCT FROM NEW.full_name OR NEW.data->>'manager_email' IS DISTINCT FROM NEW.manager_email OR
     NEW.data->>'profile' IS DISTINCT FROM NEW.profile OR NEW.data->>'lob_id' IS DISTINCT FROM NEW.lob_id OR
     NEW.data->>'accountable_leader_email' IS DISTINCT FROM NEW.accountable_leader_email OR
     NEW.data->'designee_emails' IS DISTINCT FROM NEW.designee_emails OR NEW.data->>'ancestry' IS DISTINCT FROM NEW.ancestry OR
     (NEW.data->>'absence_review')::boolean IS DISTINCT FROM NEW.absence_review THEN
    RAISE EXCEPTION 'organization member projection differs from evidence';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER org_member_guard BEFORE INSERT OR UPDATE OR DELETE ON public.org_member FOR EACH ROW EXECUTE FUNCTION public.org_guard_member();

CREATE FUNCTION public.org_guard_head() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'organization workspace identity is immutable'; END IF;
  IF NEW.applied_version_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM public.org_version WHERE workspace_id=NEW.id AND id=NEW.applied_version_id AND kind='applied' AND sealed) THEN
    RAISE EXCEPTION 'organization applied head is not sealed';
  END IF;
  IF NEW.proposed_version_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM public.org_version WHERE workspace_id=NEW.id AND id=NEW.proposed_version_id AND kind='proposed' AND sealed) THEN
    RAISE EXCEPTION 'organization proposed head is not sealed';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER org_workspace_head_guard BEFORE INSERT OR UPDATE ON public.org_workspace FOR EACH ROW EXECUTE FUNCTION public.org_guard_head();

CREATE VIEW public.current_organization AS
SELECT w.id AS workspace_id,m.version_id,m.person_id,m.full_name,m.email,m.manager_email,
       manager.full_name AS manager_name,m.profile,m.evidence,m.lob_id,
       m.accountable_leader_email,leader.full_name AS accountable_leader_name,
       lob.value->>'label' AS lob_name,m.designee_emails,
       COALESCE(designees.names,'[]'::jsonb) AS designee_names,m.ancestry,m.absence_review,
       COALESCE((m.data->>'known_manager')::boolean,false) AS known_manager
FROM public.org_workspace w JOIN public.org_member m ON m.workspace_id=w.id AND m.version_id=w.applied_version_id
JOIN public.org_version v ON v.workspace_id=w.id AND v.id=m.version_id AND v.sealed
LEFT JOIN public.org_member manager ON manager.workspace_id=w.id AND manager.version_id=m.version_id AND manager.person_id=m.manager_person_id
LEFT JOIN public.org_member leader ON leader.workspace_id=w.id AND leader.version_id=m.version_id AND leader.email=m.accountable_leader_email
LEFT JOIN LATERAL (SELECT value FROM jsonb_array_elements(v.configuration->'lobs') WHERE value->>'id'=m.lob_id) lob ON true
LEFT JOIN LATERAL (
 SELECT jsonb_agg(COALESCE(d.full_name,a.value) ORDER BY a.ordinality) AS names
 FROM jsonb_array_elements_text(m.designee_emails) WITH ORDINALITY AS a(value,ordinality)
 LEFT JOIN public.org_member d ON d.workspace_id=w.id AND d.version_id=m.version_id AND d.email=a.value
) designees ON true;

CREATE VIEW public.proposed_organization AS
SELECT w.id AS workspace_id,m.version_id,m.person_id,m.full_name,m.email,m.manager_email,
       manager.full_name AS manager_name,m.profile,m.evidence,m.lob_id,
       m.accountable_leader_email,leader.full_name AS accountable_leader_name,
       lob.value->>'label' AS lob_name,m.designee_emails,
       COALESCE(designees.names,'[]'::jsonb) AS designee_names,m.ancestry,m.absence_review,
       COALESCE((m.data->>'known_manager')::boolean,false) AS known_manager
FROM public.org_workspace w JOIN public.org_member m ON m.workspace_id=w.id AND m.version_id=w.proposed_version_id
JOIN public.org_version v ON v.workspace_id=w.id AND v.id=m.version_id AND v.sealed
LEFT JOIN public.org_member manager ON manager.workspace_id=w.id AND manager.version_id=m.version_id AND manager.person_id=m.manager_person_id
LEFT JOIN public.org_member leader ON leader.workspace_id=w.id AND leader.version_id=m.version_id AND leader.email=m.accountable_leader_email
LEFT JOIN LATERAL (SELECT value FROM jsonb_array_elements(v.configuration->'lobs') WHERE value->>'id'=m.lob_id) lob ON true
LEFT JOIN LATERAL (
 SELECT jsonb_agg(COALESCE(d.full_name,a.value) ORDER BY a.ordinality) AS names
 FROM jsonb_array_elements_text(m.designee_emails) WITH ORDINALITY AS a(value,ordinality)
 LEFT JOIN public.org_member d ON d.workspace_id=w.id AND d.version_id=m.version_id AND d.email=a.value
) designees ON true;
