"""Account-record reads use actual scoped SQL while preserving canonical identity evidence."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.storage.organization import OrganizationConflict
from otm.storage.tables import (
    audit_event,
    managed_object_binding,
    operation,
    org_workspace,
    tenancy,
)
from otm.tenancies.deletion import TenancyDeletionCommand
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# One read returns both independently registered roles without scheduling any provider work.
@pytest.mark.parametrize("kind", ["create_tenancy", "import_tenancy"])
def test_actual_record_projection_and_read_only_behavior(workflow_case, kind):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    extra = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimrequiredusers"}
        if kind == "import_tenancy"
        else {}
    )
    _, receipt = action(c, person.id, kind, **extra)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    pending = c.workflow.required_users(c.principal, child.id)
    assert pending.tenancy_status == "pending"
    assert all(u.identity_state == "not_recorded" for u in pending.users)
    complete_setup(c, receipt.operation_id)
    with c.engine.connect() as connection:
        before = [
            connection.scalar(select(func.count()).select_from(t))
            for t in (audit_event, operation, managed_object_binding)
        ]
        rows = list(
            connection.execute(
                select(managed_object_binding).where(
                    managed_object_binding.c.workspace_id == c.policy.workspace_id,
                )
            ).mappings()
        )
    with patch.object(
        c.provider, "capture_onboarding_users", side_effect=AssertionError("GET cannot probe OCI")
    ):
        result = c.workflow.required_users(c.principal, child.id)
        assert result == c.workflow.required_users(c.principal, child.id)
    by_key = {r["logical_key"]: r for r in rows}
    assert [u.purpose for u in result.users] == ["automation", "recovery"]
    for user in result.users:
        assert user.identity_state == "recorded"
        assert user.identity.user_ocid == by_key["identity/user/" + user.purpose]["provider_ocid"]
        assert user.identity.domain_ocid == by_key["identity/domain"]["provider_ocid"]
        assert user.identity.source_operation_id == receipt.operation_id
    with c.engine.connect() as connection:
        assert [
            connection.scalar(select(func.count()).select_from(t))
            for t in (audit_event, operation, managed_object_binding)
        ] == before


# Known legacy completion without canonical registration remains explicitly unrecorded on every GET.
def test_legacy_unbound_and_retired_records_are_not_cloud_health(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, first = action(c, person.id, "create_tenancy")
    with patch("otm.storage.managed_bindings.capture_bindings"):
        complete_setup(c, first.operation_id)
    old = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert all(u.identity is None for u in c.workflow.required_users(c.principal, old.id).users)
    _, second = action(c, person.id, "create_tenancy")
    complete_setup(c, second.operation_id)
    child = next(
        t for t in c.workflow.tenancies(c.principal, TenancyQuery()).items if t.id != old.id
    )
    prior = c.workflow.required_users(c.principal, child.id)
    preview = c.workflow.deletion_preview(c.principal, child.id)
    deleted = c.workflow.delete_tenancy(
        c.principal,
        TenancyDeletionCommand(
            client_request_key=uuid4(),
            tenancy_id=child.id,
            context=preview.context,
            confirm_deletion=True,
            confirm_manager=True,
            confirm_shared=True,
        ),
    )
    c.worker.run(deleted.operation_id)
    result = c.workflow.required_users(c.principal, child.id)
    assert result.tenancy_status == "terminated"
    assert all(
        u.identity_state == "retired" and u.identity.retired_at is not None for u in result.users
    )
    assert [u.identity.user_ocid for u in result.users] == [
        u.identity.user_ocid for u in prior.users
    ]


# An actually registered foreign child is indistinguishable from an absent local UUID.
def test_foreign_registered_child_is_not_visible(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id)
    foreign = uuid4()
    with c.engine.begin() as connection:
        original = (
            connection.execute(
                select(org_workspace).where(org_workspace.c.id == c.policy.workspace_id)
            )
            .mappings()
            .one()
        )
        other_workspace = "foreign-" + uuid4().hex
        connection.execute(
            org_workspace.insert().values(
                id=other_workspace,
                configuration_id=original["configuration_id"],
                configuration=original["configuration"],
            )
        )
        child = dict(
            connection.execute(
                select(tenancy).where(tenancy.c.workspace_id == c.policy.workspace_id)
            )
            .mappings()
            .one()
        )
        child.update(
            id=foreign,
            workspace_id=other_workspace,
            name="Foreign child",
            tenancy_ocid="ocid1.tenancy.oc1..otmsimforeign" + foreign.hex,
            operation_id=None,
            last_operation_id=None,
            baseline_version_id=None,
            verified_baseline_version_id=None,
            desired_configuration_id=None,
            last_verified_configuration_id=None,
            configuration_observation={},
            status="cancelled",
            verified_at=None,
            configuration_verified_at=None,
        )
        connection.execute(tenancy.insert().values(**child))
    for identifier in (foreign, uuid4()):
        with pytest.raises(OrganizationConflict, match="^TENANCY_NOT_FOUND$"):
            c.workflow.required_users(c.principal, identifier)
