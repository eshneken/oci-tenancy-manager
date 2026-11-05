-- Frozen initial application schema. Later model changes require a new migration.

CREATE TABLE public.otm_operation (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	kind VARCHAR(64) NOT NULL, 
	initiating_actor_subject VARCHAR(256) NOT NULL, 
	initiating_actor_snapshot JSONB NOT NULL, 
	responsible_actor_subject VARCHAR(256) NOT NULL, 
	client_request_key UUID NOT NULL, 
	request_digest VARCHAR(64) NOT NULL, 
	current_intent_revision INTEGER NOT NULL, 
	current_intent_event_id UUID NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	stage VARCHAR(256) NOT NULL, 
	wait_reason VARCHAR(32), 
	effect_knowledge VARCHAR(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	accepted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_operation_workspace_id UNIQUE (workspace_id, id), 
	CONSTRAINT uq_operation_request UNIQUE (workspace_id, initiating_actor_subject, client_request_key), 
	CONSTRAINT ck_operation_kind CHECK (kind='inspect_import'), 
	CONSTRAINT ck_operation_state CHECK (state IN ('queued','running','waiting','needs_attention','succeeded','cancelled','failed')), 
	CONSTRAINT ck_operation_effect CHECK (effect_knowledge IN ('none','known','unknown')), 
	CONSTRAINT ck_operation_revisions CHECK (current_intent_revision>=1 AND revision>=1), 
	CONSTRAINT ck_operation_digest CHECK (request_digest ~ '^[0-9a-f]{64}$')
);

CREATE TABLE public.audit_event (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	operation_id UUID NOT NULL, 
	intent_revision INTEGER NOT NULL, 
	actor VARCHAR(256) NOT NULL, 
	actor_subject VARCHAR(256) NOT NULL, 
	actor_snapshot JSONB NOT NULL, 
	kind VARCHAR(64) NOT NULL, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	contract_version VARCHAR(64) NOT NULL, 
	data JSONB NOT NULL, 
	data_hash VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_audit_intent_revision UNIQUE (workspace_id, operation_id, intent_revision), 
	CONSTRAINT uq_audit_exact_intent UNIQUE (workspace_id, operation_id, intent_revision, id), 
	CONSTRAINT ck_audit_intent_only CHECK (kind='operation_intent'), 
	CONSTRAINT ck_audit_revision CHECK (intent_revision>=1), 
	CONSTRAINT ck_audit_digest CHECK (data_hash ~ '^[0-9a-f]{64}$'), 
	CONSTRAINT fk_audit_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id) DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE public.otm_operation ADD CONSTRAINT fk_operation_exact_intent FOREIGN KEY(workspace_id, id, current_intent_revision, current_intent_event_id) REFERENCES public.audit_event (workspace_id, operation_id, intent_revision, id) DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION public.otm_reject_audit_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
RAISE EXCEPTION 'Administrative history is append-only' USING ERRCODE='42501';
END $$;
CREATE TRIGGER otm_audit_append_only BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.audit_event FOR EACH STATEMENT
EXECUTE FUNCTION public.otm_reject_audit_mutation();
