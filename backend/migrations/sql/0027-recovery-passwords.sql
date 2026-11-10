ALTER TABLE public.otm_operation DROP CONSTRAINT ck_operation_kind;

ALTER TABLE public.otm_operation ADD CONSTRAINT ck_operation_kind CHECK (kind IN ('inspect_import','organization_action','configuration_update','configuration_check','cost_collection','required_user_check','recovery_network_repair','recovery_password'));

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;

ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry','configuration_check_outcome','cost_collection_outcome','required_user_check_outcome','recovery_network_outcome','recovery_password_outcome','recovery_password_disclosed','operation_responsibility_changed','email_delivery') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided','cost_refresh_requested') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK ((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (command_kind='organization_action' AND (step_key='apply_lifecycle' OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap','establish_automation','verify_automation','configure_required','verify_required','retire_temporary','configure_baseline','verify_configured_access','capture_required_users','prepare_recovery_password')) OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') OR (command_kind='configuration_check' AND step_key ~ '^configuration_check:[0-9a-f-]{36}$') OR (command_kind='cost_collection' AND step_key ~ '^cost:[0-9a-f-]{36}$') OR (command_kind='required_user_check' AND step_key ~ '^required_users:[0-9a-f-]{36}$') OR (command_kind='recovery_network_repair' AND step_key ~ '^recovery_network:[0-9a-f-]{36}$') OR (command_kind='recovery_password' AND step_key ~ '^recovery_password:[0-9a-f-]{36}$'));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_read_only;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_read_only CHECK ((command_kind IN ('inspect_tenancy','configuration_check','cost_collection','required_user_check') AND effect_knowledge='none') OR (command_kind IN ('organization_action','onboarding','configuration_update') AND effect_knowledge IN ('none','known')) OR (command_kind IN ('recovery_network_repair','recovery_password') AND effect_knowledge IN ('none','known','unknown')));


CREATE TABLE public.otm_credential (
	id UUID NOT NULL,
	workspace_id VARCHAR(256) NOT NULL,
	tenancy_id UUID NOT NULL,
	principal_binding_id UUID NOT NULL,
	source_operation_id UUID NOT NULL,
	location JSONB NOT NULL,
	location_hash VARCHAR(64) NOT NULL,
	state VARCHAR(16) NOT NULL,
	generation INTEGER NOT NULL,
	current_version_id UUID,
	staged_version_id UUID,
	exposure_generation INTEGER NOT NULL,
	first_disclosure_at TIMESTAMP WITH TIME ZONE,
	rotation_due_at TIMESTAMP WITH TIME ZONE,
	active_window_grant_id UUID,
	rotation_operation_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, id),
	UNIQUE (workspace_id, tenancy_id, id),
	UNIQUE (workspace_id, principal_binding_id),
	FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id),
	FOREIGN KEY(workspace_id, tenancy_id, principal_binding_id) REFERENCES public.otm_managed_object_binding (workspace_id, tenancy_id, id),
	FOREIGN KEY(workspace_id, source_operation_id) REFERENCES public.otm_operation (workspace_id, id),
	FOREIGN KEY(workspace_id, rotation_operation_id) REFERENCES public.otm_operation (workspace_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_credential_state CHECK (state IN ('staging','usable','rotating','unknown','retired') AND generation>=1 AND exposure_generation>=0 AND location_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(location)='object'),
	CONSTRAINT ck_credential_exposure CHECK ((first_disclosure_at IS NULL AND rotation_due_at IS NULL AND active_window_grant_id IS NULL) OR (first_disclosure_at IS NOT NULL AND rotation_due_at IS NOT NULL AND rotation_due_at=first_disclosure_at+interval '4 hours' AND active_window_grant_id IS NOT NULL AND exposure_generation>=1))
)

;

CREATE INDEX ix_credential_due ON public.otm_credential (workspace_id, rotation_due_at) WHERE rotation_due_at IS NOT NULL;


CREATE TABLE public.otm_credential_version (
	id UUID NOT NULL,
	workspace_id VARCHAR(256) NOT NULL,
	credential_id UUID NOT NULL,
	version_number INTEGER NOT NULL,
	reference JSONB NOT NULL,
	reference_hash VARCHAR(64) NOT NULL,
	created_operation_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, credential_id, id),
	UNIQUE (workspace_id, credential_id, version_number),
	FOREIGN KEY(workspace_id, credential_id) REFERENCES public.otm_credential (workspace_id, id),
	FOREIGN KEY(workspace_id, created_operation_id) REFERENCES public.otm_operation (workspace_id, id),
	CONSTRAINT ck_credential_version CHECK (version_number>=1 AND reference_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(reference)='object')
)

;


CREATE TABLE public.otm_human_access_grant (
	id UUID NOT NULL,
	workspace_id VARCHAR(256) NOT NULL,
	tenancy_id UUID NOT NULL,
	credential_id UUID NOT NULL,
	disclosed_version_id UUID NOT NULL,
	requesting_subject VARCHAR(256) NOT NULL,
	requester_snapshot JSONB NOT NULL,
	request_key UUID NOT NULL,
	payload_digest VARCHAR(64) NOT NULL,
	accepted_operation_id UUID NOT NULL,
	window_root_grant_id UUID NOT NULL,
	exposure_generation INTEGER NOT NULL,
	accepted_at TIMESTAMP WITH TIME ZONE NOT NULL,
	first_disclosure_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
	due_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, credential_id, id),
	UNIQUE (workspace_id, requesting_subject, request_key),
	FOREIGN KEY(workspace_id, tenancy_id, credential_id) REFERENCES public.otm_credential (workspace_id, tenancy_id, id),
	FOREIGN KEY(workspace_id, credential_id, disclosed_version_id) REFERENCES public.otm_credential_version (workspace_id, credential_id, id),
	FOREIGN KEY(workspace_id, credential_id, window_root_grant_id) REFERENCES public.otm_human_access_grant (workspace_id, credential_id, id) DEFERRABLE INITIALLY DEFERRED,
	FOREIGN KEY(workspace_id, accepted_operation_id) REFERENCES public.otm_operation (workspace_id, id),
	CONSTRAINT ck_recovery_grant_window CHECK (exposure_generation>=1 AND due_at=first_disclosure_attempt_at+interval '4 hours' AND accepted_at>=first_disclosure_attempt_at AND accepted_at<due_at AND payload_digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(requester_snapshot)='object')
)

;

CREATE INDEX ix_recovery_grant_history ON public.otm_human_access_grant (workspace_id, credential_id, accepted_at DESC);

ALTER TABLE public.otm_credential ADD CONSTRAINT fk_credential_current FOREIGN KEY(workspace_id, id, current_version_id) REFERENCES public.otm_credential_version (workspace_id, credential_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.otm_credential ADD CONSTRAINT fk_credential_staged FOREIGN KEY(workspace_id, id, staged_version_id) REFERENCES public.otm_credential_version (workspace_id, credential_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.otm_credential ADD CONSTRAINT fk_credential_window FOREIGN KEY(workspace_id, id, active_window_grant_id) REFERENCES public.otm_human_access_grant (workspace_id, credential_id, id) DEFERRABLE INITIALLY DEFERRED;

-- Immutable reference history and original exposure windows survive ordinary runtime cleanup.
CREATE FUNCTION public.otm_credential_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'staging' OR NEW.generation<>1 OR NEW.exposure_generation<>0
     OR NEW.current_version_id IS NOT NULL OR NEW.staged_version_id IS NOT NULL
     OR NEW.first_disclosure_at IS NOT NULL
  THEN RAISE EXCEPTION 'RECOVERY_CREDENTIAL_INITIAL_REQUIRED'; END IF;
  IF NOT EXISTS(
   SELECT 1 FROM public.otm_managed_object_binding b JOIN public.otm_tenancy t
    ON t.workspace_id=b.workspace_id AND t.id=b.tenancy_id
   WHERE b.workspace_id=NEW.workspace_id AND b.tenancy_id=NEW.tenancy_id
    AND b.id=NEW.principal_binding_id AND b.logical_key='identity/user/recovery'
    AND b.state='active' AND b.created_operation_id=NEW.source_operation_id
    AND t.status='pending' AND t.operation_id=NEW.source_operation_id
    AND NEW.location->>'credential_id'=NEW.id::text
    AND NEW.location->'target'->>'workspace_id'=NEW.workspace_id
    AND NEW.location->'target'->>'tenancy_id'=NEW.tenancy_id::text
    AND NEW.location->'target'->>'subject_binding_id'=b.id::text
    AND NEW.location->'target'->>'purpose'='recovery'
    AND NEW.location->'target'->>'scim_resource_id'=b.scim_resource_id
    AND NEW.location->'target'->>'provider_ocid'=b.provider_ocid
    AND NEW.location->'target'->>'tenancy_ocid'=t.tenancy_ocid
  ) THEN RAISE EXCEPTION 'RECOVERY_CREDENTIAL_SCOPE_INVALID'; END IF;
  RETURN NEW;
 END IF;
 IF (to_jsonb(NEW)-'location'-'location_hash'-'state'-'generation'-'current_version_id'-'staged_version_id'
      -'exposure_generation'-'first_disclosure_at'-'rotation_due_at'-'active_window_grant_id'
      -'rotation_operation_id'-'updated_at')
    IS DISTINCT FROM
    (to_jsonb(OLD)-'location'-'location_hash'-'state'-'generation'-'current_version_id'-'staged_version_id'
      -'exposure_generation'-'first_disclosure_at'-'rotation_due_at'-'active_window_grant_id'
      -'rotation_operation_id'-'updated_at')
 THEN RAISE EXCEPTION 'RECOVERY_CREDENTIAL_BINDING_IMMUTABLE'; END IF;
 IF NEW.location IS DISTINCT FROM OLD.location OR NEW.location_hash<>OLD.location_hash THEN
  IF OLD.state<>'rotating' OR OLD.current_version_id IS NOT NULL
    OR OLD.location->>'secret_reference' IS NOT NULL
    OR NEW.location->>'secret_reference' IS NULL
    OR (OLD.location-'secret_reference') IS DISTINCT FROM (NEW.location-'secret_reference')
    OR NOT EXISTS(SELECT 1 FROM public.otm_credential_version v
      WHERE v.workspace_id=OLD.workspace_id AND v.credential_id=OLD.id
       AND v.created_operation_id=OLD.rotation_operation_id AND v.id=NEW.staged_version_id
       AND v.reference->'location'=NEW.location)
  THEN RAISE EXCEPTION 'RECOVERY_ALLOCATION_BINDING_INVALID'; END IF;
 END IF;
 IF OLD.state='unknown' AND NEW.state NOT IN ('unknown','usable','retired')
 THEN RAISE EXCEPTION 'RECOVERY_RECONCILIATION_REQUIRED'; END IF;
 IF NEW.rotation_operation_id<>OLD.rotation_operation_id
    AND NOT (OLD.first_disclosure_at IS NULL AND NEW.first_disclosure_at IS NOT NULL)
 THEN RAISE EXCEPTION 'RECOVERY_OPERATION_IMMUTABLE'; END IF;
 IF NEW.exposure_generation<>OLD.exposure_generation
    AND NOT (OLD.first_disclosure_at IS NULL AND NEW.first_disclosure_at IS NOT NULL)
 THEN RAISE EXCEPTION 'RECOVERY_EXPOSURE_GENERATION_IMMUTABLE'; END IF;
 IF OLD.first_disclosure_at IS NOT NULL AND NEW.first_disclosure_at IS NOT NULL
   AND (NEW.first_disclosure_at<>OLD.first_disclosure_at OR NEW.rotation_due_at<>OLD.rotation_due_at
        OR NEW.active_window_grant_id<>OLD.active_window_grant_id
        OR NEW.exposure_generation<>OLD.exposure_generation
        OR NEW.rotation_operation_id<>OLD.rotation_operation_id)
 THEN RAISE EXCEPTION 'RECOVERY_DEADLINE_IMMUTABLE'; END IF;
 IF OLD.first_disclosure_at IS NULL AND NEW.first_disclosure_at IS NOT NULL THEN
  IF OLD.state<>'usable' OR NEW.state<>'usable' OR NEW.generation<>OLD.generation
    OR NEW.current_version_id IS DISTINCT FROM OLD.current_version_id
    OR NEW.exposure_generation<>OLD.exposure_generation+1
    OR NOT EXISTS(
     SELECT 1 FROM public.otm_operation o JOIN public.audit_event e
      ON e.workspace_id=o.workspace_id AND e.operation_id=o.id AND e.id=o.current_intent_event_id
     WHERE o.workspace_id=NEW.workspace_id AND o.id=NEW.rotation_operation_id
      AND o.kind='recovery_password' AND o.state IN ('queued','waiting')
      AND e.kind='operation_intent' AND e.data->'intent'->>'phase'='rotation'
      AND e.data->'intent'->>'credential_id'=NEW.id::text
      AND (e.data->'intent'->>'due_at')::timestamptz=NEW.rotation_due_at
      AND (e.data->'intent'->>'exposure_generation')::integer=NEW.exposure_generation
    )
  THEN RAISE EXCEPTION 'RECOVERY_EXPOSURE_OPERATION_REQUIRED'; END IF;
 END IF;
 IF NEW.current_version_id IS DISTINCT FROM OLD.current_version_id
    OR NEW.state='usable' AND OLD.state<>'usable'
    OR NEW.generation<>OLD.generation
    OR OLD.first_disclosure_at IS NOT NULL AND NEW.first_disclosure_at IS NULL
 THEN
  IF NEW.state<>'usable' OR NEW.current_version_id IS NULL
    OR NEW.current_version_id IS DISTINCT FROM OLD.staged_version_id
    OR NEW.generation<>OLD.generation+(CASE WHEN OLD.first_disclosure_at IS NULL THEN 0 ELSE 1 END)
    OR NOT EXISTS(
     SELECT 1 FROM public.audit_event e JOIN public.otm_credential_version v
       ON v.workspace_id=e.workspace_id AND v.created_operation_id=e.operation_id
     WHERE e.workspace_id=NEW.workspace_id AND e.operation_id=OLD.rotation_operation_id
      AND e.kind='recovery_password_outcome' AND e.data->>'state'='verified'
      AND e.data->>'credential_id'=NEW.id::text AND e.data->>'effect'='known'
      AND v.credential_id=NEW.id AND v.id=NEW.current_version_id
      AND v.reference=e.data->'version'
    )
  THEN RAISE EXCEPTION 'RECOVERY_VERIFIED_ROTATION_REQUIRED'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER credential_guard BEFORE INSERT OR UPDATE ON public.otm_credential
 FOR EACH ROW EXECUTE FUNCTION public.otm_credential_guard();

CREATE FUNCTION public.otm_recovery_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.otm_credential c
  WHERE c.workspace_id=NEW.workspace_id AND c.id=NEW.credential_id
   AND (c.location=NEW.reference->'location' OR (
        c.current_version_id IS NULL AND c.staged_version_id IS NULL
        AND c.location->>'secret_reference' IS NULL
        AND NEW.reference->'location'->>'secret_reference' IS NOT NULL
        AND (c.location-'secret_reference')=((NEW.reference->'location')-'secret_reference')
   ))
   AND NEW.reference->>'operation_id'=NEW.created_operation_id::text
   AND c.rotation_operation_id=NEW.created_operation_id
   AND c.state='rotating')
 THEN RAISE EXCEPTION 'RECOVERY_VERSION_SCOPE_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recovery_version_scope BEFORE INSERT ON public.otm_credential_version
 FOR EACH ROW EXECUTE FUNCTION public.otm_recovery_version_guard();

CREATE FUNCTION public.otm_recovery_grant_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.otm_credential c
  WHERE c.workspace_id=NEW.workspace_id AND c.tenancy_id=NEW.tenancy_id
   AND c.id=NEW.credential_id AND c.state='usable'
   AND c.current_version_id=NEW.disclosed_version_id
   AND c.exposure_generation=NEW.exposure_generation
   AND c.active_window_grant_id=NEW.window_root_grant_id
   AND c.first_disclosure_at=NEW.first_disclosure_attempt_at AND c.rotation_due_at=NEW.due_at
   AND c.rotation_operation_id=NEW.accepted_operation_id)
 THEN RAISE EXCEPTION 'RECOVERY_DISCLOSURE_SCOPE_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER recovery_grant_scope BEFORE INSERT ON public.otm_human_access_grant
 FOR EACH ROW EXECUTE FUNCTION public.otm_recovery_grant_guard();

CREATE FUNCTION public.otm_recovery_window_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.otm_human_access_grant g
  WHERE g.workspace_id=NEW.workspace_id AND g.credential_id=NEW.credential_id
   AND g.id=NEW.window_root_grant_id AND g.window_root_grant_id=g.id
   AND g.disclosed_version_id=NEW.disclosed_version_id
   AND g.exposure_generation=NEW.exposure_generation
   AND g.first_disclosure_attempt_at=NEW.first_disclosure_attempt_at AND g.due_at=NEW.due_at
   AND g.accepted_operation_id=NEW.accepted_operation_id)
 THEN RAISE EXCEPTION 'RECOVERY_DISCLOSURE_ROOT_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER recovery_window_scope AFTER INSERT ON public.otm_human_access_grant
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.otm_recovery_window_guard();

CREATE TRIGGER recovery_credential_no_delete BEFORE DELETE ON public.otm_credential
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_credential_no_truncate BEFORE TRUNCATE ON public.otm_credential
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER recovery_version_no_change BEFORE UPDATE OR DELETE ON public.otm_credential_version
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_credential_version_no_truncate BEFORE TRUNCATE ON public.otm_credential_version
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER recovery_grant_no_change BEFORE UPDATE OR DELETE ON public.otm_human_access_grant
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_human_access_grant_no_truncate BEFORE TRUNCATE ON public.otm_human_access_grant
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();


ALTER TABLE public.otm_credential ADD CONSTRAINT ck_credential_usable
 CHECK (state<>'usable' OR current_version_id IS NOT NULL);


CREATE UNIQUE INDEX uq_credential_secret_reference ON public.otm_credential ((location->>'secret_reference')) WHERE location->>'secret_reference' IS NOT NULL;
CREATE UNIQUE INDEX uq_active_recovery_credential ON public.otm_credential(workspace_id,tenancy_id) WHERE state<>'retired';

ALTER TABLE public.otm_credential ADD CONSTRAINT ck_credential_distinct_candidate CHECK (current_version_id IS NULL OR staged_version_id IS NULL OR current_version_id<>staged_version_id);

-- Preserve the exact captured-identity guards while admitting the version4 setup graph.
CREATE OR REPLACE FUNCTION public.otm_presence_connection_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE signer public.otm_managed_object_binding%ROWTYPE;
        domain public.otm_managed_object_binding%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (to_jsonb(NEW)-'state'-'retired_operation_id'-'updated_at') IS DISTINCT FROM
     (to_jsonb(OLD)-'state'-'retired_operation_id'-'updated_at')
    OR OLD.state<>'active' OR NEW.state<>'retired' OR NEW.updated_at<OLD.updated_at
  THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_IMMUTABLE'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.otm_managed_object_binding b
    JOIN public.otm_tenancy t ON t.workspace_id=b.workspace_id AND t.id=b.tenancy_id
    WHERE b.workspace_id=NEW.workspace_id AND b.tenancy_id=NEW.tenancy_id
      AND b.id=NEW.automation_binding_id AND b.state='retired'
      AND b.retired_operation_id=NEW.retired_operation_id
      AND t.status IN ('active','terminating') AND t.operation_id=NEW.retired_operation_id)
  THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_RETIREMENT_UNVERIFIED'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.state<>'active' OR NEW.retired_operation_id IS NOT NULL
    OR NEW.updated_at<>NEW.created_at
 THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_INITIAL_REQUIRED'; END IF;
 SELECT * INTO signer FROM public.otm_managed_object_binding
 WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id AND id=NEW.automation_binding_id;
 SELECT * INTO domain FROM public.otm_managed_object_binding
 WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id AND id=NEW.domain_binding_id;
 IF signer.logical_key IS DISTINCT FROM 'identity/user/automation'
    OR domain.logical_key IS DISTINCT FROM 'identity/domain'
    OR signer.state IS DISTINCT FROM 'active' OR domain.state IS DISTINCT FROM 'active'
    OR signer.identity_domain_binding_id IS DISTINCT FROM domain.id
    OR signer.created_operation_id IS DISTINCT FROM NEW.created_operation_id
    OR domain.created_operation_id IS DISTINCT FROM NEW.created_operation_id
    OR signer.source_evidence_event_id IS DISTINCT FROM NEW.source_evidence_event_id
    OR domain.source_evidence_event_id IS DISTINCT FROM NEW.source_evidence_event_id
    OR signer.created_at IS DISTINCT FROM NEW.created_at
    OR domain.created_at IS DISTINCT FROM NEW.created_at
 THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_SOURCE_UNVERIFIED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.otm_tenancy t
   JOIN public.otm_operation o ON o.workspace_id=t.workspace_id AND o.id=t.operation_id
   JOIN public.audit_event e ON e.workspace_id=o.workspace_id AND e.id=o.current_intent_event_id
    AND e.operation_id=o.id AND e.intent_revision=o.current_intent_revision
   JOIN public.audit_event c ON c.workspace_id=o.workspace_id AND c.operation_id=o.id
    AND c.id=NEW.source_evidence_event_id AND c.kind='onboarding_outcome'
   JOIN public.otm_operation_step s ON s.workspace_id=o.workspace_id AND s.operation_id=o.id
    AND s.intent_revision=o.current_intent_revision AND s.step_key='capture_required_users'
    AND s.evidence_event_id=c.id AND s.state='verified'
   WHERE t.workspace_id=NEW.workspace_id AND t.id=NEW.tenancy_id
    AND t.status='pending' AND t.provider_mode='simulated'
    AND t.tenancy_ocid LIKE 'ocid1.tenancy.oc1..otmsim%'
    AND o.id=NEW.created_operation_id AND o.kind='organization_action' AND o.state='queued'
    AND e.kind='operation_intent'
    AND e.data->'intent'->>'presence_connection_contract'='simulated-user-presence-1'
    AND e.data->'intent'->>'onboarding_version' IN ('3','4')
    AND e.data->'intent'->>'action' IN ('create_tenancy','import_tenancy')
    AND e.data->'intent'->>'pending_tenancy_id'=t.id::text AND c.at=NEW.created_at
    AND EXISTS(SELECT 1 FROM public.otm_managed_object_binding r
       WHERE r.workspace_id=t.workspace_id AND r.tenancy_id=t.id
        AND r.logical_key='identity/user/recovery' AND r.state='active'
        AND r.source_evidence_event_id=c.id AND r.created_operation_id=o.id))
 THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_SOURCE_UNVERIFIED'; END IF;
 RETURN NEW;
END $$;
