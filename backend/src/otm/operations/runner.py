"""Register the qualified fixed native task without a default deployment or authorizer."""

from uuid import UUID

import procrastinate

from otm.operations.execution import SimulatedInspectionWorker
from otm.storage.enqueue import INSPECTION_TASK, OPERATIONS_QUEUE


# Register a simulated worker on an explicitly supplied app, without opening its pool.
#
# No automatic retry is enabled. Native stalled-job recovery remains an explicit, owned
# action; replaying this read may supersede an interrupted read but never performs OCI writes.
def register_inspection_task(
    app: procrastinate.App, worker: SimulatedInspectionWorker, queue: str = OPERATIONS_QUEUE
):

    # Accept only the queued UUID reference, without actor or SDK payload arguments.
    @app.task(name=INSPECTION_TASK, queue=queue, retry=False)
    def inspect_import(operation_id):
        try:
            identifier = UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("INVALID_OPERATION_REFERENCE") from None
        worker.run(identifier)

    return inspect_import


# Register the organization lifecycle reference task on the same native, scoped worker queue.
def register_organization_task(app, worker, queue):
    from otm.storage.enqueue import ORGANIZATION_TASK

    # Only immutable operation identity crosses the queue; source rows and credentials do not.
    @app.task(name=ORGANIZATION_TASK, queue=queue, retry=False)
    def organization_action(operation_id):
        try:
            identifier = UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("INVALID_OPERATION_REFERENCE") from None
        worker.run(identifier)

    return organization_action


# Register only reference-based configuration work on the explicitly scoped native queue.
def register_configuration_task(app, worker, queue):
    from otm.storage.enqueue import CONFIGURATION_TASK

    # Native retries replay immutable scope and already-verified target prefixes.
    @app.task(name=CONFIGURATION_TASK, queue=queue, retry=False)
    def configuration_update(operation_id):
        try:
            identifier = UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("INVALID_OPERATION_REFERENCE") from None
        worker.run(identifier)

    return configuration_update


# Read-check jobs carry only their immutable operation UUID, with no implicit provider authority.
def register_configuration_check_task(app, worker, queue):
    from otm.storage.enqueue import CONFIGURATION_CHECK_TASK

    # Native stalled-job handling replays sealed child results rather than duplicating observations.
    @app.task(name=CONFIGURATION_CHECK_TASK, queue=queue, retry=False)
    def configuration_check(operation_id):
        try:
            identifier = UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("INVALID_OPERATION_REFERENCE") from None
        worker.run(identifier)

    return configuration_check


# Register a fixed read capability; reference-only jobs share the existing deployment queue.
def register_cost_task(app, worker, queue):
    from otm.storage.enqueue import COST_TASK

    # Business retries use committed collection heads and native ETA, not unbounded task retry.
    @app.task(name=COST_TASK, queue=queue, retry=False)
    def collect_costs(operation_id):
        worker.run(UUID(operation_id))

    return collect_costs


# Manual account-presence checks carry only the accepted operation reference and no credentials.
def register_presence_task(app, worker, queue):
    from otm.storage.enqueue import PRESENCE_TASK

    # Replayed reads are fenced by the persisted attempt; no automatic provider fallback exists.
    @app.task(name=PRESENCE_TASK, queue=queue, retry=False)
    def required_user_check(operation_id):
        try:
            identifier = UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("INVALID_OPERATION_REFERENCE") from None
        worker.run(identifier)

    return required_user_check


# A separate fixed write capability shares the existing native queue and reference-only payload.
def register_recovery_network_task(app, worker, queue):
    from otm.storage.enqueue import RECOVERY_NETWORK_TASK

    # No automatic retry can duplicate a possibly-sent security-policy mutation.
    @app.task(name=RECOVERY_NETWORK_TASK, queue=queue, retry=False)
    def repair_recovery_network(operation_id):
        worker.run(UUID(operation_id))

    return repair_recovery_network


# Password writes are a fixed reference-only native capability; no blind retries are enabled.
def register_recovery_password_task(app, worker, queue):
    from otm.storage.enqueue import RECOVERY_PASSWORD_TASK

    # Existing operation/credential heads govern every delivery, including delayed system work.
    @app.task(name=RECOVERY_PASSWORD_TASK, queue=queue, retry=False)
    def recovery_password(operation_id):
        worker.run(UUID(operation_id))

    return recovery_password


# Signing-key jobs share the existing native queue and carry only immutable operation references.
def register_signing_key_task(app, worker, queue):
    from otm.storage.enqueue import SIGNING_KEY_TASK

    # Business checkpoints reconcile uncertain effects; native delivery never creates another pair.
    @app.task(name=SIGNING_KEY_TASK, queue=queue, retry=False)
    def signing_key(operation_id):
        worker.run(UUID(operation_id))

    return signing_key
