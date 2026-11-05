"""CSV redaction/formula safety, complete filtered snapshots and command-boundary failures."""

import csv
import json
from contextlib import nullcontext
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from test_admission_service import NOW
from test_audit_history import event
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.audit.contracts import AuditExportQuery, AuditQuery
from otm.auth.http import BrowserSettings
from otm.auth.service import AdminPrincipal, SessionFailure
from otm.storage.audit_export import (
    AuditExportTooLarge,
    SqlAuditExport,
    authorize_export,
    csv_cell,
    csv_document,
)

__all__ = ["session_case"]


# Formulas with whitespace/BOM/control prefixes stay inert; ordinary punctuation remains readable.
@pytest.mark.parametrize(
    "value", ["=1+1", "+SUM(A1)", "-1", "@SUM(A1)", " \t=1", "\ufeff=1", "name\ncell", "\x01=1"]
)
def test_spreadsheet_formula_neutralization(value):
    assert csv_cell(value) == "'" + value


# CSV quoting protects separators/quotes without deleting text; nulls and UTC instants stay usable.
def test_csv_projection_is_closed_and_utf8():
    row = event()
    row["administrator_name"] = 'Example, "administrator"'
    output = csv_document([row])
    rows = list(csv.DictReader(StringIO(output.decode("utf-8-sig"))))
    assert rows[0]["administrator_name"] == 'Example, "administrator"'
    assert rows[0]["at"] == NOW.isoformat()
    assert rows[0]["operation_id"] == ""
    assert "private_marker" not in output.decode("utf-8-sig")
    assert len(rows[0]) == 12


# Only aware UTC timestamps are accepted, with an inclusive start and exclusive end.
def test_date_contract_and_handler_round_trip(session_case):
    options = AuditExportQuery.model_validate_json(
        json.dumps({"from_at": NOW.isoformat(), "to_at": (NOW + timedelta(days=1)).isoformat()})
    )
    assert options.from_at == NOW
    for values in (
        {"from_at": NOW.isoformat(), "to_at": NOW.isoformat()},
        {"from_at": "2026-10-30T00:00:00"},
        {"from_at": "2026-10-30T00:00:00+01:00"},
        {"page": 1},
    ):
        with pytest.raises(ValidationError):
            AuditExportQuery.model_validate_json(json.dumps(values))
    store = Mock()
    store.directory.return_value = dict(items=[], total=0, page=1, page_size=10, pages=1)
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), audit_history=store
    )
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.get(
            "/api/audit-history",
            params={"from_at": NOW.isoformat(), "to_at": (NOW + timedelta(days=1)).isoformat()},
            headers=cookie(session_case),
        )
        assert response.status_code == 200
        assert store.directory.call_args.args[1].from_at == NOW
        assert (
            client.get("/api/audit-history?from_at=bad", headers=cookie(session_case)).status_code
            == 400
        )
    assert AuditQuery(from_at=NOW).from_at == NOW


# Inject one explicit transaction to inspect commit-before-return behavior without a real DB.
def export_case():
    connection = MagicMock()
    connection.begin.return_value = nullcontext()
    engine = Mock(
        connect=Mock(
            return_value=SimpleNamespace(
                execution_options=Mock(return_value=nullcontext(connection))
            )
        )
    )
    connection.execute.return_value.mappings.return_value.all.return_value = [event()]
    return SqlAuditExport(engine, Mock(return_value=NOW)), connection


# The complete snapshot is exported once and only a digest/count enters immutable preparation data.
def test_export_records_preparation_without_search_text(session_case):
    store, connection = export_case()
    with patch("otm.storage.audit_export.authorize_export", return_value=uuid4()):
        content = store.export(
            AdminPrincipal(session_case.session),
            AuditExportQuery(query="private search", from_at=NOW),
        )
    assert len(list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))) == 1
    values = connection.execute.call_args.args[0].compile().params
    assert values["kind"] == "audit_export"
    assert values["data"]["row_count"] == 1
    assert "private search" not in json.dumps(values["data"])
    assert values["actor_subject"] == AdminPrincipal(session_case.session).actor.key
    with pytest.raises(SessionFailure):
        store.export(object(), AuditExportQuery())


# Reaching the sentinel row raises before a byte or preparation event can be returned.
def test_export_limit_and_failed_commit_disclose_nothing(session_case):
    store, connection = export_case()
    with (
        patch("otm.storage.audit_export.authorize_export", return_value=uuid4()),
        patch("otm.storage.audit_export.MAX_EXPORT_ROWS", 0),
    ):
        with pytest.raises(AuditExportTooLarge):
            store.export(AdminPrincipal(session_case.session), AuditExportQuery())
    assert connection.execute.call_count == 1
    store, connection = export_case()
    connection.begin.return_value = MagicMock()
    connection.begin.return_value.__exit__.side_effect = RuntimeError("private commit failure")
    with (
        patch("otm.storage.audit_export.authorize_export", return_value=uuid4()),
        pytest.raises(RuntimeError),
    ):
        store.export(AdminPrincipal(session_case.session), AuditExportQuery())


# Anchor/session/grant checks share the export transaction; stale metadata cannot authorize output.
@pytest.mark.parametrize(
    "damage", ["none", "anchor", "session", "identity", "grant", "reference", "revision"]
)
def test_export_rechecks_exact_current_authority(session_case, damage):
    principal = AdminPrincipal(session_case.session)
    identifier = uuid4()
    row = principal.session.model_dump()
    grant = dict(id=identifier, authorization_revision=principal.session.entitlement_revision)
    row["entitlement_reference"] = str(identifier)
    if damage == "session":
        row = None
    elif damage == "identity":
        row["subject"] = "another"
    elif damage == "grant":
        grant = None
    elif damage == "reference":
        row["entitlement_reference"] = "wrong"
    elif damage == "revision":
        grant["authorization_revision"] = uuid4()
    connection = Mock()
    connection.execute.side_effect = [
        Mock(scalar_one_or_none=Mock(return_value=None if damage == "anchor" else identifier)),
        Mock(mappings=Mock(return_value=Mock(one_or_none=Mock(return_value=row)))),
        Mock(mappings=Mock(return_value=Mock(one_or_none=Mock(return_value=grant)))),
    ]
    if damage == "none":
        assert authorize_export(connection, principal, Mock(return_value=NOW)) == identifier
    else:
        with pytest.raises(SessionFailure):
            authorize_export(connection, principal, Mock(return_value=NOW))


# Bounded JSON and current authority retain safe origin, body and storage diagnostics.
def test_export_http_guards_and_errors(session_case):
    store = Mock()
    store.export.return_value = b'"id"\r\n'
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), audit_export=store
    )
    headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert (
            client.post(
                "/api/audit-history/export", json={}, headers=cookie(session_case)
            ).status_code
            == 403
        )
        response = client.post("/api/audit-history/export", json={}, headers=headers)
        assert response.status_code == 200 and response.headers["content-type"].startswith(
            "text/csv"
        )
        assert 'filename="audit-history.csv"' in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "no-store"
        for content in (b'{"page":1}', b"{", b"x" * 4097):
            assert (
                client.post(
                    "/api/audit-history/export",
                    content=content,
                    headers={**headers, "content-type": "application/json"},
                ).status_code
                == 400
            )
        assert (
            client.post("/api/audit-history/export", content="{}", headers=headers).status_code
            == 400
        )
        for failure, code in (
            (AuditExportTooLarge(), 413),
            (RuntimeError("private"), 503),
            (SessionFailure(403, "ADMINISTRATOR_REQUIRED"), 403),
        ):
            store.export.side_effect = failure
            response = client.post("/api/audit-history/export", json={}, headers=headers)
            assert response.status_code == code and "private" not in response.text
    with pytest.raises(ValueError):
        create_app(audit_export=store)


# An export blocked on database locks checks the clock afterwards, not at request arrival.
def test_export_lock_wait_cannot_revive_expired_session(session_case):
    principal = AdminPrincipal(session_case.session)
    connection = Mock()
    clock = Mock(return_value=principal.session.expires_at)
    row = principal.session.model_dump()

    # Simulate acquisition of each database lock before the authoritative time is sampled.
    def locked(statement):
        clock.assert_not_called()
        if connection.execute.call_count == 1:
            return Mock(scalar_one_or_none=Mock(return_value=uuid4()))
        return Mock(mappings=Mock(return_value=Mock(one_or_none=Mock(return_value=row))))

    connection.execute.side_effect = locked
    with pytest.raises(SessionFailure):
        authorize_export(connection, principal, clock)
    clock.assert_called_once_with()
    assert connection.execute.call_count == 2


# Date predicates share one SQL source and never choose another workspace or timezone.
def test_date_selection_uses_half_open_bounds():
    from sqlalchemy import select

    from otm.storage.audit_directory import selection
    from otm.storage.tables import audit_event

    start, end = NOW, NOW + timedelta(days=1)
    source, where, order = selection("scoped-org", AuditExportQuery(from_at=start, to_at=end))
    compiled = (
        select(audit_event)
        .select_from(source)
        .where(*where)
        .order_by(order)
        .compile(dialect=postgresql.dialect())
    )
    assert "audit_event.at >=" in str(compiled) and "audit_event.at <" in str(compiled)
    assert start in compiled.params.values() and end in compiled.params.values()
    assert "scoped-org" in compiled.params.values()
