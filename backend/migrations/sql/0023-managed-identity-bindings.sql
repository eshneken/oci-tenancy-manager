CREATE TABLE public.otm_managed_object_binding (
	id UUID NOT NULL,
	workspace_id VARCHAR(256) NOT NULL,
	tenancy_id UUID NOT NULL,
	logical_key VARCHAR(64) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	handler_contract_version VARCHAR(64) NOT NULL,
	generation INTEGER NOT NULL,
	identity_domain_binding_id UUID,
	provider_ocid VARCHAR(256) NOT NULL,
	scim_resource_id VARCHAR(256),
	user_name VARCHAR(256),
	ownership_mode VARCHAR(32) NOT NULL,
	state VARCHAR(16) NOT NULL,
	created_operation_id UUID NOT NULL,
	source_evidence_event_id UUID NOT NULL,
	retired_operation_id UUID,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_managed_binding_scope UNIQUE (workspace_id, tenancy_id, id),
	CONSTRAINT uq_managed_binding_generation UNIQUE (workspace_id, tenancy_id, logical_key, generation),
	CONSTRAINT fk_managed_binding_tenancy FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id),
	CONSTRAINT fk_managed_binding_domain FOREIGN KEY(workspace_id, tenancy_id, identity_domain_binding_id) REFERENCES public.otm_managed_object_binding (workspace_id, tenancy_id, id),
	CONSTRAINT fk_managed_binding_capture FOREIGN KEY(workspace_id, created_operation_id, source_evidence_event_id) REFERENCES public.audit_event (workspace_id, operation_id, id),
	CONSTRAINT fk_managed_binding_retirement FOREIGN KEY(workspace_id, retired_operation_id) REFERENCES public.otm_operation (workspace_id, id),
	CONSTRAINT ck_managed_binding_version CHECK (generation>=1 AND handler_contract_version='required-user-binding-1'),
	CONSTRAINT ck_managed_binding_state CHECK ((state='active' AND retired_operation_id IS NULL) OR (state='retired' AND retired_operation_id IS NOT NULL)),
	CONSTRAINT ck_managed_binding_time CHECK (updated_at>=created_at),
	CONSTRAINT ck_managed_binding_shape CHECK ((kind='identity_domain' AND logical_key='identity/domain' AND ownership_mode='observed_reference' AND identity_domain_binding_id IS NULL AND scim_resource_id IS NULL AND user_name IS NULL AND provider_ocid ~ '^ocid1[.]domain[.][A-Za-z0-9.]+$') OR (kind='managed_user' AND logical_key IN ('identity/user/automation','identity/user/recovery') AND ownership_mode='managed' AND identity_domain_binding_id IS NOT NULL AND scim_resource_id IS NOT NULL AND length(btrim(scim_resource_id))>0 AND user_name IS NOT NULL AND length(btrim(user_name))>0 AND provider_ocid ~ '^ocid1[.]user[.][A-Za-z0-9.]+$'))
);

CREATE UNIQUE INDEX uq_managed_binding_live_key ON public.otm_managed_object_binding (workspace_id, tenancy_id, logical_key) WHERE state = 'active';
CREATE UNIQUE INDEX uq_managed_binding_live_ocid ON public.otm_managed_object_binding (workspace_id, tenancy_id, provider_ocid) WHERE state = 'active';
CREATE UNIQUE INDEX uq_managed_binding_live_scim ON public.otm_managed_object_binding (workspace_id, tenancy_id, identity_domain_binding_id, scim_resource_id) WHERE state = 'active' AND scim_resource_id IS NOT NULL;


-- Only immutable identity/provenance inserts and logical retirement are supported in this slice.
CREATE FUNCTION public.otm_managed_binding_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE facts jsonb; subject jsonb; domain public.otm_managed_object_binding%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (to_jsonb(NEW)-'state'-'retired_operation_id'-'updated_at') IS DISTINCT FROM
     (to_jsonb(OLD)-'state'-'retired_operation_id'-'updated_at')
    OR OLD.state<>'active' OR NEW.state<>'retired'
    OR NEW.retired_operation_id IS NULL OR NEW.updated_at<OLD.updated_at
  THEN RAISE EXCEPTION 'MANAGED_BINDING_IMMUTABLE'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.otm_tenancy t
    JOIN public.otm_operation o ON o.workspace_id=t.workspace_id AND o.id=t.operation_id
    JOIN public.audit_event e ON e.workspace_id=o.workspace_id AND e.id=o.current_intent_event_id
     AND e.operation_id=o.id AND e.kind='operation_intent'
    WHERE t.workspace_id=NEW.workspace_id AND t.id=NEW.tenancy_id
     AND o.id=NEW.retired_operation_id AND o.kind='organization_action' AND o.state='queued'
     AND EXISTS(SELECT 1 FROM jsonb_array_elements(e.data->'intent'->'associations') a
       WHERE a->>'tenancy_id'=NEW.tenancy_id::text AND a->>'action'='delete'))
  THEN RAISE EXCEPTION 'MANAGED_BINDING_RETIREMENT_UNVERIFIED'; END IF;
  RETURN NEW;
 END IF;
 IF NEW.state<>'active' OR NEW.generation<>1 OR NEW.retired_operation_id IS NOT NULL
    OR NEW.updated_at<>NEW.created_at
 THEN RAISE EXCEPTION 'MANAGED_BINDING_INITIAL_REQUIRED'; END IF;
 SELECT e.data->'required_users' INTO facts FROM public.audit_event e
 JOIN public.otm_operation_step s ON s.workspace_id=e.workspace_id AND s.operation_id=e.operation_id
  AND s.evidence_event_id=e.id AND s.step_key='capture_required_users' AND s.state='verified'
 JOIN public.otm_operation o ON o.workspace_id=s.workspace_id AND o.id=s.operation_id
  AND o.current_intent_revision=s.intent_revision
 JOIN public.otm_tenancy t ON t.workspace_id=NEW.workspace_id AND t.id=NEW.tenancy_id
 WHERE e.workspace_id=NEW.workspace_id AND e.id=NEW.source_evidence_event_id
  AND e.operation_id=NEW.created_operation_id AND e.kind='onboarding_outcome'
  AND (SELECT count(*) FROM public.otm_operation_step p
    WHERE p.workspace_id=s.workspace_id AND p.operation_id=s.operation_id
     AND p.intent_revision=s.intent_revision AND p.state='verified'
     AND p.step_key IN ('establish_automation','verify_automation','configure_required',
       'verify_required','configure_baseline','verify_configured_access'))=6
  AND e.at=NEW.created_at
  AND e.data->>'step'='capture_required_users' AND e.data->>'outcome'='verified'
  AND t.status='pending' AND t.operation_id=NEW.created_operation_id
  AND e.data->'required_users'->>'workspace_id'=NEW.workspace_id
  AND e.data->'required_users'->>'tenancy_ocid'=t.tenancy_ocid
  AND e.data->'required_users'->>'parent_tenancy_ocid'=t.parent_tenancy_ocid
  AND e.data->'required_users'->>'organization_id'=t.organization_id;
 IF facts IS NULL THEN RAISE EXCEPTION 'MANAGED_BINDING_SOURCE_UNVERIFIED'; END IF;
 IF NEW.kind='identity_domain' THEN
  IF NEW.provider_ocid IS DISTINCT FROM facts->>'domain_ocid'
  THEN RAISE EXCEPTION 'MANAGED_BINDING_SOURCE_UNVERIFIED'; END IF;
 ELSE
  SELECT * INTO domain FROM public.otm_managed_object_binding
   WHERE workspace_id=NEW.workspace_id AND tenancy_id=NEW.tenancy_id
    AND id=NEW.identity_domain_binding_id;
  subject := facts->split_part(NEW.logical_key,'/',3);
  IF domain.kind IS DISTINCT FROM 'identity_domain' OR domain.state IS DISTINCT FROM 'active'
    OR domain.source_evidence_event_id IS DISTINCT FROM NEW.source_evidence_event_id
    OR domain.provider_ocid IS DISTINCT FROM subject->>'domain_ocid'
    OR NEW.provider_ocid IS DISTINCT FROM subject->>'provider_ocid'
    OR NEW.scim_resource_id IS DISTINCT FROM subject->>'scim_resource_id'
    OR NEW.user_name IS DISTINCT FROM subject->>'user_name'
  THEN RAISE EXCEPTION 'MANAGED_BINDING_SOURCE_UNVERIFIED'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER managed_binding_guard BEFORE INSERT OR UPDATE ON public.otm_managed_object_binding
 FOR EACH ROW EXECUTE FUNCTION public.otm_managed_binding_guard();
CREATE TRIGGER managed_binding_no_delete BEFORE DELETE ON public.otm_managed_object_binding
 FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_managed_object_binding_no_truncate BEFORE TRUNCATE ON public.otm_managed_object_binding
 FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
