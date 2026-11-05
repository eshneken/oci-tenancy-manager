-- Expand immutable audit evidence without weakening exact-intent foreign keys.
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_intent_only;
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_revision;
ALTER TABLE public.audit_event ALTER COLUMN intent_revision DROP NOT NULL;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK (
 (kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1)
 OR (kind IN ('inspection_dispatch','inspection_outcome') AND intent_revision IS NULL)
);
ALTER TABLE public.audit_event ADD CONSTRAINT uq_audit_operation_event
 UNIQUE(workspace_id,operation_id,id);

CREATE TABLE public.otm_operation_step (
	workspace_id VARCHAR(256) NOT NULL, 
	operation_id UUID NOT NULL, 
	intent_revision INTEGER NOT NULL, 
	step_key VARCHAR(256) NOT NULL, 
	intent_event_id UUID NOT NULL, 
	command_kind VARCHAR(64) NOT NULL, 
	contract_version VARCHAR(64) NOT NULL, 
	inputs JSONB NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	execution_generation INTEGER NOT NULL, 
	attempt_number INTEGER NOT NULL, 
	current_attempt_id UUID NOT NULL, 
	effect_knowledge VARCHAR(16) NOT NULL, 
	last_outcome JSONB, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	evidence_event_id UUID, 
	PRIMARY KEY (workspace_id, operation_id, intent_revision, step_key), 
	CONSTRAINT ck_inspection_step_kind CHECK (step_key='inspect_target' AND command_kind='inspect_tenancy'), 
	CONSTRAINT ck_inspection_step_state CHECK (state IN ('running','verified','needs_attention')), 
	CONSTRAINT ck_inspection_step_generations CHECK (intent_revision>=1 AND execution_generation>=1 AND attempt_number>=1), 
	CONSTRAINT ck_inspection_read_only CHECK (effect_knowledge='none'), 
	CONSTRAINT fk_step_exact_intent FOREIGN KEY(workspace_id, operation_id, intent_revision, intent_event_id) REFERENCES public.audit_event (workspace_id, operation_id, intent_revision, id) DEFERRABLE INITIALLY DEFERRED, 
	CONSTRAINT fk_step_operation FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT fk_step_evidence FOREIGN KEY(workspace_id, operation_id, evidence_event_id) REFERENCES public.audit_event (workspace_id, operation_id, id)
)

;
