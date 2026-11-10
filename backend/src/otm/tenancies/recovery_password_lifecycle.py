"""Serialize termination with credential obligations without reserving a child for four hours."""

from sqlalchemy import select, update

from otm.storage.organization import OrganizationConflict
from otm.storage.tables import operation, recovery_credential, signing_credential, tenancy


# Every termination entry point uses the same tenancy-to-credential lock order as disclosure.
def require_termination_ready(connection, workspace, tenancy_ids):
    identifiers = sorted(set(tenancy_ids), key=str)
    if not identifiers:
        return
    connection.execute(
        select(tenancy.c.id)
        .where(
            tenancy.c.workspace_id == workspace,
            tenancy.c.id.in_(identifiers),
        )
        .order_by(tenancy.c.id)
        .with_for_update()
    ).all()
    rows = (
        connection.execute(
            select(recovery_credential)
            .where(
                recovery_credential.c.workspace_id == workspace,
                recovery_credential.c.tenancy_id.in_(identifiers),
                recovery_credential.c.state != "retired",
            )
            .order_by(recovery_credential.c.id)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if any(
        row["first_disclosure_at"] is not None
        or row["state"]
        in {
            "staging",
            "rotating",
            "unknown",
        }
        for row in rows
    ):
        raise OrganizationConflict("RECOVERY_PASSWORD_ROTATION_REQUIRED")


# Only confirmed initiation retires ordinary eligibility; immutable history/custody are retained.
def retire_terminated_credentials(connection, workspace, tenancy_ids, at):
    identifiers = tuple(set(tenancy_ids))
    if not identifiers:
        return
    confirmed = select(tenancy.c.id).where(
        tenancy.c.workspace_id == workspace,
        tenancy.c.id.in_(identifiers),
        tenancy.c.status == "terminated",
    )
    connection.execute(
        update(recovery_credential)
        .where(
            recovery_credential.c.workspace_id == workspace,
            recovery_credential.c.tenancy_id.in_(confirmed),
            recovery_credential.c.state == "usable",
            recovery_credential.c.first_disclosure_at.is_(None),
        )
        .values(state="retired", updated_at=at)
    )

    # Confirmed initiation also tombstones the managed signer and cancels its future ETA.
    # Pending termination/cancellation never enters this confirmed-child subquery.
    retired = (
        connection.execute(
            update(signing_credential)
            .where(
                signing_credential.c.workspace_id == workspace,
                signing_credential.c.tenancy_id.in_(confirmed),
                signing_credential.c.state != "retired",
            )
            .values(state="retired", updated_at=at)
            .returning(signing_credential.c.rotation_operation_id)
        )
        .scalars()
        .all()
    )
    if retired:
        connection.execute(
            update(operation)
            .where(
                operation.c.workspace_id == workspace,
                operation.c.id.in_(retired),
                operation.c.kind == "signing_key",
                operation.c.state.in_(("waiting", "queued", "needs_attention")),
            )
            .values(
                state="cancelled",
                stage="Tenancy termination initiated",
                wait_reason=None,
                completed_at=at,
                updated_at=at,
            )
        )
