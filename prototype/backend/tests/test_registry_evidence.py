"""In-memory legacy replay and absence/return evidence decisions, without executing SQL."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from conftest import NOW, example_config
from otm.organization.associations import TenancyRegistry
from otm.organization.contracts import PersonState, ReviewDecision
from otm.organization.schema import schema_tables


# Create an explicit simulated legacy outcome, with optional qualified absence evidence.
def decision(person, operation, *, at=NOW, basis=None):
    return ReviewDecision(
        kind="PERSON_ABSENCE_REVIEW" if basis else "TENANCY_SETUP_REVIEW",
        target="person@example.test",
        disposition="resolved",
        person_id=person,
        recorded_at=at,
        actor="local:admin",
        reason="Synthetic evidence scenario",
        operation=operation,
        simulation="succeeded",
        basis=basis,
    )


# Return no persisted rows while allowing real query construction against table metadata.
def empty_rows():
    return SimpleNamespace(mappings=Mock(return_value=[]))


# Repeated state projection derives identical IDs and retains unknown shared ownership.
@pytest.mark.parametrize(
    "operation,kind,role",
    [
        ("create_tenancy", "individual", "owner"),
        ("import_tenancy", "individual", "owner"),
        ("shared_membership", "shared", "member"),
    ],
)
def test_legacy_replay_is_deterministic_and_preserves_shared_uncertainty(operation, kind, role):
    person = uuid4()
    config = example_config().model_copy(
        update={"review_decisions": (decision(person, operation),)}
    )
    _, tables = schema_tables("otm_unit")
    registry = TenancyRegistry(SimpleNamespace(tables=tables), "unit-org")
    registry._restore_feed_returns = Mock()
    connection = SimpleNamespace(execute=Mock(side_effect=lambda *_: empty_rows()))
    first, second = registry._state(connection, config), registry._state(connection, config)
    assert first == second
    assert first["tenancy"][0]["kind"] == kind
    assert first["association"][0]["role"] == role
    assert first["association"][0]["tenancy_id"] == first["tenancy"][0]["id"]
    assert bool(first["warnings"]) is (kind == "shared")


# Ambiguous historical deletions preserve access for review instead of guessing a target.
@pytest.mark.parametrize("owned_count", [0, 1, 2])
def test_legacy_delete_requires_unique_owned_tenancy(owned_count):
    person = uuid4()
    decisions = tuple(decision(person, "create_tenancy") for _ in range(owned_count)) + (
        decision(person, "delete_tenancy", at=NOW + timedelta(hours=1)),
    )
    config = example_config().model_copy(update={"review_decisions": decisions})
    registry = TenancyRegistry(SimpleNamespace(tables=schema_tables("otm_unit")[1]), "unit-org")
    registry._restore_feed_returns = Mock()
    connection = SimpleNamespace(execute=Mock(side_effect=lambda *_: empty_rows()))
    state = registry._state(connection, config)
    if owned_count == 1:
        assert state["tenancy"][0]["status"] == "deleted"
        assert state["association"][0]["status"] == "removed"
        assert str(person) in state["hidden"] and not state["warnings"]
    else:
        assert len(state["warnings"]) == 1
        assert all(row["status"] == "active" for row in state["association"])
        assert str(person) not in state["hidden"]


# Keep retains outside accountability; no-tenancy opts out of management.
@pytest.mark.parametrize("operation", ["keep_tenancy", "no_tenancy_required"])
def test_legacy_keep_and_no_tenancy_decisions_retain_distinct_meanings(operation):
    person = uuid4()
    config = example_config().model_copy(
        update={"review_decisions": (decision(person, operation),)}
    )
    registry = TenancyRegistry(SimpleNamespace(tables=schema_tables("otm_unit")[1]), "unit-org")
    registry._restore_feed_returns = Mock()
    state = registry._state(
        SimpleNamespace(execute=Mock(side_effect=lambda *_: empty_rows())), config
    )
    assert (str(person) in state["outside"]) is (operation == "keep_tenancy")
    assert (str(person) in state["hidden"]) is (operation == "no_tenancy_required")


# Provide fetched evidence; database query scoping remains integration-tested.
@pytest.fixture
def returning():
    person = str(uuid4())
    ending = decision(person, "offboard_person")
    config = example_config().model_copy(update={"review_decisions": (ending,)})
    state = {"hidden": {person}, "outside": {person}, "pending": set(), "association": []}
    profile = PersonState(
        id=person, email="person@example.test", full_name="Example Person", profile="employee"
    )
    head = SimpleNamespace(people=(profile,), published_at=NOW + timedelta(days=10))
    store = SimpleNamespace(
        tables=schema_tables("otm_unit")[1],
        _workspace=Mock(return_value={"applied_version_id": str(uuid4())}),
        _revision=Mock(return_value=head),
    )
    connection = SimpleNamespace(
        execute=Mock(return_value=SimpleNamespace(all=Mock(return_value=[])))
    )
    return SimpleNamespace(
        person=person,
        config=config,
        state=state,
        head=head,
        store=store,
        connection=connection,
        registry=TenancyRegistry(store, "unit-org"),
    )


# Arrange a fetched evidence row with independent publication time and census qualification.
def evidence(case, day, presence, since=None, *, qualified=True):
    return (
        case.person,
        {"published_at": (NOW + timedelta(days=day)).isoformat(), "absence_eligible": qualified},
        presence,
        since,
    )


# Run the actual absence/return decision over fetched evidence and expose only state output.
def restore(case, rows):
    case.connection.execute.return_value.all.return_value = rows
    case.registry._restore_feed_returns(case.connection, case.config, case.state)
    return case.state


# Replay evidence by publication time rather than trusting database or upload ordering.
def test_qualified_absence_then_return_reopens_onboarding_even_if_rows_arrive_unsorted(returning):
    rows = [
        evidence(returning, 3, "feed_row"),
        evidence(returning, 2, "prior_only", NOW.isoformat()),
    ]
    result = restore(returning, rows)
    assert returning.person in result["pending"]
    assert returning.person not in result["hidden"] | result["outside"]


# Historical, partial and nonpositive snapshots cannot manufacture a qualified return.
@pytest.mark.parametrize(
    "fault",
    [
        "no_absence",
        "partial_absence",
        "partial_return",
        "before_decision",
        "after_head",
        "same_time",
    ],
)
def test_unqualified_or_out_of_window_evidence_cannot_reopen_onboarding(returning, fault):
    absent = evidence(returning, 2, "prior_only", NOW.isoformat())
    present = evidence(returning, 3, "feed_row")
    rows = [absent, present]
    if fault == "no_absence":
        rows = [present]
    elif fault == "partial_absence":
        rows[0] = evidence(returning, 2, "prior_only", NOW.isoformat(), qualified=False)
    elif fault == "partial_return":
        rows[1] = evidence(returning, 3, "feed_row", qualified=False)
    elif fault == "before_decision":
        rows = [
            evidence(returning, -2, "prior_only", NOW.isoformat()),
            evidence(returning, -1, "feed_row"),
        ]
    elif fault == "after_head":
        rows[1] = evidence(returning, 11, "feed_row")
    else:
        rows = [evidence(returning, 0, "feed_row", NOW.isoformat())]
    result = restore(returning, rows)
    assert result["hidden"] == {returning.person} and not result["pending"]


# A real episode timestamp permits return; legacy or malformed evidence must not guess.
@pytest.mark.parametrize(
    "basis,expected", [(NOW.isoformat(), True), ("legacy", False), ("invalid-date", False)]
)
def test_settled_qualified_episode_survives_without_original_absence_snapshot(
    returning, basis, expected
):
    returning.config = returning.config.model_copy(
        update={
            "review_decisions": (decision(returning.person, "delete_tenancy", basis=basis),),
        }
    )
    result = restore(returning, [evidence(returning, 2, "feed_row")])
    assert (returning.person in result["pending"]) is expected


# Only a hidden offboarded employee without access can become a fresh onboarding case.
@pytest.mark.parametrize(
    "fault",
    ["explicit_exemption", "active_link", "no_current_profile", "no_applied_version", "not_hidden"],
)
def test_reappearance_preserves_explicit_exemption_and_existing_access(returning, fault):
    if fault == "explicit_exemption":
        returning.config = returning.config.model_copy(
            update={
                "review_decisions": (decision(returning.person, "no_tenancy_required"),),
            }
        )
    elif fault == "active_link":
        returning.state["association"].append({"person_id": returning.person, "status": "active"})
    elif fault == "no_current_profile":
        returning.head.people = ()
    elif fault == "no_applied_version":
        returning.store._workspace.return_value["applied_version_id"] = None
    else:
        returning.state["hidden"].clear()
    restore(
        returning,
        [evidence(returning, 1, "prior_only", NOW.isoformat()), evidence(returning, 2, "feed_row")],
    )
    assert not returning.state["pending"]
    returning.connection.execute.assert_not_called()


# A later no-tenancy decision remains durable after a previous offboard-and-return episode.
def test_latest_explicit_exemption_wins_over_older_offboarding(returning):
    returning.config = returning.config.model_copy(
        update={
            "review_decisions": (
                decision(returning.person, "offboard_person"),
                decision(returning.person, "no_tenancy_required", at=NOW + timedelta(days=1)),
            )
        }
    )
    restore(
        returning,
        [evidence(returning, 2, "prior_only", NOW.isoformat()), evidence(returning, 3, "feed_row")],
    )
    assert returning.state["hidden"] == {returning.person} and not returning.state["pending"]


# A manager reference without an employee row cannot establish that an employee returned.
def test_reference_only_profile_does_not_qualify_for_reonboarding(returning):
    returning.head.people = tuple(
        person.model_copy(update={"profile": "reference"}) for person in returning.head.people
    )
    restore(
        returning,
        [
            evidence(returning, 1, "prior_only", NOW.isoformat()),
            evidence(returning, 2, "feed_row"),
        ],
    )
    assert not returning.state["pending"]
    returning.connection.execute.assert_not_called()


# One employee's absence and another's presence cannot combine into a false return.
def test_absence_and_return_evidence_cannot_cross_employee_identities(returning):
    other = str(uuid4())
    returning.head.people += (
        PersonState(
            id=other,
            email="other@example.test",
            full_name="Other Example",
            profile="employee",
        ),
    )
    returning.config = returning.config.model_copy(
        update={
            "review_decisions": (
                *returning.config.review_decisions,
                decision(other, "offboard_person"),
            )
        }
    )
    returning.state["hidden"].add(other)
    returning.state["outside"].add(other)
    present = evidence(returning, 2, "feed_row")
    rows = [evidence(returning, 1, "prior_only", NOW.isoformat()), (other, *present[1:])]
    result = restore(returning, rows)
    assert result["hidden"] == {returning.person, other}
    assert not result["pending"]
