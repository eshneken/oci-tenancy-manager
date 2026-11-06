"""Explicit simulated automation connections; no credential material or real access assertions."""

from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from otm.storage.tables import managed_object_binding as binding
from otm.storage.tables import user_presence_connection as connections
from otm.storage.transaction import require_transaction


# Register only explicitly opted-in fresh captures; never backfill from a read or historical replay.
def capture_connection(connection, row, intent, event_id, at):
    require_transaction(connection)
    if intent.presence_connection_contract is None:
        return None
    if intent.onboarding_version != 3 or intent.action not in {"create_tenancy", "import_tenancy"}:
        raise ValueError("PRESENCE_CONNECTION_SOURCE_UNVERIFIED")
    rows = list(
        connection.execute(
            select(binding).where(
                binding.c.workspace_id == intent.workspace_id,
                binding.c.tenancy_id == intent.pending_tenancy_id,
                binding.c.logical_key.in_(("identity/domain", "identity/user/automation")),
                binding.c.state == "active",
            )
        ).mappings()
    )
    keys = {item["logical_key"]: item for item in rows}
    domain, signer = keys.get("identity/domain"), keys.get("identity/user/automation")
    if (
        len(rows) != 2
        or domain is None
        or signer is None
        or (
            signer["identity_domain_binding_id"] != domain["id"]
            or any(
                item["created_operation_id"] != row["id"]
                or item["source_evidence_event_id"] != event_id
                for item in rows
            )
        )
    ):
        raise ValueError("PRESENCE_CONNECTION_SOURCE_UNVERIFIED")
    existing = (
        connection.execute(
            select(connections).where(
                connections.c.workspace_id == intent.workspace_id,
                connections.c.tenancy_id == intent.pending_tenancy_id,
            )
        )
        .mappings()
        .all()
    )
    facts = dict(
        workspace_id=intent.workspace_id,
        tenancy_id=intent.pending_tenancy_id,
        automation_binding_id=signer["id"],
        domain_binding_id=domain["id"],
        revision=1,
        provider_mode="simulated",
        contract_version=intent.presence_connection_contract,
        state="active",
        created_operation_id=row["id"],
        source_evidence_event_id=event_id,
        retired_operation_id=None,
        created_at=at,
        updated_at=at,
    )
    if existing:
        if len(existing) != 1 or any(existing[0][key] != value for key, value in facts.items()):
            raise ValueError("PRESENCE_CONNECTION_CONFLICT")
        return existing[0]["id"]
    identifier = uuid4()
    try:
        connection.execute(connections.insert().values(id=identifier, **facts))
    except DBAPIError:
        raise ValueError("PRESENCE_CONNECTION_CONFLICT") from None
    return identifier


# The caller retires canonical identities first in the same verified termination transaction.
def retire_connection(connection, workspace, tenancy_id, operation_id, at):
    require_transaction(connection)
    connection.execute(
        update(connections)
        .where(
            connections.c.workspace_id == workspace,
            connections.c.tenancy_id == tenancy_id,
            connections.c.state == "active",
        )
        .values(state="retired", retired_operation_id=operation_id, updated_at=at)
    )
