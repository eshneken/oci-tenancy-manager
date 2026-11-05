-- Generated local prototype table DDL; not a production migration.

-- Store.initialize also infrastructure-services immutable-content and sealed-revision triggers.

CREATE SCHEMA IF NOT EXISTS "otm_org";

CREATE TABLE otm_org.org_configuration (
	id UUID NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE otm_org.org_person (
	id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE otm_org.org_population (
	id VARCHAR NOT NULL, 
	configuration_id UUID NOT NULL, 
	head_id UUID, 
	PRIMARY KEY (id), 
	FOREIGN KEY(configuration_id) REFERENCES otm_org.org_configuration (id)
);

CREATE TABLE otm_org.org_snapshot (
	id UUID NOT NULL, 
	population_id VARCHAR NOT NULL, 
	source_id VARCHAR NOT NULL, 
	external_id VARCHAR NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (population_id, source_id, external_id), 
	FOREIGN KEY(population_id) REFERENCES otm_org.org_population (id)
);

CREATE TABLE otm_org.org_receipt (
	id UUID NOT NULL, 
	snapshot_id UUID NOT NULL, 
	received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	raw_digest VARCHAR(64), 
	disposition VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(snapshot_id) REFERENCES otm_org.org_snapshot (id)
);

CREATE TABLE otm_org.org_revision (
	id UUID NOT NULL, 
	population_id VARCHAR NOT NULL, 
	predecessor_id UUID, 
	snapshot_id UUID NOT NULL, 
	configuration_id UUID NOT NULL, 
	sealed BOOLEAN DEFAULT 'false' NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (population_id, id), 
	FOREIGN KEY(population_id) REFERENCES otm_org.org_population (id), 
	FOREIGN KEY(predecessor_id) REFERENCES otm_org.org_revision (id), 
	FOREIGN KEY(snapshot_id) REFERENCES otm_org.org_snapshot (id), 
	FOREIGN KEY(configuration_id) REFERENCES otm_org.org_configuration (id)
);

CREATE TABLE otm_org.org_state (
	revision_id UUID NOT NULL, 
	person_id UUID NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	manager_person_id UUID, 
	data JSONB NOT NULL, 
	PRIMARY KEY (revision_id, person_id), 
	UNIQUE (revision_id, email), 
	CONSTRAINT not_self_managed CHECK (person_id <> manager_person_id), 
	FOREIGN KEY(revision_id) REFERENCES otm_org.org_revision (id), 
	FOREIGN KEY(person_id) REFERENCES otm_org.org_person (id), 
	CONSTRAINT manager_same_revision FOREIGN KEY(revision_id, manager_person_id) REFERENCES otm_org.org_state (revision_id, person_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX manager_children ON otm_org.org_state (revision_id, manager_person_id, person_id);

CREATE TABLE otm_org.org_result (
	snapshot_id UUID NOT NULL, 
	state VARCHAR NOT NULL, 
	revision_id UUID, 
	diagnostics JSONB NOT NULL, 
	PRIMARY KEY (snapshot_id), 
	FOREIGN KEY(snapshot_id) REFERENCES otm_org.org_snapshot (id), 
	FOREIGN KEY(revision_id) REFERENCES otm_org.org_revision (id)
);

CREATE TABLE otm_org.org_incident (
	id UUID NOT NULL, 
	population_id VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	target VARCHAR NOT NULL, 
	first_revision_id UUID NOT NULL, 
	last_revision_id UUID NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(population_id) REFERENCES otm_org.org_population (id), 
	FOREIGN KEY(first_revision_id) REFERENCES otm_org.org_revision (id), 
	FOREIGN KEY(last_revision_id) REFERENCES otm_org.org_revision (id)
);

CREATE UNIQUE INDEX one_open_incident ON otm_org.org_incident (population_id, kind, target) WHERE resolved_at IS NULL;

CREATE TABLE otm_org.org_event (
	id UUID NOT NULL, 
	revision_id UUID NOT NULL, 
	actor VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	data JSONB NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(revision_id) REFERENCES otm_org.org_revision (id)
);

CREATE TABLE otm_org.org_notification (
	id UUID NOT NULL, 
	incident_id UUID NOT NULL, 
	revision_id UUID NOT NULL, 
	recipients JSONB NOT NULL, 
	state VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (incident_id), 
	FOREIGN KEY(incident_id) REFERENCES otm_org.org_incident (id), 
	FOREIGN KEY(revision_id) REFERENCES otm_org.org_revision (id)
);

ALTER TABLE otm_org.org_population ADD CONSTRAINT population_head_same_scope FOREIGN KEY(id, head_id) REFERENCES otm_org.org_revision (population_id, id);
