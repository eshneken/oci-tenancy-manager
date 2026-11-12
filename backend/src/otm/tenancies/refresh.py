"""Thin fleet admission over existing read workflows, without a new queue or coordinator table."""

from uuid import uuid5

from sqlalchemy import select

from otm.auth.service import SessionFailure
from otm.configuration.drift_context import registered_child
from otm.configuration.drift_contracts import ConfigurationCheckRequest
from otm.financial.contracts import CostRefreshRequest
from otm.financial.service import CostConflict
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import operation, tenancy
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.refresh_contracts import (
    FleetRefreshReceipt,
    FleetRefreshStatus,
    RefreshCategory,
    RefreshJob,
)

READ_KINDS = ("cost_collection", "required_user_check", "configuration_check")


# Independent admissions keep partial success durable; no provider method runs in the request.
def refresh_fleet(workflow, principal, command):
    workspace = workflow.store._principal(principal)
    with read_snapshot(workflow.store.engine) as connection:
        rows = (
            connection.execute(
                select(tenancy)
                .where(tenancy.c.workspace_id == workspace, tenancy.c.status == "active")
                .order_by(tenancy.c.id)
                .limit(1001)
            )
            .mappings()
            .all()
        )
        if len(rows) > 1000:
            raise OrganizationConflict("FLEET_REFRESH_TOO_LARGE")
        identifiers = tuple(row["id"] for row in rows if registered_child(row, workflow.policy))
    categories = []
    for category, service in (
        ("costs", workflow.cost_collections),
        ("users", workflow.presence_checks),
        ("configuration", workflow.configuration_checks),
    ):
        operations, skipped, failed = [], 0, 0
        for identifier in identifiers:
            # Server-side actor/workspace guards still execute for each independent admission.
            key = uuid5(command.client_request_key, f"{workspace}:{category}:{identifier}")
            if service is None:
                skipped += 1
                continue
            try:
                if category == "costs":
                    receipt = service.start(
                        principal, CostRefreshRequest(client_request_key=key, tenancy_id=identifier)
                    )
                    operations.extend(receipt.operation_ids)
                    skipped += receipt.skipped_count
                elif category == "users":
                    receipt = service.start(
                        principal,
                        identifier,
                        PresenceCheckRequest(client_request_key=key),
                        join_pending=True,
                    )
                    operations.append(receipt.operation_id)
                else:
                    receipt = service.start(
                        principal,
                        ConfigurationCheckRequest(client_request_key=key, tenancy_id=identifier),
                        join_pending=True,
                    )
                    operations.append(receipt.operation_id)
            except SessionFailure:
                # Revocation is never downgraded into an apparently successful partial refresh.
                raise
            except (OrganizationConflict, CostConflict):
                skipped += 1
            except RequestConflict:
                raise
            except Exception:
                # Do not return SQL/provider/identity text; preserve independently accepted work.
                failed += 1
        categories.append(
            RefreshCategory(
                category=category,
                operation_ids=tuple(dict.fromkeys(operations)),
                skipped_count=skipped,
                failed_count=failed,
            )
        )
    return FleetRefreshReceipt(tenancy_count=len(identifiers), categories=tuple(categories))


# Only existing read-job states in the current administrator's workspace can be observed.
def refresh_status(workflow, principal, command):
    workspace = workflow.store._principal(principal)
    identifiers = tuple(dict.fromkeys(command.operation_ids))
    with read_snapshot(workflow.store.engine) as connection:
        rows = (
            connection.execute(
                select(operation.c.id, operation.c.state).where(
                    operation.c.workspace_id == workspace,
                    operation.c.id.in_(identifiers),
                    operation.c.kind.in_(READ_KINDS),
                )
            )
            .mappings()
            .all()
        )
    states = {row["id"]: row["state"] for row in rows}
    return FleetRefreshStatus(
        jobs=tuple(
            RefreshJob(
                operation_id=identifier,
                state=(
                    "unavailable"
                    if identifier not in states
                    else "pending"
                    if states[identifier] in {"queued", "running", "waiting"}
                    else "finished"
                    if states[identifier] == "succeeded"
                    else "failed"
                ),
            )
            for identifier in identifiers
        )
    )
