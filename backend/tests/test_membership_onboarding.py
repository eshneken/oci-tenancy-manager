"""Exact membership targets, legacy digest compatibility and baseline setup ordering."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from test_configuration_updates import update_case
from test_onboarding import case
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import (
    attach,
    command,
    database,
    intent,
    person,
    principal,
    registry,
    service,
)

from otm.providers.lifecycle import LifecycleBlocked, LifecycleCompletion
from otm.tenancies.contracts import MemberRemoval
from otm.tenancies.membership_access import save_removal_steps, validate_removals
from otm.tenancies.onboarding import advance, onboarding_steps
from otm.tenancies.onboarding_baseline import configure_baseline

__all__ = ["registry", "update_case"]


# New optional fields must not alter the canonical JSON of any legacy action.
def test_existing_compartment_exclusive_command_and_digest(registry):
    p = person(registry)
    original = command(registry, p, "create_tenancy", name="example")
    assert "existing_compartment_ocid" not in original.model_dump(mode="json")
    with pytest.raises(ValueError, match="EXCLUSIVE"):
        type(original)(**original.model_dump(), existing_compartment_ocid="other")
    joined = command(registry, p, "join_shared", existing_compartment_ocid="selected")
    assert joined.model_dump()["existing_compartment_ocid"] == "selected"
    with pytest.raises(ValueError, match="EXCLUSIVE"):
        type(joined)(**{**joined.model_dump(), "compartment_name": "new"})


# Only a server-listed nonroot compartment is admitted, with no new-compartment inputs.
@pytest.mark.parametrize("choice", ["valid", "foreign", "root"])
def test_existing_compartment_admission_and_exact_binding(registry, choice):
    s, p = registry, person(registry)
    app, connection = service(s), database()
    connection.execute.return_value.scalar_one.return_value = p.id
    tenant, _ = attach(s, person(s, "one@example.test"), kind="shared")
    options = app.facade.compartments(tenant["tenancy_ocid"])
    selected = (
        options[1].ocid
        if choice == "valid"
        else (tenant["tenancy_ocid"] if choice == "root" else "foreign")
    )
    connection.execute.return_value.mappings.return_value.one.return_value = dict(
        id=uuid4(), authorization_revision=uuid4(), identity_kind="local_recovery", email=None
    )
    cmd = command(s, p, "join_shared", tenancy_id=tenant["id"], existing_compartment_ocid=selected)
    if choice != "valid":
        with pytest.raises(Exception, match="EXISTING_COMPARTMENT_REQUIRED"):
            app._admit(
                connection,
                s,
                cmd,
                p,
                None,
                principal(),
                NOW,
            )
        return
    app._admit(
        connection,
        s,
        cmd,
        p,
        None,
        principal(),
        NOW,
    )
    frozen = intent(
        s,
        app,
        p,
        action="join_shared",
        pending_association_id=uuid4(),
        existing_compartment_ocid=selected,
    )
    frozen = frozen.model_copy(
        update={"target": frozen.target.model_copy(update={"tenancy_ocid": tenant["tenancy_ocid"]})}
    )
    completion = app.facade.apply(frozen)
    assert completion.bindings[0].compartment_ocid == selected
    assert completion.bindings[0].parent_compartment_ocid is None


# A wrong, missing or duplicate identity retirement receipt cannot close a shared association.
@pytest.mark.parametrize("damage", ["none", "missing", "foreign", "duplicate", "unverified"])
def test_exact_removal_receipts(registry, damage):
    from otm.tenancies.contracts import FrozenAssociation

    app, p = service(registry), person(registry)
    tenant, link = attach(registry, p, kind="shared")
    association = FrozenAssociation(
        id=link["id"],
        tenancy_id=tenant["id"],
        tenancy_revision=1,
        role="member",
        action="remove",
        tenancy_ocid=tenant["tenancy_ocid"],
        parent_tenancy_ocid=tenant["parent_tenancy_ocid"],
        user_ocid=link["user_ocid"],
    )
    frozen = intent(registry, app, p, action="remove_member", associations=(association,))
    completion = app.facade.apply(frozen)
    validate_removals(frozen, completion)
    receipt = completion.removals[0]
    if damage == "none":
        connection = MagicMock()
        save_removal_steps(
            connection,
            {
                "workspace_id": registry.workspace,
                "id": uuid4(),
                "current_intent_revision": 1,
                "current_intent_event_id": uuid4(),
            },
            completion.removals,
            {},
            uuid4(),
            NOW,
        )
        assert connection.execute.call_count == 2
        return
    values = (
        ()
        if damage == "missing"
        else (receipt, receipt)
        if damage == "duplicate"
        else (
            receipt.model_copy(
                update={"user_ocid": "other"} if damage == "foreign" else {"user_deleted": False}
            ),
        )
    )
    with pytest.raises(LifecycleBlocked):
        validate_removals(frozen, LifecycleCompletion.model_construct(bindings=(), removals=values))
    with pytest.raises(LifecycleBlocked):
        app.facade.remove_member_access(frozen, association.model_copy(update={"user_ocid": None}))


# Baseline object writes and reads retain partial state but advance verification only as a whole.
@pytest.mark.parametrize("failure", [None, "budget", "pin"])
def test_onboarding_baseline_readback_and_partial_state(update_case, failure):
    c = update_case
    row = {**c.row, "baseline_version_id": c.baseline.id}
    if failure == "pin":
        row["baseline_version_id"] = uuid4()
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one.return_value = row
    intent = SimpleNamespace(pending_tenancy_id=row["id"], baseline=c.baseline)
    context = {"workspace_id": c.policy.workspace_id, "id": uuid4()}
    facade = SimpleNamespace(configuration_facade=c.facade)
    original = c.facade.read

    # Fail only a requested category so earlier read-verified objects remain retry evidence.
    def read(target, category, stored):
        if category == failure:
            raise ValueError("synthetic readback failure")
        return original(target, category, stored)

    with patch.object(c.facade, "read", side_effect=read):
        if failure:
            with pytest.raises(ValueError):
                configure_baseline(
                    connection,
                    context,
                    intent,
                    facade,
                    NOW,
                )
        else:
            configure_baseline(connection, context, intent, facade, NOW)
    if failure == "pin":
        assert connection.execute.call_count == 1
    else:
        values = connection.execute.call_args_list[1].args[0].compile().params
        assert len(values["configuration_observation"]) >= 3
        assert ("verified_baseline_version_id" in values) == (failure is None)


# After baseline policy writes, fresh signer/recovery probes must precede bootstrap retirement.
@pytest.mark.parametrize("denied", [False, True])
def test_version_two_baseline_and_post_policy_access_order(registry, update_case, denied):
    from otm.tenancies import onboarding as flow

    app, frozen, row, _ = case(registry)
    frozen = frozen.model_copy(update={"onboarding_version": 2, "baseline": update_case.baseline})
    discovered = app.facade.inspect_onboarding(frozen, app.facade.onboarding_handoff(frozen))
    steps = {key: {"state": "verified", "inputs": {}} for key, _ in flow.STEPS[:-1]}
    steps["handoff"] = {"inputs": {"cleanup_confirmed": True}}
    steps["inspect_bootstrap"]["inputs"] = {"discovery": discovered.model_dump(mode="json")}
    calls = []

    # Count fresh post-baseline probes rather than trusting the earlier verified step flags.
    def probe(intent, key, discovery):
        calls.append(key)
        if denied and key == "verify_required":
            raise ValueError("synthetic access loss")

    with (
        patch.object(flow, "step_rows", return_value=steps),
        patch.object(flow, "save_step"),
        patch.object(flow, "transition"),
        patch(
            "otm.tenancies.onboarding_baseline.configure_baseline",
            side_effect=lambda *args: calls.append("baseline"),
        ),
        patch.object(app.facade, "onboarding_step", side_effect=probe),
    ):
        assert advance(MagicMock(), row, frozen, app.facade, NOW) is not denied
    assert calls[:3] == ["baseline", "verify_automation", "verify_required"]
    assert ("retire_temporary" in calls) is not denied
    assert len(onboarding_steps(frozen)) == 8


# Omitted positive proof must never default to a successful account deletion.
@pytest.mark.parametrize("missing", ["group_memberships_removed", "user_deleted"])
def test_missing_user_removal_proof_is_rejected(missing):
    values = dict(
        association_id=uuid4(),
        tenancy_ocid="ocid1.tenancy.oc1..otmsimchild",
        user_ocid="ocid1.user.oc1..otmsimuser",
        group_memberships_removed=True,
        user_deleted=True,
    )
    values.pop(missing)
    with pytest.raises(ValueError):
        MemberRemoval(**values)


# A malformed new setup graph cannot downgrade itself into the old baseline-free sequence.
@pytest.mark.parametrize("version", [2, 3])
def test_version_two_requires_a_published_baseline(registry, version):
    app, original, _, _ = case(registry)
    values = original.model_dump(mode="json")
    values["onboarding_version"] = version
    with pytest.raises(ValueError, match="PUBLISHED_ONBOARDING_BASELINE_REQUIRED"):
        type(original).model_validate_json(json.dumps(values))
