-- Immutable read-only configuration observations; preserve existing assignments and history.

ALTER TABLE public.otm_operation DROP CONSTRAINT ck_operation_kind;

ALTER TABLE public.otm_operation ADD CONSTRAINT ck_operation_kind CHECK (kind IN ('inspect_import','organization_action','configuration_update','configuration_check'));

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;

ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry','configuration_check_outcome') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK ((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (command_kind='organization_action' AND (step_key='apply_lifecycle' OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap','establish_automation','verify_automation','configure_required','verify_required','retire_temporary','configure_baseline','verify_configured_access')) OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') OR (command_kind='configuration_check' AND step_key ~ '^configuration_check:[0-9a-f-]{36}$'));

ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_read_only;

ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_read_only CHECK ((command_kind IN ('inspect_tenancy','configuration_check') AND effect_knowledge='none') OR (command_kind IN ('organization_action','onboarding','configuration_update') AND effect_knowledge IN ('none','known')));

CREATE TABLE public.otm_configuration_check (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	tenancy_id UUID NOT NULL, 
	operation_id UUID NOT NULL, 
	acquisition_sequence BIGINT GENERATED ALWAYS AS IDENTITY, 
	contract_version VARCHAR(32) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	checked_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	context JSONB NOT NULL, 
	context_hash VARCHAR(64) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	results JSONB NOT NULL, 
	evidence_event_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_configuration_check_target UNIQUE (workspace_id, operation_id, tenancy_id), 
	CONSTRAINT fk_check_child FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	CONSTRAINT fk_check_evidence FOREIGN KEY(workspace_id, operation_id, evidence_event_id) REFERENCES public.audit_event (workspace_id, operation_id, id), 
	CONSTRAINT ck_check_version CHECK (acquisition_sequence>0 AND checked_at>=started_at AND contract_version='configuration-check-1'), 
	CONSTRAINT ck_check_state CHECK (state IN ('matching','drifted','unavailable','superseded')), 
	CONSTRAINT ck_check_context CHECK (context_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(context)='object'), 
	CONSTRAINT ck_check_results CHECK (jsonb_typeof(results)='array' AND jsonb_array_length(results)=4), 
	UNIQUE (acquisition_sequence)
);

CREATE INDEX ix_configuration_check_current ON public.otm_configuration_check (workspace_id, tenancy_id, acquisition_sequence DESC);

CREATE TRIGGER configuration_check_immutable BEFORE UPDATE OR DELETE ON public.otm_configuration_check FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();

CREATE TRIGGER otm_configuration_check_no_truncate BEFORE TRUNCATE ON public.otm_configuration_check FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
