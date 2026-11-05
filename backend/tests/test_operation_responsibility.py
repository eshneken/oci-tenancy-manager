"""Frozen authority, explicit self-claim and closed replay/read boundaries."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_onboarding import case, registry
from test_tenancy_workflow_units import NOW, principal

from otm.operations.contracts import ActorIdentity, canonical_hash
from otm.operations.responsibility import (
    ResponsibilityCommand,
    ResponsibilityEvidence,
    decode_evidence,
    eligible,
    execution_authority,
    latest_claim,
    take_responsibility,
)
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict

__all__ = ["registry"]


# Build independent creator, claimant and sealed evidence around the existing guided-intent fixture.
@pytest.fixture
def responsibility_case(registry):
    app, intent, row, frozen = case(registry)
    row["kind"] = "organization_action"
    actor = principal()
    creator = ActorIdentity(
        issuer="https://sso.example.test", subject="creator", display_name="Creator"
    )
    frozen = frozen.model_copy(update={"actor": creator})
    row.update(initiating_actor_subject=creator.key, responsible_actor_subject=creator.key)
    connection = Mock()
    app.store._write.side_effect = lambda user: nullcontext((connection, registry.workspace, NOW))
    command = ResponsibilityCommand(client_request_key=uuid4(), expected_revision=1)
    grant = dict(id=uuid4(), authorization_revision=uuid4(), display_name="Claimant")
    evidence = ResponsibilityEvidence(
        client_request_key=command.client_request_key,
        request_hash=canonical_hash(command.model_dump(mode="json")),
        before_subject=creator.key,
        before_name="Creator",
        after_actor=actor.actor,
        administrator_id=grant["id"],
        authorization_revision=grant["authorization_revision"],
        intent_event_id=row["current_intent_event_id"],
        intent_hash=canonical_hash(frozen.model_dump(mode="json")),
        expected_revision=1,
        operation_revision=2,
    )
    audit = dict(
        data=evidence.model_dump(mode="json"),
        data_hash=canonical_hash(evidence.model_dump(mode="json")),
        actor_subject=actor.actor.key,
        actor_snapshot=actor.actor.model_dump(mode="json"),
        at=NOW,
    )
    return SimpleNamespace(
        app=app,
        row=row,
        frozen=frozen,
        actor=actor,
        connection=connection,
        command=command,
        grant=grant,
        evidence=evidence,
        audit=audit,
        creator=creator,
    )


# Eligible capability is intentionally limited to human-waiting guided create/import operations.
@pytest.mark.parametrize(
    "state,allowed",
    [
        ("waiting", True),
        ("needs_attention", True),
        ("queued", False),
        ("running", False),
        ("succeeded", False),
        ("cancelled", False),
        ("failed", False),
    ],
)
def test_eligibility(responsibility_case, state, allowed):
    c = responsibility_case
    assert eligible({**c.row, "state": state}, c.frozen.intent) == allowed
    assert not eligible(c.row, c.frozen.intent.model_copy(update={"onboarding_version": None}))


# Latest takeover binds exact intent/subject/revision and does not silently revive an old grant.
def test_authority_and_integrity(responsibility_case):
    c = responsibility_case
    with patch("otm.operations.responsibility.latest_claim", return_value=None):
        assert execution_authority(c.connection, c.row, c.frozen)[2] == c.creator
        with pytest.raises(ValueError):
            execution_authority(
                c.connection, {**c.row, "responsible_actor_subject": c.actor.actor.key}, c.frozen
            )
    new = {**c.row, "responsible_actor_subject": c.actor.actor.key, "revision": 2}
    with patch("otm.operations.responsibility.latest_claim", return_value=c.audit):
        assert execution_authority(c.connection, new, c.frozen) == (
            c.grant["id"],
            c.grant["authorization_revision"],
            c.actor.actor,
        )
        for field, value in [
            ("revision", 1),
            ("current_intent_event_id", uuid4()),
            ("responsible_actor_subject", c.creator.key),
        ]:
            with pytest.raises(ValueError):
                execution_authority(c.connection, {**new, field: value}, c.frozen)
    assert decode_evidence(c.audit) == c.evidence
    for field, value in [
        ("data_hash", "a" * 64),
        ("actor_subject", "foreign"),
        ("actor_snapshot", {}),
    ]:
        with pytest.raises(ValueError):
            decode_evidence({**c.audit, field: value})
    with pytest.raises(ValueError):
        ResponsibilityEvidence.model_validate({**c.evidence.model_dump(), "operation_revision": 5})
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.audit
    assert latest_claim(c.connection, c.row) == c.audit


# Claim uses locked live scope, changes only responsibility/revision/time, and queues no
# provider work.
def test_claim_and_replay(responsibility_case):
    c = responsibility_case
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [c.row, None]
    c.connection.execute.return_value.mappings.return_value.one.return_value = c.grant
    with (
        patch("otm.operations.responsibility.load_intent", return_value=c.frozen),
        patch(
            "otm.operations.responsibility.execution_authority",
            return_value=(uuid4(), uuid4(), c.creator),
        ),
    ):
        result = take_responsibility(c.app, c.actor, c.row["id"], c.command)
    assert result.state == "waiting"
    writes = [
        call.args[0]
        for call in c.connection.execute.call_args_list
        if getattr(call.args[0], "is_update", False)
    ]
    assert set(writes[0].compile().params) == {
        "responsible_actor_subject",
        "revision",
        "updated_at",
        "workspace_id_1",
        "id_1",
    }
    c.app.enqueuer.enqueue.assert_not_called()
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        {**c.row, "revision": 4},
        c.audit,
    ]
    assert take_responsibility(c.app, c.actor, c.row["id"], c.command).accepted_at == NOW
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        c.row,
        c.audit,
    ]
    with pytest.raises(RequestConflict):
        take_responsibility(
            c.app, c.actor, c.row["id"], c.command.model_copy(update={"expected_revision": 2})
        )


# Foreign IDs, stale previews, self-claim and paused policy fail before any assignment update.
@pytest.mark.parametrize("condition", ["absent", "stale", "own", "queued", "unsupported", "paused"])
def test_claim_guards(responsibility_case, condition):
    c = responsibility_case
    row = dict(c.row)
    if condition == "absent":
        row = None
    if condition == "stale":
        row["revision"] = 3
    if condition == "own":
        row["responsible_actor_subject"] = c.actor.actor.key
    if condition == "queued":
        row["state"] = "queued"
    if condition == "unsupported":
        row["kind"] = "configuration_check"
    if condition == "paused":
        c.app.policy_loader = Mock(
            return_value=SimpleNamespace(policy=c.app.policy, execution_paused=True)
        )
    c.connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [row, None]
    with patch("otm.operations.responsibility.load_intent", return_value=c.frozen):
        with pytest.raises(OrganizationConflict):
            take_responsibility(c.app, c.actor, c.row["id"], c.command)
    assert not any(
        getattr(call.args[0], "is_update", False) for call in c.connection.execute.call_args_list
    )
