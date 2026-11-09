"""Disposable organization restoration never resurrects deleted provider or tenancy state."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_organization_fixtures import example_records
from test_organization_storage_postgres import factors, intake, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, feed, workflow_case

from otm.organization.contracts import Completeness, Record
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import org_person, tenancy, tenancy_membership
from otm.tenancies.views import ReviewQuery, TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Model only the pre-upgrade bug in this owned disposable DB; no runtime repair/backfill is added.
def legacy_offboard(c, identifier, **changes):
    with c.engine.begin() as connection:
        connection.execute(
            update(org_person)
            .where(
                org_person.c.workspace_id == c.policy.workspace_id, org_person.c.id == identifier
            )
            .values(
                **{
                    "directory_status": "offboarded",
                    "setup_required": False,
                    "removed_capture_at": None,
                    **changes,
                }
            )
        )


# Fresh full/partial rows restore old mistakes once without recreating tenancy or access state.
@pytest.mark.parametrize("partial", [False, True])
def test_legacy_source_present_restoration_and_no_resurrection(workflow_case, partial):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, created = action(c, person.id, "create_tenancy")
    complete_setup(c, created.operation_id)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, deleted = action(c, person.id, "delete_tenancy", tenancy_id=child.id)
    c.worker.run(deleted.operation_id)
    legacy_offboard(c, person.id)
    with c.engine.connect() as connection:
        old_links = [dict(r) for r in connection.execute(select(tenancy_membership)).mappings()]
        old_child = dict(
            connection.execute(select(tenancy).where(tenancy.c.id == child.id)).mappings().one()
        )
    c.clock.return_value += timedelta(seconds=10)
    rows = (
        tuple(r for r in example_records() if r.email == person.email)
        if partial
        else example_records()
    )
    incoming = intake(c, uuid4().hex, rows)
    if partial:
        incoming = incoming.model_copy(
            update={
                "envelope": incoming.envelope.model_copy(
                    update={"declared_completeness": Completeness.PARTIAL}
                )
            }
        )
    assert c.store.ingest(c.principal, incoming).state == "published"
    assert c.workflow.preview(c.principal, person.id).directory_status == "included"
    first = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "TENANCY_SETUP_REVIEW" and r.person_id == person.id
    )
    assert c.store.ingest(c.principal, incoming).state == "duplicate"
    feed(c, example_records())
    repeated = [
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "TENANCY_SETUP_REVIEW" and r.person_id == person.id
    ]
    assert [r.id for r in repeated] == [first.id]
    with c.engine.connect() as connection:
        assert [
            dict(r) for r in connection.execute(select(tenancy_membership)).mappings()
        ] == old_links
        assert (
            dict(
                connection.execute(select(tenancy).where(tenancy.c.id == child.id)).mappings().one()
            )
            == old_child
        )
    assert c.workflow.tenancies(c.principal, TenancyQuery()).total == 0


# Neither transport replay, stale/staged data, references nor configuration-only review is a return.
def test_non_applied_or_reference_evidence_cannot_restore(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    legacy_offboard(c, person.id)

    # Assert state without repairing any row or replaying lifecycle effects.
    def remains_offboarded():
        assert c.workflow.preview(c.principal, person.id).directory_status == "offboarded"

    # Same capture under a new delivery cannot be newly applied positive evidence.
    assert c.store.ingest(c.principal, intake(c, uuid4().hex)).state != "published"
    remains_offboarded()
    with c.store._write(c.principal) as (connection, workspace, at):
        from otm.tenancies.directory import registry_state

        c.workflow._reconcile_current(connection, registry_state(connection, workspace), at)
    remains_offboarded()
    c.clock.return_value += timedelta(seconds=10)
    rows = (
        Record(
            source_record_id="reference-only",
            full_name="Reference child",
            email="reference-child@example.test",
            manager_email=person.email,
        ),
    )
    incoming = intake(c, uuid4().hex, rows)
    incoming = incoming.model_copy(
        update={
            "envelope": incoming.envelope.model_copy(
                update={"declared_completeness": Completeness.PARTIAL}
            )
        }
    )
    c.store.ingest(c.principal, incoming)
    remains_offboarded()
    c.clock.return_value += timedelta(seconds=10)
    staged = c.store.ingest(c.principal, intake(c, uuid4().hex), stage_only=True)
    assert staged.state == "staged"
    remains_offboarded()
    c.store.apply(c.principal, staged.proposed_version_id)
    assert c.workflow.preview(c.principal, person.id).directory_status == "included"


# Standalone cleanup never removes an absent employee; explicit, confirmed offboarding does.
def test_absent_employee_cleanup_then_explicit_offboarding_and_return(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, created = action(c, person.id, "create_tenancy")
    complete_setup(c, created.operation_id)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    feed(c, tuple(r for r in example_records() if r.email != person.email))
    _, deleted = action(c, person.id, "delete_tenancy", tenancy_id=child.id)
    c.worker.run(deleted.operation_id)
    assert c.workflow.preview(c.principal, person.id).directory_status == "included"
    review = next(
        r
        for r in c.workflow.reviews(c.principal, ReviewQuery()).items
        if r.kind == "PERSON_ABSENCE_REVIEW" and r.person_id == person.id
    )
    with pytest.raises(OrganizationConflict, match="DESTRUCTIVE_CONFIRMATION_REQUIRED"):
        action(
            c,
            person.id,
            "offboard_person",
            review_id=review.id,
            confirm_no_associations=True,
            confirm_destructive=False,
        )
    # A fixture-only pre-upgrade admission has no new consent field in its canonical digest.
    with patch("otm.tenancies.workflows.DESTRUCTIVE_ACTIONS", frozenset()):
        historical, receipt = action(
            c,
            person.id,
            "offboard_person",
            review_id=review.id,
            confirm_no_associations=True,
            confirm_destructive=False,
        )
    assert "confirm_destructive" not in historical.model_dump(mode="json")
    assert c.workflow.act(c.principal, historical) == receipt
    assert c.workflow.preview(c.principal, person.id).directory_status == "offboarded"
    feed(c, example_records())
    assert c.workflow.preview(c.principal, person.id).directory_status == "included"
    assert (
        len(
            [
                r
                for r in c.workflow.reviews(c.principal, ReviewQuery()).items
                if r.person_id == person.id and r.kind == "TENANCY_SETUP_REVIEW"
            ]
        )
        == 1
    )


# Actual controls for exemption, retired identity and in-flight work survive fresh full publication.
def test_exempt_merged_and_pending_controls_survive_feed(workflow_case):
    c = workflow_case
    people = {p.email: p.id for p in c.store.head(c.principal).people}
    engineer, leader, delegate = (
        people[a] for a in ("engineer@example.test", "one@example.test", "delegate@example.test")
    )
    _, pending = action(c, engineer, "create_tenancy")
    legacy_offboard(c, engineer)
    action(c, leader, "no_tenancy_required")
    legacy_offboard(c, delegate, directory_status="merged")
    feed(c, example_records())
    with c.engine.connect() as connection:
        controls = {r["id"]: r for r in connection.execute(select(org_person)).mappings()}
    assert controls[engineer]["directory_status"] == "offboarded"
    assert controls[engineer]["pending_operation_id"] == pending.operation_id
    assert controls[leader]["directory_status"] == "exempt"
    assert controls[delegate]["directory_status"] == "merged"
