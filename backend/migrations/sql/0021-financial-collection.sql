-- Current-cycle financial acquisition and immutable same-response snapshots.

ALTER TABLE public.otm_operation DROP CONSTRAINT ck_operation_kind;

ALTER TABLE public.otm_operation ADD CONSTRAINT ck_operation_kind CHECK (kind IN ('inspect_import','organization_action','configuration_update','configuration_check','cost_collection'));

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;

ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry','configuration_check_outcome','cost_collection_outcome','operation_responsibility_changed','email_delivery') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided','cost_refresh_requested') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_read_only;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_read_only CHECK ((command_kind IN ('inspect_tenancy','configuration_check','cost_collection') AND effect_knowledge='none') OR (command_kind IN ('organization_action','onboarding','configuration_update') AND effect_knowledge IN ('none','known')));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK ((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (command_kind='organization_action' AND (step_key='apply_lifecycle' OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap','establish_automation','verify_automation','configure_required','verify_required','retire_temporary','configure_baseline','verify_configured_access')) OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') OR (command_kind='configuration_check' AND step_key ~ '^configuration_check:[0-9a-f-]{36}$') OR (command_kind='cost_collection' AND step_key ~ '^cost:[0-9a-f-]{36}$'));


CREATE TABLE public.otm_financial_collection (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	tenancy_id UUID NOT NULL, 
	operation_id UUID NOT NULL, 
	context JSONB NOT NULL, 
	context_hash VARCHAR(64) NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	failure_scope_hash VARCHAR(64) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	attempt_id UUID, 
	next_attempt_at TIMESTAMP WITH TIME ZONE, 
	safe_code VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_financial_collection_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_financial_collection_exact UNIQUE (workspace_id, id, tenancy_id, context_hash, source_hash), 
	CONSTRAINT uq_financial_child UNIQUE (workspace_id, operation_id, tenancy_id), 
	CONSTRAINT fk_financial_collection_child FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	CONSTRAINT fk_financial_collection_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT ck_financial_collection_state CHECK (state IN ('queued','reading','retry','succeeded','failed','superseded')), 
	CONSTRAINT ck_financial_collection_attempt CHECK (attempts>=0 AND attempts<=3 AND updated_at>=created_at AND ((attempts=0 AND attempt_id IS NULL) OR (attempts>0 AND attempt_id IS NOT NULL))), 
	CONSTRAINT ck_financial_collection_context CHECK (context_hash ~ '^[0-9a-f]{64}$' AND source_hash ~ '^[0-9a-f]{64}$' AND failure_scope_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(context)='object')
)

;

CREATE INDEX ix_financial_collection_child ON public.otm_financial_collection (workspace_id, tenancy_id, created_at DESC);

CREATE INDEX ix_financial_collection_failure_scope ON public.otm_financial_collection (workspace_id, failure_scope_hash, updated_at DESC);

CREATE UNIQUE INDEX uq_financial_active_context ON public.otm_financial_collection (workspace_id, tenancy_id, context_hash) WHERE state IN ('queued', 'reading', 'retry');


CREATE TABLE public.otm_financial_observation (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	tenancy_id UUID NOT NULL, 
	collection_id UUID NOT NULL, 
	context_hash VARCHAR(64) NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	budget_ocid VARCHAR(256) NOT NULL, 
	observed_budget_amount NUMERIC(20, 4), 
	actual_spend NUMERIC(20, 4), 
	forecasted_spend NUMERIC(20, 4), 
	currency VARCHAR(3), 
	time_spend_computed TIMESTAMP WITH TIME ZONE, 
	captured_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	period_start TIMESTAMP WITH TIME ZONE, 
	period_end TIMESTAMP WITH TIME ZONE, 
	snapshot JSONB NOT NULL, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_financial_observation_collection UNIQUE (workspace_id, collection_id), 
	CONSTRAINT fk_financial_observation_collection FOREIGN KEY(workspace_id, collection_id, tenancy_id, context_hash, source_hash) REFERENCES public.otm_financial_collection (workspace_id, id, tenancy_id, context_hash, source_hash), 
	CONSTRAINT fk_financial_observation_child FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	CONSTRAINT ck_financial_observation_hash CHECK (context_hash ~ '^[0-9a-f]{64}$' AND snapshot_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(snapshot)='object'), 
	CONSTRAINT ck_financial_budget_nonnegative CHECK (observed_budget_amount IS NULL OR observed_budget_amount>=0), 
	CONSTRAINT ck_financial_observation_period CHECK ((period_start IS NULL AND period_end IS NULL) OR (period_start IS NOT NULL AND period_end IS NOT NULL AND period_end>period_start))
)

;

CREATE INDEX ix_financial_observation_current ON public.otm_financial_observation (workspace_id, tenancy_id, source_hash, time_spend_computed DESC, captured_at DESC);

CREATE FUNCTION public.otm_financial_collection_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.state<>'queued' OR NEW.attempts<>0 THEN RAISE EXCEPTION 'FINANCIAL_INITIAL_REQUIRED'; END IF;
   RETURN NEW;
 END IF;
 IF (NEW.id,NEW.workspace_id,NEW.tenancy_id,NEW.operation_id,NEW.context,NEW.context_hash,NEW.source_hash,NEW.failure_scope_hash,NEW.created_at)
    IS DISTINCT FROM (OLD.id,OLD.workspace_id,OLD.tenancy_id,OLD.operation_id,OLD.context,OLD.context_hash,OLD.source_hash,OLD.failure_scope_hash,OLD.created_at)
 THEN RAISE EXCEPTION 'FINANCIAL_CONTEXT_IMMUTABLE'; END IF;
 IF OLD.state IN ('succeeded','failed','superseded') THEN RAISE EXCEPTION 'FINANCIAL_TERMINAL_IMMUTABLE'; END IF;
 IF NOT ((OLD.state IN ('queued','retry','reading') AND NEW.state='reading') OR
     (OLD.state='reading' AND NEW.state IN ('retry','succeeded','failed','superseded')))
 THEN RAISE EXCEPTION 'FINANCIAL_TRANSITION_INVALID'; END IF;
 IF NEW.updated_at<OLD.updated_at OR
    (NEW.state='reading' AND (NEW.attempts<>OLD.attempts+1 OR NEW.attempt_id IS NOT DISTINCT FROM OLD.attempt_id)) OR
    (NEW.state<>'reading' AND (NEW.attempts<>OLD.attempts OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id))
 THEN RAISE EXCEPTION 'FINANCIAL_ATTEMPT_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER financial_collection_guard BEFORE INSERT OR UPDATE ON public.otm_financial_collection
 FOR EACH ROW EXECUTE FUNCTION public.otm_financial_collection_guard();
CREATE TRIGGER financial_collection_no_delete BEFORE DELETE ON public.otm_financial_collection
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_financial_collection_no_truncate BEFORE TRUNCATE ON public.otm_financial_collection
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER financial_observation_immutable BEFORE UPDATE OR DELETE ON public.otm_financial_observation
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_financial_observation_no_truncate BEFORE TRUNCATE ON public.otm_financial_observation
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();




