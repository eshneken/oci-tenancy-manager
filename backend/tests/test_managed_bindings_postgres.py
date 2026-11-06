"""Canonical mappings retain exact provenance, scoped history and worker-only write authority."""

import json
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.operations.contracts import IntentEventData
from otm.storage.managed_bindings import capture_bindings
from otm.storage.tables import audit_event, operation
from otm.storage.tables import managed_object_binding as binding
from otm.tenancies.onboarding_contracts import OnboardingCommand, OnboardingEvidence
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Read an isolated workspace's identity mappings without treating presence as a health observation.
def bindings(c):
    with c.engine.connect() as connection:
        return list(
            connection.execute(
                select(binding)
                .where(
                    binding.c.workspace_id == c.policy.workspace_id,
                )
                .order_by(binding.c.logical_key)
            ).mappings()
        )


# Both entry paths retain one domain and two independent subjects with exact immutable evidence.
@pytest.mark.parametrize("kind", ["create_tenancy", "import_tenancy"])
def test_canonical_capture_and_identical_replay(workflow_case, kind):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    extra = {"import_ocid": "ocid1.tenancy.oc1..otmsimbindings"} if kind == "import_tenancy" else {}
    _, receipt = action(c, person.id, kind, **extra)
    complete_setup(c, receipt.operation_id)
    rows = bindings(c)
    assert len(rows) == 3 and all(r["generation"] == 1 and r["state"] == "active" for r in rows)
    assert (
        rows[0]["kind"] == "identity_domain" and rows[0]["ownership_mode"] == "observed_reference"
    )
    assert rows[0]["scim_resource_id"] is None and rows[0]["user_name"] is None
    assert {r["identity_domain_binding_id"] for r in rows[1:]} == {rows[0]["id"]}
    assert len({r["provider_ocid"] for r in rows}) == 3
    with c.engine.begin() as connection:
        event = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.id == rows[0]["source_evidence_event_id"],
                )
            )
            .mappings()
            .one()
        )
        intent_event = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.operation_id == receipt.operation_id,
                audit_event.c.kind == "operation_intent",
            )
        ).scalar_one()
        row = (
            connection.execute(
                select(operation).where(
                    operation.c.id == receipt.operation_id,
                )
            )
            .mappings()
            .one()
        )
        intent = IntentEventData.model_validate_json(json.dumps(intent_event)).intent
        evidence = OnboardingEvidence.model_validate(event["data"])
        result = capture_bindings(
            connection, row, intent, evidence.required_users, event["id"], event["at"]
        )
    assert set(result) == {r["id"] for r in rows}
    c.worker.run(receipt.operation_id)
    assert bindings(c) == rows


# Database constraints enforce scoping and provenance even if a caller tries to bypass the service.
@pytest.mark.parametrize(
    "damage",
    [
        "workspace",
        "child",
        "domain",
        "event",
        "operation",
        "ocid",
        "scim",
        "generation",
        "rewrite",
        "delete",
        "truncate",
    ],
)
def test_database_rejects_forged_or_mutated_bindings(workflow_case, damage):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    step = c.provider.onboarding_step

    # Keep the child pending with valid captured mappings so SQL provenance checks really qualify.
    def retain_bootstrap(intent, key, discovery):
        if key == "retire_temporary":
            raise ValueError("synthetic cleanup pause")
        return step(intent, key, discovery)

    with patch.object(c.provider, "onboarding_step", side_effect=retain_bootstrap):
        complete_setup(c, receipt.operation_id, expected_phase="blocked")
    rows = bindings(c)
    with pytest.raises(DBAPIError):
        with c.engine.begin() as connection:
            if damage == "rewrite":
                connection.execute(
                    update(binding)
                    .where(binding.c.id == rows[1]["id"])
                    .values(
                        provider_ocid="ocid1.user.oc1..otmsimforged",
                    )
                )
            elif damage == "delete":
                connection.execute(binding.delete().where(binding.c.id == rows[1]["id"]))
            elif damage == "truncate":
                connection.exec_driver_sql("TRUNCATE public.otm_managed_object_binding")
            else:
                values = dict(rows[1])
                values["id"] = uuid4()
                field = {
                    "workspace": "workspace_id",
                    "child": "tenancy_id",
                    "domain": "identity_domain_binding_id",
                    "event": "source_evidence_event_id",
                    "operation": "created_operation_id",
                    "ocid": "provider_ocid",
                    "scim": "scim_resource_id",
                    "generation": "generation",
                }[damage]
                values[field] = (
                    uuid4() if field.endswith("_id") else 2 if damage == "generation" else "forged"
                )
                connection.execute(binding.insert().values(**values))
    assert bindings(c) == rows


# An insert interruption rolls back the whole mapping set and blocks cleanup; retry creates three.
def test_partial_binding_insert_blocks_retirement_and_can_retry(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    execute = Connection.execute
    inserts = 0

    # Fail after the domain insert to prove actual PostgreSQL savepoint rollback, not mock behavior.
    def interrupt(connection, statement, *args, **kwargs):
        nonlocal inserts
        if getattr(statement, "is_insert", False) and getattr(statement, "table", None) is binding:
            inserts += 1
            if inserts == 2:
                raise ValueError("synthetic insert interruption")
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", new=interrupt):
        complete_setup(c, receipt.operation_id, expected_phase="blocked")
    assert bindings(c) == []
    view = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert not any(s.key == "retire_temporary" and s.state == "verified" for s in view.checks)
    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=view.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    c.worker.run(receipt.operation_id)
    assert c.workflow.onboarding(c.principal, receipt.operation_id).phase == "complete"
    assert len(bindings(c)) == 3


# Only verified termination initiation retires management; immutable identities/provenance survive.
@pytest.mark.parametrize("whole", [True, False])
def test_termination_retires_bindings_without_deleting_history(workflow_case, whole):
    from otm.tenancies.deletion import TenancyDeletionCommand

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id)
    rows = bindings(c)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    if whole:
        preview = c.workflow.deletion_preview(c.principal, child.id)
        deleted = c.workflow.delete_tenancy(
            c.principal,
            TenancyDeletionCommand(
                client_request_key=uuid4(),
                context=preview.context,
                tenancy_id=child.id,
                confirm_deletion=True,
                confirm_manager=True,
                confirm_shared=True,
            ),
        )
    else:
        _, deleted = action(c, person.id, "delete_tenancy", tenancy_id=child.id)
    c.worker.run(deleted.operation_id)
    after = bindings(c)
    assert {r["id"] for r in after} == {r["id"] for r in rows}
    assert all(
        r["state"] == "retired" and r["retired_operation_id"] == deleted.operation_id for r in after
    )


# Previously completed captures remain unbound rather than being adopted by startup/read/redelivery.
def test_historical_capture_is_not_materialized_on_redelivery(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    from otm.tenancies.contracts import OrganizationIntent

    # Preserve the accepted legacy shape before the connection marker existed.
    def legacy(**fields):
        return OrganizationIntent(**{**fields, "presence_connection_contract": None})

    with patch("otm.tenancies.workflows.OrganizationIntent", side_effect=legacy):
        _, receipt = action(c, person.id, "create_tenancy")
    with patch("otm.storage.managed_bindings.capture_bindings"):
        complete_setup(c, receipt.operation_id)
    assert bindings(c) == []
    c.workflow.tenancies(c.principal, TenancyQuery())
    c.workflow.onboarding(c.principal, receipt.operation_id)
    c.worker.run(receipt.operation_id)
    assert bindings(c) == []


# A denied/failed provider initiation cannot retire canonical identities ahead of actual acceptance.
def test_failed_termination_keeps_current_bindings(workflow_case):
    from otm.providers.lifecycle import LifecycleBlocked

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id)
    before = bindings(c)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, deleted = action(c, person.id, "delete_tenancy", tenancy_id=child.id)
    with patch.object(c.provider, "apply", side_effect=LifecycleBlocked("TARGET_CHANGED")):
        c.worker.run(deleted.operation_id)
    assert bindings(c) == before


# Captured presence cannot grant managed ownership after a required setup proof loses verification.
def test_missing_setup_proof_blocks_binding_source(workflow_case):
    from otm.storage.tables import operation_step

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    step = c.provider.onboarding_step

    # Preserve a legitimate current capture with a pending child for independent source tests.
    def pause_cleanup(intent, key, discovery):
        if key == "retire_temporary":
            raise ValueError("synthetic cleanup pause")
        return step(intent, key, discovery)

    with patch.object(c.provider, "onboarding_step", side_effect=pause_cleanup):
        complete_setup(c, receipt.operation_id, expected_phase="blocked")
    rows = bindings(c)
    with c.engine.begin() as connection:
        event = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.id == rows[0]["source_evidence_event_id"],
                )
            )
            .mappings()
            .one()
        )
        row = (
            connection.execute(
                select(operation).where(
                    operation.c.id == receipt.operation_id,
                )
            )
            .mappings()
            .one()
        )
        data = connection.execute(
            select(audit_event.c.data).where(
                audit_event.c.id == row["current_intent_event_id"],
            )
        ).scalar_one()
        intent = IntentEventData.model_validate_json(json.dumps(data)).intent
        evidence = OnboardingEvidence.model_validate(event["data"])
        connection.execute(
            update(operation_step)
            .where(
                operation_step.c.operation_id == receipt.operation_id,
                operation_step.c.step_key == "configure_required",
            )
            .values(state="needs_attention", verified_at=None)
        )
        with pytest.raises(ValueError, match="MANAGED_BINDING_SOURCE_UNVERIFIED"):
            capture_bindings(
                connection, row, intent, evidence.required_users, event["id"], event["at"]
            )
    with pytest.raises(DBAPIError) as caught:
        with c.engine.begin() as connection:
            connection.execute(binding.insert().values(**{**rows[1], "id": uuid4()}))
    assert caught.value.orig.diag.message_primary == "MANAGED_BINDING_SOURCE_UNVERIFIED"
    assert bindings(c) == rows
