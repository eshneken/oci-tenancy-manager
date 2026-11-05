"""Isolated association decisions; PostgreSQL tests separately verify SQL and atomic persistence."""

from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from conftest import NOW, example_config
from otm.organization.associations import TenancyRegistry
from otm.organization.contracts import PersonState, ReviewDecision
from otm.organization.store import PublicationConflict


# Use real domain models and registry decisions with only persistence/projection seams stubbed.
#
# Each command receives a private working copy. Failed decisions cannot alter the input fixture;
# these tests assert no save/publication/audit call, not database rollback or SQL correctness.
@pytest.fixture
def case():
    config = example_config().model_copy(update={"registry_initialized": True})
    owner, recipient = str(uuid4()), str(uuid4())
    context = {
        "workspace_id": "unit-org",
        "applied_version_id": str(uuid4()),
        "proposed_version_id": None,
        "configuration_id": str(config.id),
        "proposal_status": "already_applied",
    }
    context["proposed_version_id"] = context["applied_version_id"]
    people = {
        key: {
            "id": key,
            "name": name,
            "email": email,
            "profile": "employee",
            "managed": True,
            "source_present": True,
            "eligible_transfer": True,
        }
        for key, name, email in (
            (owner, "Example Owner", "owner@example.test"),
            (recipient, "Example Recipient", "recipient@example.test"),
        )
    }
    head = SimpleNamespace(
        people=tuple(
            PersonState(id=key, email=p["email"], full_name=p["name"], profile="employee")
            for key, p in people.items()
        )
    )
    connection = object()
    store = SimpleNamespace(
        engine=SimpleNamespace(
            begin=Mock(return_value=nullcontext(connection)),
            connect=Mock(return_value=nullcontext(connection)),
        ),
        _workspace=Mock(return_value=dict(context)),
        workspace_context=Mock(return_value=dict(context)),
        configuration=Mock(return_value=config),
        head=Mock(return_value=head),
        update_configuration=Mock(
            return_value=SimpleNamespace(model_dump=Mock(return_value={"state": "published"}))
        ),
        _audit=Mock(),
    )
    state = {
        "tenancy": [],
        "association": [],
        "hidden": set(),
        "outside": set(),
        "pending": {owner},
        "warnings": [],
    }
    registry = TenancyRegistry(store, "unit-org")
    registry._state = Mock(side_effect=lambda *_: deepcopy(state))
    registry._people = Mock(side_effect=lambda *_: deepcopy(people))
    registry._save = Mock()
    return SimpleNamespace(
        registry=registry,
        store=store,
        state=state,
        people=people,
        config=config,
        owner=owner,
        recipient=recipient,
        context=context,
        connection=connection,
    )


# Arrange a registered tenancy and optional ownership independently of the command path.
def tenancy(case, kind="individual", owner=None, *, name="Example sandbox"):
    key = str(uuid4())
    case.state["tenancy"].append(
        {"id": key, "name": name, "kind": kind, "status": "active", "legacy": False}
    )
    if owner is not False:
        association(case, key, owner or case.owner, "owner")
    return key


# Arrange an active link so scenarios exercise selection, role and last-link rules.
def association(case, tenancy_id, person, role="member"):
    key = str(uuid4())
    case.state["association"].append(
        {"id": key, "tenancy_id": tenancy_id, "person_id": person, "role": role, "status": "active"}
    )
    return key


# Invoke the real command coordinator with the current workspace confirmation.
def command(case, operation, **values):
    return case.registry.operate(
        {"context": dict(case.context), "person_id": case.owner, "operation": operation, **values}
    )


# Expose the decision output handed to persistence, rather than reproducing its algorithm.
def saved(case):
    return case.registry._save.call_args.args[2]


# Require business rejection before any save, publication or success audit.
def rejected(case, operation, message, **values):
    with pytest.raises(ValueError, match=message):
        command(case, operation, **values)
    case.registry._save.assert_not_called()
    case.store.update_configuration.assert_not_called()
    case.store._audit.assert_not_called()


# Create/import attach the employee and close onboarding without claiming an OCI mutation.
@pytest.mark.parametrize("operation", ["create_tenancy", "import_tenancy"])
def test_onboarding_records_ownership_closure_and_simulated_audit(case, operation):
    result = command(case, operation, name="New sandbox")
    output = saved(case)
    assert result["simulated"] and result["oci_performed"] is False
    assert not result["person_removed"] and result["remaining_associations"] == 1
    assert output["association"][0]["person_id"] == case.owner
    assert output["association"][0]["role"] == "owner"
    assert output["association"][0]["tenancy_id"] == output["tenancy"][0]["id"]
    assert case.owner not in output["pending"]
    args = case.store.update_configuration.call_args
    assert args.kwargs["connection"] is case.connection
    assert {d.kind for d in args.args[0].review_decisions} == {
        "TENANCY_SETUP_REVIEW",
        "PERSON_ABSENCE_REVIEW",
    }
    audit = case.store._audit.call_args.args[4]
    assert audit["operation"] == operation and audit["remaining_associations"] == 1
    assert audit["oci_performed"] is False and audit["before"]["tenancy"] == []


# Each independent version token protects against acting on an outdated preview.
@pytest.mark.parametrize("field", ["applied_version_id", "proposed_version_id", "configuration_id"])
def test_stale_confirmation_cannot_publish_or_audit(case, field):
    case.store._workspace.return_value[field] = str(uuid4())
    with pytest.raises(PublicationConflict, match="context changed"):
        command(case, "create_tenancy")
    case.registry._state.assert_not_called()
    case.store.update_configuration.assert_not_called()
    case.store._audit.assert_not_called()


# Association changes cannot cross workspaces or silently apply a staged organization.
@pytest.mark.parametrize("fault", ["workspace", "pending"])
def test_wrong_workspace_or_unapplied_proposal_blocks_changes(case, fault):
    if fault == "workspace":
        case.context["workspace_id"] = "other-org"
    else:
        proposed = str(uuid4())
        case.context["proposed_version_id"] = proposed
        case.store._workspace.return_value["proposed_version_id"] = proposed
        case.store.workspace_context.return_value["proposal_status"] = "pending"
    with pytest.raises(PublicationConflict, match="pending organization"):
        command(case, "create_tenancy")
    case.registry._save.assert_not_called()
    case.store._audit.assert_not_called()


# Historical/reference/absent identities cannot acquire a new tenancy through onboarding.
@pytest.mark.parametrize(
    "fault", ["missing_head", "unknown_person", "reference", "unmanaged", "absent", "outside"]
)
def test_onboarding_requires_current_managed_employee(case, fault):
    if fault == "missing_head":
        case.store.head.return_value = None
    elif fault == "unknown_person":
        del case.people[case.owner]
    elif fault == "reference":
        case.people[case.owner]["profile"] = "reference"
    elif fault == "unmanaged":
        case.people[case.owner]["managed"] = False
    elif fault == "absent":
        case.people[case.owner]["source_present"] = False
    else:
        case.state["outside"].add(case.owner)
    rejected(case, "create_tenancy", "snapshot|employee|Re-onboard|present")


# Names must be usable and distinct among active registered tenancies.
@pytest.mark.parametrize("name", ["   ", "x" * 201, "EXAMPLE SANDBOX"])
def test_creation_rejects_blank_long_and_case_insensitive_duplicate_names(case, name):
    tenancy(case)
    rejected(case, "create_tenancy", "distinct tenancy name", name=name)


# Joining an owned shared tenancy gives membership without replacing accountability.
def test_shared_membership_preserves_owner_and_adds_only_member(case):
    key = tenancy(case, "shared", case.recipient)
    command(case, "join_shared", tenancy_id=key)
    links = saved(case)["association"]
    assert {(a["person_id"], a["role"]) for a in links} == {
        (case.recipient, "owner"),
        (case.owner, "member"),
    }
    assert len(saved(case)["tenancy"]) == 1


# Membership must target an active shared tenancy with an owner and no duplicate access.
@pytest.mark.parametrize(
    "fault", ["unregistered", "deleted", "individual", "ownerless", "duplicate"]
)
def test_shared_join_rejects_unusable_or_duplicate_target(case, fault):
    key = tenancy(case, "shared", case.recipient)
    if fault == "unregistered":
        key = str(uuid4())
    elif fault == "deleted":
        case.state["tenancy"][0]["status"] = "deleted"
    elif fault == "individual":
        case.state["tenancy"][0]["kind"] = "individual"
    elif fault == "ownerless":
        case.state["association"].clear()
    else:
        association(case, key, case.owner)
    rejected(case, "join_shared", "registered|recorded owner|already has", tenancy_id=key)


# Deleting an individual tenancy cannot erase a separate shared-tenancy membership.
@pytest.mark.parametrize("retained", [False, True])
def test_delete_hides_person_only_after_last_active_association(case, retained):
    key = tenancy(case)
    if retained:
        shared = tenancy(case, "shared", case.recipient, name="Team sandbox")
        association(case, shared, case.owner)
    result = command(case, "delete_tenancy", tenancy_id=key)
    output = saved(case)
    assert result["person_removed"] is not retained
    assert result["remaining_associations"] == int(retained)
    assert output["tenancy"][0]["status"] == "deleted"
    assert (case.owner in output["hidden"]) is not retained
    assert output["tenancy"][-1]["status"] == ("active" if retained else "deleted")


# Deletion cannot remove shared ownership, other users' resources or unrelated tenancies.
@pytest.mark.parametrize(
    "fault", ["shared_owner", "other_members", "member_cannot_delete", "unrelated"]
)
def test_delete_role_and_other_association_guards(case, fault):
    key = tenancy(case, "shared" if fault == "shared_owner" else "individual")
    if fault == "other_members":
        association(case, key, case.recipient)
    elif fault == "member_cannot_delete":
        case.state["association"][0]["role"] = "member"
    elif fault == "unrelated":
        case.state["association"][0]["person_id"] = case.recipient
    rejected(
        case,
        "delete_tenancy",
        "Transfer shared|other members|not allowed|no active",
        tenancy_id=key,
    )


# Transfer retires old links and leaves exactly one owner, preserving the shared tenancy.
def test_owner_transfer_promotes_existing_member_and_closes_their_onboarding(case):
    key = tenancy(case, "shared")
    association(case, key, case.recipient)
    case.state["pending"].add(case.recipient)
    result = command(case, "transfer_owner", tenancy_id=key, owner_person_id=case.recipient)
    output = saved(case)
    active = [a for a in output["association"] if a["status"] == "active"]
    assert [(a["person_id"], a["role"]) for a in active] == [(case.recipient, "owner")]
    assert result["person_removed"] and output["tenancy"][0]["status"] == "active"
    assert case.recipient not in output["pending"]
    config = case.store.update_configuration.call_args.args[0]
    assert any(
        d.person_id == UUID(case.recipient) and d.operation == "transfer_owner"
        for d in config.review_decisions
    )


# Ownership cannot be transferred to self, an unknown identity or a departed employee.
@pytest.mark.parametrize("recipient", ["same", "unknown", "ineligible"])
def test_transfer_requires_a_different_current_eligible_employee(case, recipient):
    key = tenancy(case, "shared")
    target = (
        case.owner
        if recipient == "same"
        else str(uuid4())
        if recipient == "unknown"
        else case.recipient
    )
    if recipient == "ineligible":
        case.people[case.recipient]["eligible_transfer"] = False
    rejected(
        case,
        "transfer_owner",
        "different, currently present",
        tenancy_id=key,
        owner_person_id=target,
    )


# Incomplete or duplicate plans cannot silently discard access that was not reviewed.
@pytest.mark.parametrize("plan_fault", ["missing", "duplicate", "unknown"])
def test_offboarding_requires_exactly_one_choice_for_every_association(case, plan_fault):
    tenancy(case)
    link = case.state["association"][0]["id"]
    plan = (
        []
        if plan_fault == "missing"
        else [
            {"association_id": link, "action": "delete"},
            {
                "association_id": link if plan_fault == "duplicate" else str(uuid4()),
                "action": "keep",
            },
        ]
    )
    rejected(case, "offboard_person", "exactly one action", plan=plan)


# A reviewed keep decision retains an outside profile instead of hiding remaining access.
def test_offboarding_can_retain_shared_membership_as_outside_organization(case):
    owned = tenancy(case)
    shared = tenancy(case, "shared", case.recipient, name="Team sandbox")
    member = association(case, shared, case.owner)
    owner_link = next(a["id"] for a in case.state["association"] if a["tenancy_id"] == owned)
    result = command(
        case,
        "offboard_person",
        plan=[
            {"association_id": owner_link, "action": "delete"},
            {"association_id": member, "action": "keep"},
        ],
    )
    assert not result["person_removed"] and result["remaining_associations"] == 1
    assert case.owner in saved(case)["outside"]
    assert case.owner not in saved(case)["hidden"]


# Zero-link offboarding still requires an intentional administrator decision.
def test_offboarding_without_links_requires_explicit_confirmation(case):
    rejected(case, "offboard_person", "Confirm that no tenancy")


# Offboarding changes managed eligibility without mutating the source person snapshot.
def test_confirmed_zero_link_offboarding_preserves_source_identity(case):
    before = tuple(case.store.head.return_value.people)
    result = command(case, "offboard_person", confirm_no_associations=True)
    assert result["person_removed"] and result["remaining_associations"] == 0
    assert tuple(case.store.head.return_value.people) == before
    assert case.owner in saved(case)["hidden"]


# Opting out of management differs from simulating infrastructure creation or deletion.
def test_no_tenancy_required_is_nonsimulated_and_rejects_existing_access(case):
    result = command(case, "no_tenancy_required")
    assert result["person_removed"] and not result["simulated"]
    assert case.owner in saved(case)["hidden"]


# An owner cannot disappear from management while retaining unreviewed access.
def test_no_tenancy_required_cannot_orphan_existing_associations(case):
    tenancy(case)
    rejected(case, "no_tenancy_required", "Resolve existing associations")


# Explicit re-onboarding clears the durable exclusion and opens onboarding, not a tenancy.
def test_reonboarding_restores_present_unmanaged_identity_without_creating_access(case):
    case.people[case.owner]["managed"] = False
    case.state["hidden"].add(case.owner)
    case.state["outside"].add(case.owner)
    config = case.config.model_copy(
        update={
            "excluded_emails": ("owner@example.test",),
            "review_decisions": (
                ReviewDecision(
                    kind="TENANCY_SETUP_REVIEW",
                    target="owner@example.test",
                    disposition="resolved",
                    recorded_at=NOW,
                    actor="local:admin",
                    reason="No tenancy needed",
                    person_id=case.owner,
                    operation="no_tenancy_required",
                ),
            ),
        }
    )
    case.store.configuration.return_value = config
    result = command(case, "reonboard")
    output = saved(case)
    assert not result["simulated"] and result["remaining_associations"] == 0
    assert (
        case.owner in output["pending"] and case.owner not in output["hidden"] | output["outside"]
    )
    updated = case.store.update_configuration.call_args.args[0]
    assert updated.excluded_emails == () and updated.review_decisions == ()


# Re-onboarding cannot duplicate management or revive an identity absent from the feed.
@pytest.mark.parametrize("fault", ["managed", "absent", "linked"])
def test_reonboarding_rejects_ineligible_profiles(case, fault):
    case.people[case.owner]["managed"] = fault == "managed"
    if fault == "absent":
        case.people[case.owner]["source_present"] = False
    if fault == "linked":
        tenancy(case)
    rejected(case, "reonboard", "present, unmanaged employee")


# Returning employees retain their associations and clear the outside marker explicitly.
@pytest.mark.parametrize("fault", [None, "absent", "not_outside"])
def test_return_to_organization_requires_present_retained_profile(case, fault):
    tenancy(case)
    if fault != "not_outside":
        case.state["outside"].add(case.owner)
    if fault == "absent":
        case.people[case.owner]["source_present"] = False
    if fault:
        rejected(case, "return_to_org", "returned employee")
    else:
        result = command(case, "return_to_org")
        assert not result["simulated"] and result["remaining_associations"] == 1
        assert case.owner not in saved(case)["outside"]


# Promote an eligible member to repair an ownerless shared tenancy.
@pytest.mark.parametrize("fault", [None, "individual", "already_owned", "ineligible"])
def test_assigning_legacy_shared_owner_requires_unowned_shared_target(case, fault):
    key = tenancy(case, "individual" if fault == "individual" else "shared", owner=False)
    association(case, key, case.owner)
    if fault == "already_owned":
        association(case, key, case.recipient, "owner")
    elif fault == "ineligible":
        case.people[case.owner]["eligible_transfer"] = False
    if fault:
        rejected(case, "assign_owner", "only available|present managed employee", tenancy_id=key)
    else:
        command(case, "assign_owner", tenancy_id=key)
        active = [a for a in saved(case)["association"] if a["status"] == "active"]
        assert [(a["person_id"], a["role"]) for a in active] == [(case.owner, "owner")]


# Only an owner edits a unique tenancy name; shared membership blocks individual conversion.
@pytest.mark.parametrize("fault", [None, "non_owner", "members", "duplicate", "blank", "too_long"])
def test_tenancy_edit_preserves_ownership_and_rejects_unsafe_conversions(case, fault):
    key = tenancy(case, "shared")
    options = {"name": "Renamed sandbox", "kind": "individual"}
    if fault == "non_owner":
        case.state["association"][0]["person_id"] = case.recipient
    elif fault == "members":
        association(case, key, case.recipient)
    elif fault == "duplicate":
        tenancy(case, name="Existing sandbox")
        options["name"] = "EXISTING SANDBOX"
    elif fault == "blank":
        options["name"] = "   "
    elif fault == "too_long":
        options["name"] = "x" * 201
    if fault:
        rejected(
            case,
            "update_tenancy",
            "registered owner|Remove shared|distinct tenancy",
            tenancy_id=key,
            **options,
        )
    else:
        before = deepcopy(case.state["association"])
        command(case, "update_tenancy", tenancy_id=key, **options)
        assert saved(case)["tenancy"][0]["name"] == "Renamed sandbox"
        assert saved(case)["tenancy"][0]["kind"] == "individual"
        assert saved(case)["association"] == before
        assert case.store.update_configuration.call_args.args[0].review_decisions == ()


# Removing the last shared membership hides the employee while preserving the team tenancy.
def test_member_removal_keeps_tenancy_and_remaining_owner(case):
    key = tenancy(case, "shared", case.recipient)
    association(case, key, case.owner)
    result = command(case, "remove_member", tenancy_id=key)
    output = saved(case)
    assert result["person_removed"] and output["tenancy"][0]["status"] == "active"
    assert [a["person_id"] for a in output["association"] if a["status"] == "active"] == [
        case.recipient
    ]


# Unrecognized commands fail rather than silently closing an organization review.
def test_unknown_operation_cannot_save_or_audit_success(case):
    rejected(case, "invented_operation", "Unknown registry operation")


# Inventory exposes active associations, onboarding status and safe actions per role.
def test_active_projection_excludes_removed_links_and_deleted_tenancies(case):
    individual = tenancy(case)
    shared = tenancy(case, "shared", case.recipient, name="Team sandbox")
    member = association(case, shared, case.owner)
    deleted = tenancy(case, name="Retired sandbox")
    case.state["tenancy"][-1]["status"] = "deleted"
    for link in case.state["association"]:
        if link["tenancy_id"] == deleted:
            link["status"] = "removed"
    view = case.registry.read()
    assert {t["id"] for t in view["tenancies"]} == {individual, shared}
    owner = next(p for p in view["people"] if p["id"] == case.owner)
    assert owner["association_count"] == 2 and owner["status"] == "Onboarding"
    by_link = {a["id"]: a for a in owner["associations"]}
    assert by_link[member]["allowed_actions"] == ["remove", "keep"]
    individual_link = next(a for a in owner["associations"] if a["tenancy_id"] == individual)
    assert individual_link["allowed_actions"] == ["delete", "transfer", "keep"]
    recipient = next(p for p in view["people"] if p["id"] == case.recipient)
    assert (
        recipient["associations"][0]["block_reasons"]["delete"]
        == "Transfer shared tenancy ownership first."
    )


# Keep source inclusion and tenancy accountability independent in inventory.
@pytest.mark.parametrize(
    "managed,present,outside,expected",
    [
        (False, True, False, "Not managed"),
        (True, False, False, "Outside organization · association retained"),
        (True, True, True, "Outside organization · association retained"),
        (True, True, False, "Managed"),
    ],
)
def test_inventory_status_respects_source_presence_and_managed_eligibility(
    case, managed, present, outside, expected
):
    tenancy(case)
    case.state["pending"].clear()
    case.people[case.owner].update(managed=managed, source_present=present)
    if outside:
        case.state["outside"].add(case.owner)
    view = case.registry.read()
    person = next(p for p in view["people"] if p["id"] == case.owner)
    assert person["status"] == expected
    assert (person in view["unmanaged_people"]) is not managed
