"""Verify root promotions before deletion without absorbing unrelated privilege drift."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from test_onboarding import case
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import principal, registry

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.lifecycle import LifecycleBlocked
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.providers.member_inventory_simulator import MemberInventory
from otm.storage.organization import OrganizationConflict
from otm.tenancies import owner_access as owners
from otm.tenancies.contracts import FrozenAssociation, OrganizationActionOutcome
from otm.tenancies.import_contracts import (
    AdoptedIdentity,
    AdoptedMember,
    ImportedAccessSnapshot,
    compare_imported,
)

__all__ = ["registry"]


# Independent provider defaults supply the existing analyst; no user/account is generated from a
# choice.
def setup(state, directory=None, disposition="remove"):
    app, frozen, _, _ = case(state, "import_tenancy")
    facade = SimulatedLifecycleFacade(app.policy, member_inventory=directory)
    discovery = facade.inspect_onboarding(frozen, facade.onboarding_handoff(frozen))
    inventory = facade.inspect_existing_access(frozen.target.tenancy_ocid, discovery.domain_ocid)
    old, recipient = inventory.users[0], inventory.users[2]
    item = FrozenAssociation(
        id=uuid4(),
        tenancy_id=uuid4(),
        tenancy_revision=1,
        role="owner",
        action="transfer",
        tenancy_ocid=inventory.tenancy_ocid,
        parent_tenancy_ocid=frozen.parent_tenancy_ocid,
        recipient_person_id=uuid4(),
        new_association_id=uuid4(),
        recipient_user_ocid=recipient.user_ocid,
        recipient_compartment_ocid=recipient.scopes[0].ocid,
        user_ocid=old.user_ocid,
        owner_administration_required=True,
        recipient_domain_ocid=inventory.domain_ocid,
        recipient_scim_id=recipient.scim_id,
        former_owner_disposition=disposition,
        recipient_imported_access=AdoptedIdentity(
            domain_ocid=inventory.domain_ocid, identity=recipient
        ),
    )
    frozen = frozen.model_copy(
        update={
            "action": "transfer_owner",
            "pending_association_id": None,
            "pending_tenancy_id": None,
            "onboarding_version": None,
            "associations": (item,),
        }
    )
    return facade, frozen, item, inventory


# Every scope/identity/privilege substitution must fail before the outgoing identity is removed.
@pytest.mark.parametrize(
    "fault",
    [
        "group",
        "role",
        "policy",
        "scope",
        "incomplete",
        "authorized",
        "supported",
        "resources",
        "domain_admin",
        "scim",
        "user",
        "association",
        "domain",
        "tenant",
    ],
)
def test_bad_owner_readback_prevents_deletion(registry, fault):
    facade, intent, item, _ = setup(registry)
    original = facade.inspect_owner

    # Change independent readback after writes, leaving the actual outgoing identity untouched.
    def changed(*arguments):
        proof = original(*arguments)
        fields = {
            "group": {"policy_group_id": "wrong"},
            "role": {"administrator_role_id": "wrong"},
            "policy": {"root_policy_id": "wrong"},
            "scope": {"policy_scope_ocid": "wrong"},
            "incomplete": {"complete": False},
            "authorized": {"authorized": False},
            "supported": {"supported": False},
            "resources": {"manage_all_resources": False},
            "domain_admin": {"domain_administrator": False},
            "association": {"association_id": uuid4()},
            "domain": {"domain_ocid": "wrong"},
            "tenant": {"tenancy_ocid": "wrong"},
        }
        if fault in {"scim", "user"}:
            return proof.model_copy(
                update={
                    "identity": proof.identity.model_copy(
                        update={"scim_id" if fault == "scim" else "user_ocid": "wrong"}
                    )
                }
            )
        return proof.model_copy(update=fields[fault])

    with (
        patch.object(facade, "inspect_owner", side_effect=changed),
        patch.object(facade, "remove_member_access") as remove,
    ):
        with pytest.raises(LifecycleBlocked):
            facade.apply(intent)
        remove.assert_not_called()
    assert item.user_ocid in {
        u.user_ocid
        for u in facade.inspect_existing_access(item.tenancy_ocid, item.recipient_domain_ocid).users
    }


# Foreign recipient bindings and duplicate IDs are rejected by the same pre-deletion validator.
@pytest.mark.parametrize(
    "fault", ["tenant", "person", "root", "parent", "duplicate", "proof_missing", "proof_duplicate"]
)
def test_binding_substitutions(registry, fault):
    facade, intent, _, _ = setup(registry, disposition="keep_member")
    completion = facade.apply(intent)
    binding = completion.bindings[0]
    changes = {
        "tenant": {"tenancy_ocid": "foreign"},
        "person": {"person_id": uuid4()},
        "root": {"compartment_ocid": "foreign"},
        "parent": {"parent_compartment_ocid": "foreign"},
    }
    if fault in changes:
        completion = completion.model_copy(
            update={"bindings": (binding.model_copy(update=changes[fault]),)}
        )
    elif fault == "duplicate":
        completion = completion.model_copy(update={"bindings": completion.bindings * 2})
    else:
        completion = completion.model_copy(
            update={
                "owner_administrations": ()
                if fault == "proof_missing"
                else completion.owner_administrations * 2
            }
        )
    with pytest.raises(LifecycleBlocked):
        owners.validate(intent, completion)


# A promotion survives a separate provider process; a removed user's tombstone also survives
# restart.
def test_persistent_promotion_and_tombstone(registry, tmp_path):
    folder = tmp_path / "members"
    folder.mkdir(mode=0o700)
    facade, intent, item, inventory = setup(registry, folder)
    completed = facade.apply(intent)
    proof = completed.owner_administrations[0]
    assert proof.identity.scim_id == inventory.users[2].scim_id
    assert proof.identity.administrator
    assert len(proof.identity.scopes) == 3
    assert completed.bindings[0].compartment_ocid == item.tenancy_ocid
    again = SimulatedLifecycleFacade(facade.policy, member_inventory=folder)
    assert again.inspect_owner(item, item.recipient_user_ocid) == proof
    observed = again.inspect_existing_access(item.tenancy_ocid, item.recipient_domain_ocid)
    assert item.user_ocid not in {u.user_ocid for u in observed.users}
    with pytest.raises(ValueError, match="MEMBER_DELETED"):
        again.member_inventory.write(
            item.tenancy_ocid, item.user_ocid, {"user": True, "groups": True}
        )
    assert (
        again.inspect_member(item.tenancy_ocid, item.recipient_domain_ocid, item.user_ocid) is None
    )


# Corrupt provider records and contended scope locks never silently recreate fixture defaults.
def test_corrupt_and_contended_provider_state(tmp_path):
    folder = tmp_path / "members"
    folder.mkdir(mode=0o700)
    store = MemberInventory(folder)
    store.write("child", "user", {"user": False, "groups": False})
    with store.records.locked(store.key("child")):
        with pytest.raises(BlockingIOError):
            MemberInventory(folder).read("child")
    filename = folder / (store.key("child", "user") + ".json")
    filename.write_text("{broken")
    with pytest.raises(ValueError):
        store.read("child")
    with pytest.raises(ValueError):
        store.write("child", "user", {"user": True, "groups": True})


# Only the approved admin delta becomes expected; extra observed grants remain visible as drift.
def test_promotion_does_not_bless_drift(registry):
    facade, intent, item, inventory = setup(registry, disposition="keep_member")
    before = inventory.users[2]
    facade._member_access[(item.tenancy_ocid, before.user_ocid)] = {
        "user": True,
        "groups": True,
        "domain_ocid": item.recipient_domain_ocid,
        "identity": before.model_copy(
            update={"groups": (*before.groups, "unapproved"), "policy_hash": "f" * 64}
        ).model_dump(mode="json"),
    }
    completion = facade.apply(intent)
    expected = owners.expectation(item.recipient_imported_access, uuid4(), item.tenancy_ocid)
    assert expected.identity == before
    assert "unapproved" not in expected.expected_owner.identity.groups
    snapshot = ImportedAccessSnapshot(
        tenancy_ocid=item.tenancy_ocid,
        domain_ocid=item.recipient_domain_ocid,
        members=(
            AdoptedMember(
                association_id=item.new_association_id,
                person_id=item.recipient_person_id,
                access=expected,
            ),
        ),
        known_user_ocids=tuple(u.user_ocid for u in inventory.users),
    )
    result = compare_imported(
        snapshot, facade.inspect_existing_access(item.tenancy_ocid, item.recipient_domain_ocid), NOW
    )
    assert result.state == "drifted" and result.members[0].state == "different"
    assert completion.owner_administrations[0].manage_all_resources


# Current metadata is authenticated against exact immutable accepted and successful outcome
# evidence.
@pytest.mark.parametrize(
    "fault", [None, "hash", "missing", "duplicate", "identity", "person", "scope"]
)
def test_expected_owner_evidence(registry, fault):
    facade, intent, item, _ = setup(registry, disposition="keep_member")
    completion = facade.apply(intent)
    identifier = uuid4()
    access = owners.expectation(item.recipient_imported_access, identifier, item.tenancy_ocid)
    target = {
        "id": item.new_association_id,
        "tenancy_id": item.tenancy_id,
        "person_id": item.recipient_person_id,
        "user_ocid": item.recipient_user_ocid,
        "imported_access": access.model_dump(mode="json"),
    }
    accepted = IntentEventData(intent=intent, actor=principal().actor).model_dump(mode="json")
    outcome = OrganizationActionOutcome(
        action="transfer_owner",
        safe_code="SIMULATED_LIFECYCLE_VERIFIED",
        owner_administrations=completion.owner_administrations,
        verified_at=NOW,
    ).model_dump(mode="json")
    events = [
        {
            "operation_id": identifier,
            "kind": kind,
            "data": value,
            "data_hash": canonical_hash(value),
        }
        for kind, value in [
            ("operation_intent", accepted),
            ("organization_action_outcome", outcome),
        ]
    ]
    if fault == "hash":
        events[0]["data_hash"] = "0" * 64
    elif fault == "missing":
        events = events[:1]
    elif fault == "duplicate":
        events.append(events[0])
    elif fault == "identity":
        target["imported_access"]["identity"]["email"] = "changed@example.test"
    elif fault == "person":
        target["person_id"] = uuid4()
    elif fault == "scope":
        target["tenancy_id"] = uuid4()
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = events
    if fault is None:
        owners.authenticate(connection, intent.workspace_id, [target])
    else:
        with pytest.raises(ValueError):
            owners.authenticate(connection, intent.workspace_id, [target])


# Scoped domain discovery rejects absent/ambiguous bindings; admission freezes independent SCIM IDs.
def test_prepare_owner_scope(registry):
    facade, intent, item, _ = setup(registry)
    connection = MagicMock()
    connection.execute.return_value.scalars.return_value.all.return_value = [
        item.recipient_domain_ocid
    ]
    result = owners.prepare(connection, registry, (item,), facade)
    assert result[0].recipient_scim_id == item.recipient_scim_id
    for rows in ([], ["a", "b"]):
        connection.execute.return_value.scalars.return_value.all.return_value = rows
        with pytest.raises(OrganizationConflict):
            owners.domain(connection, registry.workspace, item.tenancy_id)
    connection.execute.return_value.scalars.return_value.all.return_value = [
        item.recipient_domain_ocid
    ]
    with patch.object(facade, "inspect_member", return_value=None):
        with pytest.raises(OrganizationConflict):
            owners.prepare(connection, registry, (item,), facade)
    plain = item.model_copy(update={"action": "keep", "owner_administration_required": False})
    assert owners.prepare(connection, registry, (plain,), facade) == (plain,)
    assert owners.promoted(
        facade.apply(intent).owner_administrations[0].identity,
        item.tenancy_ocid,
        item.recipient_domain_ocid,
    ).administrator
