"""Real review episodes, idempotent handoff, verified registry effects and identity decisions."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_organization_fixtures import example_records
from test_organization_storage_postgres import factors, intake, login_case, organization_case

from otm.operations.contracts import InspectionPolicy
from otm.organization.contracts import Record
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.tables import audit_event, operation, tenancy, tenancy_membership
from otm.tenancies.contracts import OrganizationAction
from otm.tenancies.views import ReviewQuery, TenancyQuery
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["organization_case", "factors", "login_case"]


# The same real session/store and scoped native queue back these production workflow scenarios.
@pytest.fixture
def workflow_case(organization_case):
    c = organization_case
    policy = InspectionPolicy(
        workspace_id=c.policy.workspace_id,
        policy_revision=uuid4(),
        organization_id="synthetic-org",
        parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        access_binding_id=uuid4(),
    )
    facade = SimulatedLifecycleFacade(policy)
    loader = Mock(return_value=SimpleNamespace(policy=policy, execution_paused=False))
    service = OrganizationWorkflows(
        c.store,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(c.policy.workspace_id), task=ORGANIZATION_TASK
        ),
        policy=policy,
        facade=facade,
        policy_loader=loader,
    )
    worker = OrganizationLifecycleWorker(c.engine, c.policy.workspace_id, c.clock, loader, facade)
    c.store.ingest(c.principal, intake(c))
    from test_baseline_authoring import content

    from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
    from otm.configuration.service import BaselineAuthoring
    from otm.providers.baseline_simulator import SimulatedBaselineQualifier

    recipes = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = recipes.save(c.principal, SaveBaselineDraft(content=content()))
    recipes.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    return SimpleNamespace(
        **vars(c), workflow=service, worker=worker, provider=facade, loader=loader
    )


# Each upload is a new source observation with explicit advance rather than a content deduplication.
def feed(c, records):
    c.clock.return_value += timedelta(seconds=10)
    return c.store.ingest(c.principal, intake(c, uuid4().hex, tuple(records)))


# Construct a real preview-bound command and preserve a request UUID across deliberate replay tests.
def action(c, person, action_name, *, review_id=None, **fields):
    preview = c.workflow.preview(c.principal, person, review_id)
    if action_name in {
        "offboard_person",
        "delete_tenancy",
        "remove_member",
        "transfer_owner",
        "merge",
    }:
        fields.setdefault("confirm_destructive", True)
    if action_name == "create_tenancy":
        fields.setdefault("name", "sandbox" + uuid4().hex[:12])
        fields.setdefault("home_region", "us-ashburn-1")
    command = OrganizationAction(
        client_request_key=uuid4(),
        context=preview.context,
        person_id=person,
        review_id=review_id,
        action=action_name,
        **fields,
    )
    return command, c.workflow.act(c.principal, command)


# Drive the real persisted handoff and explicit cleanup preview rather than bypassing guided setup.
def complete_setup(c, identifier, *, expected_phase="complete"):
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c.worker.run(identifier)
    handoff = c.workflow.onboarding(c.principal, identifier)
    assert handoff.phase == "handoff" and handoff.public_key is None
    c.workflow.onboarding_action(
        c.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=handoff.revision,
            action="verify_handoff",
            handoff=handoff.suggested_handoff,
        ),
    )
    c.worker.run(identifier)
    preview = c.workflow.onboarding(c.principal, identifier)
    assert preview.phase == "review" and preview.discovery is not None
    details = c.workflow.tenancy_detail(c.principal, preview.tenancy_id)
    assert details.tenancy.status == "pending" and details.onboarding_operation_id == identifier
    c.workflow.onboarding_action(
        c.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=preview.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    c.worker.run(identifier)
    final = c.workflow.onboarding(c.principal, identifier)
    assert final.phase == expected_phase
    if expected_phase == "complete":
        assert all(s.state == "verified" for s in final.checks)


# Baseline is quiet; later additions persist one inbox episode through repeat/no-op uploads.
def test_baseline_addition_and_async_create(workflow_case):
    c = workflow_case
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    history = c.workflow.reviews(c.principal, ReviewQuery(category="history"))
    assert [r.kind for r in history.items] == ["ORGANIZATION_BASELINE"]
    record = Record(
        source_record_id="new",
        full_name="New Engineer",
        email="new@example.test",
        manager_email="one@example.test",
    )
    rows = (*example_records(), record)
    feed(c, rows)
    first = c.workflow.reviews(c.principal, ReviewQuery()).items[0]
    assert first.kind == "TENANCY_SETUP_REVIEW"
    feed(c, rows)
    current = c.workflow.reviews(c.principal, ReviewQuery()).items[0]
    assert (
        current.id == first.id
        and current.first_seen_at == first.first_seen_at
        and current.last_seen_at > first.last_seen_at
    )
    command, receipt = action(
        c, current.person_id, "create_tenancy", review_id=current.id, name="newengineer"
    )
    assert receipt.state == "queued"
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    inventory = c.workflow.tenancies(c.principal, TenancyQuery())
    assert (
        inventory.total == 1
        and inventory.items[0].status == "pending"
        and inventory.items[0].member_count == 1
    )
    assert c.workflow.act(c.principal, command).operation_id == receipt.operation_id
    complete_setup(c, receipt.operation_id)
    c.worker.run(receipt.operation_id)
    inventory = c.workflow.tenancies(c.principal, TenancyQuery())
    assert inventory.items[0].status == "active" and inventory.items[0].member_count == 1
    assert inventory.items[0].operation_state == "succeeded"
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == receipt.operation_id)
            )
            == "succeeded"
        )
        assert (
            len(
                connection.execute(
                    select(tenancy_membership).where(
                        tenancy_membership.c.workspace_id == c.policy.workspace_id
                    )
                ).all()
            )
            == 1
        )
    feed(c, rows)
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0


# One person can own a child and belong to a shared child; offboarding retires only selected links.
def test_shared_membership_and_complete_offboarding(workflow_case):
    c = workflow_case
    people = {p.email: p for p in c.store.head(c.principal).people}
    engineer = people["engineer@example.test"].id
    owner = people["one@example.test"].id
    _, shared = action(c, owner, "create_tenancy", name="sharedteam", tenancy_kind="shared")
    complete_setup(c, shared.operation_id)
    shared_row = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, individual = action(c, engineer, "create_tenancy", name="personalengineer")
    complete_setup(c, individual.operation_id)
    _, joined = action(
        c,
        engineer,
        "join_shared",
        tenancy_id=shared_row.id,
        parent_compartment_ocid=shared_row.tenancy_ocid,
        compartment_name="engineersandbox",
    )
    c.worker.run(joined.operation_id)
    assert c.workflow.tenancy_detail(c.principal, shared_row.id).tenancy.member_count == 2
    feed(c, tuple(r for r in example_records() if r.email != "engineer@example.test"))
    review = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "PERSON_ABSENCE_REVIEW"
    )
    preview = c.workflow.preview(c.principal, engineer, review.id)
    choices = tuple(
        {"association_id": str(a.id), "action": "remove" if a.role == "member" else "delete"}
        for a in preview.associations
    )
    command = OrganizationAction.model_validate_json(
        __import__("json").dumps(
            {
                "client_request_key": str(uuid4()),
                "context": preview.context.model_dump(mode="json"),
                "person_id": str(engineer),
                "review_id": str(review.id),
                "action": "offboard_person",
                "confirm_destructive": True,
                "plan": choices,
                "confirm_shared": True,
            }
        )
    )
    receipt = c.workflow.act(c.principal, command)
    assert receipt.state == "queued" and c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    assert c.workflow.preview(c.principal, engineer).directory_status == "included"
    c.worker.run(receipt.operation_id)
    assert c.workflow.preview(c.principal, engineer).directory_status == "offboarded"
    detail = c.workflow.tenancy_detail(c.principal, shared_row.id)
    assert detail.tenancy.member_count == 1 and detail.tenancy.cleanup_count == 1
    assert any(a.cleanup_required and a.compartment_ocid for a in detail.memberships)
    feed(c, example_records())
    reviews = c.workflow.reviews(c.principal, ReviewQuery())
    assert any(r.kind == "TENANCY_SETUP_REVIEW" and r.person_id == engineer for r in reviews.items)


# Permanent LOB ignore survives new feeds; explicit no-tenancy exemptions require deliberate
# re-onboarding.
def test_ignore_no_tenancy_and_explicit_reonboarding(workflow_case):
    c = workflow_case
    rows = (
        *example_records(),
        Record(
            source_record_id="assistant",
            full_name="Executive Assistant",
            email="assistant@example.test",
            manager_email="root@example.test",
        ),
    )
    feed(c, rows)
    case = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "LOB_MAPPING_REVIEW"
    )
    _, receipt = action(c, case.person_id, "ignore", review_id=case.id)
    assert receipt.provider_mode == "application" and receipt.operation_id is None
    feed(c, rows)
    assert not any(
        r.kind == "LOB_MAPPING_REVIEW" for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )
    setup = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "TENANCY_SETUP_REVIEW"
    )
    command, saved = action(c, setup.person_id, "no_tenancy_required", review_id=setup.id)
    assert c.workflow.act(c.principal, command) == saved
    feed(c, rows)
    assert c.workflow.preview(c.principal, setup.person_id).directory_status == "exempt"
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    action(c, setup.person_id, "reonboard")
    assert any(
        r.kind == "TENANCY_SETUP_REVIEW"
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )


# The confirmed old identity survives while its personal/shared associations and immutable history
# remain.
def test_identity_merge_preserves_associations_and_closes_pair(workflow_case):
    c = workflow_case
    people = {p.email: p for p in c.store.head(c.principal).people}
    old = people["engineer@example.test"].id
    _, created = action(c, old, "create_tenancy", name="renamesurvivor")
    complete_setup(c, created.operation_id)
    before = c.workflow.preview(c.principal, old).associations
    renamed = Record(
        source_record_id="renamed",
        full_name="Renamed Engineer",
        email="renamed@example.test",
        manager_email="one@example.test",
    )
    rows = tuple(r for r in example_records() if r.email != "engineer@example.test") + (renamed,)
    feed(c, rows)
    cases = c.workflow.reviews(c.principal, ReviewQuery()).items
    absent = next(r for r in cases if r.kind == "PERSON_ABSENCE_REVIEW")
    new = next(r for r in cases if r.kind == "TENANCY_SETUP_REVIEW")
    action(c, old, "merge", review_id=absent.id, partner_person_id=new.person_id)
    current = c.store.head(c.principal)
    survivor = next(p for p in current.people if p.email == renamed.email)
    assert survivor.id == old and survivor.full_name == renamed.full_name
    assert c.workflow.preview(c.principal, old).associations[0].id == before[0].id
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    feed(c, rows)
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    assert c.store.head(c.principal).people
    # A merged survivor's original anchor email is not the current feed identity.
    _, deletion = action(c, old, "delete_tenancy", tenancy_id=before[0].tenancy_id)
    c.worker.run(deletion.operation_id)
    feed(c, tuple(r for r in rows if r.email != renamed.email))
    absence = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "PERSON_ABSENCE_REVIEW" and r.person_id == old
    )
    action(c, old, "offboard_person", review_id=absence.id, confirm_no_associations=True)
    assert c.workflow.preview(c.principal, old).directory_status == "offboarded"
    feed(c, rows)
    restored = c.workflow.preview(c.principal, old)
    assert restored.directory_status == "included" and restored.person.email == renamed.email
    assert restored.associations == ()
    assert (
        len(
            [
                r
                for r in c.workflow.reviews(c.principal, ReviewQuery()).items
                if r.kind == "TENANCY_SETUP_REVIEW" and r.person_id == old
            ]
        )
        == 1
    )


# Fixed source warnings close automatically and identical later recurrence begins a distinct dated
# episode.
def test_informational_warning_fix_and_recurrence(workflow_case):
    c = workflow_case
    wrong = tuple(
        r.model_copy(update={"reported_top_manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    feed(c, wrong)
    history = c.workflow.reviews(c.principal, ReviewQuery(category="history", page_size=50))
    first = next(r for r in history.items if r.kind == "TOP_MANAGER_MISMATCH")
    assert first.status == "open"
    feed(c, example_records())
    closed = next(
        r
        for r in c.workflow.reviews(
            c.principal, ReviewQuery(category="history", page_size=50)
        ).items
        if r.id == first.id
    )
    assert (
        closed.status == "resolved"
        and closed.resolution == "source_corrected"
        and closed.resolved_at
    )
    feed(c, wrong)
    warnings = [
        r
        for r in c.workflow.reviews(
            c.principal, ReviewQuery(category="history", page_size=50)
        ).items
        if r.kind == "TOP_MANAGER_MISMATCH"
    ]
    assert len(warnings) == 2 and len({r.id for r in warnings}) == 2


# A queued onboarding handoff cannot provision access after the employee departs in a newer census.
def test_departure_before_dispatch_is_visible_and_cancellable(workflow_case):
    c = workflow_case
    rows = (
        *example_records(),
        Record(
            source_record_id="new",
            full_name="New Engineer",
            email="new@example.test",
            manager_email="one@example.test",
        ),
    )
    feed(c, rows)
    setup = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "TENANCY_SETUP_REVIEW"
    )
    _, accepted = action(
        c, setup.person_id, "create_tenancy", review_id=setup.id, name="departurebeforeworker"
    )
    feed(c, example_records())
    c.worker.run(accepted.operation_id)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == accepted.operation_id)
            )
            == "needs_attention"
        )
        assert (
            connection.scalar(
                select(tenancy_membership.c.status).where(
                    tenancy_membership.c.person_id == setup.person_id
                )
            )
            == "pending"
        )
    command, cancelled = action(
        c, setup.person_id, "cancel_simulation", operation_id=accepted.operation_id
    )
    assert cancelled.state == "cancelled" and c.workflow.act(c.principal, command) == cancelled
    c.worker.run(accepted.operation_id)
    assert c.workflow.tenancies(c.principal, TenancyQuery()).total == 0
    assert any(
        r.kind == "PERSON_ABSENCE_REVIEW"
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )


# Unexpected facade failure rolls back reservations' publication and becomes a visible safe
# business result.
def test_worker_exception_and_cancel_restores_original_review(workflow_case):
    c = workflow_case
    rows = (
        *example_records(),
        Record(
            source_record_id="new",
            full_name="New Engineer",
            email="new@example.test",
            manager_email="one@example.test",
        ),
    )
    feed(c, rows)
    setup = c.workflow.reviews(c.principal, ReviewQuery()).items[0]
    _, accepted = action(
        c, setup.person_id, "create_tenancy", review_id=setup.id, name="providerfailure"
    )
    from unittest.mock import patch

    with patch(
        "otm.tenancies.onboarding.advance", side_effect=RuntimeError("private provider failure")
    ):
        c.worker.run(accepted.operation_id)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(operation.c.state).where(operation.c.id == accepted.operation_id)
            )
            == "needs_attention"
        )
    action(c, setup.person_id, "cancel_simulation", operation_id=accepted.operation_id)
    restored = c.workflow.reviews(c.principal, ReviewQuery()).items[0]
    assert restored.id == setup.id and restored.first_seen_at == setup.first_seen_at
    assert c.workflow.preview(c.principal, setup.person_id).pending_operation_id is None


# Shared owners transfer rather than delete during offboarding; promotion preserves member history.
def test_shared_owner_transfer_promotes_existing_member(workflow_case):
    c = workflow_case
    people = {p.email: p for p in c.store.head(c.principal).people}
    owner = people["engineer@example.test"].id
    recipient = people["delegate@example.test"].id
    _, created = action(c, owner, "create_tenancy", name="transferteam", tenancy_kind="shared")
    complete_setup(c, created.operation_id)
    row = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, joined = action(
        c,
        recipient,
        "join_shared",
        tenancy_id=row.id,
        parent_compartment_ocid=row.tenancy_ocid,
        compartment_name="delegate",
    )
    c.worker.run(joined.operation_id)
    _, transferred = action(
        c,
        owner,
        "transfer_owner",
        tenancy_id=row.id,
        recipient_person_id=recipient,
        confirm_shared=True,
    )
    c.worker.run(transferred.operation_id)
    detail = c.workflow.tenancy_detail(c.principal, row.id)
    assert detail.tenancy.owner_person_id == recipient and detail.tenancy.member_count == 1
    assert len(detail.memberships) == 3
    assert next(a for a in detail.memberships if a.status == "active").role == "owner"


# Source-present tenancy cleanup keeps directory presence and opens one new onboarding episode.
def test_present_last_tenancy_deletion_preserves_employee(workflow_case):
    c = workflow_case
    p = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, p.id, "create_tenancy", name="presentownerchild")
    complete_setup(c, receipt.operation_id)
    tenant = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, deleted = action(c, p.id, "delete_tenancy", tenancy_id=tenant.id)
    c.worker.run(deleted.operation_id)
    assert c.workflow.preview(c.principal, p.id).directory_status == "included"
    feed(c, example_records())
    first = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.person_id == p.id and r.kind == "TENANCY_SETUP_REVIEW"
    )
    feed(c, example_records())
    reviews = c.workflow.reviews(c.principal, ReviewQuery()).items
    assert [r.id for r in reviews if r.person_id == p.id and r.kind == "TENANCY_SETUP_REVIEW"] == [
        first.id
    ]
    assert c.workflow.tenancies(c.principal, TenancyQuery()).total == 0


# Cancelling an absence handoff restores its original episode; the queued job cannot act.
def test_cancel_absence_handoff_reopens_same_episode(workflow_case):
    c = workflow_case
    p = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, created = action(c, p.id, "create_tenancy", name="cancelabsencechild")
    complete_setup(c, created.operation_id)
    feed(c, tuple(r for r in example_records() if r.email != p.email))
    case = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "PERSON_ABSENCE_REVIEW"
    )
    preview = c.workflow.preview(c.principal, p.id, case.id)
    _, accepted = action(
        c,
        p.id,
        "offboard_person",
        review_id=case.id,
        plan=tuple({"association_id": a.id, "action": "delete"} for a in preview.associations),
    )
    assert c.workflow.reviews(c.principal, ReviewQuery()).total == 0
    _, cancelled = action(c, p.id, "cancel_simulation", operation_id=accepted.operation_id)
    assert cancelled.state == "cancelled"
    restored = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "PERSON_ABSENCE_REVIEW"
    )
    assert restored.id == case.id and restored.first_seen_at == case.first_seen_at
    c.worker.run(accepted.operation_id)
    assert c.workflow.tenancies(c.principal, TenancyQuery()).items[0].status == "active"


# Failed publication/retry retains known setup effects and refuses no-effect cancellation.
@pytest.mark.parametrize("failure_point", ["final", "partial_retry"])
def test_known_onboarding_effect_survives_failure(workflow_case, failure_point):
    from unittest.mock import patch

    from otm.providers.lifecycle import LifecycleBlocked
    from otm.storage.organization import OrganizationConflict
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c = workflow_case
    p = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, accepted = action(c, p.id, "create_tenancy")
    identifier = accepted.operation_id
    c.worker.run(identifier)
    view = c.workflow.onboarding(c.principal, identifier)
    c.workflow.onboarding_action(
        c.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=view.revision,
            action="verify_handoff",
            handoff=view.suggested_handoff,
        ),
    )
    c.worker.run(identifier)
    view = c.workflow.onboarding(c.principal, identifier)
    c.workflow.onboarding_action(
        c.principal,
        identifier,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=view.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    dispatch = c.provider.onboarding_step

    # Preserve one verified setup prefix, then fail its following independent signer check.
    def fail_after_automation(frozen, key, discovery):
        if key == "verify_automation":
            raise ValueError("synthetic failure")
        return dispatch(frozen, key, discovery)

    if failure_point == "final":
        # Initial admission/inspection are done; only the post-setup publication read-back fails.
        with (
            patch.object(c.provider, "onboarding_step"),
            patch.object(c.provider, "apply", side_effect=LifecycleBlocked("TARGET_CHANGED")),
        ):
            c.worker.run(identifier)
    else:
        with patch.object(c.provider, "onboarding_step", side_effect=fail_after_automation):
            c.worker.run(identifier)
        view = c.workflow.onboarding(c.principal, identifier)
        c.workflow.onboarding_action(
            c.principal,
            identifier,
            OnboardingCommand(
                client_request_key=uuid4(),
                revision=view.revision,
                action="start_setup",
                confirm_cleanup=True,
            ),
        )
        with patch.object(
            c.provider, "onboarding_step", side_effect=RuntimeError("synthetic retry failure")
        ):
            c.worker.run(identifier)
    with c.engine.connect() as connection:
        row = (
            connection.execute(select(operation).where(operation.c.id == identifier))
            .mappings()
            .one()
        )
        assert row["state"] == "needs_attention" and row["effect_knowledge"] == "known"
    preview = c.workflow.preview(c.principal, p.id)
    assert "cancel_simulation" not in preview.actions
    with pytest.raises(OrganizationConflict):
        action(c, p.id, "cancel_simulation", operation_id=identifier)


# A shared-child deletion removes every target link but preserves other tenancies and absence work.
def test_delete_shared_tenancy_complete_impact_and_replay(workflow_case):
    from otm.tenancies.deletion import TenancyDeletionCommand

    c = workflow_case
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    owner, engineer, delegate = (
        people[e] for e in ("one@example.test", "engineer@example.test", "delegate@example.test")
    )
    _, shared = action(c, owner, "create_tenancy", name="wholeshared", tenancy_kind="shared")
    complete_setup(c, shared.operation_id)
    row = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, personal = action(c, engineer, "create_tenancy", name="retainedpersonal")
    complete_setup(c, personal.operation_id)
    for member in (engineer, delegate):
        _, joined = action(
            c,
            member,
            "join_shared",
            tenancy_id=row.id,
            parent_compartment_ocid=row.tenancy_ocid,
            compartment_name="member",
        )
        c.worker.run(joined.operation_id)
    feed(c, tuple(r for r in example_records() if r.email != "engineer@example.test"))
    preview = c.workflow.deletion_preview(c.principal, row.id)
    assert len(preview.people) == 3 and preview.shared_warning and preview.manager_warning
    assert next(p for p in preview.people if p.person_id == engineer).other_tenancy_count == 1
    assert not next(p for p in preview.people if p.person_id == delegate).leaves_directory
    command = TenancyDeletionCommand(
        client_request_key=uuid4(),
        tenancy_id=row.id,
        context=preview.context,
        confirm_deletion=True,
        confirm_manager=True,
        confirm_shared=True,
    )
    receipt = c.workflow.delete_tenancy(c.principal, command)
    assert receipt.state == "queued"
    assert c.workflow.delete_tenancy(c.principal, command).operation_id == receipt.operation_id
    pending = c.workflow.tenancy_detail(c.principal, row.id)
    assert pending.tenancy.status == "terminating" and all(
        a.status == "removing" for a in pending.memberships
    )
    assert c.workflow.preview(c.principal, delegate).directory_status == "included"
    c.worker.run(receipt.operation_id)
    final = c.workflow.tenancy_detail(c.principal, row.id)
    assert final.tenancy.status == "terminated" and final.tenancy.operation_state == "succeeded"
    assert all(a.status == "removed" for a in final.memberships)
    assert c.workflow.preview(c.principal, delegate).directory_status == "included"
    assert c.workflow.preview(c.principal, owner).directory_status == "included"
    assert c.workflow.preview(c.principal, engineer).directory_status == "included"
    assert any(
        r.person_id == engineer and r.kind == "PERSON_ABSENCE_REVIEW"
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )
    assert c.workflow.tenancies(c.principal, TenancyQuery()).total == 1
    c.worker.run(receipt.operation_id)
    assert c.workflow.tenancies(c.principal, TenancyQuery()).total == 1


# A stale membership preview is rejected; no-effect cancellation restores all shared participants.
def test_delete_shared_tenancy_stale_preview_and_cancellation(workflow_case):
    from otm.storage.organization import OrganizationConflict
    from otm.tenancies.deletion import TenancyDeletionCommand

    c = workflow_case
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    owner, member = people["one@example.test"], people["engineer@example.test"]
    _, created = action(c, owner, "create_tenancy", name="cancelshared", tenancy_kind="shared")
    complete_setup(c, created.operation_id)
    row = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    preview = c.workflow.deletion_preview(c.principal, row.id)
    stale = TenancyDeletionCommand(
        client_request_key=uuid4(),
        tenancy_id=row.id,
        context=preview.context,
        confirm_deletion=True,
        confirm_manager=True,
        confirm_shared=True,
    )
    _, joined = action(
        c,
        member,
        "join_shared",
        tenancy_id=row.id,
        parent_compartment_ocid=row.tenancy_ocid,
        compartment_name="member",
    )
    c.worker.run(joined.operation_id)
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        c.workflow.delete_tenancy(c.principal, stale)
    command = stale.model_copy(
        update={"context": c.workflow.deletion_preview(c.principal, row.id).context}
    )
    receipt = c.workflow.delete_tenancy(c.principal, command)
    _, cancelled = action(c, owner, "cancel_simulation", operation_id=receipt.operation_id)
    assert cancelled.state == "cancelled"
    detail = c.workflow.tenancy_detail(c.principal, row.id)
    assert detail.tenancy.status == "active" and all(
        a.status == "active" for a in detail.memberships
    )
    assert c.workflow.preview(c.principal, member).pending_operation_id is None
    c.worker.run(receipt.operation_id)
    assert c.workflow.tenancy_detail(c.principal, row.id).tenancy.status == "active"


# End-to-end read-back retains the chosen name/region and publishes an exact successful result link.
def test_create_requested_metadata_and_result_link(workflow_case):
    from otm.storage.operation_directory import SqlOperationDirectory

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, accepted = action(
        c, person.id, "create_tenancy", name="requestedchild", home_region="us-phoenix-1"
    )
    reader = SqlOperationDirectory(c.engine)
    assert (
        reader.detail(c.policy.workspace_id, accepted.operation_id).operation.result_tenancy_id
        is None
    )
    complete_setup(c, accepted.operation_id)
    tenancy = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert tenancy.name == "requestedchild" and tenancy.home_region == "us-phoenix-1"
    assert (
        reader.detail(c.policy.workspace_id, accepted.operation_id).operation.result_tenancy_id
        == tenancy.id
    )
    assert reader.detail("foreign-workspace", accepted.operation_id) is None


# A known registry collision rolls back admission completely; editing the name accepts one new job.
@pytest.mark.parametrize("existing_state", ["pending", "active"])
def test_create_name_collision_then_corrected_retry(workflow_case, existing_state):
    from otm.storage.organization import OrganizationConflict

    c = workflow_case
    people = {p.email: p for p in c.store.head(c.principal).people}
    _, existing = action(
        c, people["engineer@example.test"].id, "create_tenancy", name="alreadytaken"
    )
    if existing_state == "active":
        complete_setup(c, existing.operation_id)
    recipient = people["delegate@example.test"].id
    preview = c.workflow.preview(c.principal, recipient)
    command = OrganizationAction(
        client_request_key=uuid4(),
        context=preview.context,
        person_id=recipient,
        action="create_tenancy",
        name="alreadytaken",
        home_region="us-phoenix-1",
        tenancy_kind="shared",
    )
    # Compare all affected authorities across the rejected transaction, not just the response.
    tables = (operation, audit_event, tenancy, tenancy_membership)
    with c.engine.connect() as connection:
        before = [
            connection.scalar(
                select(func.count()).select_from(t).where(t.c.workspace_id == c.policy.workspace_id)
            )
            for t in tables
        ]
    with pytest.raises(OrganizationConflict, match="DISTINCT_TENANCY_NAME_REQUIRED"):
        c.workflow.act(c.principal, command)
    with c.engine.connect() as connection:
        after = [
            connection.scalar(
                select(func.count()).select_from(t).where(t.c.workspace_id == c.policy.workspace_id)
            )
            for t in tables
        ]
    assert before == after
    assert c.workflow.preview(c.principal, recipient).context == preview.context
    corrected = command.model_copy(update={"client_request_key": uuid4(), "name": "availablechild"})
    accepted = c.workflow.act(c.principal, corrected)
    assert c.workflow.act(c.principal, corrected).operation_id == accepted.operation_id
    inventory = c.workflow.tenancies(c.principal, TenancyQuery())
    assert inventory.total == 2
    row = next(t for t in inventory.items if t.name == "availablechild")
    assert row.kind == "shared" and row.home_region == "us-phoenix-1"
    complete_setup(c, accepted.operation_id)


# A forged client cannot change the import target despite the read-only browser field.
def test_import_handoff_cannot_retarget_selected_tenancy(workflow_case):
    from otm.storage.organization import OrganizationConflict
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c = workflow_case
    p = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    target = "ocid1.tenancy.oc1..otmsimexactimport"
    _, accepted = action(c, p.id, "import_tenancy", import_ocid=target)
    c.worker.run(accepted.operation_id)
    view = c.workflow.onboarding(c.principal, accepted.operation_id)
    assert view.suggested_handoff.tenancy_ocid == target
    command = OnboardingCommand(
        client_request_key=uuid4(),
        revision=view.revision,
        action="verify_handoff",
        handoff=view.suggested_handoff.model_copy(
            update={"tenancy_ocid": "ocid1.tenancy.oc1..otmsimwrongtarget"}
        ),
    )
    with pytest.raises(OrganizationConflict, match="ONBOARDING_TARGET_CHANGED"):
        c.workflow.onboarding_action(c.principal, accepted.operation_id, command)
    current = c.workflow.onboarding(c.principal, accepted.operation_id)
    assert current.revision == view.revision and current.submitted_handoff is None
    correct = command.model_copy(update={"handoff": view.suggested_handoff})
    c.workflow.onboarding_action(c.principal, accepted.operation_id, correct)
    c.worker.run(accepted.operation_id)
    verified = c.workflow.onboarding(c.principal, accepted.operation_id)
    assert verified.phase == "review" and verified.discovery.tenancy_ocid == target


# Repeated deliveries refresh live warnings while earlier baseline/metadata stays historical.
def test_latest_feed_information_is_scoped_by_feed_provenance(workflow_case):
    c = workflow_case
    query = ReviewQuery(category="informational", page_size=50)
    assert [r.kind for r in c.workflow.reviews(c.principal, query).items] == [
        "ORGANIZATION_BASELINE"
    ]
    wrong = tuple(
        r.model_copy(update={"reported_top_manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    feed(c, wrong)
    first = c.workflow.reviews(c.principal, query)
    assert first.total == first.informational_count == 1
    assert first.items[0].kind == "TOP_MANAGER_MISMATCH"
    feed(c, wrong)
    assert c.workflow.reviews(c.principal, query).items[0].id == first.items[0].id
    feed(c, example_records())
    assert c.workflow.reviews(c.principal, query).informational_count == 0
    assert c.workflow.reviews(c.principal, ReviewQuery(category="history")).total >= 2


# Exempting the current root closes onboarding without removing its hierarchy or future role health.
def test_root_tenancy_exemption_preserves_reporting_and_repeat_feeds(workflow_case):
    c = workflow_case
    root = next(p for p in c.store.head(c.principal).people if p.email == "root@example.test")
    command, saved = action(c, root.id, "no_tenancy_required")
    assert saved.provider_mode == "application" and c.workflow.act(c.principal, command) == saved
    feed(c, example_records())
    head = c.store.head(c.principal)
    assert next(p for p in head.people if p.id == root.id).ancestry == "root"
    assert c.workflow.preview(c.principal, root.id).directory_status == "exempt"
    assert not any(
        r.person_id == root.id for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )
    descendants = [p for p in head.people if p.accountable_leader_email]
    assert descendants and all(p.ancestry == "resolved" for p in descendants)
    from otm.organization.role_health import role_health

    config = c.store.inspection(c.principal)[0]
    assert all(
        r["status"] == "healthy"
        for r in role_health(
            config, {p.email: p for p in head.people}, {r.email for r in example_records()}
        )
    )
    action(c, root.id, "reonboard")
    assert c.workflow.preview(c.principal, root.id).directory_status == "included"


# Real guided handoff/blocked-retry work badges until completion; history filters never hide work.
def test_operation_badge_tracks_supported_workflow_actions(workflow_case):
    from otm.operations.views import OperationQuery
    from otm.storage.operation_directory import SqlOperationDirectory
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    reads = SqlOperationDirectory(c.engine)
    workspace = c.policy.workspace_id
    assert reads.directory(workspace, OperationQuery()).attention_count == 0
    c.worker.run(receipt.operation_id)
    handoff = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert handoff.available_actions == ("verify_handoff",)
    assert reads.directory(workspace, OperationQuery()).attention_count == 1
    assert (
        reads.directory(
            workspace, OperationQuery(state="succeeded", query="missing")
        ).attention_count
        == 1
    )
    assert reads.directory("foreign", OperationQuery()).attention_count == 0
    bad = handoff.suggested_handoff.model_copy(
        update={"bootstrap_user_ocid": "ocid1.user.oc1..otmsimbootstrapwrong"}
    )
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=handoff.revision,
            action="verify_handoff",
            handoff=bad,
        ),
    )
    c.worker.run(receipt.operation_id)
    blocked = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert blocked.state == "needs_attention" and blocked.available_actions == ("verify_handoff",)
    assert reads.directory(workspace, OperationQuery()).attention_count == 1
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=blocked.revision,
            action="verify_handoff",
            handoff=blocked.suggested_handoff,
        ),
    )
    c.worker.run(receipt.operation_id)
    review = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert review.available_actions == ("start_setup",)
    assert reads.directory(workspace, OperationQuery()).attention_count == 1
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=review.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    from unittest.mock import patch

    original = c.provider.onboarding_step

    # A failed required-access check after verified effects must retain the supported retry badge.
    def fail_required(intent, key, discovery):
        if key == "verify_required":
            raise ValueError("controlled required access failure")
        return original(intent, key, discovery)

    with patch.object(c.provider, "onboarding_step", side_effect=fail_required):
        c.worker.run(receipt.operation_id)
    partial = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert partial.state == "needs_attention" and partial.available_actions == ("start_setup",)
    assert "cancel_simulation" not in c.workflow.preview(c.principal, person.id).actions
    assert reads.directory(workspace, OperationQuery()).attention_count == 1
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=partial.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    c.worker.run(receipt.operation_id)
    assert reads.directory(workspace, OperationQuery()).attention_count == 0
    assert reads.detail(workspace, receipt.operation_id).operation.state == "succeeded"


# Unsupported waits and orphaned historical rows do not badge; an actual safe cancel still does.
def test_operation_badge_requires_pending_subject_and_supported_action(workflow_case):
    from sqlalchemy import update

    from otm.operations.views import OperationQuery
    from otm.storage.operation_directory import SqlOperationDirectory
    from otm.storage.tables import org_person

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    c.worker.run(receipt.operation_id)
    reads = SqlOperationDirectory(c.engine)
    workspace = c.policy.workspace_id
    with c.engine.begin() as connection:
        connection.execute(
            update(operation)
            .where(operation.c.id == receipt.operation_id)
            .values(wait_reason="unsupported_wait", effect_knowledge="known")
        )
    assert c.workflow.onboarding(c.principal, receipt.operation_id).available_actions == ()
    assert reads.directory(workspace, OperationQuery()).attention_count == 0
    with c.engine.begin() as connection:
        connection.execute(
            update(operation)
            .where(operation.c.id == receipt.operation_id)
            .values(effect_knowledge="none")
        )
    assert "cancel_simulation" in c.workflow.preview(c.principal, person.id).actions
    assert reads.directory(workspace, OperationQuery()).attention_count == 1
    with c.engine.begin() as connection:
        connection.execute(
            update(org_person).where(org_person.c.id == person.id).values(pending_operation_id=None)
        )
    assert reads.directory(workspace, OperationQuery()).attention_count == 0
    assert reads.detail(workspace, receipt.operation_id) is not None
