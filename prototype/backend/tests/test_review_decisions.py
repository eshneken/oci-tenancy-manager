"""Pure review decisions; PostgreSQL tests retain persistence and identity-rewrite coverage."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from conftest import NOW, example_config
from otm.organization import review_workflow
from otm.organization.contracts import IdentityMerge, PersonState, ReviewDecision
from otm.organization.review_rules import canonical_email, issue_basis, suppressed
from otm.organization.review_workflow import ReviewWorkflow, allowed_actions
from otm.organization.store import PublicationConflict


# Build a stable, synthetic reporting subject with overridable episode/effective facts.
def employee(**changes):
    return PersonState(
        id=uuid4(),
        email="person@example.test",
        full_name="Example Person",
        profile="employee",
        manager_email="one@example.test",
        ancestry="resolved",
        lob_id="one",
        accountable_leader_email="one@example.test",
        **changes,
    )


# Record a real frozen administrator decision without invoking a persistence implementation.
def closure(person, kind, *, disposition="resolved", basis=None):
    return ReviewDecision(
        kind=kind,
        target=person.email,
        disposition=disposition,
        basis=basis,
        recorded_at=NOW,
        actor="local:admin",
        reason="Verified review decision",
        person_id=person.id,
    )


# Offer business actions instead of generic resolve for tenancy onboarding/offboarding.
@pytest.mark.parametrize(
    "kind,evidence,expected",
    [
        (
            "TENANCY_SETUP_REVIEW",
            None,
            {
                "create_tenancy",
                "import_tenancy",
                "shared_membership",
                "no_tenancy_required",
                "merge",
            },
        ),
        ("PERSON_ABSENCE_REVIEW", "feed_row", {"offboard_person", "merge", "keep_returned"}),
        ("PERSON_ABSENCE_REVIEW", "prior_only", {"offboard_person", "merge"}),
        ("LOB_MAPPING_REVIEW", None, {"resolve", "ignore"}),
        ("DESIGNEE_INVALID", None, {"resolve"}),
    ],
)
def test_review_actions_distinguish_onboarding_absence_and_permanent_exemption(
    kind, evidence, expected
):
    assert set(allowed_actions(kind, evidence)) == expected


# Repeated missing snapshots stay settled, while a new departure requires another review.
def test_resolved_absence_suppresses_only_the_same_episode():
    person = employee(absence_review=True, absence_review_since=NOW)
    decision = closure(person, "PERSON_ABSENCE_REVIEW", basis=NOW.isoformat())
    config = example_config().model_copy(update={"review_decisions": (decision,)})
    assert suppressed(config, decision.kind, person.email, (person,))
    later = person.model_copy(update={"absence_review_since": NOW + timedelta(days=7)})
    assert not suppressed(config, decision.kind, person.email, (later,))
    assert issue_basis(decision.kind, person.email, ()) is None
    assert issue_basis(decision.kind, person.email, (employee(),)) == "legacy"


# Distinguish conditional dismissal from durable exemption after reporting changes.
@pytest.mark.parametrize("disposition", ["resolved", "ignored"])
def test_lob_resolution_reopens_on_changed_facts_but_ignore_remains_permanent(disposition):
    person = employee()
    decision = closure(
        person,
        "LOB_MAPPING_REVIEW",
        disposition=disposition,
        basis=issue_basis("LOB_MAPPING_REVIEW", person.email, (person,)),
    )
    config = example_config().model_copy(update={"review_decisions": (decision,)})
    assert suppressed(config, decision.kind, person.email, (person,))
    changed = person.model_copy(update={"manager_email": "two@example.test", "lob_id": "two"})
    assert suppressed(config, decision.kind, person.email, (changed,)) is (disposition == "ignored")


# Directory exclusion suppresses personal onboarding/absence issues, not designee integrity.
@pytest.mark.parametrize(
    "kind", ["PERSON_ABSENCE_REVIEW", "LOB_MAPPING_REVIEW", "DESIGNEE_INVALID"]
)
def test_managed_exclusion_does_not_hide_unrelated_configuration_issues(kind):
    person = employee()
    config = example_config().model_copy(update={"managed_exclusions": (person.id,)})
    assert suppressed(config, kind, person.email, (person,)) is (kind != "DESIGNEE_INVALID")


# A source correction reopens a dismissed conflict; a harmless display rename does not.
def test_conflict_basis_tracks_source_and_effective_values_not_display_name():
    person = employee(source_values={"manager_email": "two@example.test"})
    target = person.email + ":manager_email"
    before = issue_basis("OVERRIDE_CONFLICT", target, (person,))
    renamed = person.model_copy(update={"full_name": "Changed Display Name"})
    corrected = person.model_copy(update={"source_values": {"manager_email": "three@example.test"}})
    assert issue_basis("OVERRIDE_CONFLICT", target, (renamed,)) == before
    assert issue_basis("OVERRIDE_CONFLICT", target, (corrected,)) != before


# Email changes require explicit mappings; alias cycles cannot silently choose an identity.
def test_explicit_email_aliases_follow_chains_and_reject_cycles():
    first, second, third = "old@example.test", "middle@example.test", "current@example.test"
    one = IdentityMerge(
        old_email=first,
        new_email=second,
        person_id=uuid4(),
        retired_person_id=uuid4(),
        actor="local:admin",
        reason="Verified rename",
    )
    two = one.model_copy(update={"old_email": second, "new_email": third})
    config = example_config().model_copy(update={"identity_merges": (one, two)})
    assert canonical_email(config, first) == third
    assert canonical_email(config, "unrelated@example.test") == "unrelated@example.test"
    cyclic = config.model_copy(
        update={"identity_merges": (one, two.model_copy(update={"new_email": first}))}
    )
    with pytest.raises(ValueError, match="alias cycle"):
        canonical_email(cyclic, first)


# Isolate command policy from case queries and persistence, keeping real review decisions.
@pytest.fixture
def review(monkeypatch):
    person = employee()
    config = example_config()
    context = {
        "workspace_id": "unit-org",
        "applied_version_id": str(uuid4()),
        "configuration_id": str(config.id),
        "proposal_status": "already_applied",
    }
    context["proposed_version_id"] = context["applied_version_id"]
    case = {
        "id": "lob-review",
        "kind": "LOB_MAPPING_REVIEW",
        "category": "actionable",
        "email": person.email,
        "target": person.email,
        "person_id": str(person.id),
        "actions": ["resolve", "ignore"],
    }
    store = SimpleNamespace(
        workspace_context=Mock(return_value=dict(context)),
        head=Mock(return_value=SimpleNamespace(people=(person,))),
        configuration=Mock(return_value=config),
        update_configuration=Mock(
            return_value=SimpleNamespace(model_dump=Mock(return_value={"state": "published"}))
        ),
    )
    cases = Mock(return_value=[case])
    monkeypatch.setattr(review_workflow, "open_reviews", cases)
    registry_operation = Mock(return_value={"resolved": True, "oci_performed": False})
    monkeypatch.setattr(review_workflow.TenancyRegistry, "operate", registry_operation)
    return SimpleNamespace(
        person=person,
        config=config,
        context=context,
        case=case,
        store=store,
        workflow=ReviewWorkflow(store, "unit-org"),
        cases=cases,
        registry_operation=registry_operation,
    )


# All confirmation fields prevent a stale or cross-workspace review from taking effect.
@pytest.mark.parametrize(
    "field", ["workspace_id", "applied_version_id", "proposed_version_id", "configuration_id"]
)
def test_stale_review_tokens_fail_before_case_lookup(review, field):
    expected = dict(review.context)
    expected[field] = str(uuid4())
    with pytest.raises(PublicationConflict, match="context changed"):
        review.workflow.operate(review.case["id"], "resolve", expected)
    review.cases.assert_not_called()
    review.store.update_configuration.assert_not_called()


# Server-side case/category/action checks do not trust a previously rendered button.
@pytest.mark.parametrize("fault", ["missing", "informational", "unavailable_action"])
def test_closed_informational_or_unavailable_actions_cannot_change_configuration(review, fault):
    if fault == "missing":
        review.cases.return_value = []
    elif fault == "informational":
        review.case["category"] = "informational"
    else:
        review.case["actions"] = ["ignore"]
    with pytest.raises(ValueError, match="no longer available"):
        review.workflow.operate(review.case["id"], "resolve", review.context)
    review.store.update_configuration.assert_not_called()
    review.registry_operation.assert_not_called()


# Resolve fingerprints current facts; ignore records an unconditional exemption.
@pytest.mark.parametrize("operation", ["resolve", "ignore"])
def test_lob_decision_records_scope_without_changing_source_identity(review, operation):
    result = review.workflow.operate(review.case["id"], operation, review.context)
    assert result["resolved"] and not result["simulated"] and result["oci_performed"] is False
    updated = review.store.update_configuration.call_args.args[0]
    decision = updated.review_decisions[-1]
    assert decision.disposition == ("ignored" if operation == "ignore" else "resolved")
    assert (decision.basis is None) is (operation == "ignore")
    assert updated.identity_merges == () and updated.excluded_emails == ()
    assert decision.person_id == review.person.id


# A review command cannot silently promote different staged source data.
def test_unapplied_proposal_cannot_be_published_by_resolving_a_review(review):
    review.store.workspace_context.return_value["proposal_status"] = "pending"
    with pytest.raises(ValueError, match="pending organization proposal"):
        review.workflow.operate(review.case["id"], "resolve", review.context)
    review.store.update_configuration.assert_not_called()


# Onboarding uses the shared registry safeguards rather than a second mutation path.
@pytest.mark.parametrize(
    "operation", ["create_tenancy", "import_tenancy", "shared_membership", "no_tenancy_required"]
)
def test_onboarding_reviews_delegate_once_to_association_coordinator(review, operation):
    review.case.update(kind="TENANCY_SETUP_REVIEW", actions=allowed_actions("TENANCY_SETUP_REVIEW"))
    target = uuid4()
    review.workflow.operate(
        review.case["id"],
        operation,
        review.context,
        tenancy_id=target,
        name="Requested sandbox",
        kind="shared",
    )
    review.registry_operation.assert_called_once()
    command = review.registry_operation.call_args.args[0]
    assert command["operation"] == (
        "join_shared" if operation == "shared_membership" else operation
    )
    assert command["person_id"] == str(review.person.id) and command["tenancy_id"] == str(target)
    assert command["context"] == review.context
    review.store.update_configuration.assert_not_called()


# Reject missing, self or unknown partners rather than guessing identity from names.
@pytest.mark.parametrize("partner", [None, "person@example.test", "unknown@example.test"])
def test_merge_requires_distinct_absent_and_unresolved_new_identities(review, partner):
    review.case.update(kind="TENANCY_SETUP_REVIEW", actions=["merge"])
    with pytest.raises(ValueError, match="absent employee and an unresolved new employee"):
        review.workflow.operate(review.case["id"], "merge", review.context, partner_email=partner)
    review.store.update_configuration.assert_not_called()
