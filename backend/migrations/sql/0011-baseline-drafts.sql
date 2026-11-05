-- Authoring drafts only; no publication authority or tenancy/provider changes.
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind='baseline_draft_saved' AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));

CREATE TABLE public.otm_baseline_version (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	version_number INTEGER NOT NULL, 
	based_on_id UUID, 
	schema_version VARCHAR(32) NOT NULL, 
	policy_statements JSONB NOT NULL, 
	quota_statements JSONB NOT NULL, 
	monthly_budget_amount NUMERIC(20, 4) NOT NULL, 
	budget_currency VARCHAR(3) NOT NULL, 
	budget_period VARCHAR(16) NOT NULL, 
	tag_namespace VARCHAR(16) NOT NULL, 
	tag_defaults JSONB NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	edit_revision INTEGER NOT NULL, 
	created_by VARCHAR(256) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	published_by VARCHAR(256), 
	published_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_baseline_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_baseline_version UNIQUE (workspace_id, version_number), 
	CONSTRAINT fk_baseline_workspace FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id), 
	CONSTRAINT fk_baseline_parent FOREIGN KEY(workspace_id, based_on_id) REFERENCES public.otm_baseline_version (workspace_id, id), 
	CONSTRAINT ck_baseline_revision CHECK (version_number>=1 AND edit_revision>=1), 
	CONSTRAINT ck_baseline_scope_values CHECK (schema_version='baseline-1' AND budget_period='MONTHLY' AND tag_namespace='OTM'), 
	CONSTRAINT ck_baseline_budget CHECK (monthly_budget_amount>0 AND budget_currency ~ '^[A-Z]{3}$'), 
	CONSTRAINT ck_baseline_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_baseline_publication CHECK ((published_by IS NULL)=(published_at IS NULL)), 
	CONSTRAINT ck_baseline_lists CHECK (jsonb_typeof(policy_statements)='array' AND jsonb_array_length(policy_statements)>0 AND jsonb_typeof(quota_statements)='array' AND jsonb_array_length(quota_statements)>0 AND jsonb_typeof(tag_defaults)='array')
)

;
CREATE UNIQUE INDEX uq_baseline_editable ON public.otm_baseline_version (workspace_id) WHERE published_at IS NULL;

CREATE FUNCTION public.otm_guard_baseline() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP <> 'INSERT' AND OLD.published_at IS NOT NULL THEN RAISE EXCEPTION 'published baseline is immutable'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF TG_OP='UPDATE' AND ((NEW.id,NEW.workspace_id,NEW.version_number,NEW.based_on_id,NEW.schema_version,NEW.created_by,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.workspace_id,OLD.version_number,OLD.based_on_id,OLD.schema_version,OLD.created_by,OLD.created_at) OR NEW.edit_revision<>OLD.edit_revision+1) THEN RAISE EXCEPTION 'invalid baseline revision'; END IF;
 IF NEW.based_on_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.otm_baseline_version WHERE workspace_id=NEW.workspace_id AND id=NEW.based_on_id AND published_at IS NOT NULL) THEN RAISE EXCEPTION 'published baseline parent required'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER baseline_guard BEFORE INSERT OR UPDATE OR DELETE ON public.otm_baseline_version FOR EACH ROW EXECUTE FUNCTION public.otm_guard_baseline();
CREATE TRIGGER otm_baseline_version_no_truncate BEFORE TRUNCATE ON public.otm_baseline_version FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
