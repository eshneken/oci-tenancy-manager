ALTER TABLE public.otm_operation DROP CONSTRAINT ck_operation_kind;

ALTER TABLE public.otm_operation ADD CONSTRAINT ck_operation_kind CHECK (kind IN ('inspect_import','organization_action','configuration_update','configuration_check','cost_collection','required_user_check'));

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;

ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry','configuration_check_outcome','cost_collection_outcome','required_user_check_outcome','operation_responsibility_changed','email_delivery') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided','cost_refresh_requested') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK ((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (command_kind='organization_action' AND (step_key='apply_lifecycle' OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap','establish_automation','verify_automation','configure_required','verify_required','retire_temporary','configure_baseline','verify_configured_access','capture_required_users')) OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') OR (command_kind='configuration_check' AND step_key ~ '^configuration_check:[0-9a-f-]{36}$') OR (command_kind='cost_collection' AND step_key ~ '^cost:[0-9a-f-]{36}$') OR (command_kind='required_user_check' AND step_key ~ '^required_users:[0-9a-f-]{36}$'));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_read_only;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_read_only CHECK ((command_kind IN ('inspect_tenancy','configuration_check','cost_collection','required_user_check') AND effect_knowledge='none') OR (command_kind IN ('organization_action','onboarding','configuration_update') AND effect_knowledge IN ('none','known')));

CREATE TABLE public.otm_user_presence_check (
	operation_id UUID NOT NULL,
	workspace_id VARCHAR(256) NOT NULL,
	tenancy_id UUID NOT NULL,
	acquisition_sequence BIGINT GENERATED ALWAYS AS IDENTITY,
	context JSONB NOT NULL,
	context_hash VARCHAR(64) NOT NULL,
	state VARCHAR(16) NOT NULL,
	attempt_id UUID,
	attempt_number INTEGER NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	checked_at TIMESTAMP WITH TIME ZONE,
	results JSONB,
	evidence_event_id UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (operation_id),
	CONSTRAINT fk_presence_check_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id),
	CONSTRAINT fk_presence_check_tenancy FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id),
	CONSTRAINT fk_presence_check_evidence FOREIGN KEY(workspace_id, operation_id, evidence_event_id) REFERENCES public.audit_event (workspace_id, operation_id, id),
	CONSTRAINT ck_presence_check_context CHECK (context_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(context)='object' AND acquisition_sequence>0),
	CONSTRAINT ck_presence_check_attempt CHECK ((state='queued' AND attempt_number=0 AND attempt_id IS NULL AND started_at IS NULL) OR (state IN ('reading','complete','unavailable','superseded') AND attempt_number>=1 AND attempt_id IS NOT NULL AND started_at IS NOT NULL AND started_at>=created_at)),
	CONSTRAINT ck_presence_check_result CHECK ((state IN ('queued','reading') AND checked_at IS NULL AND results IS NULL AND evidence_event_id IS NULL) OR (state IN ('complete','unavailable','superseded') AND checked_at IS NOT NULL AND checked_at>=started_at AND results IS NOT NULL AND jsonb_typeof(results)='array' AND jsonb_array_length(results)=2 AND evidence_event_id IS NOT NULL)),
	UNIQUE (acquisition_sequence)
);

CREATE INDEX ix_presence_check_latest ON public.otm_user_presence_check (workspace_id, tenancy_id, acquisition_sequence DESC);

CREATE INDEX ix_presence_check_pending ON public.otm_user_presence_check (workspace_id, tenancy_id, context_hash) WHERE state IN ('queued', 'reading');

-- Initial contexts are accepted operation data; attempt heads may advance, sealed outcomes may not.
CREATE FUNCTION public.otm_user_presence_check_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item jsonb; subject jsonb; i integer;
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'queued' OR NEW.attempt_number<>0 OR NEW.attempt_id IS NOT NULL
     OR NEW.started_at IS NOT NULL OR NEW.checked_at IS NOT NULL
     OR NEW.results IS NOT NULL OR NEW.evidence_event_id IS NOT NULL
  THEN RAISE EXCEPTION 'PRESENCE_CHECK_INITIAL_REQUIRED'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.otm_operation o
     JOIN public.audit_event e ON e.workspace_id=o.workspace_id AND e.operation_id=o.id
      AND e.id=o.current_intent_event_id AND e.intent_revision=o.current_intent_revision
     JOIN public.otm_tenancy t ON t.workspace_id=o.workspace_id AND t.id=NEW.tenancy_id
     JOIN public.otm_user_presence_connection c ON c.workspace_id=t.workspace_id AND c.tenancy_id=t.id
      AND c.id::text=NEW.context->>'connection_id' AND c.state='active'
     WHERE o.workspace_id=NEW.workspace_id AND o.id=NEW.operation_id
      AND o.kind='required_user_check' AND o.state='queued' AND NEW.created_at=o.accepted_at
      AND e.kind='operation_intent' AND e.data->'intent'->>'kind'='required_user_check'
      AND e.data->'intent'->'snapshot'=NEW.context
      AND e.data->'intent'->>'context_hash'=NEW.context_hash
      AND t.status='active' AND t.operation_id IS NULL AND t.provider_mode='simulated'
      AND t.id::text=NEW.context->>'tenancy_id'
      AND t.revision::text=NEW.context->>'tenancy_revision'
      AND c.provider_mode='simulated' AND c.revision::text=NEW.context->>'connection_revision')
  THEN RAISE EXCEPTION 'PRESENCE_CHECK_SOURCE_UNVERIFIED'; END IF;
  RETURN NEW;
 END IF;
 IF (to_jsonb(NEW)-'state'-'attempt_id'-'attempt_number'-'started_at'-'checked_at'-'results'-'evidence_event_id')
    IS DISTINCT FROM
    (to_jsonb(OLD)-'state'-'attempt_id'-'attempt_number'-'started_at'-'checked_at'-'results'-'evidence_event_id')
    OR OLD.state NOT IN ('queued','reading')
 THEN RAISE EXCEPTION 'PRESENCE_CHECK_IMMUTABLE'; END IF;
 IF NEW.state='reading' THEN
  IF NEW.attempt_number<>OLD.attempt_number+1 OR NEW.attempt_id IS NOT DISTINCT FROM OLD.attempt_id
  THEN RAISE EXCEPTION 'PRESENCE_CHECK_ATTEMPT_INVALID'; END IF;
  RETURN NEW;
 END IF;
 IF OLD.state<>'reading' OR NEW.state NOT IN ('complete','unavailable','superseded')
    OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id
    OR NEW.attempt_number<>OLD.attempt_number OR NEW.started_at IS DISTINCT FROM OLD.started_at
 THEN RAISE EXCEPTION 'PRESENCE_CHECK_ATTEMPT_INVALID'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.audit_event e JOIN public.otm_operation o
    ON o.workspace_id=e.workspace_id AND o.id=e.operation_id
    WHERE e.workspace_id=NEW.workspace_id AND e.operation_id=NEW.operation_id
      AND e.id=NEW.evidence_event_id AND e.kind='required_user_check_outcome'
      AND o.kind='required_user_check' AND o.state='running'
      AND e.contract_version='user-presence-check-1' AND e.at=NEW.checked_at
      AND e.data->>'operation_id'=NEW.operation_id::text
      AND e.data->>'tenancy_id'=NEW.tenancy_id::text
      AND e.data->>'context_hash'=NEW.context_hash AND e.data->>'state'=NEW.state
      AND (e.data->>'started_at')::timestamptz=NEW.started_at AND e.data->'results'=NEW.results)
 THEN RAISE EXCEPTION 'PRESENCE_CHECK_EVIDENCE_INVALID'; END IF;
 FOR i IN 0..1 LOOP
  item := NEW.results->i; subject := NEW.context->'subjects'->i;
  IF item->'target' IS DISTINCT FROM subject
    OR item->'context'->>'workspace_id' IS DISTINCT FROM NEW.workspace_id
    OR item->'context'->>'operation_id' IS DISTINCT FROM NEW.operation_id::text
    OR item->'context'->>'attempt_id' IS DISTINCT FROM NEW.attempt_id::text
    OR item->'context'->>'execution_generation' IS DISTINCT FROM NEW.attempt_number::text
    OR item->'context'->>'connection_id' IS DISTINCT FROM NEW.context->>'connection_id'
    OR item->'context'->>'connection_revision' IS DISTINCT FROM NEW.context->>'connection_revision'
    OR NEW.state='superseded' AND item->>'state' IS DISTINCT FROM 'unknown'
  THEN RAISE EXCEPTION 'PRESENCE_CHECK_RESULT_SCOPE_INVALID'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER presence_check_guard BEFORE INSERT OR UPDATE ON public.otm_user_presence_check
 FOR EACH ROW EXECUTE FUNCTION public.otm_user_presence_check_guard();
CREATE TRIGGER presence_check_no_delete BEFORE DELETE ON public.otm_user_presence_check
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_user_presence_check_no_truncate BEFORE TRUNCATE ON public.otm_user_presence_check
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
