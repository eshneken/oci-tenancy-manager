"""Durable exact policy observations and independent presence against disposable PostgreSQL."""

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_local_auth_postgres import command as sign_in_command
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case
from test_user_presence_checks_postgres import make_presence, view

from otm.audit.contracts import AuditExportQuery, AuditQuery
from otm.providers.recovery_console_simulator import simulated_console_inspection
from otm.recovery_console import parse_release_cidrs
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import SqlAuditExport
from otm.storage.operation_directory import SqlOperationDirectory
from otm.storage.tables import audit_event
from otm.tenancies.presence_contracts import PresenceCheckRequest
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]
POLICY = parse_release_cidrs("198.51.100.0/24,2001:db8::/32")
OTHER = parse_release_cidrs("203.0.113.0/24")


# Configure source setup before admission; a later desired change does not alter provider fixtures.
@pytest.fixture
def console_case(workflow_case):
    workflow_case.workflow.recovery_console = POLICY
    workflow_case.provider.recovery_console = POLICY
    c = make_presence(workflow_case)
    c.service.recovery_console_loader = Mock(return_value=POLICY)
    c.reader.recovery_console_loader = c.service.recovery_console_loader
    c.reader.recovery_inspection_factory = simulated_console_inspection
    return c


# Run one admitted native-compatible read without any live identity or policy calls.
def refresh(c):
    receipt = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    c.reader.run(receipt.operation_id)
    return receipt


# Retain actual setup rules privately; durable public readback and exports omit network ranges.
def test_setup_check_persistence_and_private_projection(console_case):
    c = console_case
    receipt = refresh(c)
    result = view(c)
    assert result.recovery_console.state == "verified"
    assert [u.presence.state for u in result.users] == ["present", "present"]
    assert view(c) == result
    inventory = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert inventory.required_users.recovery_console.state == "verified"
    with c.engine.connect() as connection:
        source = (
            connection.execute(
                select(audit_event.c.data).where(
                    audit_event.c.workspace_id == c.policy.workspace_id,
                    audit_event.c.operation_id != receipt.operation_id,
                    audit_event.c.kind == "onboarding_outcome",
                )
            )
            .scalars()
            .all()
        )
        assert any("198.51.100.0/24" in str(value) for value in source)
    operations = SqlOperationDirectory(c.engine)
    directory = SqlAuditDirectory(c.engine)
    public = [
        result.model_dump_json(),
        inventory.model_dump_json(),
        operations.detail(c.policy.workspace_id, receipt.operation_id).model_dump_json(),
        directory.directory(c.policy.workspace_id, AuditQuery()).model_dump_json(),
    ]
    # CSV generation uses the same public whitelist; its byte chunks are inspected privately.
    export = SqlAuditExport(c.engine, c.clock).export(c.principal, AuditExportQuery())
    public.append(str(export))
    for payload in public:
        assert "198.51.100" not in payload and "2001:db8" not in payload


# A new CIDR revision immediately stales old policy proof while preserving stored user presence.
def test_desired_change_and_confirmed_drift(console_case):
    c = console_case
    refresh(c)
    c.service.recovery_console_loader.return_value = OTHER
    before = view(c)
    assert before.recovery_console.state == "stale"
    assert all(user.presence.state == "present" for user in before.users)
    refresh(c)
    after = view(c)
    assert after.recovery_console.state == "drift"
    assert after.recovery_console.mfa_exemption == "verified"
    assert after.recovery_console.network_boundary == "drift"
    assert all(user.presence.state == "present" for user in after.users)
    inventory = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    assert inventory.required_users.recovery_console == after.recovery_console


# A denied/unsupported policy read remains unknown without changing the independent Present result.
@pytest.mark.parametrize("fault", ["denied", "mfa", "fallback"])
def test_policy_read_controls_are_independent(console_case, fault):
    c = console_case

    # Change only independent producer facts, never desired policy or stored expected identity.
    def factory(command, source, clock):
        inspection = simulated_console_inspection(command, source, clock)
        facts = inspection.provider.facts
        if fault == "denied":
            changes = {"authorized": False}
        elif fault == "mfa":
            changes = {
                "rules": (facts.rules[0].model_copy(update={"mfa": "required"}), *facts.rules[1:])
            }
        else:
            changes = {"rules": (facts.rules[-1], *facts.rules[:-1])}
        inspection.provider.facts = facts.model_copy(update=changes)
        return inspection

    c.reader.recovery_inspection_factory = factory
    refresh(c)
    actual = view(c)
    assert actual.recovery_console.state == ("unknown" if fault == "denied" else "drift")
    assert all(user.presence.state == "present" for user in actual.users)


# Old queued work is superseded if desired policy changes between acquisition and publication.
def test_queued_policy_revision_and_late_read_fences(console_case):
    c = console_case
    receipt = c.service.start(
        c.principal, c.child.id, PresenceCheckRequest(client_request_key=uuid4())
    )
    c.service.recovery_console_loader.return_value = OTHER
    c.reader.run(receipt.operation_id)
    assert view(c).recovery_console.state != "verified"
    c.service.recovery_console_loader.return_value = POLICY
    refresh(c)
    c.clock.return_value += timedelta(days=1)
    # A real new MFA sign-in is needed after the original session expires; do not bypass auth.
    from otm.auth.local import LocalLogin

    issued = LocalLogin(c.settings, c.repository, c.custody).sign_in(sign_in_command(c))
    c.principal = c.sessions.authenticate(issued.handle.get_secret_value())
    assert view(c).recovery_console.state == "stale"


# An already enrolled legacy child never receives automatic policy configuration from a read.
def test_legacy_capture_does_not_gain_policy_on_refresh(workflow_case):
    c = make_presence(workflow_case)
    c.service.recovery_console_loader = Mock(return_value=POLICY)
    c.reader.recovery_console_loader = c.service.recovery_console_loader
    c.reader.recovery_inspection_factory = simulated_console_inspection
    refresh(c)
    result = view(c)
    assert result.recovery_console.state == "unknown"
    assert all(user.presence.state == "present" for user in result.users)
