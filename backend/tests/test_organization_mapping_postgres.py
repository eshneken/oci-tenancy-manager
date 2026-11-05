"""Real mapping publication, independent role repair, immutable evidence and concurrent fences."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_organization_fixtures import example_records
from test_organization_storage_postgres import factors, intake, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, feed, workflow_case

from otm.organization.mapping import MappingService
from otm.organization.mapping_contracts import MappingApply, MappingRequest
from otm.organization.web import OrganizationWeb
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import (
    org_person,
    tenancy_membership,
)
from otm.tenancies.views import ReviewQuery, TenancyQuery
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["workflow_case", "organization_case", "factors", "login_case"]


# Bind only changed editable fields to a freshly read context; Apply always uses the actual preview.
def preview(c, transform=None):
    service = MappingService(c.store, c.config, c.workflow)
    state = service.read(c.principal)
    body = state.candidate.model_dump()
    if transform:
        transform(body)
    request = MappingRequest(
        context=state.context, candidate=type(state.candidate).model_validate(body)
    )
    return service, service.preview(c.principal, request)


# Use exact server values rather than substituting client-computed impact or fabricated authority.
def apply(c, service, view):
    return service.apply(
        c.principal,
        MappingApply(
            context=view.context, candidate=view.candidate, preview_token=view.preview_token
        ),
    )


# Initial setup is explicit; merely viewing or uploading never seeds from the private legacy file.
def test_initial_mapping_gate_typed_emails_and_stable_server_ids(login_case):
    from test_local_auth_postgres import command
    from test_organization_fixtures import example_config

    from otm.organization.mapping_contracts import MappingCandidate, MappingContext
    from otm.storage.organization import SqlOrganizationStore

    c = login_case
    issued = c.service.sign_in(command(c))
    principal = c.sessions.authenticate(issued.handle.get_secret_value())
    store = SqlOrganizationStore(c.engine, c.sessions, c.clock)
    config = example_config()
    web = OrganizationWeb(store, c.clock, config, workflows=OrganizationWorkflows(store))
    assert not web.mapping.read(principal).configured
    csv = b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nRoot,root@example.test,,\n"
    with pytest.raises(OrganizationConflict, match="NOT_CONFIGURED"):
        web.upload(principal, csv, c.clock(), uuid4(), True)
    assert not web.mapping.read(principal).configured
    candidate = MappingCandidate.model_validate_json(
        '{"root_email":"ROOT@example.test","segments":[{"label":"Industry","leader_email":"one@example.test","designee_emails":[]}]}'
    )
    checked = web.mapping.preview(
        principal, MappingRequest(context=MappingContext(), candidate=candidate)
    )
    assert not checked.has_feed and checked.roles[0].status == "not_verified"
    saved = web.mapping.apply(
        principal,
        MappingApply(
            context=checked.context,
            candidate=checked.candidate,
            preview_token=checked.preview_token,
        ),
    )
    assert saved.configured and saved.candidate.root_email == "root@example.test"
    first = saved.candidate.segments[0].id
    assert first is not None and first != "one"
    # Restarting composition with another bootstrap file does not replace saved database authority.
    changed = OrganizationWeb(
        store,
        c.clock,
        config.model_copy(update={"lobs": ()}),
        workflows=OrganizationWorkflows(store),
    )
    assert changed.mapping.read(principal).candidate == saved.candidate


# Label/nominee changes update directory and tenancy projections without moving owners or clocks.
@pytest.mark.parametrize("stale", [False, True])
def test_apply_immediate_versions_clocks_and_frozen_associations(workflow_case, stale):
    c = workflow_case
    owner = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, owner.id, "create_tenancy", name="mappedchild")
    complete_setup(c, receipt.operation_id)
    before = c.store.head(c.principal)
    with c.engine.connect() as connection:
        controls = [
            dict(r)
            for r in connection.execute(
                select(org_person).where(org_person.c.workspace_id == c.policy.workspace_id)
            ).mappings()
        ]
        links = [
            dict(r)
            for r in connection.execute(
                select(tenancy_membership).where(
                    tenancy_membership.c.workspace_id == c.policy.workspace_id
                )
            ).mappings()
        ]
    if stale:
        from test_local_auth_postgres import command

        c.clock.return_value += timedelta(days=3)
        issued = c.service.sign_in(command(c))
        c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    # This edit intentionally removes the last optional designee; the segment itself remains.
    service, view = preview(
        c, lambda body: body["segments"][0].update(label="Renamed Industry", designee_emails=())
    )
    assert view.affected_count == 3 and view.changes[0].before.id == view.changes[0].after.id
    saved = apply(c, service, view)
    after = c.store.head(c.principal)
    assert (
        after.snapshot_id == before.snapshot_id
        and after.source_captured_at == before.source_captured_at
    )
    assert after.id != before.id and after.configuration_id != before.configuration_id
    for p in after.people:
        old = next(o for o in before.people if o.id == p.id)
        for field in (
            "last_row_observed_at",
            "last_reference_observed_at",
            "last_source_capture_at",
            "last_qualified_census_at",
            "absence_review",
            "absence_review_since",
        ):
            assert getattr(p, field) == getattr(old, field)
    assert c.workflow.tenancies(c.principal, TenancyQuery()).items[0].lob_name == "Renamed Industry"
    with c.engine.connect() as connection:
        assert controls == [
            dict(r)
            for r in connection.execute(
                select(org_person).where(org_person.c.workspace_id == c.policy.workspace_id)
            ).mappings()
        ]
        assert links == [
            dict(r)
            for r in connection.execute(
                select(tenancy_membership).where(
                    tenancy_membership.c.workspace_id == c.policy.workspace_id
                )
            ).mappings()
        ]
        assert c.store._revision(connection, c.policy.workspace_id, before.id) == before
    assert saved.candidate.segments[0].id == c.config.lobs[0].id
    assert not service.read(c.principal).blockers


# Role repair and tenancy work are distinct episodes even for an absent manager without a tenancy.
@pytest.mark.parametrize("with_tenancy", [False, True])
def test_departed_multirole_no_tenancy_and_independent_repair(workflow_case, with_tenancy):
    c = workflow_case
    # Configure a leader as a nominee too; the delegate is nominated in two separate segments.
    service, view = preview(
        c,
        lambda body: [
            body["segments"][0].update(
                designee_emails=("one@example.test", "delegate@example.test")
            ),
            body["segments"][1].update(designee_emails=("delegate@example.test",)),
        ],
    )
    apply(c, service, view)
    people = {p.email: p for p in c.store.head(c.principal).people}
    if with_tenancy:
        _, receipt = action(c, people["one@example.test"].id, "create_tenancy", name="leaderchild")
        complete_setup(c, receipt.operation_id)
        _, nominee = action(
            c, people["delegate@example.test"].id, "create_tenancy", name="delegatechild"
        )
        complete_setup(c, nominee.operation_id)
    rows = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.manager_email == "one@example.test"
        else r
        for r in example_records()
        if r.email not in {"one@example.test", "delegate@example.test"}
    )
    feed(c, rows)
    expected = {
        ("LOB_LEADER_REVIEW", "one:one@example.test"),
        ("DESIGNEE_INVALID", "one:one@example.test"),
        ("DESIGNEE_INVALID", "one:delegate@example.test"),
        ("DESIGNEE_INVALID", "two:delegate@example.test"),
    }
    with c.engine.connect() as connection:
        from otm.storage.tables import org_recommendation

        reviews = [
            dict(r)
            for r in connection.execute(
                select(org_recommendation).where(
                    org_recommendation.c.workspace_id == c.policy.workspace_id,
                    org_recommendation.c.status == "open",
                )
            ).mappings()
        ]
    first = {(r["kind"], r["target"]): r["id"] for r in reviews}
    assert expected <= set(first)
    feed(c, rows)
    with c.engine.connect() as connection:
        repeated = {
            (r["kind"], r["target"]): r["id"]
            for r in connection.execute(
                select(org_recommendation).where(
                    org_recommendation.c.workspace_id == c.policy.workspace_id,
                    org_recommendation.c.status == "open",
                )
            ).mappings()
        }
    assert all(repeated[key] == first[key] for key in expected)
    # Offboarding settles only associations/directory and cannot acknowledge role eligibility.
    target = people["one@example.test"].id
    state = c.workflow.preview(c.principal, target)
    if with_tenancy:
        _, receipt = action(
            c,
            target,
            "offboard_person",
            plan=tuple(dict(association_id=a.id, action="delete") for a in state.associations),
            confirm_manager=True,
        )
        c.worker.run(receipt.operation_id)
    else:
        action(c, target, "offboard_person", confirm_no_associations=True)
    health = service.read(c.principal)
    assert any(r.email == "one@example.test" and r.status != "healthy" for r in health.roles)
    assert any(
        r.kind == "LOB_LEADER_REVIEW" for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )
    # Remove the defective segment and its nominations explicitly; another segment must remain.
    service, view = preview(c, lambda body: body.update(segments=(body["segments"][1].copy(),)))
    clean = view.candidate.model_dump()
    clean["segments"][0]["designee_emails"] = ()
    request = MappingRequest(
        context=view.context, candidate=type(view.candidate).model_validate(clean)
    )
    view = service.preview(c.principal, request)
    apply(c, service, view)
    assert not any(
        r.kind in {"LOB_LEADER_REVIEW", "DESIGNEE_INVALID"}
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )
    assert any(
        r.kind == "PERSON_ABSENCE_REVIEW" and r.email == "delegate@example.test"
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )


# Stale contexts, edited payloads, pending lifecycle and genuinely unapplied proposals fail closed.
def test_preview_fences_pending_work_concurrent_apply_and_rollback(workflow_case):
    c = workflow_case
    service, old = preview(c, lambda body: body["segments"][0].update(label="First"))
    _, changed = preview(c, lambda body: body["segments"][0].update(label="Second"))
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        apply(c, service, changed.model_copy(update={"preview_token": old.preview_token}))
    before = c.store.head(c.principal)
    with patch.object(c.store, "_audit", side_effect=RuntimeError("synthetic audit failure")):
        with pytest.raises(RuntimeError):
            apply(c, service, old)
    assert c.store.head(c.principal) == before

    # Exactly one concurrent Apply can advance this configuration/head context.
    def attempt():
        try:
            apply(c, service, old)
            return "applied"
        except OrganizationConflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["applied", "stale"]
    c.clock.return_value += timedelta(seconds=10)
    c.store.ingest(c.principal, intake(c, "unapplied", captured_at=c.clock()), stage_only=True)
    assert "UNAPPLIED_ORGANIZATION" in service.read(c.principal).blockers
    _, view = preview(c)
    with pytest.raises(OrganizationConflict, match="PENDING_WORK"):
        apply(c, service, view)


# Completed offboarding retains qualified renewal, but returning profiles must still pass each role.
@pytest.mark.parametrize("role", ["leader", "designee"])
@pytest.mark.parametrize("eligible", [False, True])
def test_qualified_role_return_after_completed_offboarding(workflow_case, role, eligible):
    c = workflow_case
    address = "one@example.test" if role == "leader" else "delegate@example.test"
    original = c.store.head(c.principal)
    person = next(p for p in original.people if p.email == address)
    rows = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if role == "leader" and r.manager_email == address
        else r
        for r in example_records()
        if r.email != address
    )
    feed(c, rows)
    action(c, person.id, "offboard_person", confirm_no_associations=True)
    service = MappingService(c.store, c.config, c.workflow)
    assert any(
        r.email == address and r.status != "healthy" for r in service.read(c.principal).roles
    )
    returned = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.email == address and not eligible
        else r
        for r in example_records()
    )
    feed(c, returned)
    state = c.workflow.preview(c.principal, person.id)
    assert state.directory_status == "included" and state.source_present
    head = c.store.head(c.principal)
    renewed = next(p for p in head.people if p.id == person.id)
    assert not renewed.absence_review and renewed.absence_review_since is None
    assert any(
        r.kind == "TENANCY_SETUP_REVIEW" and r.person_id == person.id
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )
    health = [r for r in service.read(c.principal).roles if r.email == address]
    assert health and all((r.status == "healthy") == eligible for r in health)


# Mapping repair cannot change an accepted target; pending lifecycle work must be settled first.
def test_pending_lifecycle_mapping_guard_and_retired_ids(workflow_case):
    c = workflow_case
    service, view = preview(c, lambda body: body.update(segments=(body["segments"][0],)))
    retired = c.config.lobs[1].id
    saved = apply(c, service, view)
    body = saved.candidate.model_dump()
    body["segments"] = (
        *body["segments"],
        dict(id=retired, label="Retired", leader_email="two@example.test", designee_emails=()),
    )
    with pytest.raises(OrganizationConflict, match="SEGMENT_CHANGED"):
        service.preview(
            c.principal,
            MappingRequest(
                context=saved.context, candidate=type(saved.candidate).model_validate(body)
            ),
        )
    owner = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, accepted = action(c, owner.id, "create_tenancy", name="pendingmapping")
    service, view = preview(c, lambda body: body["segments"][0].update(label="Blocked change"))
    assert "PENDING_LIFECYCLE" in view.blockers
    with c.engine.connect() as connection:
        from otm.storage.tables import operation

        pointer = connection.execute(
            select(operation.c.current_intent_event_id, operation.c.current_intent_revision).where(
                operation.c.id == accepted.operation_id
            )
        ).one()
    with pytest.raises(OrganizationConflict, match="PENDING_WORK"):
        apply(c, service, view)
    with c.engine.connect() as connection:
        assert (
            pointer
            == connection.execute(
                select(
                    operation.c.current_intent_event_id, operation.c.current_intent_revision
                ).where(operation.c.id == accepted.operation_id)
            ).one()
        )


# A later CSV or reviewed association decision invalidates an earlier exact mapping preview.
def test_feed_registry_and_postimport_root_fences(workflow_case):
    c = workflow_case
    service, view = preview(c)
    feed(c, example_records())
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        apply(c, service, view)
    service, view = preview(c)
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    action(c, person.id, "no_tenancy_required")
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        apply(c, service, view)
    state = service.read(c.principal)
    root_changed = state.candidate.model_copy(update={"root_email": "different@example.test"})
    with pytest.raises(OrganizationConflict, match="ROOT_FIXED"):
        service.preview(c.principal, MappingRequest(context=state.context, candidate=root_changed))


# A source-present but newly ineligible leader triggers role repair rather than a false departure.
def test_replacement_follows_source_graph_and_keeps_segment_identity(workflow_case):
    c = workflow_case
    rows = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.email == "one@example.test"
        else r.model_copy(update={"manager_email": "root@example.test"})
        if r.email == "delegate@example.test"
        else r
        for r in example_records()
    )
    feed(c, rows)
    assert not any(p.absence_review for p in c.store.head(c.principal).people)
    service, view = preview(
        c,
        lambda body: body["segments"][0].update(
            leader_email="delegate@example.test", label="Replacement Segment"
        ),
    )
    assert not view.blockers
    saved = apply(c, service, view)
    assert saved.candidate.segments[0].id == c.config.lobs[0].id
    head = c.store.head(c.principal)
    engineer = next(p for p in head.people if p.email == "engineer@example.test")
    assert engineer.manager_email == "one@example.test" and engineer.lob_id == "two"
    assert next(p for p in head.people if p.email == "delegate@example.test").lob_id == "one"


# Hidden no-tenancy profiles still expose segment repairs after qualified departure.
def test_exempt_designee_departure_remains_visible_and_cannot_be_acknowledged(workflow_case):
    from otm.tenancies.contracts import OrganizationAction

    c = workflow_case
    p = next(p for p in c.store.head(c.principal).people if p.email == "delegate@example.test")
    action(c, p.id, "no_tenancy_required")
    feed(c, tuple(r for r in example_records() if r.email != p.email))
    rows = c.workflow.reviews(c.principal, ReviewQuery()).items
    role = next(r for r in rows if r.kind == "DESIGNEE_INVALID" and r.person_id == p.id)
    service = MappingService(c.store, c.config, c.workflow)
    assert any(
        r.email == p.email and r.status == "departed" for r in service.read(c.principal).roles
    )
    request = c.workflow.preview(c.principal, p.id, role.id)
    assert "resolve" not in request.actions
    with pytest.raises(OrganizationConflict):
        c.workflow.act(
            c.principal,
            OrganizationAction(
                client_request_key=uuid4(),
                context=request.context,
                person_id=p.id,
                review_id=role.id,
                action="resolve",
            ),
        )
    service, view = preview(c, lambda body: body["segments"][0].update(designee_emails=()))
    apply(c, service, view)
    assert not any(
        r.kind == "DESIGNEE_INVALID" and r.person_id == p.id
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
    )


# Root replacement preserves associations and clocks, then accepts the corrected graph.
def test_root_replacement_audit_graph_repair_and_old_root_cleanup(workflow_case):
    from otm.organization.contracts import Record
    from otm.storage.tables import audit_event

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy", name="formerrootchild")
    complete_setup(c, receipt.operation_id)
    before = c.store.head(c.principal)
    with c.engine.connect() as connection:
        links = [dict(row) for row in connection.execute(select(tenancy_membership)).mappings()]
    service = MappingService(c.store, c.config, c.workflow)
    state = service.read(c.principal)
    request = MappingRequest(
        context=state.context,
        candidate=state.candidate.model_copy(update={"root_email": "successor@example.test"}),
        change_root=True,
    )
    view = service.preview(c.principal, request)
    assert not view.root_present and view.unresolved_count == len(example_records())
    assert not view.blockers
    command = MappingApply(**request.model_dump(), preview_token=view.preview_token)
    saved = service.apply(c.principal, command)
    assert saved.candidate.root_email == "successor@example.test"
    after = c.store.head(c.principal)
    assert after.snapshot_id == before.snapshot_id
    assert after.source_captured_at == before.source_captured_at
    for p in before.people:
        updated = next(n for n in after.people if n.id == p.id)
        for field in (
            "absence_review",
            "absence_review_since",
            "last_row_observed_at",
            "last_reference_observed_at",
            "last_qualified_census_at",
        ):
            assert getattr(updated, field) == getattr(p, field)
    with c.engine.connect() as connection:
        assert links == [
            dict(row) for row in connection.execute(select(tenancy_membership)).mappings()
        ]
        events = connection.execute(select(audit_event.c.data)).scalars().all()
        assert any(
            e.get("mapping_root_before") == "root@example.test"
            and e.get("mapping_root_after") == "successor@example.test"
            for e in events
        )
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        service.apply(c.principal, command)
    # A second configuration-only edit uses the same old feed without manufacturing absence.
    service, again = preview(c, lambda body: body["segments"][0].update(label="Retained segment"))
    apply(c, service, again)
    rows = tuple(
        r.model_copy(update={"manager_email": "successor@example.test"})
        if r.email in ("one@example.test", "two@example.test")
        else r
        for r in example_records()
        if r.email != "root@example.test"
    ) + (
        Record(
            source_record_id="successor",
            full_name="Successor",
            email="successor@example.test",
            manager_email=None,
        ),
    )
    feed(c, rows)
    head = c.store.head(c.principal)
    assert next(p for p in head.people if p.email == "engineer@example.test").ancestry == "resolved"
    former = next(p for p in head.people if p.email == "root@example.test")
    assert former.absence_review
    assert all(r.status == "healthy" for r in service.read(c.principal).roles)
    assert len(c.workflow.tenancies(c.principal, TenancyQuery()).items) == 1


# Audit directory and CSV reveal actual recorded mapping deltas, independent of later live edits.
def test_mapping_history_description_and_export_are_historical(workflow_case):
    import csv
    import json
    from io import StringIO

    from otm.audit.contracts import AuditExportQuery, AuditQuery
    from otm.storage.audit_directory import SqlAuditDirectory
    from otm.storage.audit_export import SqlAuditExport

    c = workflow_case
    service, view = preview(
        c, lambda body: body["segments"][0].update(label="Renamed Alpha", designee_emails=())
    )
    apply(c, service, view)
    service, view = preview(c, lambda body: body["segments"][0].update(label="Renamed Again"))
    apply(c, service, view)
    directory = SqlAuditDirectory(c.engine).directory(
        c.policy.workspace_id, AuditQuery(category="organization", page_size=100)
    )
    row = next(e for e in directory.items if "Segment name: LOB One → Renamed Alpha" in e.changes)
    assert row.summary == "Updated organization mappings"
    assert "Renamed Alpha previous designees: delegate@example.test" in row.changes
    assert "Renamed Alpha new designees: None" in row.changes
    assert "Renamed Again" not in str(row.changes)
    received = next(e for e in directory.items if e.kind == "organization_feed_received")
    assert received.summary == "Received organization feed"
    exported = SqlAuditExport(c.engine, c.clock).export(
        c.principal, AuditExportQuery(category="organization")
    )
    record = next(
        r for r in csv.DictReader(StringIO(exported.decode("utf-8-sig"))) if r["id"] == str(row.id)
    )
    assert json.loads(record["changes"]) == list(row.changes)
    assert "source_id" not in record
    assert SqlAuditDirectory(c.engine).directory("other-workspace", AuditQuery()).total == 0


# Mapping repair retires only corrected mapping reviews, preserving cleanup and true exceptions.
@pytest.mark.parametrize("check_gate", [True, False])
def test_mapping_repair_clears_employee_reviews_and_unblocks_provisioning(
    workflow_case, check_gate
):
    from otm.organization.contracts import Record

    c = workflow_case
    rows = tuple(
        r.model_copy(update={"manager_email": "acting@example.test"})
        if r.email in {"delegate@example.test", "engineer@example.test"}
        else r
        for r in example_records()
        if r.email != "one@example.test"
    ) + (
        Record(
            source_record_id="acting",
            full_name="Acting leader",
            email="acting@example.test",
            manager_email="root@example.test",
        ),
        Record(
            source_record_id="assistant",
            full_name="Executive assistant",
            email="assistant@example.test",
            manager_email="root@example.test",
        ),
    )
    feed(c, rows)
    head = c.store.head(c.principal)
    engineer = next(p for p in head.people if p.email == "engineer@example.test")
    if check_gate:
        assert "create_tenancy" not in c.workflow.preview(c.principal, engineer.id).actions
        for choice in ("create_tenancy", "import_tenancy", "join_shared"):
            with pytest.raises(OrganizationConflict, match="ACTION_UNAVAILABLE"):
                action(c, engineer.id, choice)
    pending = c.workflow.reviews(c.principal, ReviewQuery(page_size=50))
    assert sum(r.kind == "LOB_MAPPING_REVIEW" for r in pending.items) == 4
    service, view = preview(
        c,
        lambda body: body["segments"][0].update(
            leader_email="acting@example.test", designee_emails=()
        ),
    )
    apply(c, service, view)
    active = c.workflow.reviews(c.principal, ReviewQuery(page_size=50)).items
    assert {r.email for r in active if r.kind == "LOB_MAPPING_REVIEW"} == {"assistant@example.test"}
    assert any(r.kind == "PERSON_ABSENCE_REVIEW" and r.email == "one@example.test" for r in active)
    assert any(
        r.kind == "TENANCY_SETUP_REVIEW" and r.email == "acting@example.test" for r in active
    )
    assert "create_tenancy" in c.workflow.preview(c.principal, engineer.id).actions
    history = c.workflow.reviews(c.principal, ReviewQuery(category="history", page_size=50)).items
    assert (
        sum(r.kind == "LOB_MAPPING_REVIEW" and r.resolution == "mapping_corrected" for r in history)
        == 3
    )
    # Repeated feeds retain genuine exceptions without reviving repaired mapping reviews.
    feed(c, rows)
    assert {
        r.email
        for r in c.workflow.reviews(c.principal, ReviewQuery(page_size=50)).items
        if r.kind == "LOB_MAPPING_REVIEW"
    } == {"assistant@example.test"}

    assistant_review = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery(page_size=50)).items
        if r.kind == "LOB_MAPPING_REVIEW"
    )
    assistant = next(
        p for p in c.store.head(c.principal).people if p.email == "assistant@example.test"
    )
    action(c, assistant.id, "ignore", review_id=assistant_review.id)
    ignored = c.workflow.preview(c.principal, assistant.id)
    assert ignored.mapping_required and "create_tenancy" not in ignored.actions
    # A new, genuine mapping gap gets a fresh episode after the old condition was repaired.
    rows = tuple(
        r.model_copy(update={"manager_email": "root@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in rows
    )
    feed(c, rows)
    assert any(
        r.kind == "LOB_MAPPING_REVIEW" and r.email == engineer.email
        for r in c.workflow.reviews(c.principal, ReviewQuery(page_size=50)).items
    )
