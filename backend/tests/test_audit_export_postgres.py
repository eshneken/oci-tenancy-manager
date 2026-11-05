"""Real snapshot exports, immutable preparation, exact scope and post-lock expiry boundaries."""

import csv
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from test_local_auth import factors
from test_local_auth_postgres import command, login_case

from otm.audit.contracts import AuditExportQuery, AuditQuery
from otm.auth.service import SessionFailure
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.audit_export import AuditExportTooLarge, SqlAuditExport
from otm.storage.tables import admin_session, administrator, audit_event

pytestmark = pytest.mark.postgres
__all__ = ["login_case", "factors"]


# The actual export omits its own future event and records only redacted preparation evidence.
def test_real_export_snapshot_and_preparation(login_case):
    c = login_case
    issued = c.service.sign_in(command(c))
    principal = c.sessions.authenticate(issued.handle.get_secret_value())
    exporter = SqlAuditExport(c.engine, c.clock)
    content = exporter.export(principal, AuditExportQuery())
    exported = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
    assert len(exported) == 2
    assert {r["kind"] for r in exported} == {
        "administrator_bootstrapped",
        "local_sign_in_succeeded",
    }
    assert all(r["administrator_id"] == str(c.identifier) for r in exported)
    assert c.seed not in content.decode("utf-8-sig") and c.reference not in content.decode(
        "utf-8-sig"
    )
    result = SqlAuditDirectory(c.engine).directory(c.policy.workspace_id, AuditQuery())
    assert result.total == 3
    prepared = next(r for r in result.items if r.kind == "audit_export")
    assert prepared.category == "administration" and prepared.actor_name == principal.display_name
    with c.engine.connect() as connection:
        data = connection.scalar(select(audit_event.c.data).where(audit_event.c.id == prepared.id))
    assert set(data) == {"contract_version", "row_count", "query_digest"}
    assert data["row_count"] == 2
    # Inclusive lower/exclusive upper boundaries are identical to the directory, including ties.
    bounds = dict(from_at=c.clock(), to_at=c.clock() + timedelta(microseconds=1))
    matched = SqlAuditDirectory(c.engine).directory(c.policy.workspace_id, AuditQuery(**bounds))
    second = exporter.export(principal, AuditExportQuery(**bounds))
    assert len(list(csv.DictReader(StringIO(second.decode("utf-8-sig"))))) == matched.total == 2
    assert SqlAuditDirectory(c.engine).directory("other-workspace", AuditQuery()).total == 0


# Row-cap violations and lost token/lifetime authority release no CSV or preparation event.
def test_real_export_rejections_are_atomic(login_case):
    c = login_case
    issued = c.service.sign_in(command(c))
    principal = c.sessions.authenticate(issued.handle.get_secret_value())
    exporter = SqlAuditExport(c.engine, c.clock)
    with patch("otm.storage.audit_export.MAX_EXPORT_ROWS", 1), pytest.raises(AuditExportTooLarge):
        exporter.export(principal, AuditExportQuery())
    reads = SqlAuditDirectory(c.engine)
    assert reads.directory(c.policy.workspace_id, AuditQuery()).total == 2
    # The exact token/session binding cannot be replaced by a new browser identity.
    forged = principal.session.model_copy(update={"session_token_hash": "0" * 64})
    with pytest.raises(SessionFailure):
        exporter.export(type(principal)(forged), AuditExportQuery())
    # Expiry uses the current clock after database locks, including equality at the hard limit.
    c.clock.return_value = principal.session.expires_at
    with pytest.raises(SessionFailure):
        exporter.export(principal, AuditExportQuery())
    assert reads.directory(c.policy.workspace_id, AuditQuery()).total == 2


# Stale current-grant revisions fail even for a previously valid principal.
def test_real_export_rechecks_grant_revision(login_case):
    c = login_case
    issued = c.service.sign_in(command(c))
    principal = c.sessions.authenticate(issued.handle.get_secret_value())
    with c.engine.begin() as connection:
        connection.execute(
            update(administrator)
            .where(administrator.c.id == c.identifier)
            .values(authorization_revision=uuid4())
        )
    with pytest.raises(SessionFailure):
        SqlAuditExport(c.engine, c.clock).export(principal, AuditExportQuery())
    with c.engine.begin() as connection:
        connection.execute(
            update(admin_session)
            .where(admin_session.c.id == principal.session.id)
            .values(revoked_at=c.clock())
        )
    with pytest.raises(SessionFailure):
        SqlAuditExport(c.engine, c.clock).export(principal, AuditExportQuery())
