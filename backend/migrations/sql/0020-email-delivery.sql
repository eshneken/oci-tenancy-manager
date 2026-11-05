-- Durable lifecycle email freezes routing while changing only bounded delivery knowledge.
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK ((operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome','onboarding_action','onboarding_outcome','configuration_outcome','configuration_retry','configuration_check_outcome','operation_responsibility_changed','email_delivery') AND intent_revision IS NULL))) OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL) OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL) OR (kind IN ('configuration_review_staged','baseline_draft_saved','baseline_published','baseline_default_changed') AND operation_id IS NULL AND administrator_id IS NULL AND intent_revision IS NULL));


CREATE TABLE public.otm_notification_outbox (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	operation_id UUID NOT NULL, 
	transition_key VARCHAR(64) NOT NULL, 
	intent JSONB NOT NULL, 
	intent_hash VARCHAR(64) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	attempt_id UUID, 
	last_attempt_at TIMESTAMP WITH TIME ZONE, 
	next_attempt_at TIMESTAMP WITH TIME ZONE, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	safe_code VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_notification_workspace_id UNIQUE (workspace_id, id), 
	CONSTRAINT uq_notification_transition UNIQUE (workspace_id, operation_id, transition_key), 
	CONSTRAINT fk_notification_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT ck_notification_state CHECK (state IN ('pending','blocked','sending','sent','failed','unknown','superseded')), 
	CONSTRAINT ck_notification_attempts CHECK (attempts>=0 AND attempts<=3), 
	CONSTRAINT ck_notification_hashes CHECK (intent_hash ~ '^[0-9a-f]{64}$' AND transition_key ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT ck_notification_times CHECK (updated_at>=created_at AND (last_attempt_at IS NULL OR last_attempt_at>=created_at) AND ((attempts=0 AND attempt_id IS NULL AND last_attempt_at IS NULL) OR (attempts>0 AND attempt_id IS NOT NULL AND last_attempt_at IS NOT NULL))), 
	CONSTRAINT ck_notification_sent CHECK ((state='sent' AND sent_at IS NOT NULL) OR (state<>'sent' AND sent_at IS NULL))
)

;

CREATE INDEX ix_notification_operation ON public.otm_notification_outbox (workspace_id, operation_id, created_at DESC);

CREATE INDEX ix_notification_pending ON public.otm_notification_outbox (workspace_id, state, next_attempt_at);

CREATE FUNCTION public.otm_notification_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.state NOT IN ('pending','blocked') OR NEW.attempts<>0 THEN
     RAISE EXCEPTION 'NOTIFICATION_INITIAL_HEAD_REQUIRED';
   END IF;
   RETURN NEW;
 END IF;
 IF (NEW.id,NEW.workspace_id,NEW.operation_id,NEW.transition_key,NEW.intent,NEW.intent_hash,NEW.created_at)
    IS DISTINCT FROM
    (OLD.id,OLD.workspace_id,OLD.operation_id,OLD.transition_key,OLD.intent,OLD.intent_hash,OLD.created_at) THEN
   RAISE EXCEPTION 'NOTIFICATION_INTENT_IMMUTABLE';
 END IF;
 IF OLD.state IN ('sent','failed','unknown','superseded') THEN
   RAISE EXCEPTION 'NOTIFICATION_TERMINAL_HEAD_IMMUTABLE';
 END IF;
 IF NOT ((OLD.state='pending' AND NEW.state IN ('sending','blocked','failed','superseded'))
     OR (OLD.state='blocked' AND NEW.state='superseded')
     OR (OLD.state='sending' AND NEW.state IN ('sent','pending','blocked','failed','unknown','superseded'))) THEN
   RAISE EXCEPTION 'NOTIFICATION_TRANSITION_INVALID';
 END IF;
 IF (NEW.state='sending' AND (NEW.attempts<>OLD.attempts+1 OR NEW.attempt_id IS NOT DISTINCT FROM OLD.attempt_id))
     OR (NEW.state<>'sending' AND (NEW.attempts<>OLD.attempts OR NEW.attempt_id IS DISTINCT FROM OLD.attempt_id))
     OR NEW.updated_at<OLD.updated_at THEN
   RAISE EXCEPTION 'NOTIFICATION_ATTEMPT_INVALID';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER notification_guard BEFORE INSERT OR UPDATE ON public.otm_notification_outbox
 FOR EACH ROW EXECUTE FUNCTION public.otm_notification_guard();
CREATE TRIGGER notification_no_delete BEFORE DELETE ON public.otm_notification_outbox
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_notification_outbox_no_truncate BEFORE TRUNCATE ON public.otm_notification_outbox
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
