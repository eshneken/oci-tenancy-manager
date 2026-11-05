"""One exhausted-read email episode per child/source/admin, using the existing durable outbox."""

from uuid import uuid4

from sqlalchemy import func, select

from otm.email_policy import EmailPolicyBlocked
from otm.financial.context import failure_source, target_source
from otm.notifications.contracts import CostFailureNotice
from otm.notifications.service import record_evidence
from otm.operations.contracts import canonical_hash
from otm.storage.tables import (
    administrator,
    financial_collection,
    financial_observation,
    notification_outbox,
)


# A normalized same-source observation resets the incident; transport without facts does not.
def recovered_after(connection, workspace, failure_scope_hash):
    return connection.scalar(
        select(func.max(financial_collection.c.updated_at))
        .join(
            financial_observation,
            (financial_observation.c.workspace_id == financial_collection.c.workspace_id)
            & (financial_observation.c.collection_id == financial_collection.c.id),
        )
        .where(
            financial_collection.c.workspace_id == workspace,
            financial_collection.c.failure_scope_hash == failure_scope_hash,
            financial_collection.c.state == "succeeded",
        )
    )


# Recipient membership is scoped admin authority, never tenancy ownership or lifecycle
# responsibility.
def stage_failure(notifier, connection, op, collection, target, at):
    source = target_source(target)
    failure_scope = failure_source(target)
    recovered = recovered_after(connection, op["workspace_id"], failure_scope)
    grants = (
        connection.execute(
            select(administrator).where(
                administrator.c.workspace_id == op["workspace_id"],
                administrator.c.status == "active",
            )
        )
        .mappings()
        .all()
    )
    for grant in grants:
        previous = select(notification_outbox.c.id).where(
            notification_outbox.c.workspace_id == op["workspace_id"],
            notification_outbox.c.intent["contract_version"].astext == "cost-failure-email-1",
            notification_outbox.c.intent["failure_scope_hash"].astext == failure_scope,
            notification_outbox.c.intent["administrator_id"].astext == str(grant["id"]),
        )
        if recovered:
            previous = previous.where(notification_outbox.c.created_at >= recovered)
        if connection.scalar(previous.limit(1)):
            continue
        route = notifier.policy.route(grant["email"])
        state, code = "pending", None
        try:
            notifier.policy.guard(route)
        except EmailPolicyBlocked:
            state, code = "blocked", "EMAIL_ROUTE_BLOCKED"
        notice = CostFailureNotice(
            operation_id=op["id"],
            collection_id=collection["id"],
            tenancy_id=collection["tenancy_id"],
            source_hash=source,
            failure_scope_hash=failure_scope,
            administrator_id=grant["id"],
            authorization_revision=grant["authorization_revision"],
            original_recipient=grant["email"],
            delivery_recipient=route.effective_email,
            route=route,
            application_origin=notifier.application_origin,
            delivery_profile_hash=notifier.profile_hash,
            created_at=at,
        )
        data = notice.model_dump(mode="json")
        transition = canonical_hash(
            {
                "source": source,
                "collection": str(collection["id"]),
                "administrator": str(grant["id"]),
                "event": "cost_read_failed",
            }
        )
        values = dict(
            id=uuid4(),
            workspace_id=op["workspace_id"],
            operation_id=op["id"],
            transition_key=transition,
            intent=data,
            intent_hash=canonical_hash(data),
            state=state,
            attempts=0,
            created_at=at,
            updated_at=at,
            safe_code=code,
        )
        connection.execute(notification_outbox.insert().values(**values))
        record_evidence(connection, values, state=state, attempts=0, safe_code=code, at=at)
        if state == "pending":
            notifier.enqueuer.enqueue(connection, values["id"])
