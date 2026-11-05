-- Generated local prototype table DDL; not a production migration.

-- Store.initialize also infrastructure-services immutable-content and sealed-revision triggers.

CREATE SCHEMA IF NOT EXISTS "otm_org";

CREATE TABLE otm_org.org_person (
	id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE otm_org.org_workspace (
	id VARCHAR NOT NULL, 
	configuration_id UUID NOT NULL, 
	configuration JSONB NOT NULL, 
	applied_version_id UUID, 
	proposed_version_id UUID, 
	applied_kind VARCHAR DEFAULT 'applied' NOT NULL, 
	proposed_kind VARCHAR DEFAULT 'proposed' NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (applied_kind = 'applied' AND proposed_kind = 'proposed')
);

CREATE TABLE otm_org.org_feed (
	id UUID NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	source_id VARCHAR NOT NULL, 
	external_id VARCHAR NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE, 
	digest VARCHAR(64) NOT NULL, 
	data JSONB NOT NULL, 
	state VARCHAR NOT NULL, 
	diagnostics JSONB NOT NULL, 
	proposed_version_id UUID, 
	applied_version_id UUID, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, source_id, external_id), 
	UNIQUE (workspace_id, id), 
	FOREIGN KEY(workspace_id) REFERENCES otm_org.org_workspace (id)
);

CREATE TABLE otm_org.org_tenancy (
	id UUID NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	kind VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	legacy BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, id), 
	CHECK (kind IN ('individual', 'shared')), 
	CHECK (status IN ('active', 'deleted')), 
	FOREIGN KEY(workspace_id) REFERENCES otm_org.org_workspace (id)
);

CREATE TABLE otm_org.org_version (
	id UUID NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	base_version_id UUID, 
	feed_id UUID NOT NULL, 
	configuration_id UUID NOT NULL, 
	configuration JSONB NOT NULL, 
	sealed BOOLEAN DEFAULT 'false' NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (kind IN ('proposed', 'applied')), 
	UNIQUE (workspace_id, id), 
	UNIQUE (workspace_id, id, kind), 
	FOREIGN KEY(workspace_id, feed_id) REFERENCES otm_org.org_feed (workspace_id, id), 
	FOREIGN KEY(workspace_id) REFERENCES otm_org.org_workspace (id), 
	FOREIGN KEY(workspace_id, base_version_id) REFERENCES otm_org.org_version (workspace_id, id)
);

CREATE TABLE otm_org.org_tenancy_association (
	id UUID NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	tenancy_id UUID NOT NULL, 
	person_id UUID NOT NULL, 
	role VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id, tenancy_id) REFERENCES otm_org.org_tenancy (workspace_id, id), 
	CHECK (role IN ('owner', 'member')), 
	CHECK (status IN ('active', 'removed')), 
	FOREIGN KEY(workspace_id) REFERENCES otm_org.org_workspace (id), 
	FOREIGN KEY(person_id) REFERENCES otm_org.org_person (id)
);

CREATE UNIQUE INDEX uq_active_tenancy_owner ON otm_org.org_tenancy_association (workspace_id, tenancy_id) WHERE status = 'active' AND role = 'owner';

CREATE UNIQUE INDEX uq_active_tenancy_person ON otm_org.org_tenancy_association (workspace_id, tenancy_id, person_id) WHERE status = 'active';

CREATE TABLE otm_org.org_member (
	version_id UUID NOT NULL, 
	person_id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	full_name VARCHAR, 
	manager_person_id UUID, 
	manager_email VARCHAR(320), 
	profile VARCHAR NOT NULL, 
	evidence VARCHAR NOT NULL, 
	lob_id VARCHAR, 
	accountable_leader_email VARCHAR(320), 
	designee_emails JSONB NOT NULL, 
	ancestry VARCHAR NOT NULL, 
	absence_review BOOLEAN NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (version_id, person_id), 
	UNIQUE (version_id, email), 
	CONSTRAINT not_self_managed CHECK (person_id <> manager_person_id), 
	CONSTRAINT manager_same_revision FOREIGN KEY(version_id, manager_person_id) REFERENCES otm_org.org_member (version_id, person_id) DEFERRABLE INITIALLY DEFERRED, 
	FOREIGN KEY(version_id) REFERENCES otm_org.org_version (id), 
	FOREIGN KEY(person_id) REFERENCES otm_org.org_person (id)
);

CREATE INDEX manager_children ON otm_org.org_member (version_id, manager_person_id);

CREATE TABLE otm_org.org_recommendation (
	id UUID NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	feed_id UUID NOT NULL, 
	proposed_version_id UUID NOT NULL, 
	applied_version_id UUID, 
	person_id UUID, 
	category VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	target VARCHAR NOT NULL, 
	field VARCHAR, 
	before_value JSONB, 
	after_value JSONB, 
	status VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	reason VARCHAR, 
	actor VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES otm_org.org_workspace (id), 
	FOREIGN KEY(feed_id) REFERENCES otm_org.org_feed (id), 
	FOREIGN KEY(proposed_version_id) REFERENCES otm_org.org_version (id), 
	FOREIGN KEY(applied_version_id) REFERENCES otm_org.org_version (id), 
	FOREIGN KEY(person_id) REFERENCES otm_org.org_person (id)
);

CREATE UNIQUE INDEX one_open_exception ON otm_org.org_recommendation (workspace_id, kind, target) WHERE category = 'exception' AND status IN ('open', 'acknowledged');

CREATE TABLE otm_org.audit_event (
	id UUID NOT NULL, 
	workspace_id VARCHAR NOT NULL, 
	feed_id UUID, 
	version_id UUID, 
	actor VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES otm_org.org_workspace (id), 
	FOREIGN KEY(feed_id) REFERENCES otm_org.org_feed (id), 
	FOREIGN KEY(version_id) REFERENCES otm_org.org_version (id)
);

CREATE TABLE otm_org.notification_outbox (
	id UUID NOT NULL, 
	recommendation_id UUID NOT NULL, 
	version_id UUID NOT NULL, 
	recipients JSONB NOT NULL, 
	state VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (recommendation_id), 
	FOREIGN KEY(recommendation_id) REFERENCES otm_org.org_recommendation (id), 
	FOREIGN KEY(version_id) REFERENCES otm_org.org_version (id)
);

ALTER TABLE otm_org.org_workspace ADD FOREIGN KEY(id, applied_version_id, applied_kind) REFERENCES otm_org.org_version (workspace_id, id, kind);

ALTER TABLE otm_org.org_workspace ADD FOREIGN KEY(id, proposed_version_id, proposed_kind) REFERENCES otm_org.org_version (workspace_id, id, kind);
