"""Unit rules for registry projections, safe admission and local facade contracts."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW, envelope, example_config, example_records
from test_organization_reconcile import revision

from otm.operations.contracts import InspectionPolicy
from otm.organization.reconcile import prepare
from otm.providers.lifecycle import LifecycleBlocked
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import (
    LifecycleTarget,
    OrganizationAction,
    OrganizationContext,
    OrganizationIntent,
)
from otm.tenancies.directory import (
    RegistryState,
    association_view,
    person_workflow,
    review_directory,
    tenancy_directory,
)
from otm.tenancies.views import ReviewQuery, TenancyQuery
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows, require_context


# Use actual graph-derived people and explicit registry rows without a database or provider
# dependency.
@pytest.fixture
def registry():
    config = example_config()
    head = revision(prepare(example_records(), envelope(), config, None, NOW))
    people = {p.id: p for p in head.people}
    controls = {
        p.id: dict(
            id=p.id,
            email=p.email,
            directory_status="included",
            setup_required=False,
            setup_episode_id=None,
            pending_operation_id=None,
            removed_capture_at=None,
        )
        for p in people.values()
    }
    return RegistryState(
        "fixture-workspace",
        OrganizationContext(
            applied_version_id=head.id,
            proposed_version_id=uuid4(),
            configuration_id=config.id,
            registry_revision=1,
        ),
        config,
        head,
        people,
        controls,
        {p.email for p in people.values()},
        {},
        (),
        (),
        {},
    )


# Identify a synthetic person by email so assertions remain independent of UUID generation/order.
def person(state, address="engineer@example.test"):
    return next(p for p in state.people.values() if p.email == address)


# Add one explicit qualified child and owner; history and additional associations are
# test-controlled.
def attach(state, owner, *, kind="individual", status="active", **changes):
    key, link_id = uuid4(), uuid4()
    row = dict(
        id=key,
        name="Engineer sandbox",
        tenancy_ocid="ocid1.tenancy.oc1..otmsim" + key.hex,
        parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        organization_id="synthetic-org",
        home_region="us-ashburn-1",
        kind=kind,
        status=status,
        provider_mode="simulated",
        origin="create",
        revision=1,
        operation_id=None,
        last_operation_id=None,
        verified_at=NOW,
        created_at=NOW,
    )
    row.update(changes)
    link = dict(
        id=link_id,
        person_id=owner.id,
        tenancy_id=key,
        role="owner",
        status="active",
        user_ocid="ocid1.user.oc1..otmsimuser",
        compartment_ocid=None,
        compartment_name=None,
        parent_compartment_ocid=None,
        cleanup_required=False,
        operation_id=None,
        revision=1,
    )
    state.tenancies[key] = row
    state.links = (*state.links, link)
    return row, link


# Small persisted episodes model the durable inbox independently of the source warning
# implementation.
def review(state, p, kind="TENANCY_SETUP_REVIEW", **changes):
    row = dict(
        id=uuid4(),
        person_id=p.id,
        kind=kind,
        category="actionable",
        status="open",
        target=p.email,
        basis="episode",
        first_seen_at=NOW,
        last_seen_at=NOW,
        resolved_at=None,
        resolution=None,
        operation_id=None,
        version_id=state.head.id,
        data={"name": p.full_name, "email": p.email},
    )
    row.update(changes)
    state.reviews = (*state.reviews, row)
    return row


# Compose a server-owned simulation policy matching only this isolated synthetic workspace.
def service(state):
    policy = InspectionPolicy(
        workspace_id=state.workspace,
        policy_revision=uuid4(),
        organization_id="synthetic-org",
        parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        access_binding_id=uuid4(),
    )
    facade = SimulatedLifecycleFacade(policy)
    return OrganizationWorkflows(Mock(), policy=policy, facade=facade, enqueuer=Mock())


# Preview commands carry exact context rather than trusting any browser-provided role or owner
# label.
def command(state, p, action, **fields):
    if action == "create_tenancy":
        fields.setdefault("home_region", "us-ashburn-1")
    return OrganizationAction(
        client_request_key=uuid4(), context=state.context, person_id=p.id, action=action, **fields
    )


# Frozen work references the confirmed person and trusted scope, not a live UI lookup at dispatch
# time.
def intent(state, app, p, action="create_tenancy", **fields):
    return OrganizationIntent(
        workspace_id=state.workspace,
        policy_revision=app.policy.policy_revision,
        organization_id=app.policy.organization_id,
        parent_tenancy_ocid=app.policy.parent_tenancy_ocid,
        administrator_id=uuid4(),
        authorization_revision=uuid4(),
        action=action,
        target=LifecycleTarget(
            person_id=p.id, display_name=p.full_name, tenancy_ocid="ocid1.tenancy.oc1..otmsimchild"
        ),
        person_was_absent=False,
        person_was_manager=p.known_manager,
        **fields,
    )


# Pure inventory projections count owners, preserve history, search literal text and clamp pages.
def test_registry_projection_and_role_choices(registry):
    s, p = registry, person(registry)
    row, link = attach(s, p)
    assert s.eligible(p.id) and len(s.associations(person=p.id)) == 1
    assert association_view(s, link).actions == ("delete", "transfer", "keep")
    shared, owner = attach(s, person(s, "one@example.test"), kind="shared")
    assert association_view(s, owner).actions == ("transfer", "keep")
    member = {**link, "id": uuid4(), "tenancy_id": shared["id"], "role": "member"}
    s.links = (*s.links, member)
    assert association_view(s, member).actions == ("remove", "keep")
    link["status"] = "removed"
    link["cleanup_required"] = True
    assert not s.associations(tenant=row["id"])
    assert len(s.associations(tenant=row["id"], history=True)) == 1
    listing = tenancy_directory(s, TenancyQuery(sort="member_count", direction="desc"))
    assert listing.total_tenancies == 2 and listing.items[0].member_count == 2
    assert listing.items[1].cleanup_count == 1
    assert tenancy_directory(s, TenancyQuery(query="unmatched", page=4)).page == 1
    row["status"] = "cancelled"
    assert tenancy_directory(s, TenancyQuery()).total_tenancies == 1
    vanished = uuid4()
    s.controls[vanished] = {"email": "historical@example.test"}
    assert s.option(vanished).name == "historical@example.test"
    with pytest.raises(OrganizationConflict):
        s.option(uuid4())


# Review filtering separates history and actionable counts and must honor each advertised sort
# control.
def test_review_projection_sorting_and_history(registry):
    s = registry
    p, q = person(s), person(s, "one@example.test")
    first = review(s, p)
    second = review(s, q, first_seen_at=NOW + timedelta(seconds=1))
    review(s, p, "METADATA_UPDATED", category="change", status="resolved", resolved_at=NOW)
    listing = review_directory(s, ReviewQuery(sort="name", direction="desc"))
    assert [r.name for r in listing.items] == sorted([p.full_name, q.full_name], reverse=True)
    assert listing.actionable_count == 2 and listing.history_count == 1
    assert review_directory(s, ReviewQuery(query="unmatched")).total == 0
    assert review_directory(s, ReviewQuery(category="history")).items[0].status == "resolved"
    assert (
        review_directory(s, ReviewQuery(sort="first_seen_at", direction="desc")).items[0].id
        == second["id"]
    )
    assert first["id"] != second["id"]


# Eligibility and merged/absent decisions do not conflate source presence with managed inclusion.
def test_preview_decisions_pending_and_merge_eligibility(registry):
    s, p = registry, person(registry)
    assert "create_tenancy" in person_workflow(s, p.id, mode="simulated").actions
    assert person_workflow(s, p.id, mode="unavailable").actions == ("no_tenancy_required",)
    lob = review(s, p, "LOB_MAPPING_REVIEW")
    assert person_workflow(s, p.id, mode="simulated", review_id=lob["id"]).actions == (
        "ignore",
        "resolve",
    )
    with pytest.raises(OrganizationConflict, match="REVIEW_CHANGED"):
        person_workflow(s, p.id, mode="simulated", review_id=uuid4())
    with pytest.raises(OrganizationConflict, match="PERSON_NOT_FOUND"):
        person_workflow(s, uuid4(), mode="simulated")
    s.controls[p.id]["directory_status"] = "exempt"
    assert person_workflow(s, p.id, mode="simulated").actions == ("reonboard",)
    op = uuid4()
    s.controls[p.id]["pending_operation_id"] = op
    s.operations[op], s.operation_subjects[op] = "needs_attention", p.id
    assert person_workflow(s, p.id, mode="simulated").actions == ("cancel_simulation",)
    s.operation_subjects[op] = uuid4()
    assert person_workflow(s, p.id, mode="simulated").actions == ()
    s.controls[p.id].update(pending_operation_id=None, directory_status="included")
    missing = p.model_copy(update={"absence_review": True})
    s.people[p.id] = missing
    s.supplied.remove(p.email)
    review(s, missing, "PERSON_ABSENCE_REVIEW")
    q = person(s, "delegate@example.test")
    review(s, q)
    preview = person_workflow(s, p.id, mode="simulated")
    assert "merge" in preview.actions and preview.merge_partners[0].id == q.id
    assert "offboard_person" in preview.actions
    s.supplied.add(p.email)
    assert "mark_returned" in person_workflow(s, p.id, mode="simulated").actions


# Missing/partial association plans, role misuse and manager/shared-impact acknowledgments fail
# closed.
def test_plans_bind_exact_registered_associations(registry):
    s, p = registry, person(registry)
    app = service(s)
    row, link = attach(s, p)
    with pytest.raises(OrganizationConflict, match="REVIEW_ALL"):
        app._plan(s, command(s, p, "offboard_person"), p)
    with pytest.raises(OrganizationConflict, match="REGISTERED_ASSOCIATION"):
        app._plan(s, command(s, p, "delete_tenancy", tenancy_id=uuid4()), p)
    frozen = app._plan(s, command(s, p, "delete_tenancy", tenancy_id=row["id"]), p)
    assert frozen[0].id == link["id"] and frozen[0].user_ocid == link["user_ocid"]
    manager = p.model_copy(update={"known_manager": True})
    with pytest.raises(OrganizationConflict, match="MANAGER_CONFIRMATION"):
        app._plan(s, command(s, p, "delete_tenancy", tenancy_id=row["id"]), manager)
    row["parent_tenancy_ocid"] = "ocid1.tenancy.oc1..foreign"
    with pytest.raises(OrganizationConflict, match="REGISTERED_CHILD"):
        app._plan(s, command(s, p, "delete_tenancy", tenancy_id=row["id"]), p)
    row["parent_tenancy_ocid"] = app.policy.parent_tenancy_ocid
    row["kind"] = "shared"
    with pytest.raises(OrganizationConflict, match="ASSOCIATION_PLAN_CHANGED"):
        app._plan(s, command(s, p, "delete_tenancy", tenancy_id=row["id"]), p)
    q = person(s, "delegate@example.test")
    transfer = command(s, p, "transfer_owner", tenancy_id=row["id"], recipient_person_id=q.id)
    with pytest.raises(OrganizationConflict, match="SHARED_CONFIRMATION"):
        app._plan(s, transfer, p)
    assert (
        app._plan(s, transfer.model_copy(update={"confirm_shared": True}), p)[0].recipient_person_id
        == q.id
    )
    s.controls[q.id]["pending_operation_id"] = uuid4()
    with pytest.raises(OrganizationConflict, match="CURRENT_TRANSFER"):
        app._plan(s, transfer, p)


# The facade returns deterministic bindings and rejects parent, foreign policy and unknown
# compartments.
def test_facade_identity_bindings_and_scope(registry):
    s, p = registry, person(registry)
    app = service(s)
    association, tenant = uuid4(), uuid4()
    frozen = intent(s, app, p, pending_association_id=association, pending_tenancy_id=tenant)
    result = app.facade.apply(frozen)
    assert result == app.facade.apply(frozen) and result.bindings[0].person_id == p.id
    with pytest.raises(LifecycleBlocked):
        app.facade.apply(frozen.model_copy(update={"workspace_id": "foreign"}))
    with pytest.raises(LifecycleBlocked):
        app.facade.compartments(app.policy.parent_tenancy_ocid)
    shared = frozen.model_copy(
        update={"action": "join_shared", "parent_compartment_ocid": frozen.target.tenancy_ocid}
    )
    assert app.facade.apply(shared).bindings[0].compartment_ocid
    with pytest.raises(LifecycleBlocked):
        app.facade.apply(
            shared.model_copy(update={"parent_compartment_ocid": "ocid1.compartment.oc1..foreign"})
        )
    with pytest.raises(ValueError, match="INVALID_LIFECYCLE_CODE"):
        LifecycleBlocked("arbitrary provider text")


# Dispatch rejects a departed new owner and changed reservations before calling any provider
# capability.
def test_worker_dispatch_presence_and_pending_guards(registry):
    s, p = registry, person(registry)
    app = service(s)
    frozen = intent(s, app, p)
    worker = OrganizationLifecycleWorker(
        Mock(), s.workspace, Mock(return_value=NOW), Mock(), app.facade
    )
    op = uuid4()
    with pytest.raises(LifecycleBlocked):
        worker._validate(s, frozen, op)
    s.controls[p.id]["pending_operation_id"] = op
    worker._validate(s, frozen, op)
    s.supplied.remove(p.email)
    with pytest.raises(LifecycleBlocked, match="TARGET_CHANGED"):
        worker._validate(s, frozen, op)
    s.supplied.add(p.email)
    with pytest.raises(LifecycleBlocked, match="PERSON_RETURNED"):
        worker._validate(s, frozen.model_copy(update={"person_was_absent": True}), op)
    with (
        patch.object(worker, "_run", side_effect=RuntimeError("private provider text")),
        patch.object(worker, "_record_failure") as record,
    ):
        worker.run(op)
        record.assert_called_once_with(op)
    require_context(s, s.context)
    with pytest.raises(OrganizationConflict):
        require_context(s, s.context.model_copy(update={"registry_revision": 2}))


# Boundary mocks return selected rows only; PostgreSQL tests separately prove constraints/rollback.
def database():
    from unittest.mock import MagicMock

    return MagicMock()


# Authenticated identity is immutable evidence; browser input never supplies this actor or grant
# revision.
def principal():
    from otm.operations.contracts import ActorIdentity

    actor = ActorIdentity(
        issuer="urn:otm:fixture", subject="administrator", display_name="Test administrator"
    )
    return SimpleNamespace(
        actor=actor, session=SimpleNamespace(issuer=actor.issuer, subject=actor.subject)
    )


# Local admission reserves pending registry rows, records a typed intent and enqueues only the
# operation ID.
@pytest.mark.parametrize("action_name", ["create_tenancy", "import_tenancy", "join_shared"])
def test_admission_writes_exact_intent_and_queue_reference(registry, action_name):
    s, p = registry, person(registry)
    app, connection = service(s), database()
    connection.execute.return_value.scalar_one.return_value = p.id
    connection.execute.return_value.mappings.return_value.one.return_value = dict(
        id=uuid4(), authorization_revision=uuid4(), identity_kind="local_recovery", email=None
    )
    fields = dict(name="explicitchild")
    if action_name == "import_tenancy":
        fields["import_ocid"] = "ocid1.tenancy.oc1..otmsimimport"
    if action_name == "join_shared":
        row, _ = attach(s, person(s, "one@example.test"), kind="shared")
        fields = dict(
            tenancy_id=row["id"],
            parent_compartment_ocid=row["tenancy_ocid"],
            compartment_name="engineer",
        )
    receipt = app._admit(
        connection, s, command(s, p, action_name, **fields), p, None, principal(), NOW
    )
    assert receipt.state == "queued" and receipt.provider_mode == "simulated"
    app.enqueuer.enqueue.assert_called_once_with(connection, receipt.operation_id)
    statements = [call.args[0] for call in connection.execute.call_args_list]
    event = next(
        stmt.compile().params
        for stmt in statements
        if getattr(stmt, "is_insert", False) and stmt.table.name == "audit_event"
    )
    frozen = event["data"]["intent"]
    assert frozen["action"] == action_name and frozen["target"]["person_id"] == str(p.id)
    assert frozen["pending_association_id"] and "password" not in str(event)
    app.store._audit.assert_called_once()


# Queue/policy, exact import target and shared-parent selection guards precede any admission writes.
@pytest.mark.parametrize(
    "variant,code",
    [
        ("paused", "LIFECYCLE_PROVIDER_UNAVAILABLE"),
        ("unmapped", "ACCOUNTABILITY_MAPPING_REQUIRED"),
        ("blank", "VALID_CREATE_NAME_REQUIRED"),
        ("import", "EXACT_IMPORT_TARGET_REQUIRED"),
        ("foreign", "SIMULATED_CHILD_REQUIRED"),
        ("join", "AVAILABLE_SHARED_TENANCY_REQUIRED"),
        ("compartment", "SHARED_COMPARTMENT_NAME_REQUIRED"),
        ("parent", "EXISTING_PARENT_COMPARTMENT_REQUIRED"),
    ],
)
def test_admission_preconditions_before_writes(registry, variant, code):
    s, p = registry, person(registry)
    app, connection = service(s), database()
    action_name, fields = "create_tenancy", dict(name="child")
    if variant == "paused":
        app.policy_loader = Mock(return_value=SimpleNamespace(execution_paused=True))
    elif variant == "unmapped":
        p = p.model_copy(update={"lob_id": None})
    elif variant == "blank":
        fields["name"] = " "
    elif variant in {"import", "foreign"}:
        action_name = "import_tenancy"
        if variant == "foreign":
            fields["import_ocid"] = "ocid1.tenancy.oc1..foreign"
    else:
        action_name = "join_shared"
        fields = dict(tenancy_id=uuid4())
        if variant != "join":
            row, _ = attach(s, person(s, "one@example.test"), kind="shared")
            fields["tenancy_id"] = row["id"]
            if variant == "parent":
                fields["compartment_name"] = "Engineer"
    with pytest.raises(OrganizationConflict, match=code):
        app._admit(connection, s, command(s, p, action_name, **fields), p, None, principal(), NOW)
    connection.execute.assert_not_called()


# Exempt/offboard/return decisions preserve identity and protect existing associations and the root.
def test_metadata_decision_transitions_and_guards(registry):
    s, p = registry, person(registry)
    app, connection, actor = service(s), database(), principal().actor
    app._application_decision(
        connection, s, command(s, p, "no_tenancy_required"), p, None, actor, NOW
    )
    changed = connection.execute.call_args.args[0].compile().params
    assert changed["directory_status"] == "exempt" and not changed["setup_required"]
    with pytest.raises(OrganizationConflict, match="REVIEW_ALL"):
        app._application_decision(
            connection, s, command(s, p, "offboard_person"), p, None, actor, NOW
        )
    root = person(s, "root@example.test")
    with pytest.raises(OrganizationConflict, match="ROOT_PROTECTED"):
        app._application_decision(
            connection, s, command(s, root, "offboard_person"), root, None, actor, NOW
        )
    with pytest.raises(OrganizationConflict, match="IGNORE_REQUIRES"):
        app._application_decision(connection, s, command(s, p, "ignore"), p, None, actor, NOW)
    lob = review(s, p, "LOB_MAPPING_REVIEW")
    config = app._application_decision(connection, s, command(s, p, "ignore"), p, lob, actor, NOW)
    assert config.review_decisions[-1].disposition == "ignored" and config.id != s.config.id
    s.controls[p.id]["directory_status"] = "exempt"
    app._application_decision(connection, s, command(s, p, "reonboard"), p, None, actor, NOW)
    assert connection.execute.call_args.args[0].compile().params["setup_required"] is True
    app._application_decision(connection, s, command(s, p, "mark_returned"), p, None, actor, NOW)
    assert connection.execute.call_args.args[0].compile().params["directory_status"] == "included"
    s.supplied.remove(p.email)
    with pytest.raises(OrganizationConflict, match="SOURCE_PRESENT"):
        app._application_decision(
            connection, s, command(s, p, "mark_returned"), p, None, actor, NOW
        )
    attach(s, p)
    with pytest.raises(OrganizationConflict, match="REONBOARD"):
        app._application_decision(connection, s, command(s, p, "reonboard"), p, None, actor, NOW)


# Request replay accepts only the original hash and keeps metadata-only receipts independent of
# heads.
def test_request_receipts_and_conflicting_reuse(registry):
    from otm.operations.contracts import canonical_hash
    from otm.storage.admission import RequestConflict
    from otm.tenancies.contracts import ActionReceipt

    s, p = registry, person(registry)
    app, connection, actor = service(s), database(), principal().actor
    cmd = command(s, p, "create_tenancy", name="child")
    row = dict(
        id=uuid4(),
        state="queued",
        accepted_at=NOW,
        request_digest=canonical_hash(cmd.model_dump(mode="json")),
    )
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    assert app._replay(connection, s.workspace, actor, cmd).operation_id == row["id"]
    row["request_digest"] = "different"
    with pytest.raises(RequestConflict):
        app._replay(connection, s.workspace, actor, cmd)
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    receipt = ActionReceipt(
        operation_id=None, state="succeeded", provider_mode="application", accepted_at=NOW
    )
    saved = dict(
        request_digest=canonical_hash(cmd.model_dump(mode="json")),
        receipt=receipt.model_dump(mode="json"),
    )
    connection.execute.return_value.scalar_one_or_none.return_value = saved
    assert app._replay(connection, s.workspace, actor, cmd) == receipt
    saved["request_digest"] = "different"
    with pytest.raises(RequestConflict):
        app._replay(connection, s.workspace, actor, cmd)
    connection.execute.return_value.scalar_one_or_none.return_value = None
    assert app._replay(connection, s.workspace, actor, cmd) is None


# Worker verifies immutable association bindings, role and child scope again after administrator
# admission.
def test_worker_frozen_association_and_promotion_checks(registry):
    s, p = registry, person(registry)
    app = service(s)
    row, link = attach(s, p)
    plan = app._plan(s, command(s, p, "delete_tenancy", tenancy_id=row["id"]), p)
    op = uuid4()
    s.controls[p.id]["pending_operation_id"] = op
    row["operation_id"] = op
    worker = OrganizationLifecycleWorker(
        Mock(), s.workspace, Mock(return_value=NOW), Mock(), app.facade
    )
    frozen = intent(s, app, p, action="delete_tenancy", associations=plan)
    worker._validate(s, frozen, op)
    link["user_ocid"] = "ocid1.user.oc1..different"
    with pytest.raises(LifecycleBlocked, match="TARGET_CHANGED"):
        worker._validate(s, frozen, op)
    link["user_ocid"] = plan[0].user_ocid
    s.people[p.id] = p.model_copy(update={"known_manager": True})
    with pytest.raises(LifecycleBlocked):
        worker._validate(s, frozen, op)
    s.people[p.id] = p
    row["kind"] = "shared"
    with pytest.raises(LifecycleBlocked):
        worker._validate(s, frozen, op)


# Publication rejects incomplete/foreign provider read-back before emitting any success or
# registry write.
def test_worker_binding_publication_and_verified_deletion(registry):
    from otm.providers.lifecycle import LifecycleCompletion

    s, p = registry, person(registry)
    app, connection, op = service(s), database(), uuid4()
    worker = OrganizationLifecycleWorker(
        Mock(), s.workspace, Mock(return_value=NOW), Mock(), app.facade
    )
    frozen = intent(s, app, p, pending_association_id=uuid4(), pending_tenancy_id=uuid4())
    with pytest.raises(LifecycleBlocked):
        worker._publish(connection, s, frozen, LifecycleCompletion(), op, NOW)
    connection.execute.assert_not_called()
    connection.execute.return_value.first.return_value = (uuid4(),)
    worker._publish(connection, s, frozen, app.facade.apply(frozen), op, NOW)
    updates = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_update", False)
    ]
    assert any(values.get("status") == "active" and values.get("user_ocid") for values in updates)
    connection.reset_mock()
    row, link = attach(s, p)
    plan = app._plan(s, command(s, p, "delete_tenancy", tenancy_id=row["id"]), p)
    deleting = intent(s, app, p, action="delete_tenancy", associations=plan)
    connection.execute.return_value.first.return_value = None
    worker._publish(connection, s, deleting, LifecycleCompletion(), op, NOW)
    updates = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_update", False)
    ]
    assert any(values.get("directory_status") == "offboarded" for values in updates)
    assert any(values.get("status") == "terminated" for values in updates)
    worker._finish(
        connection,
        dict(current_intent_event_id=uuid4(), revision=1),
        deleting,
        op,
        NOW,
        "SIMULATED_LIFECYCLE_VERIFIED",
        "succeeded",
        True,
    )
    assert any(
        getattr(call.args[0], "is_insert", False)
        and call.args[0].table.name == "otm_operation_step"
        for call in connection.execute.call_args_list
    )


# Prepared graph changes produce durable episodes and one compact history item per changed person.
def test_review_reconciliation_baseline_changes_and_persistence(registry):
    from otm.organization.reviews import reconcile_reviews

    s, p = registry, person(registry)
    connection = database()
    connection.execute.return_value.mappings.side_effect = [
        list_result(s.controls.values()),
        list_result(()),
    ]
    candidate = SimpleNamespace(issues=(("TOP_MANAGER_MISMATCH", p.email),))
    reconcile_reviews(
        connection,
        s.workspace,
        s.head,
        None,
        candidate,
        s.config,
        supplied=s.supplied,
        at=NOW,
        baseline=True,
    )
    inserts = [
        c.args[0].compile().params
        for c in connection.execute.call_args_list
        if getattr(c.args[0], "is_insert", False)
    ]
    assert {r["kind"] for r in inserts} == {"TOP_MANAGER_MISMATCH", "ORGANIZATION_BASELINE"}
    existing = review(s, p, "TOP_MANAGER_MISMATCH", category="informational")
    s.controls[p.id].update(setup_required=True, setup_episode_id=uuid4())
    modified = p.model_copy(update={"full_name": "Renamed engineer"})
    head = s.head.model_copy(
        update={"people": tuple(modified if q.id == p.id else q for q in s.head.people)}
    )
    connection = database()
    connection.execute.return_value.mappings.side_effect = [
        list_result(s.controls.values()),
        list_result((existing,)),
    ]
    reconcile_reviews(
        connection,
        s.workspace,
        head,
        s.head,
        SimpleNamespace(issues=()),
        s.config,
        supplied=s.supplied,
        at=NOW + timedelta(seconds=1),
    )
    statements = [c.args[0].compile().params for c in connection.execute.call_args_list]
    assert any(r.get("kind") == "TENANCY_SETUP_REVIEW" for r in statements)
    assert any(r.get("kind") == "METADATA_UPDATED" for r in statements)
    assert any(r.get("resolution") == "source_corrected" for r in statements)
    connection = database()
    connection.execute.return_value.mappings.side_effect = [
        list_result(s.controls.values()),
        list_result((existing,)),
    ]
    reconcile_reviews(
        connection,
        s.workspace,
        s.head,
        s.head,
        candidate,
        s.config,
        supplied=s.supplied,
        at=NOW + timedelta(seconds=2),
    )
    assert any(
        c.args[0].compile().params.get("last_seen_at") == NOW + timedelta(seconds=2)
        for c in connection.execute.call_args_list
    )


# Mapping result doubles model SQL boundary results while leaving all reconciliation logic real.
def list_result(rows):
    result = database()
    result.__iter__.return_value = iter(rows)
    result.all.return_value = list(rows)
    return result


# The explicit absence-to-return rule differs from continuous-presence deletion and stable
# exemptions.
def test_managed_directory_return_and_exemption_rules(registry):
    from otm.organization.reviews import directory_transitions

    s, p = registry, person(registry)
    connection = database()
    s.controls[p.id].update(
        directory_status="offboarded", removed_capture_at=NOW - timedelta(days=1)
    )
    connection.execute.return_value.mappings.return_value = list_result(s.controls.values())
    changed = directory_transitions(connection, s.workspace, s.head, s.head, s.supplied)
    assert changed[p.id]["setup_required"] and changed[p.id]["directory_status"] == "included"
    s.controls[p.id].update(directory_status="exempt", removed_capture_at=None)
    connection = database()
    connection.execute.return_value.mappings.return_value = list_result(s.controls.values())
    assert (
        directory_transitions(connection, s.workspace, s.head, s.head, s.supplied)[p.id][
            "directory_status"
        ]
        == "exempt"
    )
    assert connection.execute.call_count == 1


# Public read services perform scope authorization before resolving registry details or optional
# parents.
def test_read_services_empty_directory_and_detail(registry):
    from contextlib import nullcontext

    s, p = registry, person(registry)
    app, connection = service(s), database()
    app.store._principal.return_value = s.workspace
    connection.scalar.return_value = None
    with (
        patch("otm.tenancies.workflows.read_snapshot", return_value=nullcontext(connection)),
        patch("otm.tenancies.workflows.registry_state", return_value=s),
    ):
        assert app.reviews(principal(), ReviewQuery()).total == 0
        assert app.tenancies(principal(), TenancyQuery()).total == 0
        assert app.preview(principal(), p.id).person.id == p.id
        with pytest.raises(OrganizationConflict, match="TENANCY_NOT_FOUND"):
            app.tenancy_detail(principal(), uuid4())
        row, _ = attach(s, p)
        assert len(app.tenancy_detail(principal(), row["id"]).compartment_parents) == 3
        connection.scalar.return_value = s.head.id
        assert app.tenancies(principal(), TenancyQuery()).total == 1
        assert app.reviews(principal(), ReviewQuery()).total == 0


# Resolve each physical table into the one coherent snapshot used by all workflow previews.
def test_registry_snapshot_loads_scoped_rows(registry):
    from otm.tenancies.directory import registry_state

    s, p = registry, person(registry)
    connection = database()
    header = dict(
        applied_version_id=s.head.id,
        proposed_version_id=s.context.proposed_version_id,
        configuration_id=s.config.id,
        configuration=s.config.model_dump(mode="json"),
        registry_revision=1,
    )
    first = database()
    first.one_or_none.return_value = header
    connection.execute.return_value.mappings.side_effect = [
        first,
        list_result(s.controls.values()),
        list_result(()),
        list_result(()),
        list_result(()),
        list_result(
            [
                dict(
                    id=s.head.id,
                    feed_id=s.head.snapshot_id,
                    base_version_id=None,
                    configuration=s.config.model_dump(mode="json"),
                )
            ]
        ),
        list_result(()),
        first,
    ]
    first.one_or_none.side_effect = [header, None]
    connection.execute.return_value.scalar_one.return_value = {"records": [{"email": p.email}]}
    with patch("otm.tenancies.directory.SqlOrganizationStore._revision", return_value=s.head):
        loaded = registry_state(connection, s.workspace)
    assert loaded.supplied == {p.email} and loaded.context == s.context
    connection = database()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    with pytest.raises(OrganizationConflict, match="FEED_REQUIRED"):
        registry_state(connection, s.workspace)


# Application-only acceptance writes a receipt and advances context without enqueuing provider work.
def test_application_action_atomic_entry_and_replay(registry):
    from contextlib import nullcontext

    s, p = registry, person(registry)
    app, connection = service(s), database()
    app.store._write.return_value = nullcontext((connection, s.workspace, NOW))
    cmd = command(s, p, "no_tenancy_required")
    with (
        patch("otm.tenancies.workflows.registry_state", return_value=s),
        patch.object(app, "_replay", return_value=None),
        patch.object(app, "_reconcile_current") as refresh,
    ):
        receipt = app.act(principal(), cmd)
        assert receipt.provider_mode == "application" and receipt.operation_id is None
        refresh.assert_called_once()
        app.enqueuer.enqueue.assert_not_called()
        with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
            app.act(
                principal(),
                cmd.model_copy(
                    update={"context": s.context.model_copy(update={"registry_revision": 9})}
                ),
            )
        s.controls[p.id]["pending_operation_id"] = uuid4()
        with pytest.raises(OrganizationConflict, match="ACTION_UNAVAILABLE"):
            app.act(principal(), cmd)
    with patch.object(app, "_replay", return_value=receipt):
        assert app.act(principal(), cmd) == receipt


# Identity merge keeps the absent stable identifier while rebasing configuration references
# explicitly.
def test_identity_merge_unit_preserves_survivor_and_rejects_busy_pair(registry):
    s, p = registry, person(registry)
    q = person(s, "delegate@example.test")
    old = p.model_copy(update={"absence_review": True})
    s.people[p.id] = old
    s.supplied.remove(p.email)
    review(s, old, "PERSON_ABSENCE_REVIEW")
    review(s, q)
    app, connection = service(s), database()
    cmd = command(s, old, "merge", partner_person_id=q.id)
    result = app._merge(connection, s, cmd, principal().actor, NOW)
    assert result.identity_merges[-1].person_id == old.id
    assert result.identity_merges[-1].new_email == q.email
    assert result.identity_merges[-1].retired_person_id == q.id
    s.controls[q.id]["pending_operation_id"] = uuid4()
    with pytest.raises(OrganizationConflict, match="REVIEWS_CHANGED"):
        app._merge(connection, s, cmd, principal().actor, NOW)
    with pytest.raises(OrganizationConflict, match="PAIR_REQUIRED"):
        app._merge(
            connection,
            s,
            cmd.model_copy(update={"partner_person_id": None}),
            principal().actor,
            NOW,
        )


# Worker verifies current grants/policy and records a closed outcome; arbitrary provider errors
# stay private.
@pytest.mark.parametrize(
    "variant,expected",
    [("ok", "succeeded"), ("revoked", "needs_attention"), ("paused", "needs_attention")],
)
def test_worker_transaction_dispatch_and_outcome(registry, variant, expected):
    from contextlib import nullcontext

    from otm.operations.contracts import IntentEventData, canonical_hash

    s, p = registry, person(registry)
    app, connection, op = service(s), database(), uuid4()
    frozen = intent(s, app, p)
    actor = principal().actor
    event = IntentEventData(intent=frozen, actor=actor).model_dump(mode="json")
    row = dict(
        id=op,
        workspace_id=s.workspace,
        responsible_actor_subject=actor.key,
        kind="organization_action",
        state="queued",
        current_intent_event_id=uuid4(),
        current_intent_revision=1,
        initiating_actor_subject=actor.key,
        revision=1,
    )
    header = database()
    header.one_or_none.return_value = dict(id=s.workspace)
    op_result = database()
    op_result.one_or_none.return_value = row
    event_result = database()
    event_result.one.return_value = dict(data=event, data_hash=canonical_hash(event))
    grant_result = database()
    grant_result.one_or_none.return_value = dict(
        status="revoked" if variant == "revoked" else "active",
        authorization_revision=frozen.authorization_revision,
        issuer=actor.issuer,
        subject=actor.subject,
    )
    connection.execute.return_value.scalar_one_or_none.return_value = uuid4()
    connection.execute.return_value.mappings.side_effect = [
        header,
        op_result,
        event_result,
        grant_result,
    ]
    loader = Mock(
        return_value=SimpleNamespace(execution_paused=variant == "paused", policy=app.policy)
    )
    worker = OrganizationLifecycleWorker(
        Mock(begin=Mock(return_value=nullcontext(connection))),
        s.workspace,
        Mock(return_value=NOW),
        loader,
        app.facade,
    )
    s.controls[p.id]["pending_operation_id"] = op
    with (
        patch("otm.tenancies.worker.require_transaction"),
        patch("otm.tenancies.worker.registry_state", return_value=s),
        patch.object(worker, "_publish") as publish,
    ):
        worker._run(op)
    assert publish.call_count == (1 if expected == "succeeded" else 0)
    outcomes = [
        c.args[0].compile().params
        for c in connection.execute.call_args_list
        if getattr(c.args[0], "is_insert", False) and c.args[0].table.name == "audit_event"
    ]
    assert len(outcomes) == 1
    assert (
        outcomes[0]["data"]["safe_code"]
        == {
            "ok": "SIMULATED_LIFECYCLE_VERIFIED",
            "revoked": "AUTHORIZATION_CHANGED",
            "paused": "LIFECYCLE_UNAVAILABLE",
        }[variant]
    )


# Cancellation restores the handed review and releases only unverified local reservations.
def test_local_cancellation_restores_original_review(registry):
    from otm.operations.contracts import IntentEventData, canonical_hash

    s, p = registry, person(registry)
    app, connection, op = service(s), database(), uuid4()
    row, link = attach(s, p, status="pending", operation_id=op, verified_at=None)
    link.update(status="pending", operation_id=op)
    s.controls[p.id]["pending_operation_id"] = op
    case = review(s, p, status="resolved", resolution="create_tenancy", operation_id=op)
    frozen = intent(s, app, p, pending_tenancy_id=row["id"], pending_association_id=link["id"])
    event = IntentEventData(intent=frozen, actor=principal().actor).model_dump(mode="json")
    operation_row = dict(
        kind="organization_action",
        state="queued",
        effect_knowledge="none",
        current_intent_event_id=uuid4(),
        revision=1,
    )
    selected = database()
    selected.one_or_none.return_value = operation_row
    selected_event = database()
    selected_event.one.return_value = dict(data=event, data_hash=canonical_hash(event))
    connection.execute.return_value.mappings.side_effect = [selected, selected_event]
    cmd = command(s, p, "cancel_simulation", operation_id=op)
    with patch.object(app, "_reconcile_current") as refresh:
        receipt = app._cancel_simulation(connection, s, cmd, p, principal().actor, NOW)
        assert receipt.state == "cancelled" and receipt.operation_id == op
        refresh.assert_called_once()
    params = [c.args[0].compile().params for c in connection.execute.call_args_list]
    assert any(values.get("status") == "open" for values in params)
    assert any(values.get("status") == "cancelled" for values in params)
    assert any(values.get("setup_required") is True for values in params)
    assert case["first_seen_at"] == NOW
    connection = database()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        **operation_row,
        "state": "succeeded",
    }
    with pytest.raises(OrganizationConflict, match="SIMULATION_ALREADY_FINISHED"):
        app._cancel_simulation(connection, s, cmd, p, principal().actor, NOW)


# Conditional configuration decisions re-evaluate the same source without changing the original
# capture time.
def test_reapply_preserves_source_time_and_republishes_both_heads(registry):
    from otm.organization.contracts import Intake

    s = registry
    app, connection = service(s), database()
    config = s.config.model_copy(update={"id": uuid4()})
    connection.execute.return_value.mappings.return_value.one.return_value = dict(
        id=s.head.snapshot_id
    )
    app.store._persist.side_effect = [
        s.head.model_copy(update={"id": uuid4()}),
        s.head.model_copy(update={"id": uuid4()}),
    ]
    source = Intake(envelope=envelope(), records=example_records())
    with (
        patch("otm.tenancies.workflows.source_intake", return_value=source),
        patch("otm.tenancies.workflows.reconcile_reviews") as reconcile,
    ):
        app._reapply(connection, s, config, NOW + timedelta(days=10))
        assert app.store._persist.call_count == 2
        assert reconcile.call_args.kwargs["supplied"] == s.supplied
        app._reconcile_current(connection, s, NOW)
        assert reconcile.call_count == 2
    with pytest.raises(ValueError, match="INVALID_ORGANIZATION"):
        app._reapply(connection, s, s.config, NOW)


# Safe HTTP failure translation never reflects raw provider, SQL or employee-supplied error text.
@pytest.mark.parametrize(
    "failure,status,code",
    [
        (OrganizationConflict("TENANCY_NOT_FOUND"), 404, "WORKSPACE_RECORD_NOT_FOUND"),
        (OrganizationConflict("ORGANIZATION_PREVIEW_CHANGED"), 409, "ORGANIZATION_PREVIEW_CHANGED"),
        (OrganizationConflict("private text"), 409, "ORGANIZATION_WORKFLOW_CHANGED"),
        (ValueError("private text"), 400, "INVALID_ORGANIZATION_ACTION"),
        (RuntimeError("private text"), 503, "ORGANIZATION_WORKFLOW_UNAVAILABLE"),
    ],
)
def test_workflow_http_failure_mapping(failure, status, code):
    import json

    from otm.tenancies.http import guarded

    response = guarded(Mock(side_effect=failure))
    assert response.status_code == status and json.loads(response.body)["code"] == code


# Only a later qualified return can settle the absence already handled by explicit offboarding.
def test_return_history_is_working_copy_and_preserves_predecessor(registry):
    from otm.organization.reviews import qualified_return_history

    s, p = registry, person(registry)
    absent = p.model_copy(update={"absence_review": True, "absence_review_since": NOW})
    prior = s.head.model_copy(
        update={"people": tuple(absent if q.id == p.id else q for q in s.head.people)}
    )
    candidate = prepare(
        example_records(),
        envelope("return", NOW + timedelta(seconds=1)),
        s.config,
        prior,
        NOW + timedelta(seconds=1),
    )
    connection = database()
    connection.execute.return_value.mappings.return_value = list_result(
        (dict(id=p.id, removed_capture_at=NOW),)
    )
    settled = qualified_return_history(connection, s.workspace, prior, candidate, s.supplied)
    assert (
        settled.id == prior.id
        and not next(q for q in settled.people if q.id == p.id).absence_review
    )
    assert next(q for q in prior.people if q.id == p.id).absence_review
    assert qualified_return_history(connection, s.workspace, None, candidate, s.supplied) is None
    assert (
        qualified_return_history(
            connection,
            s.workspace,
            prior,
            candidate.model_copy(update={"absence_eligible": False}),
            s.supplied,
        )
        is prior
    )


# Router wiring preserves queued/immediate semantics and bounds JSON before invoking app code.
def test_workflow_router_queued_and_metadata_http_receipts(registry):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from otm.tenancies.contracts import ActionReceipt
    from otm.tenancies.http import workflow_router

    s, p = registry, person(registry)
    app, boundary = FastAPI(), Mock()

    # Route adaptation is under test; production authorization is exercised separately.
    @app.middleware("http")
    async def attach_test_user(request, call_next):
        request.scope["user"] = object()
        return await call_next(request)

    app.include_router(workflow_router(boundary))
    client = TestClient(app)
    body = command(s, p, "create_tenancy", name="Synthetic child").model_dump(mode="json")
    boundary.act.return_value = ActionReceipt(
        operation_id=uuid4(), state="queued", provider_mode="simulated", accepted_at=NOW
    )
    assert client.post("/api/organization/actions", json=body).status_code == 202
    boundary.act.return_value = ActionReceipt(
        operation_id=None, state="succeeded", provider_mode="application", accepted_at=NOW
    )
    assert client.post("/api/organization/actions", json=body).status_code == 200
    before = boundary.act.call_count
    assert (
        client.post("/api/organization/actions", json={**body, "actor": "forged"}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/organization/actions",
            content=b"x" * 32769,
            headers={"Content-Type": "application/json"},
        ).status_code
        == 400
    )
    assert client.post("/api/organization/actions", content=b"{}").status_code == 400
    assert boundary.act.call_count == before


# Shared-only filtering precedes paging/search while overview cards continue counting all tenancies.
def test_shared_only_inventory_and_http_query(registry):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from otm.tenancies.http import workflow_router

    s, p = registry, person(registry)
    for _ in range(12):
        attach(s, p)
    shared, _ = attach(s, person(s, "one@example.test"), kind="shared", name="Shared team")
    result = tenancy_directory(s, TenancyQuery(shared_only=True, page=2))
    assert result.page == result.pages == result.total == 1
    assert result.items[0].id == shared["id"]
    assert (
        result.total_tenancies == 13 and result.individual_count == 12 and result.shared_count == 1
    )
    assert tenancy_directory(s, TenancyQuery(shared_only=True, query="unmatched")).total == 0
    app, boundary = FastAPI(), Mock()

    # This isolates HTTP query forwarding; the separate real browser suite covers authorization.
    @app.middleware("http")
    async def attach_test_user(request, call_next):
        request.scope["user"] = object()
        return await call_next(request)

    boundary.tenancies.side_effect = lambda user, query: tenancy_directory(s, query)
    app.include_router(workflow_router(boundary))
    with TestClient(app) as client:
        for checked, expected in ((True, 1), (False, 13)):
            response = client.get("/api/tenancies", params={"shared_only": str(checked).lower()})
            assert response.status_code == 200 and response.json()["total"] == expected
            assert boundary.tenancies.call_args.args[1].shared_only is checked
            assert response.json()["total_tenancies"] == 13


# Missing/invalid SDK creation inputs and an unsubscribed region fail before any operation write.
@pytest.mark.parametrize(
    "fields,code",
    [
        ({"home_region": "us-phoenix-1"}, "VALID_CREATE_NAME_REQUIRED"),
        ({"name": "UPPER", "home_region": "us-phoenix-1"}, "VALID_CREATE_NAME_REQUIRED"),
        ({"name": "not-valid", "home_region": "us-phoenix-1"}, "VALID_CREATE_NAME_REQUIRED"),
        ({"name": "validchild"}, "PARENT_SUBSCRIBED_REGION_REQUIRED"),
        (
            {"name": "validchild", "home_region": "unknown-region-1"},
            "PARENT_SUBSCRIBED_REGION_REQUIRED",
        ),
    ],
)
def test_required_creation_metadata_before_admission(registry, fields, code):
    s, p = registry, person(registry)
    app, connection = service(s), database()
    request = OrganizationAction(
        client_request_key=uuid4(),
        context=s.context,
        person_id=p.id,
        action="create_tenancy",
        **fields,
    )
    with pytest.raises(OrganizationConflict, match=code):
        app._admit(connection, s, request, p, None, principal(), NOW)
    connection.execute.assert_not_called()


# Requested region/name remain frozen inputs; the simulator reads them back without an Ashburn
# default.
def test_requested_metadata_and_registered_completion_link(registry):
    from otm.operations.contracts import IntentEventData, canonical_hash
    from otm.storage.operation_directory import SqlOperationDirectory

    s, p = registry, person(registry)
    app = service(s)
    frozen = intent(
        s, app, p, pending_tenancy_id=uuid4(), name="requestedchild", home_region="us-phoenix-1"
    )
    observed = app.facade.inspect_onboarding(frozen, app.facade.onboarding_handoff(frozen))
    assert observed.name == "requestedchild" and observed.home_region == "us-phoenix-1"
    imported = frozen.model_copy(
        update={"action": "import_tenancy", "name": None, "home_region": None}
    )
    imported_observed = app.facade.inspect_onboarding(
        imported, app.facade.onboarding_handoff(imported)
    )
    assert (
        imported_observed.name.startswith("sandbox-")
        and imported_observed.home_region == "us-ashburn-1"
    )
    data = IntentEventData(intent=frozen, actor=principal().actor).model_dump(mode="json")
    record = dict(
        id=uuid4(),
        workspace_id=s.workspace,
        kind="organization_action",
        state="succeeded",
        stage="Verified",
        accepted_at=NOW,
        updated_at=NOW,
        completed_at=NOW,
        initiating_actor_subject=principal().actor.key,
        intent_data=data,
        intent_hash=canonical_hash(data),
        registered_tenancy_id=frozen.pending_tenancy_id,
    )
    reader = SqlOperationDirectory(Mock())
    assert reader.summary(record).result_tenancy_id == frozen.pending_tenancy_id
    assert reader.summary({**record, "state": "queued"}).result_tenancy_id is None
    assert reader.summary({**record, "registered_tenancy_id": None}).result_tenancy_id is None
    sql = str(reader.selection().compile())
    assert "otm_tenancy.workspace_id = public.otm_operation.workspace_id" in sql
    assert "otm_tenancy.tenancy_ocid" in sql


# Local duplicate detection includes pending children and rejects before reservations/audit/jobs.
@pytest.mark.parametrize("status", ["active", "pending", "terminating"])
def test_duplicate_creation_name_rejected_without_writes(registry, status):
    s, p = registry, person(registry)
    attach(s, p, name="takenchild", status=status)
    app, connection = service(s), database()
    request = OrganizationAction(
        client_request_key=uuid4(),
        context=s.context,
        person_id=p.id,
        action="create_tenancy",
        name="takenchild",
        home_region="us-phoenix-1",
    )
    with pytest.raises(OrganizationConflict, match="DISTINCT_TENANCY_NAME_REQUIRED"):
        app._admit(connection, s, request, p, None, principal(), NOW)
    connection.execute.assert_not_called()
    app.enqueuer.enqueue.assert_not_called()


# Boundary replacement may not weaken source authority or be reused as an ordinary decision.
@pytest.mark.parametrize("damage", ["implicit", "authority", "source", "not_configuration_only"])
def test_root_replacement_reapply_preserves_other_source_policy(registry, damage):
    s = registry
    app = service(s)
    changes = {"root_email": "successor@example.test"}
    if damage == "authority":
        changes["authoritative"] = not s.config.policy.authoritative
    if damage == "source":
        changes["source_id"] = "another-source"
    config = s.config.model_copy(
        update={"id": uuid4(), "policy": s.config.policy.model_copy(update=changes)}
    )
    with pytest.raises(ValueError, match="INVALID_ORGANIZATION_DECISION_CONFIGURATION"):
        app._reapply(
            database(),
            s,
            config,
            NOW,
            allow_root_change=damage != "implicit",
            configuration_only=damage != "not_configuration_only",
        )


# Match current accountability identities, including the configured root exemption.
@pytest.mark.parametrize(
    "case,valid",
    [
        ("valid", True),
        ("root", True),
        ("none", False),
        ("missing", False),
        ("retired", False),
        ("wrong_leader", False),
        ("unresolved", False),
    ],
)
def test_current_accountability_predicate(registry, case, valid):
    from otm.organization.review_rules import has_valid_accountability

    p = person(registry, "root@example.test") if case == "root" else person(registry)
    changes = {
        "missing": {"lob_id": None},
        "retired": {"lob_id": "retired"},
        "wrong_leader": {"accountable_leader_email": "other@example.test"},
        "unresolved": {"ancestry": "incomplete"},
    }.get(case, {})
    p = None if case == "none" else p.model_copy(update=changes)
    assert has_valid_accountability(p, registry.config) is valid


# Corrected mapping conditions never settle lifecycle work or unmapped exceptions.
@pytest.mark.parametrize(
    "case,closes",
    [
        ("valid", True),
        ("renamed_target", True),
        ("root", True),
        ("missing", False),
        ("absence", False),
        ("setup", False),
    ],
)
def test_corrected_mapping_review_closure_is_narrow(registry, case, closes):
    from otm.organization.reviews import reconcile_reviews

    s = registry
    p = person(s, "root@example.test") if case == "root" else person(s)
    if case == "missing":
        p = p.model_copy(update={"lob_id": None})
    current = s.head.model_copy(
        update={"people": tuple(p if q.id == p.id else q for q in s.head.people)}
    )
    kind = {"absence": "PERSON_ABSENCE_REVIEW", "setup": "TENANCY_SETUP_REVIEW"}.get(
        case, "LOB_MAPPING_REVIEW"
    )
    row = review(s, p, kind)
    if case == "renamed_target":
        row["target"] = "previous.email@example.test"
    connection = database()
    connection.execute.return_value.mappings.side_effect = [
        list_result(s.controls.values()),
        list_result((row,)),
    ]
    reconcile_reviews(
        connection,
        s.workspace,
        current,
        current,
        SimpleNamespace(issues=()),
        s.config,
        supplied=s.supplied,
        at=NOW,
        configuration_only=True,
    )
    updates = [
        call.args[0].compile().params
        for call in connection.execute.call_args_list
        if getattr(call.args[0], "is_update", False)
    ]
    assert any(v.get("resolution") == "mapping_corrected" for v in updates) is closes


# Mapping repair gates provisioning, preserving cleanup and the root exemption.
def test_unmapped_preview_blocks_only_provisioning(registry):
    s = registry
    p = person(s)
    s.people[p.id] = p.model_copy(update={"lob_id": None, "accountable_leader_email": None})
    view = person_workflow(s, p.id, mode="simulated")
    assert view.mapping_required
    assert not {"create_tenancy", "import_tenancy", "join_shared"}.intersection(view.actions)
    attach(s, p)
    assert "delete_tenancy" in person_workflow(s, p.id, mode="simulated").actions
    s.people[p.id] = s.people[p.id].model_copy(update={"absence_review": True})
    assert "offboard_person" in person_workflow(s, p.id, mode="simulated").actions
    root = person(s, "root@example.test")
    assert not person_workflow(s, root.id, mode="simulated").mapping_required
    assert "create_tenancy" in person_workflow(s, root.id, mode="simulated").actions


# Latest-feed cards retain full history, ignore completed decisions and use pinned segment labels.
def test_latest_feed_information_and_readable_segment_history(registry):
    s = registry
    p = person(s)
    old_version, reapply = uuid4(), uuid4()
    s.feed_version_ids = {s.head.id, reapply}
    old = review(
        s, p, "METADATA_UPDATED", category="change", status="resolved", version_id=old_version
    )
    changed = review(
        s,
        p,
        "METADATA_UPDATED",
        category="change",
        status="resolved",
        version_id=reapply,
        data={
            "name": p.full_name,
            "email": p.email,
            "before": {"lob_id": "retired"},
            "after": {"lob_id": "replacement"},
        },
    )
    s.segment_labels[reapply] = {
        "before": {"retired": "Previous segment"},
        "after": {"replacement": "Replacement segment"},
    }
    warning = review(s, p, "TOP_MANAGER_MISMATCH", category="informational")
    review(s, p, "ANCESTRY_UNRESOLVED", category="informational", status="resolved")
    review(s, p, status="resolved")
    review(s, p)
    listing = review_directory(s, ReviewQuery(category="informational"))
    assert listing.informational_count == listing.total == 2
    assert {r.id for r in listing.items} == {changed["id"], warning["id"]}
    item = next(r for r in listing.items if r.id == changed["id"])
    assert item.data["before"]["lob_name"] == "Previous segment"
    assert item.data["after"]["lob_name"] == "Replacement segment"
    assert "lob_name" not in changed["data"]["before"]
    assert review_directory(s, ReviewQuery(query="unmatched")).informational_count == 2
    assert old["id"] in {r.id for r in review_directory(s, ReviewQuery(category="history")).items}
    assert listing.actionable_count == 1
    changed["data"]["before"]["lob_id"] = "unknown"
    changed["data"]["after"]["lob_id"] = None
    item = next(
        r
        for r in review_directory(s, ReviewQuery(category="informational")).items
        if r.id == changed["id"]
    )
    assert item.data["before"]["lob_name"] == "Unknown industry segment"
    assert item.data["after"]["lob_name"] is None


# Tenancy exemption must not be confused with removing the configured hierarchy root.
def test_configured_root_can_decline_tenancy_but_cannot_be_offboarded(registry):
    s = registry
    root = person(s, "root@example.test")
    app, connection = service(s), database()
    assert "no_tenancy_required" in person_workflow(s, root.id, mode="simulated").actions
    config = app._application_decision(
        connection, s, command(s, root, "no_tenancy_required"), root, None, principal().actor, NOW
    )
    assert config == s.config
    assert connection.execute.call_args.args[0].compile().params["directory_status"] == "exempt"
    absent = root.model_copy(update={"absence_review": True})
    s.people[root.id] = absent
    assert "offboard_person" not in person_workflow(s, root.id, mode="simulated").actions
    with pytest.raises(OrganizationConflict, match="ROOT_PROTECTED"):
        app._application_decision(
            connection,
            s,
            command(s, root, "offboard_person", confirm_no_associations=True),
            root,
            None,
            principal().actor,
            NOW,
        )


# Workflow units isolate recipe retrieval while separate baseline tests exercise SQL and validation.
@pytest.fixture(autouse=True)
def selected_recipe():
    from test_baseline_authoring import row
    from test_baseline_publication import published_row

    from otm.configuration.service import draft_view

    version = draft_view(published_row(row(), principal()))
    with patch("otm.tenancies.workflows.current_baseline", return_value=version):
        yield version
