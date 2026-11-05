-- Deliberately retain NULL for pre-existing default selections and tenancy assignments.
ALTER TABLE public.org_workspace ADD COLUMN current_baseline_id UUID;
ALTER TABLE public.org_workspace ADD CONSTRAINT fk_workspace_baseline FOREIGN KEY(id,current_baseline_id) REFERENCES public.otm_baseline_version(workspace_id,id);
ALTER TABLE public.otm_tenancy ADD COLUMN baseline_version_id UUID;
ALTER TABLE public.otm_tenancy ADD CONSTRAINT fk_tenancy_baseline FOREIGN KEY(workspace_id,baseline_version_id) REFERENCES public.otm_baseline_version(workspace_id,id);
CREATE FUNCTION public.otm_guard_default_baseline() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
 IF NEW.current_baseline_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.otm_baseline_version WHERE workspace_id=NEW.id AND id=NEW.current_baseline_id AND published_at IS NOT NULL AND publication_mode='simulated') THEN
  RAISE EXCEPTION 'published scoped baseline required' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER otm_default_baseline_guard BEFORE INSERT OR UPDATE OF current_baseline_id ON public.org_workspace FOR EACH ROW EXECUTE FUNCTION public.otm_guard_default_baseline();
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));
