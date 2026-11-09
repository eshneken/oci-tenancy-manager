"""Durable assignment evidence and inventory/detail consistency in disposable PostgreSQL."""

from datetime import timedelta
from uuid import uuid4

import pytest
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case
from test_user_presence_checks_postgres import make_presence, view

from otm.audit.contracts import AuditExportQuery, AuditQuery
from otm.providers.administrator_access_simulator import simulated_administrator_inspection
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import SqlAuditExport
from otm.storage.operation_directory import SqlOperationDirectory
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# All writes are isolated to owned fixture data; this never calls a live OCI identity domain.
@pytest.fixture
def assignments_case(workflow_case):
    c = make_presence(workflow_case)
    c.reader.administrator_inspection_factory = simulated_administrator_inspection
    return c


# Admit/read/publish through the real service, transaction locks and existing evidence rows.
def refresh(c):
    receipt = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    c.reader.run(receipt.operation_id)
    return receipt


# Matching records persist through independent reads and drive the same inventory fact model.
def test_durable_assignment_results(assignments_case):
    c = assignments_case
    receipt = refresh(c)
    result = view(c)
    access = result.users[0].administrator_access
    assert access.group == "verified" and access.domain_role == "verified"
    assert access.operation_id == receipt.operation_id
    assert view(c) == result
    inventory = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert inventory.required_users.administrator_access == access
    assert result.users[1].administrator_access.group == "verified"
    assert (
        inventory.required_users.recovery_administrator_access
        == result.users[1].administrator_access
    )
    public = result.model_dump_json() + inventory.model_dump_json()
    public += (
        SqlOperationDirectory(c.engine)
        .detail(c.policy.workspace_id, receipt.operation_id)
        .model_dump_json()
    )
    public += (
        SqlAuditDirectory(c.engine).directory(c.policy.workspace_id, AuditQuery()).model_dump_json()
    )
    public += (
        SqlAuditExport(c.engine, c.clock)
        .export(c.principal, AuditExportQuery())
        .decode("utf-8-sig")
    )
    assert "group_members" not in public and "role_groups" not in public
    assert "domain-admin-app-" not in public


# Actual assignment mutations never change the independent user-presence observation.
@pytest.mark.parametrize("purpose", ["automation", "recovery"])
@pytest.mark.parametrize(
    "fault,group,role",
    [
        ("group", "missing", "missing"),
        ("role", "verified", "missing"),
        ("denied", "unknown", "unknown"),
        ("partial", "unknown", "unknown"),
        ("wrong_app", "unknown", "unknown"),
        ("disabled", "missing", "missing"),
    ],
)
def test_assignment_faults_are_independent(assignments_case, fault, group, role, purpose):
    c = assignments_case

    # Inject independent fixture facts below the real validation wrapper, never product UI controls.
    def factory(command, source, clock):
        inspection = simulated_administrator_inspection(command, source, clock)
        facts = inspection.provider.facts
        if command.target.purpose != purpose:
            return inspection
        changed = (
            {"group_members": ()}
            if fault == "group"
            else {"role_groups": ()}
            if fault == "role"
            else {"authorized": False}
            if fault == "denied"
            else {"complete": False}
            if fault == "partial"
            else {"group_enabled": False}
            if fault == "disabled"
            else {"binding": facts.binding.model_copy(update={"application_id": "wrong-app"})}
        )
        inspection.provider.facts = facts.model_copy(update=changed)
        return inspection

    c.reader.administrator_inspection_factory = factory
    refresh(c)
    actual = view(c)
    assert all(user.presence.state == "present" for user in actual.users)
    index = 0 if purpose == "automation" else 1
    assert actual.users[index].administrator_access.group == group
    assert actual.users[index].administrator_access.domain_role == role
    assert actual.users[1 - index].administrator_access.group == "verified"
    inventory = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert inventory.required_users.administrator_access == actual.users[0].administrator_access
    assert (
        inventory.required_users.recovery_administrator_access
        == actual.users[1].administrator_access
    )


# Absent legacy source assignments are never backfilled from desired names or user existence.
@pytest.mark.parametrize("purpose", ["automation", "recovery"])
def test_legacy_assignments_are_unverifiable(assignments_case, purpose):
    c = assignments_case
    original = c.reader.source

    # Replay a historical producer shape while preserving authenticated scope and existing users.
    def legacy(connection, snapshot):
        return original(connection, snapshot).model_copy(update={purpose + "_administrator": None})

    c.reader.source = legacy
    refresh(c)
    assert view(c).users[0].presence.state == "present"
    assert (
        view(c).users[0 if purpose == "automation" else 1].administrator_access.group == "unknown"
    )


# Slow callbacks lose their assignment proof even when the provider itself reported success.
def test_late_assignment_evidence_is_unverifiable(assignments_case):
    c = assignments_case
    original = simulated_administrator_inspection

    # Move the fixture clock only after a valid exact-subject read, simulating delayed publication.
    def factory(command, source, clock):
        inspection = original(command, source, clock)
        read = inspection.inspect

        # The outer worker must independently enforce the same bounded read window.
        def delayed(command):
            result = read(command)
            c.clock.return_value += timedelta(seconds=31)
            return result

        inspection.inspect = delayed
        return inspection

    c.reader.administrator_inspection_factory = factory
    refresh(c)
    assert view(c).users[0].administrator_access.group == "unknown"
