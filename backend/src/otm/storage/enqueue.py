"""Native name-based deferral on the exact caller-owned transaction; no private dispatch pool."""

import hashlib
from uuid import UUID

import procrastinate
from sqlalchemy.engine import Connection

from otm.storage.transaction import require_transaction

INSPECTION_TASK = "otm.inspect_import"
PRESENCE_TASK = "otm.required_user_check"
RECOVERY_NETWORK_TASK = "otm.recovery_network_repair"
COST_TASK = "otm.cost_collection"
CONFIGURATION_CHECK_TASK = "otm.configuration_check"
CONFIGURATION_TASK = "otm.configuration_update"
ORGANIZATION_TASK = "otm.organization_action"
OPERATIONS_QUEUE = "otm.operations"


# Isolate explicit deployment workspaces without adding another queue manager or table.
def workspace_queue(workspace: str) -> str:
    # Native NOTIFY adds its own prefix; keep the entire channel within PostgreSQL's63 bytes.
    return "otm.sim." + hashlib.sha256(workspace.encode()).hexdigest()[:32]


# Queue a stable operation reference; actor claims, credentials and SDK payloads stay out.
class InspectionEnqueuer:
    # Use native external-connection deferral without opening a private pool.
    def __init__(self, queue: str = OPERATIONS_QUEUE, *, task: str = INSPECTION_TASK):
        if task not in {
            PRESENCE_TASK,
            RECOVERY_NETWORK_TASK,
            COST_TASK,
            INSPECTION_TASK,
            ORGANIZATION_TASK,
            CONFIGURATION_TASK,
            CONFIGURATION_CHECK_TASK,
        }:
            raise ValueError("UNSUPPORTED_OPERATION_TASK")
        self.queue, self.task = queue, task
        self._app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector())

    # Defer one fixed capability without inventing a no-op worker or claiming completion.
    #
    # Registered simulated handlers cover inspection, lifecycle, configuration and cost reads.
    # Real OCI and corporate entitlement composition remain separate work.
    def enqueue(self, connection: Connection, operation_id: UUID, *, delay_seconds=0) -> None:
        raw = require_transaction(connection)
        # Prefer builtins, then migration-owned objects; explicitly put temp relations last.
        # Runtime roles must not have CREATE on public (qualified during deployment).
        connection.exec_driver_sql("SET LOCAL search_path = pg_catalog, public, pg_temp")
        self._app.configure_task(
            self.task,
            allow_unknown=True,
            queue=self.queue,
            connection=raw,
            lock="operation:" + str(operation_id),
            # None means immediately eligible; host-derived zero ETAs can be ahead of DB time.
            schedule_in={"seconds": delay_seconds} if delay_seconds else None,
        ).defer(operation_id=str(operation_id))
