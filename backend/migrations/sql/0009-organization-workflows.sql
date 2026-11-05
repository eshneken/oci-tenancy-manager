-- Durable organization review episodes and registered tenancy associations.
ALTER TABLE public.org_workspace ADD COLUMN registry_revision integer NOT NULL DEFAULT 1;
ALTER TABLE public.org_workspace ADD CONSTRAINT ck_org_registry_revision CHECK(registry_revision>=1);
ALTER TABLE public.org_person ADD COLUMN directory_status varchar(16) NOT NULL DEFAULT 'included';
ALTER TABLE public.org_person ADD COLUMN setup_required boolean NOT NULL DEFAULT false;
ALTER TABLE public.org_person ADD COLUMN setup_episode_id uuid;
ALTER TABLE public.org_person ADD COLUMN removed_capture_at timestamptz;
ALTER TABLE public.org_person ADD COLUMN pending_operation_id uuid;
ALTER TABLE public.org_person ADD CONSTRAINT ck_org_person_directory CHECK(directory_status IN ('included','exempt','offboarded','outside','merged'));
ALTER TABLE public.org_person ADD CONSTRAINT fk_org_person_pending_operation FOREIGN KEY(workspace_id,pending_operation_id) REFERENCES public.otm_operation(workspace_id,id);
-- Reporting identity stays immutable while managed-directory decisions are independent state.
DROP TRIGGER org_person_immutable ON public.org_person;
CREATE FUNCTION public.org_guard_person() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP='DELETE' OR (NEW.id,NEW.workspace_id,NEW.email) IS DISTINCT FROM (OLD.id,OLD.workspace_id,OLD.email) THEN
   RAISE EXCEPTION 'organization identity is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER org_person_immutable BEFORE UPDATE OR DELETE ON public.org_person FOR EACH ROW EXECUTE FUNCTION public.org_guard_person();
ALTER TABLE public.otm_operation DROP CONSTRAINT ck_operation_kind;
ALTER TABLE public.otm_operation ADD CONSTRAINT ck_operation_kind CHECK(kind IN ('inspect_import','organization_action'));
ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_step_kind;
ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_step_kind CHECK((step_key='inspect_target' AND command_kind='inspect_tenancy') OR (step_key='apply_lifecycle' AND command_kind='organization_action'));
ALTER TABLE public.otm_operation_step DROP CONSTRAINT ck_inspection_read_only;
ALTER TABLE public.otm_operation_step ADD CONSTRAINT ck_inspection_read_only CHECK((command_kind='inspect_tenancy' AND effect_knowledge='none') OR (command_kind='organization_action' AND effect_knowledge IN ('none','known')));
ALTER TABLE public.audit_event DROP CONSTRAINT ck_audit_event_revision;
ALTER TABLE public.audit_event ADD CONSTRAINT ck_audit_event_revision CHECK(
 (operation_id IS NOT NULL AND administrator_id IS NULL AND ((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_outcome') AND intent_revision IS NULL)))
 OR (kind IN ('administrator_revoked','administrator_bootstrapped','local_credentials_reset','local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NOT NULL)
 OR (kind IN ('organization_configured','organization_feed_received','organization_feed_rejected','organization_published','organization_review_decided') AND operation_id IS NULL AND intent_revision IS NULL AND administrator_id IS NULL)
);


CREATE TABLE public.org_recommendation (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	person_id UUID, 
	kind VARCHAR(64) NOT NULL, 
	category VARCHAR(24) NOT NULL, 
	target VARCHAR(512) NOT NULL, 
	basis VARCHAR(256) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	version_id UUID NOT NULL, 
	resolution VARCHAR(64), 
	operation_id UUID, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_org_recommendation_scope UNIQUE (workspace_id, id), 
	FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id), 
	FOREIGN KEY(workspace_id, person_id) REFERENCES public.org_person (workspace_id, id), 
	FOREIGN KEY(workspace_id, version_id) REFERENCES public.org_version (workspace_id, id), 
	FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT ck_org_review_category CHECK (category IN ('actionable','informational','change')), 
	CONSTRAINT ck_org_review_status CHECK (status IN ('open','resolved','ignored')), 
	CONSTRAINT ck_org_review_times CHECK (last_seen_at>=first_seen_at AND (resolved_at IS NULL OR resolved_at>=first_seen_at))
)

;
CREATE INDEX ix_org_review_inbox ON public.org_recommendation (workspace_id, category, status, last_seen_at);
CREATE UNIQUE INDEX uq_org_review_open ON public.org_recommendation (workspace_id, kind, target) WHERE status = 'open';

CREATE TABLE public.otm_tenancy (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	tenancy_ocid VARCHAR(256) NOT NULL, 
	parent_tenancy_ocid VARCHAR(256) NOT NULL, 
	organization_id VARCHAR(256) NOT NULL, 
	home_region VARCHAR(64) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	provider_mode VARCHAR(16) NOT NULL, 
	origin VARCHAR(16) NOT NULL, 
	revision INTEGER DEFAULT '1' NOT NULL, 
	operation_id UUID, 
	last_operation_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tenancy_scope UNIQUE (workspace_id, id), 
	CONSTRAINT uq_tenancy_ocid UNIQUE (workspace_id, tenancy_ocid), 
	FOREIGN KEY(workspace_id) REFERENCES public.org_workspace (id), 
	FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	FOREIGN KEY(workspace_id, last_operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT ck_tenancy_kind_origin CHECK (kind IN ('individual','shared') AND origin IN ('create','import')), 
	CONSTRAINT ck_tenancy_status CHECK (status IN ('pending','active','terminating','terminated','failed','cancelled')), 
	CONSTRAINT ck_tenancy_qualification CHECK (provider_mode='simulated' AND tenancy_ocid<>parent_tenancy_ocid AND revision>=1)
)

;
CREATE INDEX ix_tenancy_inventory ON public.otm_tenancy (workspace_id, status, name);

CREATE TABLE public.otm_tenancy_membership (
	id UUID NOT NULL, 
	workspace_id VARCHAR(256) NOT NULL, 
	tenancy_id UUID NOT NULL, 
	person_id UUID NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	user_ocid VARCHAR(256), 
	compartment_ocid VARCHAR(256), 
	compartment_name VARCHAR(100), 
	parent_compartment_ocid VARCHAR(256), 
	cleanup_required BOOLEAN DEFAULT 'false' NOT NULL, 
	operation_id UUID, 
	revision INTEGER DEFAULT '1' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tenancy_membership_scope UNIQUE (workspace_id, id), 
	FOREIGN KEY(workspace_id, tenancy_id) REFERENCES public.otm_tenancy (workspace_id, id), 
	FOREIGN KEY(workspace_id, person_id) REFERENCES public.org_person (workspace_id, id), 
	FOREIGN KEY(workspace_id, operation_id) REFERENCES public.otm_operation (workspace_id, id), 
	CONSTRAINT ck_membership_role_status CHECK (role IN ('owner','member') AND status IN ('pending','active','removing','removed','failed')), 
	CONSTRAINT ck_membership_revision CHECK (revision>=1)
)

;
CREATE INDEX ix_membership_person ON public.otm_tenancy_membership (workspace_id, person_id, status);
CREATE UNIQUE INDEX uq_membership_current ON public.otm_tenancy_membership (workspace_id, tenancy_id, person_id) WHERE status IN ('pending', 'active', 'removing');
CREATE UNIQUE INDEX uq_membership_owner ON public.otm_tenancy_membership (workspace_id, tenancy_id) WHERE role = 'owner' AND status IN ('pending', 'active', 'removing');

CREATE FUNCTION public.otm_registry_history_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN RAISE EXCEPTION 'registry history is protected'; END IF;
 IF (NEW.id,NEW.workspace_id,NEW.created_at) IS DISTINCT FROM (OLD.id,OLD.workspace_id,OLD.created_at) THEN RAISE EXCEPTION 'registry identity is immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER otm_tenancy_immutable BEFORE UPDATE OR DELETE ON public.otm_tenancy FOR EACH ROW EXECUTE FUNCTION public.otm_registry_history_guard();
CREATE TRIGGER otm_tenancy_no_truncate BEFORE TRUNCATE ON public.otm_tenancy FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER otm_tenancy_membership_immutable BEFORE UPDATE OR DELETE ON public.otm_tenancy_membership FOR EACH ROW EXECUTE FUNCTION public.otm_registry_history_guard();
CREATE TRIGGER otm_tenancy_membership_no_truncate BEFORE TRUNCATE ON public.otm_tenancy_membership FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_recommendation_no_delete BEFORE DELETE ON public.org_recommendation FOR EACH ROW EXECUTE FUNCTION public.org_deny_change();
CREATE TRIGGER org_recommendation_no_truncate BEFORE TRUNCATE ON public.org_recommendation FOR EACH STATEMENT EXECUTE FUNCTION public.org_deny_change();
-- An active child has exactly one accountable owner. Pending rows may reserve that role.
CREATE FUNCTION public.otm_guard_active_owner() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE target uuid; scope text;
BEGIN
 IF TG_TABLE_NAME='otm_tenancy' THEN target:=NEW.id; scope:=NEW.workspace_id;
 ELSE target:=NEW.tenancy_id; scope:=NEW.workspace_id; END IF;
 IF EXISTS(SELECT 1 FROM public.otm_tenancy WHERE id=target AND workspace_id=scope AND status='active')
 AND (SELECT count(*) FROM public.otm_tenancy_membership WHERE tenancy_id=target AND workspace_id=scope AND role='owner' AND status='active')<>1 THEN
  RAISE EXCEPTION 'active tenancy requires one owner';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER otm_tenancy_owner_guard AFTER INSERT OR UPDATE ON public.otm_tenancy DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.otm_guard_active_owner();
CREATE CONSTRAINT TRIGGER otm_membership_owner_guard AFTER INSERT OR UPDATE ON public.otm_tenancy_membership DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.otm_guard_active_owner();

CREATE OR REPLACE VIEW public.current_organization AS SELECT w.id AS workspace_id,m.version_id,m.person_id,m.full_name,m.email,m.manager_email,
       manager.full_name AS manager_name,m.profile,m.evidence,m.lob_id,
       m.accountable_leader_email,leader.full_name AS accountable_leader_name,
       lob.value->>'label' AS lob_name,m.designee_emails,
       COALESCE(designees.names,'[]'::jsonb) AS designee_names,m.ancestry,m.absence_review,
       COALESCE((m.data->>'known_manager')::boolean,false) AS known_manager,managed_person.directory_status,managed_person.setup_required,managed_person.pending_operation_id,
       (SELECT count(*) FROM public.otm_tenancy_membership a WHERE a.workspace_id=w.id AND a.person_id=m.person_id AND a.status IN ('active','removing')) AS tenancy_count
FROM public.org_workspace w JOIN public.org_member m ON m.workspace_id=w.id AND m.version_id=w.applied_version_id
JOIN public.org_person managed_person ON managed_person.workspace_id=w.id AND managed_person.id=m.person_id
JOIN public.org_version v ON v.workspace_id=w.id AND v.id=m.version_id AND v.sealed
LEFT JOIN public.org_member manager ON manager.workspace_id=w.id AND manager.version_id=m.version_id AND manager.person_id=m.manager_person_id
LEFT JOIN public.org_member leader ON leader.workspace_id=w.id AND leader.version_id=m.version_id AND leader.email=m.accountable_leader_email
LEFT JOIN LATERAL (SELECT value FROM jsonb_array_elements(v.configuration->'lobs') WHERE value->>'id'=m.lob_id) lob ON true
LEFT JOIN LATERAL (
 SELECT jsonb_agg(COALESCE(d.full_name,a.value) ORDER BY a.ordinality) AS names
 FROM jsonb_array_elements_text(m.designee_emails) WITH ORDINALITY AS a(value,ordinality)
 LEFT JOIN public.org_member d ON d.workspace_id=w.id AND d.version_id=m.version_id AND d.email=a.value
) designees ON true
WHERE managed_person.directory_status IN ('included','outside');
CREATE UNIQUE INDEX uq_org_decision_request ON public.audit_event(workspace_id,actor_subject,(data->>'request_key')) WHERE kind='organization_review_decided' AND data->>'request_key' IS NOT NULL;
