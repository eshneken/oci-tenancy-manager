CREATE TABLE public.otm_user_presence_connection (
	id UUID NOT NULL,
	workspace_id VARCHAR(256) NOT NULL,
	tenancy_id UUID NOT NULL,
	automation_binding_id UUID NOT NULL,
	domain_binding_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	provider_mode VARCHAR(16) NOT NULL,
	contract_version VARCHAR(64) NOT NULL,
	state VARCHAR(16) NOT NULL,
	created_operation_id UUID NOT NULL,
	source_evidence_event_id UUID NOT NULL,
	retired_operation_id UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_presence_connection_scope UNIQUE (workspace_id, tenancy_id, id),
	CONSTRAINT fk_presence_connection_child FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id),
	CONSTRAINT fk_presence_connection_signer FOREIGN KEY(workspace_id, tenancy_id, automation_binding_id) REFERENCES public.otm_managed_object_binding (workspace_id, tenancy_id, id),
	CONSTRAINT fk_presence_connection_domain FOREIGN KEY(workspace_id, tenancy_id, domain_binding_id) REFERENCES public.otm_managed_object_binding (workspace_id, tenancy_id, id),
	CONSTRAINT fk_presence_connection_source FOREIGN KEY(workspace_id, created_operation_id, source_evidence_event_id) REFERENCES public.audit_event (workspace_id, operation_id, id),
	CONSTRAINT fk_presence_connection_retirement FOREIGN KEY(workspace_id, retired_operation_id) REFERENCES public.otm_operation (workspace_id, id),
	CONSTRAINT ck_presence_connection_version CHECK (revision=1 AND provider_mode='simulated' AND contract_version='simulated-user-presence-1'),
	CONSTRAINT ck_presence_connection_state CHECK ((state='active' AND retired_operation_id IS NULL) OR (state='retired' AND retired_operation_id IS NOT NULL)),
	CONSTRAINT ck_presence_connection_time CHECK (updated_at>=created_at)
);

CREATE UNIQUE INDEX uq_presence_connection_active ON public.otm_user_presence_connection (workspace_id, tenancy_id) WHERE state = 'active';

-- Connection rows select only the explicit simulator; they never certify OCI signing authority.
CREATE FUNCTION public.otm_presence_connection_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE signer public.otm_managed_object_binding%ROWTYPE;
        domain public.otm_managed_object_binding%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (to_jsonb(NEW)-'state'-'retired_operation_id'-'updated_at') IS DISTINCT FROM
     (to_jsonb(OLD)-'state'-'retired_operation_id'-'updated_at')
    OR OLD.state<>'active' OR NEW.state<>'retired' OR NEW.updated_at<OLD.updated_at
  THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_IMMUTABLE'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.otm_managed_object_binding b
    JOIN public.otm_tenancy t ON t.workspace_id=b.workspace_id AND t.id=b.tenancy_id
    WHERE b.workspace_id=NEW.workspace_id AND b.tenancy_id=NEW.tenancy_id
      AND b.id=NEW.automation_binding_id AND b.state='retired'
      AND b.retired_operation_id=NEW.retired_operation_id
      AND t.status IN ('active','terminating') AND t.operation_id=NEW.retired_operation_id)
  THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_RETIREMENT_UNVERIFIED'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.state<>'active' OR NEW.retired_operation_id IS NOT NULL
    OR NEW.updated_at<>NEW.created_at
 THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_INITIAL_REQUIRED'; END IF;
 SELECT * INTO signer FROM public.otm_managed_object_binding
 WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id AND id=NEW.automation_binding_id;
 SELECT * INTO domain FROM public.otm_managed_object_binding
 WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id AND id=NEW.domain_binding_id;
 IF signer.logical_key IS DISTINCT FROM 'identity/user/automation'
    OR domain.logical_key IS DISTINCT FROM 'identity/domain'
    OR signer.state IS DISTINCT FROM 'active' OR domain.state IS DISTINCT FROM 'active'
    OR signer.identity_domain_binding_id IS DISTINCT FROM domain.id
    OR signer.created_operation_id IS DISTINCT FROM NEW.created_operation_id
    OR domain.created_operation_id IS DISTINCT FROM NEW.created_operation_id
    OR signer.source_evidence_event_id IS DISTINCT FROM NEW.source_evidence_event_id
    OR domain.source_evidence_event_id IS DISTINCT FROM NEW.source_evidence_event_id
    OR signer.created_at IS DISTINCT FROM NEW.created_at
    OR domain.created_at IS DISTINCT FROM NEW.created_at
 THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_SOURCE_UNVERIFIED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.otm_tenancy t
   JOIN public.otm_operation o ON o.workspace_id=t.workspace_id AND o.id=t.operation_id
   JOIN public.audit_event e ON e.workspace_id=o.workspace_id AND e.id=o.current_intent_event_id
    AND e.operation_id=o.id AND e.intent_revision=o.current_intent_revision
   JOIN public.audit_event c ON c.workspace_id=o.workspace_id AND c.operation_id=o.id
    AND c.id=NEW.source_evidence_event_id AND c.kind='onboarding_outcome'
   JOIN public.otm_operation_step s ON s.workspace_id=o.workspace_id AND s.operation_id=o.id
    AND s.intent_revision=o.current_intent_revision AND s.step_key='capture_required_users'
    AND s.evidence_event_id=c.id AND s.state='verified'
   WHERE t.workspace_id=NEW.workspace_id AND t.id=NEW.tenancy_id
    AND t.status='pending' AND t.provider_mode='simulated'
    AND t.tenancy_ocid LIKE 'ocid1.tenancy.oc1..otmsim%'
    AND o.id=NEW.created_operation_id AND o.kind='organization_action' AND o.state='queued'
    AND e.kind='operation_intent'
    AND e.data->'intent'->>'presence_connection_contract'='simulated-user-presence-1'
    AND e.data->'intent'->>'onboarding_version'='3'
    AND e.data->'intent'->>'action' IN ('create_tenancy','import_tenancy')
    AND e.data->'intent'->>'pending_tenancy_id'=t.id::text AND c.at=NEW.created_at
    AND EXISTS(SELECT 1 FROM public.otm_managed_object_binding r
       WHERE r.workspace_id=t.workspace_id AND r.tenancy_id=t.id
        AND r.logical_key='identity/user/recovery' AND r.state='active'
        AND r.source_evidence_event_id=c.id AND r.created_operation_id=o.id))
 THEN RAISE EXCEPTION 'PRESENCE_CONNECTION_SOURCE_UNVERIFIED'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER presence_connection_guard BEFORE INSERT OR UPDATE ON public.otm_user_presence_connection
 FOR EACH ROW EXECUTE FUNCTION public.otm_presence_connection_guard();
CREATE TRIGGER presence_connection_no_delete BEFORE DELETE ON public.otm_user_presence_connection
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_user_presence_connection_no_truncate BEFORE TRUNCATE ON public.otm_user_presence_connection
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
