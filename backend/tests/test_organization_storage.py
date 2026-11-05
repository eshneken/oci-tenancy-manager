"""Organization repository scope, evidence reconstruction and publication guards."""

import json
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW, envelope, example_config, example_records
from test_sessions import session_case

from otm.auth.service import AdminPrincipal, SessionFailure
from otm.operations.contracts import canonical_hash
from otm.organization.contracts import IdentityMerge, Intake, Revision
from otm.organization.reconcile import prepare
from otm.storage.organization import (
    OrganizationConflict,
    SqlOrganizationStore,
    member_values,
    outcome,
)

__all__ = ["session_case"]


# Build source-bound immutable evidence independently of any persistence or local runtime state.
def source_case():
    config = example_config()
    source = Intake(envelope=envelope(), records=example_records())
    candidate = prepare(source.records, source.envelope, config, None, NOW)
    revision = Revision(
        id=uuid4(),
        predecessor_id=None,
        configuration_id=config.id,
        snapshot_id=uuid4(),
        population_id=config.policy.population_id,
        published_at=NOW,
        source_captured_at=NOW,
        declared_completeness="complete",
        assessed_coverage="complete",
        absence_eligible=True,
        people=candidate.people,
    )
    feed = dict(
        id=revision.snapshot_id,
        source_id=source.envelope.source_id,
        population_id=source.envelope.population_id,
        external_id=source.envelope.external_snapshot_id,
        captured_at=source.envelope.captured_at,
        data=source.model_dump(mode="json"),
        digest=canonical_hash(source.model_dump(mode="json")),
        state="received",
        diagnostics=[],
        proposed_version_id=None,
        applied_version_id=None,
    )
    state = dict(
        configuration=config.model_dump(mode="json"),
        configuration_id=config.id,
        applied_version_id=None,
        proposed_version_id=None,
    )
    return SimpleNamespace(
        config=config, source=source, candidate=candidate, revision=revision, feed=feed, state=state
    )


# A private connection double supports transaction/error assertions; real SQL semantics have PG
# tests.
def store_case(session_case):
    connection = MagicMock()
    engine = Mock()
    engine.begin.return_value = nullcontext(connection)
    sessions = Mock()
    principal = AdminPrincipal(session_case.session)
    return SqlOrganizationStore(engine, sessions, Mock(return_value=NOW)), connection, principal


# Outcomes remain typed and readable; projection construction never discards retained person
# evidence.
def test_member_projection_and_outcome_contract():
    c = source_case()
    identities = {p.email: p.id for p in c.revision.people}
    for person in c.revision.people:
        row = member_values(person, identities, {person.email})
        assert row["data"] == person.model_dump(mode="json") and row["person_id"] == person.id
        assert row["evidence"] == "feed_row"
    p = c.revision.people[-1]
    assert member_values(p, identities, set())["evidence"] == "retained"
    ref = p.model_copy(update={"profile": "reference"})
    assert member_values(ref, identities, set())["evidence"] == "reference"
    assert outcome(c.feed).state == "received"
    assert outcome(c.feed, duplicate=True).original_state == "received"


# Scope always comes from the principal and the in-transaction authority check cannot be omitted.
def test_writer_authorization_and_workspace_lock(session_case):
    store, connection, principal = store_case(session_case)
    with pytest.raises(SessionFailure):
        store._principal(object())
    with (
        patch("otm.storage.organization.authorize_administrator") as authorize,
        patch("otm.storage.organization.require_transaction") as transaction,
    ):
        with store._write(principal) as (conn, scope, at):
            assert conn is connection and scope == principal.session.workspace_id and at == NOW
        authorize.assert_called_once_with(connection, principal, store.clock)
        transaction.assert_called_once_with(connection)
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        "id": "scoped"
    }
    assert store._workspace(connection, "scoped", lock=True) == {"id": "scoped"}
    assert "FOR UPDATE" in str(connection.execute.call_args.args[0])
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    with pytest.raises(OrganizationConflict):
        store._workspace(connection, "missing")


# Initialization is idempotent only for identical configuration and never overwrites a seeded org.
@pytest.mark.parametrize("mode", ["new", "replay", "changed", "oversized"])
def test_configuration_initialization_boundary(session_case, mode):
    store, connection, principal = store_case(session_case)
    c = source_case()
    connection.execute.return_value.scalar_one_or_none.return_value = (
        "scope" if mode == "new" else None
    )
    row = dict(configuration=c.config.model_dump(mode="json"))
    if mode == "changed":
        row["configuration"] = {}
    config = c.config
    if mode == "oversized":
        config = c.config.model_copy(
            update={"excluded_emails": tuple(f"user{i}@example.test" for i in range(4000))}
        )
    with (
        patch.object(store, "_write", return_value=nullcontext((connection, "scope", NOW))),
        patch.object(store, "_workspace", return_value=row),
        patch.object(store, "_audit") as audit,
    ):
        if mode in {"changed", "oversized"}:
            with pytest.raises(ValueError):
                store.configure_initial(principal, config)
        else:
            store.configure_initial(principal, config)
            assert audit.called == (mode == "new")


# Safe audit evidence correlates versions/source without copying configuration or source rows.
def test_redacted_organization_audit(session_case):
    store, connection, principal = store_case(session_case)
    c = source_case()
    store._audit(
        connection,
        "scope",
        principal.actor,
        "organization_feed_received",
        NOW,
        c.config,
        feed_id=c.feed["id"],
    )
    values = connection.execute.call_args.args[0].compile().params
    assert values["administrator_id"] is None and values["operation_id"] is None
    assert values["data_hash"] == canonical_hash(values["data"])
    assert "root@example.test" not in json.dumps(values["data"])


# Closed revision loading rejects absent/unsealed, incomplete, inconsistent member or header
# evidence.
@pytest.mark.parametrize(
    "damage",
    ["none", "missing", "count", "member", "header", "evidence", "population", "feed_scope"],
)
def test_revision_reconstruction_guards(session_case, damage):
    store, connection, principal = store_case(session_case)
    c = source_case()
    people = sorted(c.revision.people, key=lambda p: p.email)
    ids = {p.email: p.id for p in people}
    row = dict(
        id=c.revision.id,
        configuration_id=c.config.id,
        feed_id=c.feed["id"],
        base_version_id=None,
        member_count=len(people),
        data=c.revision.model_dump(mode="json", exclude={"people"}),
        configuration=c.config.model_dump(mode="json"),
    )
    members = [member_values(p, ids, {p.email}) for p in people]
    if damage == "count":
        row["member_count"] += 1
    if damage == "member":
        members[0]["full_name"] = "forged"
    if damage == "header":
        row["id"] = uuid4()
    if damage == "evidence":
        members[0]["evidence"] = "retained"
    if damage == "population":
        row["data"]["population_id"] = "forged-population"
    if damage == "feed_scope":
        c.feed["external_id"] = "forged-delivery"
    one = MagicMock()
    one.mappings.return_value.one_or_none.return_value = None if damage == "missing" else row
    many = MagicMock()
    many.mappings.return_value.all.return_value = members
    receipt = MagicMock()
    receipt.mappings.return_value.one.return_value = c.feed
    connection.execute.side_effect = [one, receipt, many]
    if damage != "none":
        with pytest.raises(ValueError):
            store._revision(connection, "scope", c.revision.id)
    else:
        assert store._revision(connection, "scope", c.revision.id).id == c.revision.id


# Head access rechecks authority and only reads the selected current pointer within one snapshot.
@pytest.mark.parametrize("proposed,exists", [(False, False), (False, True), (True, True)])
def test_head_snapshot_scope(session_case, proposed, exists):
    store, connection, principal = store_case(session_case)
    c = source_case()
    state = dict(
        applied_version_id=c.revision.id if exists else None, proposed_version_id=c.revision.id
    )
    with (
        patch("otm.storage.organization.read_snapshot", return_value=nullcontext(connection)),
        patch.object(store, "_workspace", return_value=state),
        patch.object(store, "_revision", return_value=c.revision) as read,
    ):
        result = store.head(principal, proposed=proposed)
        assert (result is not None) == exists
        if exists:
            read.assert_called_once_with(connection, principal.session.workspace_id, c.revision.id)


# Scoped person IDs are reused between proposal and application and sealing follows every member
# insert.
@pytest.mark.parametrize("existing,invalid_merge", [(False, False), (True, False), (False, True)])
def test_version_persistence_stable_identity_and_merge_scope(session_case, existing, invalid_merge):
    store, connection, principal = store_case(session_case)
    c = source_case()
    rows = [dict(id=p.id, email=p.email) for p in c.candidate.people] if existing else []
    connection.execute.return_value.mappings.return_value.all.return_value = rows
    config = c.config
    if invalid_merge:
        config = config.model_copy(
            update={
                "identity_merges": (
                    IdentityMerge(
                        old_email="old@example.test",
                        new_email="new@example.test",
                        person_id=uuid4(),
                        retired_person_id=uuid4(),
                        actor="reviewed",
                        reason="verified",
                    ),
                )
            }
        )
        with pytest.raises(OrganizationConflict):
            store._persist(connection, "scope", c.feed, config, c.candidate, "proposed")
    else:
        result = store._persist(connection, "scope", c.feed, config, c.candidate, "proposed")
        assert result.population_id == config.policy.population_id and len(result.people) == len(
            c.candidate.people
        )
        assert connection.execute.call_args.args[0].compile().params["sealed"] is True
        if existing:
            assert {p.id for p in result.people} == {p.id for p in c.candidate.people}


# Staging validates immutable source plus raw/effective graphs before moving any visible pointer.
@pytest.mark.parametrize("mode", ["valid", "hash", "cycle", "superseded"])
def test_source_bound_staging(session_case, mode):
    store, connection, principal = store_case(session_case)
    c = source_case()
    if mode == "hash":
        c.feed["digest"] = "0" * 64
    if mode == "cycle":
        source = c.source.model_copy(
            update={
                "records": tuple(
                    r.model_copy(update={"manager_email": r.email})
                    if r.email == "engineer@example.test"
                    else r
                    for r in c.source.records
                )
            }
        )
        c.feed.update(
            data=source.model_dump(mode="json"),
            digest=canonical_hash(source.model_dump(mode="json")),
        )
    if mode == "superseded":
        c.state["proposed_version_id"] = c.revision.id
    with (
        patch.object(store, "_revision", return_value=c.revision),
        patch.object(store, "_persist", return_value=c.revision) as persist,
        patch.object(store, "_audit") as audit,
    ):
        if mode == "hash":
            with pytest.raises(ValueError):
                store._stage(connection, "scope", c.feed, c.config, c.state, NOW)
        else:
            store._stage(connection, "scope", c.feed, c.config, c.state, NOW)
            assert persist.called == (mode == "valid")
            if mode != "valid":
                assert audit.call_args.args[3] == "organization_feed_rejected"


# Apply never accepts arbitrary/stale candidates and recomputes from the exact persisted feed.
@pytest.mark.parametrize("mode", ["valid", "cas", "clock", "hash", "stale"])
def test_exact_proposal_application(session_case, mode):
    store, connection, principal = store_case(session_case)
    c = source_case()
    c.state["proposed_version_id"] = c.revision.id
    connection.execute.return_value.mappings.return_value.one.return_value = c.feed
    if mode == "cas":
        c.state["proposed_version_id"] = uuid4()
    if mode == "hash":
        c.feed["digest"] = "0" * 64
    at = (
        NOW - timedelta(seconds=1)
        if mode == "clock"
        else NOW + timedelta(days=2)
        if mode == "stale"
        else NOW
    )
    with (
        patch.object(store, "_revision", return_value=c.revision),
        patch.object(store, "_persist", return_value=c.revision) as persist,
        patch.object(store, "_audit"),
        patch("otm.organization.reviews.reconcile_reviews"),
    ):
        if mode != "valid":
            with pytest.raises(ValueError):
                store._apply(connection, "scope", c.revision.id, c.state, c.config, at)
        else:
            store._apply(connection, "scope", c.revision.id, c.state, c.config, at)
            persist.assert_called_once()


# Invalid envelopes and changed delivery reuse fail before staging or publishing a different graph.
@pytest.mark.parametrize(
    "mode", ["new", "staged", "duplicate", "changed", "raw", "scope", "length", "empty"]
)
def test_ingest_input_and_replay_boundaries(session_case, mode):
    store, connection, principal = store_case(session_case)
    c = source_case()
    source = c.source
    raw_digest = None
    if mode == "raw":
        raw_digest = "not-a-digest"
    if mode == "scope":
        source = source.model_copy(
            update={
                "envelope": source.envelope.model_copy(
                    update={"population_id": "another-population"}
                )
            }
        )
    if mode == "length":
        source = source.model_copy(
            update={
                "envelope": source.envelope.model_copy(update={"external_snapshot_id": "x" * 513})
            }
        )
    if mode == "empty":
        source = source.model_copy(update={"records": ()})
    prior = {**c.feed, "state": "published"} if mode in {"duplicate", "changed"} else None
    if prior:
        prior["raw_digest"] = None
    if mode == "changed":
        prior["digest"] = "0" * 64
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = prior
    connection.execute.return_value.mappings.return_value.one.return_value = {
        **c.feed,
        "state": "staged" if mode == "staged" else "published",
    }
    with (
        patch.object(store, "_write", return_value=nullcontext((connection, "scope", NOW))),
        patch.object(store, "_workspace", return_value=c.state),
        patch.object(store, "_stage") as stage,
        patch.object(store, "_apply"),
        patch.object(store, "_audit"),
    ):
        if mode in {"changed", "raw", "scope", "length", "empty"}:
            with pytest.raises(ValueError):
                store.ingest(principal, source, raw_digest=raw_digest)
            stage.assert_not_called()
        else:
            result = store.ingest(principal, source, stage_only=mode == "staged")
            assert result.state == (
                "duplicate"
                if mode == "duplicate"
                else "staged"
                if mode == "staged"
                else "published"
            )


# Known applied proposals return their original receipt rather than publishing them a second time.
@pytest.mark.parametrize("duplicate", [False, True])
def test_apply_public_entry_replay(session_case, duplicate):
    store, connection, principal = store_case(session_case)
    c = source_case()
    c.feed["state"] = "published"
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = (
        c.feed if duplicate else None
    )
    connection.execute.return_value.mappings.return_value.one.return_value = c.feed
    with (
        patch.object(store, "_write", return_value=nullcontext((connection, "scope", NOW))),
        patch.object(store, "_workspace", return_value=c.state),
        patch.object(store, "_apply") as apply,
    ):
        result = store.apply(principal, uuid4())
        assert result.state == ("duplicate" if duplicate else "published")
        assert apply.called != duplicate


# New organization events expose only safe labels; computation cannot be misattributed to a human.
@pytest.mark.parametrize(
    "kind",
    [
        "organization_configured",
        "organization_feed_received",
        "organization_feed_rejected",
        "organization_published",
    ],
)
def test_organization_audit_public_projection(kind):
    from test_audit_history import event

    from otm.organization.persistence_contracts import (
        ORGANIZATION_SERVICE_ACTOR,
        OrganizationEvidence,
    )
    from otm.storage.audit_directory import entry

    c = source_case()
    row = event()
    row.update(kind=kind, administrator_id=None)
    data = OrganizationEvidence(
        source_id=c.config.policy.source_id,
        population_id=c.config.policy.population_id,
        configuration_id=c.config.id,
        feed_id=uuid4(),
    ).model_dump(mode="json")
    row.update(data=data, data_hash=canonical_hash(data))
    if kind in {"organization_feed_rejected", "organization_published"}:
        row.update(
            actor_snapshot=ORGANIZATION_SERVICE_ACTOR.model_dump(mode="json"),
            actor_subject=ORGANIZATION_SERVICE_ACTOR.key,
        )
    projected = entry(row)
    assert projected.category == "organization" and set(projected.model_dump()) == {
        "id",
        "at",
        "kind",
        "category",
        "actor_name",
        "operation_id",
        "administrator_id",
        "administrator_name",
        "safe_code",
        "organization_subject_name",
        "resources",
        "baseline_id",
        "summary",
        "changes",
    }
    assert "source_id" not in projected.model_dump_json()
    row["data"] = {**data, "unexpected": "private"}
    row["data_hash"] = canonical_hash(row["data"])
    with pytest.raises(ValueError):
        entry(row)
    if kind == "organization_published":
        row.update(data=data, data_hash=canonical_hash(data))
        human = event()
        row.update(actor_snapshot=human["actor_snapshot"], actor_subject=human["actor_subject"])
        with pytest.raises(ValueError):
            entry(row)
