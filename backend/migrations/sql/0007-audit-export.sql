-- Add the closed audit-export preparation event; existing rows and append-only guards remain.
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL));

CREATE INDEX ix_audit_workspace_at_id ON public.audit_event (workspace_id, at, id);
