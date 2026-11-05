"""Closed security evidence shared by local authentication and IdP-independent logout."""

from uuid import uuid4

from otm.auth.local import SecurityEvidence
from otm.operations.contracts import canonical_hash
from otm.storage.tables import audit_event


# Store one closed security outcome without factor values, request input or bearer material.
def security_event(
    connection, *, workspace, kind, grant_id, actor, at, session_id=None, revision=None
):
    data = SecurityEvidence(
        contract_version="local-auth-1",
        outcome=kind,
        session_id=session_id,
        authorization_revision=revision,
    ).model_dump(mode="json")
    connection.execute(
        audit_event.insert().values(
            id=uuid4(),
            workspace_id=workspace,
            operation_id=None,
            administrator_id=grant_id,
            intent_revision=None,
            actor=actor.key,
            actor_subject=actor.key,
            actor_snapshot=actor.model_dump(mode="json"),
            kind=kind,
            at=at,
            contract_version="local-auth-1",
            data=data,
            data_hash=canonical_hash(data),
        )
    )
