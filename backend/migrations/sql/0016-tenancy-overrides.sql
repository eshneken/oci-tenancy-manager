-- Accepted authored revisions and staged review plans; no existing row or intent is rewritten.
CREATE FUNCTION public.otm_valid_override_statements(value JSONB) RETURNS boolean LANGUAGE SQL IMMUTABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT CASE WHEN value IS NULL THEN true WHEN jsonb_typeof(value)='array' THEN jsonb_array_length(value) BETWEEN 1 AND 50 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(value) entry WHERE jsonb_typeof(entry)<>'string' OR length(entry #>> '{}') NOT BETWEEN 1 AND 2000 OR (entry #>> '{}') !~ '[^[:space:]]') ELSE false END
$$;


CREATE TABLE public.otm_tenancy_configuration (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	tenancy_id UUID NOT NULL, 
	revision_number INTEGER NOT NULL, 
	previous_id UUID, 
	baseline_version_id UUID NOT NULL, 
	policy_override_statements JSONB, 
	quota_override_statements JSONB, 
	monthly_budget_override_amount NUMERIC(20, 4), 
	resolution_contract_version VARCHAR(32) NOT NULL, 
	effective_hash VARCHAR(64) NOT NULL, 
	operation_id UUID NOT NULL, 
	created_by VARCHAR(256) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_configuration_scope UNIQUE (workspace_id, tenancy_id, id), 
	CONSTRAINT uq_configuration_revision UNIQUE (workspace_id, tenancy_id, revision_number), 
	CONSTRAINT fk_configuration_tenancy FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	CONSTRAINT fk_configuration_previous FOREIGN KEY(workspace_id, tenancy_id, previous_id) REFERENCES public.otm_tenancy_configuration (workspace_id, tenancy_id, id), 
	CONSTRAINT fk_configuration_baseline FOREIGN KEY(workspace_id, baseline_version_id) REFERENCES public.otm_baseline_version (workspace_id, id), 
	CONSTRAINT fk_configuration_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT ck_configuration_version CHECK (revision_number>=1 AND resolution_contract_version='simulated-config-1' AND effective_hash ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_configuration_budget CHECK (monthly_budget_override_amount IS NULL OR (monthly_budget_override_amount>0 AND monthly_budget_override_amount<10000000000000000 AND trunc(monthly_budget_override_amount)=monthly_budget_override_amount)), 
	CONSTRAINT ck_configuration_statements CHECK (public.otm_valid_override_statements(policy_override_statements) AND public.otm_valid_override_statements(quota_override_statements))
)

;


CREATE TABLE public.otm_configuration_plan (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	scope_tenancy_id UUID, 
	target_baseline_version_id UUID, 
	candidate_set_hash VARCHAR(64) NOT NULL, 
	client_request_key UUID NOT NULL, 
	revision INTEGER NOT NULL, 
	created_by VARCHAR(256) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	operation_id UUID, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_configuration_plan_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_configuration_plan_request UNIQUE (workspace_id, created_by, client_request_key), 
	CONSTRAINT fk_plan_workspace FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id), 
	CONSTRAINT fk_plan_scope_tenancy FOREIGN KEY(workspace_id, scope_tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	CONSTRAINT fk_plan_baseline FOREIGN KEY(workspace_id, target_baseline_version_id) REFERENCES public.otm_baseline_version (workspace_id, id), 
	CONSTRAINT fk_plan_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT ck_plan_revision CHECK (revision>=1 AND candidate_set_hash ~ '^[0-9a-f]{64}$')
)

;


CREATE TABLE public.otm_configuration_plan_target (
	workspace_id VARCHAR(256) NOT NULL, 
	plan_id UUID NOT NULL, 
	tenancy_id UUID NOT NULL, 
	proposal JSONB NOT NULL, 
	proposal_hash VARCHAR(64) NOT NULL, 
	policy_choice VARCHAR(32), 
	quota_choice VARCHAR(32), 
	reviewed_by VARCHAR(256), 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	accepted_configuration_id UUID, 
	PRIMARY KEY (workspace_id, plan_id, tenancy_id), 
	CONSTRAINT fk_plan_target_plan FOREIGN KEY(workspace_id, plan_id) REFERENCES public.otm_configuration_plan (workspace_id, id), 
	CONSTRAINT fk_plan_target_tenancy FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	CONSTRAINT fk_plan_target_configuration FOREIGN KEY(workspace_id, tenancy_id, accepted_configuration_id) REFERENCES public.otm_tenancy_configuration (workspace_id, tenancy_id, id), 
	CONSTRAINT ck_plan_target_proposal CHECK (jsonb_typeof(proposal)='object' AND proposal_hash ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_plan_target_review CHECK ((policy_choice IS NULL OR policy_choice IN ('use_new_baseline','keep_override')) AND (quota_choice IS NULL OR quota_choice IN ('use_new_baseline','keep_override')) AND (reviewed_by IS NULL)=(reviewed_at IS NULL))
)

;

ALTER TABLE public.otm_tenancy ADD COLUMN desired_configuration_id UUID;

ALTER TABLE public.otm_tenancy ADD CONSTRAINT fk_tenancy_desired_configuration_id FOREIGN KEY(workspace_id, id, desired_configuration_id) REFERENCES public.otm_tenancy_configuration (workspace_id, tenancy_id, id);

ALTER TABLE public.otm_tenancy ADD COLUMN last_verified_configuration_id UUID;

ALTER TABLE public.otm_tenancy ADD CONSTRAINT fk_tenancy_last_verified_configuration_id FOREIGN KEY(workspace_id, id, last_verified_configuration_id) REFERENCES public.otm_tenancy_configuration (workspace_id, tenancy_id, id);

ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));


CREATE FUNCTION public.otm_guard_configuration_insert() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.otm_baseline_version WHERE workspace_id=NEW.workspace_id AND id=NEW.baseline_version_id AND published_at IS NOT NULL) THEN RAISE EXCEPTION 'published configuration baseline required'; END IF;
 IF (NEW.previous_id IS NULL AND NEW.revision_number<>1) OR (NEW.previous_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.otm_tenancy_configuration WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id AND id=NEW.previous_id AND revision_number=NEW.revision_number-1)) THEN RAISE EXCEPTION 'invalid configuration predecessor'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER configuration_insert_guard BEFORE INSERT ON public.otm_tenancy_configuration FOR EACH ROW EXECUTE FUNCTION public.otm_guard_configuration_insert();
CREATE TRIGGER configuration_immutable BEFORE UPDATE OR DELETE ON public.otm_tenancy_configuration FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();

CREATE TRIGGER otm_tenancy_configuration_no_truncate BEFORE TRUNCATE ON public.otm_tenancy_configuration FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();

CREATE TRIGGER otm_configuration_plan_no_truncate BEFORE TRUNCATE ON public.otm_configuration_plan FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();

CREATE TRIGGER otm_configuration_plan_target_no_truncate BEFORE TRUNCATE ON public.otm_configuration_plan_target FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();


CREATE FUNCTION public.otm_guard_accepted_plan() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_TABLE_NAME='otm_configuration_plan' THEN
  IF TG_OP='INSERT' THEN
   IF NEW.operation_id IS NOT NULL THEN RAISE EXCEPTION 'new plan must be a draft'; END IF;
  ELSIF OLD.operation_id IS NOT NULL THEN RAISE EXCEPTION 'accepted plan is immutable'; END IF;
 ELSE
  IF TG_OP='INSERT' THEN
   IF EXISTS(SELECT 1 FROM public.otm_configuration_plan WHERE workspace_id=NEW.workspace_id AND id=NEW.plan_id AND operation_id IS NOT NULL) THEN RAISE EXCEPTION 'accepted plan target is immutable'; END IF;
  ELSIF EXISTS(SELECT 1 FROM public.otm_configuration_plan WHERE workspace_id=OLD.workspace_id AND id=OLD.plan_id AND operation_id IS NOT NULL) THEN RAISE EXCEPTION 'accepted plan target is immutable'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER accepted_plan_guard BEFORE INSERT OR UPDATE OR DELETE ON public.otm_configuration_plan FOR EACH ROW EXECUTE FUNCTION public.otm_guard_accepted_plan();
CREATE TRIGGER accepted_target_guard BEFORE INSERT OR UPDATE OR DELETE ON public.otm_configuration_plan_target FOR EACH ROW EXECUTE FUNCTION public.otm_guard_accepted_plan();
