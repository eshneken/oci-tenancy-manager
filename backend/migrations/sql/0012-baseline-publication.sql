-- Local publication remains distinct from future OCI qualification and default selection.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.otm_baseline_version WHERE published_at IS NOT NULL) THEN
  RAISE EXCEPTION 'pre-existing manual baseline publications require reviewed migration';
 END IF;
END $$;
ALTER TABLE public.otm_baseline_version ADD COLUMN published_by_name VARCHAR(256);
ALTER TABLE public.otm_baseline_version ADD COLUMN publication_mode VARCHAR(16);
ALTER TABLE public.otm_baseline_version ADD CONSTRAINT ck_baseline_qualification CHECK (
 (published_at IS NULL AND publication_mode IS NULL AND published_by_name IS NULL) OR
 (published_at IS NOT NULL AND publication_mode IS NOT NULL AND publication_mode='simulated' AND published_by_name IS NOT NULL)
);
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('baseline_draft_saved','baseline_published') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));
