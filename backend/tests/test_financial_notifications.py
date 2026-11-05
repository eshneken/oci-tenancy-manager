"""Independent cost incident, administrator and contact-routing boundaries."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from test_financial_units import NOW, cost_case, drift_case, update_case
from test_notifications import notice

from otm.email_policy import MailPolicy
from otm.financial.context import failure_source
from otm.financial.notifications import stage_failure
from otm.notifications.contracts import CostFailureNotice
from otm.notifications.service import decode_intent
from otm.operations.contracts import canonical_hash

__all__ = ["cost_case", "drift_case", "update_case", "notice"]


# Policy timing/configuration edits keep incident identity, but a different budget/access
# source does not.
def test_failure_scope_excludes_non_source_revisions(cost_case):
    c = cost_case
    source = failure_source(c.target)
    changed = c.target.model_copy(
        update={
            "configuration": c.target.configuration.model_copy(
                update={"revision": 2, "baseline_id": uuid4(), "configuration_id": uuid4()}
            ),
            "profile": c.profile.model_copy(
                update={"source_max_age_seconds": 1, "retry_delays_seconds": ()}
            ),
        }
    )
    assert failure_source(changed) == source
    assert failure_source(c.target.model_copy(update={"budget_ocid": "different"})) != source
    assert (
        failure_source(c.target.model_copy(update={"source_access_binding_id": uuid4()})) != source
    )


# Cost routing freezes the independent administrator recipient and exact acquisition failure
# evidence.
def notice_intent(c, n):
    return CostFailureNotice(
        operation_id=c.operation["id"],
        collection_id=c.collection["id"],
        tenancy_id=c.row["id"],
        source_hash=c.collection["source_hash"],
        failure_scope_hash=failure_source(c.target),
        administrator_id=c.grant["id"],
        authorization_revision=c.grant["authorization_revision"],
        original_recipient="admin@example.test",
        delivery_recipient="capture@example.test",
        route=n.policy.route("admin@example.test"),
        created_at=NOW,
    )


# One continued incident stages once; a blocked route is audited without permitting SMTP.
def test_staging_dedup_blocked_and_capture(cost_case):
    c = cost_case
    notifier = SimpleNamespace(
        policy=MailPolicy(environment="staging", email_override="capture@example.test"),
        application_origin=None,
        profile_hash=None,
        enqueuer=Mock(),
    )
    c.grant["email"] = "admin@example.test"
    c.connection.execute.return_value.mappings.return_value.all.return_value = [c.grant]
    c.connection.scalar.side_effect = [None, None]
    with patch("otm.financial.notifications.record_evidence") as evidence:
        stage_failure(notifier, c.connection, c.operation, c.collection, c.target, NOW)
        assert evidence.call_args.kwargs["state"] == "pending"
        notifier.enqueuer.enqueue.assert_called_once()
        c.connection.scalar.side_effect = [NOW - timedelta(seconds=1), uuid4()]
        stage_failure(notifier, c.connection, c.operation, c.collection, c.target, NOW)
        assert evidence.call_count == 1
        c.grant["email"] = None
        c.connection.scalar.side_effect = [None, None]
        stage_failure(notifier, c.connection, c.operation, c.collection, c.target, NOW)
        assert (
            evidence.call_args.kwargs["state"] == "pending"
        )  # staging override is an explicit capture route
        notifier.policy = MailPolicy(environment="production")
        c.connection.scalar.side_effect = [None, None]
        stage_failure(notifier, c.connection, c.operation, c.collection, c.target, NOW)
        assert evidence.call_args.kwargs["state"] == "blocked"


# Before every SMTP attempt, current source/grant/route authority is rechecked rather than
# owner metadata.
def test_cost_notice_context_and_envelope(cost_case, notice):
    c, n = cost_case, notice
    intent = notice_intent(c, n)
    data = intent.model_dump(mode="json")
    row = {
        **n.row,
        "operation_id": c.operation["id"],
        "intent": data,
        "intent_hash": canonical_hash(data),
    }
    assert decode_intent(row) == intent
    c.grant["email"] = "admin@example.test"
    collection = {**c.collection, "state": "failed", "safe_code": "COST_RETRIES_EXHAUSTED"}
    n.worker.workspace = c.policy.workspace_id
    n.worker.cost_context_loader = lambda: (c.loader(), c.profile)
    n.worker.clock = lambda: NOW
    n.worker.application_origin = None

    # Each real branch gets independent query results; no lifecycle authority helper is involved.
    def run(*, current=collection, grant=c.grant, registered=c.row):
        n.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
            current,
            grant,
            registered,
        ]
        n.connection.scalar.return_value = None
        return n.worker._context_issue(n.connection, row, c.operation, intent)

    assert run() is None
    assert run(grant=None) == ("blocked", "EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE")
    assert run(current=None) == ("superseded", "EMAIL_CONTEXT_CHANGED")
    assert run(registered=None) == ("superseded", "EMAIL_CONTEXT_CHANGED")
    n.worker.cost_context_loader = None
    assert run() == ("blocked", "EMAIL_CONTEXT_CHANGED")
    n.worker.cost_context_loader = lambda: (SimpleNamespace(execution_paused=True), c.profile)
    assert run() == ("blocked", "EMAIL_CONTEXT_CHANGED")
    n.worker.cost_context_loader = lambda: (c.loader(), c.profile)
    assert run(registered={**c.row, "revision": 2}) is None
    n.worker.application_origin = "https://app.example.test"
    assert run() == ("blocked", "EMAIL_APPLICATION_ORIGIN_CHANGED")
    n.worker.application_origin = None
    n.worker.transport.profile_hash = "a" * 64
    assert run() == ("blocked", "EMAIL_TRANSPORT_CHANGED")
    n.worker.transport.profile_hash = None
    n.worker.policy_loader = lambda: MailPolicy(environment="production")
    assert run() == ("blocked", "EMAIL_ROUTE_BLOCKED")
    n.worker.policy_loader = lambda: n.policy
    n.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = None
    with (
        patch("otm.financial.notifications.recovered_after", return_value=NOW),
        patch.object(n.worker, "_locked", return_value=(row, c.operation)),
        patch.object(n.worker, "_context_issue", return_value=None),
        patch("otm.notifications.worker.record_evidence"),
    ):
        n.worker.engine.begin.return_value.__enter__.return_value = n.connection
        envelope, attempt = n.worker._prepare(row["id"])
        assert (
            envelope.subject == "Tenancy cost collection failed"
            and envelope.recipient == "capture@example.test"
            and attempt
        )


# Acquisition failure cannot be hidden by a retry or another compatible queued request.
def test_retained_failure_is_visible_during_pending_reads(cost_case):
    from test_financial_units import observed

    c = cost_case
    row, snapshot = observed(c)
    for state in ["retry", "reading", "queued"]:
        head = {
            **c.collection,
            "state": state,
            "safe_code": None,
            "continuing_outcome": "COST_READ_UNAVAILABLE",
        }
        with patch(
            "otm.financial.service.current_records",
            return_value=({c.row["id"]: (row, snapshot)}, {c.row["id"]: head}),
        ):
            view = c.service.summaries(c.connection, c.policy.workspace_id, [c.row])[c.row["id"]]
        assert (
            view.state == "unavailable"
            and view.pending
            and not view.actual_over_budget
            and view.retrieved_at == snapshot.retrieved_at
        )
