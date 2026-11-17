"""Exact import consent, participant fences and independent human-access observations."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from test_onboarding import case
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import person, registry

from otm.operations.contracts import canonical_hash
from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.organization import OrganizationConflict
from otm.tenancies import import_adoption as adoption
from otm.tenancies.import_contracts import (
    ExistingAccessInventory,
    ImportAdoption,
    compare_imported,
    import_hash,
)

__all__ = ["registry"]


# Use independent simulator observations rather than generating identities from employee matches.
def scenario(state):
    app, intent, row, _ = case(state, "import_tenancy")
    intent = intent.model_copy(update={"import_adoption_contract": "import-adoption-1"})
    discovery = app.facade.inspect_onboarding(
        intent, app.facade.onboarding_handoff(intent)
    ).model_dump(mode="json")
    inventory = adoption.read_inventory(app.facade, intent, discovery)
    owner, member = person(state), person(state, "one@example.test")
    state.controls[owner.id]["pending_operation_id"] = row["id"]
    choice = ImportAdoption(
        inventory_hash=import_hash(inventory),
        lifecycle_confirmed=True,
        members=(
            {"user_ocid": inventory.users[0].user_ocid, "person_id": owner.id},
            {"user_ocid": inventory.users[2].user_ocid, "person_id": member.id},
        ),
    )
    manifest = adoption.plan(state, row, intent, inventory, choice)
    return app, intent, row, discovery, inventory, choice, manifest


# Reserved pending rows retain every scope while compatibility columns carry only the primary scope.
def pending(state, intent, row, manifest):
    links = []
    for member in manifest.members:
        access = member.access
        state.controls[member.person_id]["pending_operation_id"] = row["id"]
        links.append(
            dict(
                id=member.association_id,
                workspace_id=state.workspace,
                tenancy_id=intent.pending_tenancy_id,
                person_id=member.person_id,
                operation_id=row["id"],
                status="pending",
                role="owner" if member.person_id == intent.target.person_id else "member",
                user_ocid=access.identity.user_ocid,
                compartment_ocid=access.identity.scopes[0].ocid,
                imported_access=access.model_dump(mode="json"),
            )
        )
    return (
        state._replace(links=tuple(links))
        if hasattr(state, "_replace")
        else state.__class__(**{**vars(state), "links": tuple(links)})
    )


# Consent binds immutable inventory and owner identity; shared root and multiple scopes are valid.
def test_adoption_and_completion(registry):
    app, intent, row, discovery, inventory, choice, manifest = scenario(registry)
    assert adoption.enabled(intent)
    assert adoption.review(registry, row, intent, inventory).inventory_hash == choice.inventory_hash
    assert len(manifest.members[1].access.identity.scopes) == 2
    assert manifest.members[0].access.identity.scopes[0].kind == "root"
    result = adoption.completion(intent, manifest)
    assert {b.user_ocid for b in result.bindings} == {m.user_ocid for m in choice.members}
    adoption.verify(app.facade, intent, discovery, manifest)
    state = pending(registry, intent, row, manifest)
    adoption.validate_participants(state, intent, manifest, row["id"])
    connection = MagicMock()
    connection.execute.return_value.rowcount = 1
    adoption.reserve(connection, registry, row, intent, manifest, NOW)
    assert connection.execute.call_count == 4
    connection.execute.return_value.rowcount = 0
    with pytest.raises(OrganizationConflict, match="OWNER_RESERVED"):
        adoption.reserve(connection, registry, row, intent, manifest, NOW)


# Missing consent, stale inventory, unknown identities and invalid owner mapping never grant
# adoption.
@pytest.mark.parametrize(
    "fault", ["none", "hash", "owner", "user", "admin", "excluded", "reserved"]
)
def test_review_rejections(registry, fault):
    _, intent, row, _, inventory, choice, _ = scenario(registry)
    if fault == "none":
        choice = None
    elif fault == "hash":
        choice = choice.model_copy(update={"inventory_hash": "0" * 64})
    elif fault == "owner":
        choice = choice.model_copy(update={"members": choice.members[1:]})
    elif fault == "user":
        choice = choice.model_copy(
            update={"members": (choice.members[0].model_copy(update={"user_ocid": "unknown"}),)}
        )
    elif fault == "admin":
        choice = choice.model_copy(
            update={
                "members": (
                    choice.members[0].model_copy(
                        update={"user_ocid": inventory.users[2].user_ocid}
                    ),
                )
            }
        )
    elif fault == "excluded":
        registry.controls[choice.members[1].person_id]["directory_status"] = "removed"
    else:
        registry.controls[choice.members[1].person_id]["pending_operation_id"] = uuid4()
    with pytest.raises(OrganizationConflict):
        adoption.plan(registry, row, intent, inventory, choice)


# Reorgs and exact binding substitutions after consent block dispatch, even with intact
# reservations.
@pytest.mark.parametrize(
    "fault", ["mapping", "profile", "absent", "reservation", "role", "scope", "metadata", "missing"]
)
def test_participant_fences(registry, fault):
    _, intent, row, _, _, _, manifest = scenario(registry)
    state = pending(registry, intent, row, manifest)
    member = manifest.members[1]
    if fault in {"mapping", "profile", "absent"}:
        changes = {
            "mapping": {"lob_id": None},
            "profile": {"profile": "external"},
            "absent": {"absence_review": True},
        }[fault]
        state.people[member.person_id] = state.people[member.person_id].model_copy(update=changes)
    elif fault == "reservation":
        state.controls[member.person_id]["pending_operation_id"] = None
    elif fault == "missing":
        state.links[1]["operation_id"] = uuid4()
    else:
        key = {"role": "role", "scope": "compartment_ocid", "metadata": "imported_access"}[fault]
        state.links[1][key] = "changed"
    with pytest.raises(LifecycleBlocked, match="TARGET_CHANGED"):
        adoption.validate_participants(state, intent, manifest, row["id"])


# Enumeration order is harmless; duplicate identities/grants, wrong root scope and duplicate
# choices fail.
def test_closed_inventory_contracts(registry):
    _, _, _, _, inventory, choice, _ = scenario(registry)
    assert (
        ExistingAccessInventory.model_validate(
            {**inventory.model_dump(), "users": inventory.users[::-1]}
        )
        == inventory
    )
    variants = [
        {**inventory.model_dump(), "users": inventory.users + inventory.users[:1]},
        {
            **inventory.model_dump(),
            "users": [
                inventory.users[0].model_copy(
                    update={
                        "scopes": (
                            inventory.users[0].scopes[0].model_copy(update={"kind": "compartment"}),
                        )
                    }
                )
            ],
        },
    ]
    for value in variants:
        with pytest.raises(ValueError):
            ExistingAccessInventory.model_validate(value)
    for field in ("groups", "roles", "scopes"):
        user = inventory.users[0].model_dump()
        user[field] = user[field] * 2
        with pytest.raises(ValueError):
            type(inventory.users[0]).model_validate(user)
    with pytest.raises(ValueError):
        ImportAdoption.model_validate({**choice.model_dump(), "members": choice.members * 2})
    with pytest.raises(ValueError):
        ImportAdoption.model_validate({**choice.model_dump(), "lifecycle_confirmed": False})


# Mutable step inputs must match the exact immutable operation event and its authenticated digest.
def test_manifest_and_discovery_evidence(registry):
    _, _, row, _, inventory, _, manifest = scenario(registry)
    connection = MagicMock()
    for name, model, reader, kind in (
        ("import_inventory", inventory, adoption.discovered_inventory, "inspect"),
        ("import_manifest", manifest, adoption.accepted, "handoff"),
    ):
        value = model.model_dump(mode="json")
        step = {"inputs": {name: value}, "evidence_event_id": uuid4()}
        data = {name: value}
        record = {"data": data, "data_hash": canonical_hash(data)}
        connection.execute.return_value.mappings.return_value.one.return_value = record
        arg = step if kind == "inspect" else {"handoff": step}
        assert reader(connection, row, arg) == model
        record["data_hash"] = "0" * 64
        with pytest.raises(ValueError, match="EVIDENCE_INVALID"):
            reader(connection, row, arg)
        step["inputs"].clear()
        with pytest.raises((ValueError, OrganizationConflict)):
            reader(connection, row, arg)


# Failed/incomplete enumeration is unavailable; successful absence and privilege differences are
# drift.
@pytest.mark.parametrize(
    "fault",
    ["none", "incomplete", "domain", "tenant", "missing", "grants", "unmanaged", "matching"],
)
def test_independent_access_checks(registry, fault):
    _, intent, row, _, inventory, _, manifest = scenario(registry)
    state = pending(registry, intent, row, manifest)
    for link in state.links:
        link["status"] = "active"
    child = {"id": intent.pending_tenancy_id, "tenancy_ocid": intent.target.tenancy_ocid}
    snapshot = adoption.membership_snapshot(state.workspace, child, state.links)
    changed = inventory
    if fault == "none":
        changed = None
    elif fault in {"incomplete", "domain", "tenant"}:
        key, value = {
            "incomplete": ("complete", False),
            "domain": ("domain_ocid", "wrong"),
            "tenant": ("tenancy_ocid", "wrong"),
        }[fault]
        changed = inventory.model_copy(update={key: value})
    elif fault == "missing":
        changed = inventory.model_copy(update={"users": inventory.users[1:]})
    elif fault == "grants":
        changed = inventory.model_copy(
            update={
                "users": (
                    inventory.users[0].model_copy(update={"groups": ()}),
                    *inventory.users[1:],
                )
            }
        )
    elif fault == "unmanaged":
        new = inventory.users[0].model_copy(update={"user_ocid": "new-user", "scim_id": "new-scim"})
        changed = inventory.model_copy(update={"users": (*inventory.users, new)})
    result = compare_imported(snapshot, changed, NOW)
    assert result.state == (
        "unavailable"
        if fault in {"none", "incomplete", "domain", "tenant"}
        else "matching"
        if fault == "matching"
        else "drifted"
    )
    if fault == "missing":
        assert result.members[0].state in {"missing", "matching"}
        assert any(m.state == "missing" for m in result.members)
    assert result.context_hash == import_hash(snapshot)
    assert adoption.membership_snapshot(state.workspace, child, ()) is None


# Provider verification rejects unknown scope/incomplete inventory and any human permission delta.
def test_provider_verification(registry):
    app, intent, _, discovery, inventory, _, manifest = scenario(registry)
    facade = MagicMock(wraps=app.facade)
    facade.inspect_existing_access.return_value = inventory.model_copy(update={"complete": False})
    with pytest.raises(OrganizationConflict, match="UNVERIFIED"):
        adoption.read_inventory(facade, intent, discovery)
    user = inventory.users[0]
    scope = user.scopes[0].model_copy(update={"ocid": "unknown-scope", "kind": "compartment"})
    facade.inspect_existing_access.return_value = inventory.model_copy(
        update={"users": (user.model_copy(update={"scopes": (scope,)}),)}
    )
    with pytest.raises(OrganizationConflict, match="SCOPE_UNVERIFIED"):
        adoption.read_inventory(facade, intent, discovery)
    facade.inspect_existing_access.return_value = inventory.model_copy(
        update={"users": inventory.users[1:]}
    )
    with pytest.raises(OrganizationConflict, match="INVENTORY_CHANGED"):
        adoption.verify(facade, intent, discovery, manifest)


# Current labels require exact membership context and the independently recorded freshness window.
@pytest.mark.parametrize(
    "fault", ["none", "unchecked", "result", "authority", "context", "old", "future", "current"]
)
def test_imported_access_projection(registry, fault):
    from datetime import timedelta
    from types import SimpleNamespace
    from unittest.mock import patch

    from otm.tenancies.presence import imported_view

    _, intent, row, _, inventory, _, manifest = scenario(registry)
    state = pending(registry, intent, row, manifest)
    for link in state.links:
        link["status"] = "active"
    scope = adoption.membership_snapshot(
        state.workspace,
        {"id": intent.pending_tenancy_id, "tenancy_ocid": intent.target.tenancy_ocid},
        state.links,
    )
    result = compare_imported(scope, inventory, NOW)
    if fault == "context":
        result = result.model_copy(update={"context_hash": "0" * 64})
    latest = None if fault == "unchecked" else {"operation_id": row["id"]}
    snapshot = SimpleNamespace(import_access=None if fault == "none" else scope)
    at = (
        NOW + timedelta(days=1)
        if fault == "old"
        else NOW - timedelta(seconds=1)
        if fault == "future"
        else NOW
    )
    evidence = SimpleNamespace(import_access=None if fault == "result" else result)
    with (
        patch("otm.tenancies.presence.decode_result", return_value=evidence),
        patch(
            "otm.tenancies.presence.presence_views",
            return_value={} if fault == "authority" else {"automation": object()},
        ),
    ):
        view = imported_view(snapshot, latest, {"data": {}, "data_hash": "unused"}, at)
    if fault == "none":
        assert view is None
    else:
        assert view.state == (
            "not_checked"
            if fault == "unchecked"
            else "unavailable"
            if fault in {"result", "authority"}
            else "stale"
            if fault in {"context", "old", "future"}
            else "matching"
        )


# Membership snapshots reject foreign scope, mixed domains and identity/provenance substitutions.
@pytest.mark.parametrize("fault", ["workspace", "tenant", "user", "domain", "inactive"])
def test_imported_snapshot_fences(registry, fault):
    _, intent, row, _, _, _, manifest = scenario(registry)
    state = pending(registry, intent, row, manifest)
    for link in state.links:
        link["status"] = "active"
    link = state.links[1]
    if fault in {"workspace", "tenant"}:
        link["workspace_id" if fault == "workspace" else "tenancy_id"] = "foreign"
    elif fault == "user":
        link["user_ocid"] = "different"
    elif fault == "domain":
        link["imported_access"]["domain_ocid"] = "different"
    else:
        link["status"] = "removed"
    child = {"id": intent.pending_tenancy_id, "tenancy_ocid": intent.target.tenancy_ocid}
    if fault == "inactive":
        assert len(adoption.membership_snapshot(state.workspace, child, state.links).members) == 1
    else:
        with pytest.raises(ValueError, match="IMPORT_CHECK"):
            adoption.membership_snapshot(state.workspace, child, state.links)
