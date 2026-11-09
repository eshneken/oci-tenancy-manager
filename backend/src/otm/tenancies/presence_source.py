"""Authenticate retained setup and subsequent exact recovery-network source evidence."""

import json

from sqlalchemy import select

from otm.operations.contracts import canonical_hash
from otm.storage.tables import audit_event
from otm.storage.tables import user_presence_connection as connections
from otm.tenancies.onboarding_contracts import OnboardingEvidence


# Producer evidence is authenticated independently from current expected identity references.
def load_presence_source(connection, snapshot):
    binding = (
        connection.execute(
            select(connections).where(
                connections.c.workspace_id == snapshot.subjects[0].workspace_id,
                connections.c.tenancy_id == snapshot.tenancy_id,
                connections.c.id == snapshot.connection_id,
            )
        )
        .mappings()
        .one()
    )
    event = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == snapshot.subjects[0].workspace_id,
                audit_event.c.operation_id == binding["created_operation_id"],
                audit_event.c.id == binding["source_evidence_event_id"],
                audit_event.c.kind == "onboarding_outcome",
            )
        )
        .mappings()
        .one()
    )
    evidence = OnboardingEvidence.model_validate_json(json.dumps(event["data"]))
    if (
        canonical_hash(event["data"]) != event["data_hash"]
        or evidence.step != "capture_required_users"
        or evidence.outcome != "verified"
        or evidence.required_users is None
    ):
        raise ValueError("PRESENCE_SOURCE_INVALID")
    from otm.tenancies.recovery_network import latest_network_capture

    return latest_network_capture(
        connection, snapshot.subjects[0].workspace_id, snapshot, evidence.required_users
    )
