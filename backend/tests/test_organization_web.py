"""CSV boundary, scoped screen projections and safe failures without a database or browser."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_organization_fixtures import NOW, example_config
from test_organization_storage import source_case
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import COOKIE_NAME, BrowserSettings
from otm.auth.service import AdminPrincipal, SessionFailure
from otm.organization.csv_feed import MAX_BYTES, CsvFeedError, parse_csv
from otm.organization.persistence_contracts import OrganizationOutcome
from otm.organization.views import OrganizationQuery
from otm.organization.web import OrganizationWeb, load_profile, project
from otm.storage.organization import OrganizationConflict, SqlOrganizationStore

__all__ = ["session_case"]
ORIGIN = "https://otm.example.test"
CSV = b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nRoot,root@example.test,,\n"


# One synthetic immutable revision supports scoped service/view tests independent of persistence.
def web_case():
    c = source_case()
    c.feed.update(received_at=NOW, workspace_id="example-org")
    store = Mock(
        inspection=Mock(return_value=(c.config, c.revision, None, c.feed, c.candidate.issues))
    )
    store.ingest.return_value = OrganizationOutcome(snapshot_id=uuid4(), state="published")
    return SimpleNamespace(
        **vars(c), store=store, web=OrganizationWeb(store, Mock(return_value=NOW), c.config)
    )


# File validation completes before the initial source configuration or ingestion can write.
def test_upload_validation_idempotency_and_source_authority():
    c = web_case()
    key = uuid4()
    for content in (b"wrong,headers\n", b"", CSV.replace(b"Root,", b","), CSV + b"Broken\n"):
        with pytest.raises(CsvFeedError):
            c.web.upload("principal", content, NOW, key, True)
    c.store.inspection.assert_not_called()
    c.web.upload("principal", CSV, NOW, key, True)
    first = c.store.ingest.call_args
    c.web.upload("principal", CSV, NOW, key, True)
    assert c.store.ingest.call_args == first
    c.web.upload("principal", CSV, NOW, uuid4(), False)
    newer = c.store.ingest.call_args.args[1]
    assert newer.envelope.external_snapshot_id != first.args[1].envelope.external_snapshot_id
    assert newer.envelope.source_id == c.config.policy.source_id
    assert newer.envelope.declared_completeness == "partial"
    c.store.configure_initial.assert_not_called()
    c.store.inspection.return_value = (None, None, None, None, ())
    with pytest.raises(OrganizationConflict, match="ORGANIZATION_NOT_CONFIGURED"):
        c.web.upload("principal", CSV, NOW, key, True)
    c.store.configure_initial.assert_not_called()
    c.web.initial = None
    with pytest.raises(OrganizationConflict):
        c.web.upload("principal", CSV, NOW, uuid4(), True)


# Explicit private profiles are bounded and cannot activate undated development source trust.
def test_profile_is_explicit_bounded_and_production_dated(tmp_path):
    assert load_profile(None) is None
    path = tmp_path / "profile.json"
    c = example_config()
    path.write_text(c.model_dump_json())
    assert load_profile(path) == c
    path.write_text("x" * 65537)
    with pytest.raises(ValueError, match="INVALID_ORGANIZATION_CONFIGURATION"):
        load_profile(path)
    path.write_text(
        example_config(
            authoritative=False, allow_undated_development_metadata=True
        ).model_dump_json()
    )
    with pytest.raises(ValueError, match="DATED_PRODUCTION_FEEDS_REQUIRED"):
        load_profile(path)


# Null/partial directory data stays honest and sort/search input is literal instead of executable
# SQL.
def test_directory_projection_search_sort_and_clamped_pages():
    c = web_case()
    page = c.web.directory("p", OrganizationQuery(page=99, page_size=10, direction="desc"))
    assert page.employee_count == 5 and page.pages == page.page == 1
    assert page.latest.snapshot_id == c.feed["id"]
    assert page.items[0].full_name == "Root"
    assert any(f.code == "EMPLOYEE_ADDED" for f in page.findings)
    searched = c.web.directory("p", OrganizationQuery(query="LOB One", sort="manager_name"))
    assert searched.total == 3
    assert c.web.directory("p", OrganizationQuery(query="' OR 1=1 --")).total == 0
    c.store.inspection.return_value = (None, None, None, None, ())
    assert not c.web.directory("p", OrganizationQuery()).upload_enabled
    c.web.initial = None
    empty = c.web.directory("p", OrganizationQuery())
    assert not empty.configured and not empty.upload_enabled and not empty.items


# Delta projections preserve raw text safely, emit graph issues and identify automatic metadata
# changes.
def test_project_issues_absence_reference_and_changed_metadata():
    c = web_case()
    people = list(c.revision.people)
    idx = next(i for i, p in enumerate(people) if p.email == "engineer@example.test")
    engineer = people[idx]
    people[idx] = engineer.model_copy(
        update={
            "full_name": "O'Connor <script>literal</script>",
            "absence_review": True,
            "ancestry": "incomplete",
        }
    )
    current = c.revision.model_copy(update={"people": tuple(people)})
    rows, findings = project(
        c.config,
        current,
        c.revision,
        (("PERSON_ABSENCE_REVIEW", engineer.email), ("ANCESTRY_UNRESOLVED", engineer.email)),
    )
    assert next(r for r in rows if r.email == engineer.email).absence_review
    assert {f.category for f in findings} == {"actionable", "informational", "change"}
    assert any(f.code == "METADATA_UPDATED" for f in findings)
    assert any("<script>" in r.full_name for r in rows)
    excluded = c.config.model_copy(update={"managed_exclusions": (engineer.id,)})
    assert engineer.email not in {p.email for p in project(excluded, current, c.revision)[0]}
    people[idx] = engineer.model_copy(update={"profile": "reference"})
    rows, _ = project(c.config, current.model_copy(update={"people": tuple(people)}), None)
    assert engineer.email not in {r.email for r in rows}


# Snapshot inspection is read-only, scoped and coherent, including an entirely unconfigured
# workspace.
def test_inspection_empty_and_existing_heads(session_case):
    c = web_case()
    connection = MagicMock()
    engine = Mock(connect=Mock(return_value=nullcontext(connection)))
    principal = AdminPrincipal(session_case.session)
    store = SqlOrganizationStore(engine, session_case.service, Mock(return_value=NOW))
    with patch("otm.storage.organization.read_snapshot", return_value=nullcontext(connection)):
        connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
        assert store.inspection(principal) == (None, None, None, None, ())
        state = {
            "configuration": c.config.model_dump(mode="json"),
            "applied_version_id": c.revision.id,
        }
        c.revision = c.revision.model_copy(update={"predecessor_id": uuid4()})
        connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
            state,
            c.feed,
        ]
        connection.execute.return_value.mappings.return_value.one.return_value = c.feed
        connection.execute.return_value.scalar_one.return_value = c.config.model_dump(mode="json")
        with patch.object(store, "_revision", side_effect=[c.revision, None]):
            assert store.inspection(principal)[1] == c.revision
        state["applied_version_id"] = None
        connection.execute.return_value.mappings.return_value.one_or_none.side_effect = [
            state,
            None,
        ]
        assert store.inspection(principal)[1:] == (None, None, None, ())


# Authenticated endpoints preserve browser boundary checks and emit only fixed error projections.
@pytest.fixture
def web_http(session_case):
    c = web_case()
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), organization=c.web
    )
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set(COOKIE_NAME, session_case.handle)
        c.client = client
        c.headers = {
            "origin": ORIGIN,
            "x-otm-request": "1",
            "content-type": "text/csv",
            "x-otm-as-of": NOW.isoformat(),
            "x-otm-delivery": str(uuid4()),
            "x-otm-complete": "true",
        }
        yield c


# Directory input is allowlisted and storage/authorization failures disclose neither data nor SQL.
def test_http_reads_and_upload_success_errors(web_http):
    c = web_http
    assert c.client.get("/api/organization").status_code == 200
    assert c.client.get("/api/organization?sort=DROP%20TABLE").status_code == 400
    assert (
        c.client.post("/api/organization/feeds", content=CSV, headers=c.headers).status_code == 200
    )
    c.store.inspection.side_effect = RuntimeError("private SQL")
    response = c.client.get("/api/organization")
    assert response.status_code == 503 and "private" not in response.text
    c.store.inspection.side_effect = SessionFailure(403, "ADMINISTRATOR_REQUIRED")
    assert c.client.get("/api/organization").status_code == 403
    c.store.inspection.side_effect = None
    for error, status in (
        (OrganizationConflict("private"), 409),
        (ValueError("private"), 400),
        (SessionFailure(403, "ADMINISTRATOR_REQUIRED"), 403),
        (RuntimeError("private"), 503),
    ):
        c.store.ingest.side_effect = error
        response = c.client.post("/api/organization/feeds", content=CSV, headers=c.headers)
        assert response.status_code == status and "private" not in response.text


# Malformed files, excessive bodies and invalid source metadata are refused before mutation.
@pytest.mark.parametrize(
    "kind,status",
    [
        ("type", 415),
        ("timestamp", 400),
        ("future", 400),
        ("key", 400),
        ("complete", 400),
        ("size", 413),
        ("csv", 400),
        ("csrf", 403),
        ("unauthenticated", 401),
    ],
)
def test_http_upload_rejects_untrusted_input(web_http, kind, status):
    c = web_http
    headers, content = dict(c.headers), CSV
    if kind == "type":
        headers["content-type"] = "application/json"
    elif kind == "timestamp":
        headers["x-otm-as-of"] = "2026-10-12T12:00:00"
    elif kind == "future":
        headers["x-otm-as-of"] = (NOW + timedelta(days=1)).isoformat()
    elif kind == "key":
        headers["x-otm-delivery"] = "'; DROP TABLE org_person; --"
    elif kind == "complete":
        headers["x-otm-complete"] = "arbitrary"
    elif kind == "size":
        content = b"x" * (MAX_BYTES + 1)
    elif kind == "csv":
        content = b"bad,headers\n"
    elif kind == "csrf":
        headers.pop("origin")
    else:
        c.client.cookies.clear()
    response = c.client.post("/api/organization/feeds", content=content, headers=headers)
    assert response.status_code == status
    c.store.ingest.assert_not_called()


# Long names are bounded while apostrophes, SQL-like strings and markup stay legitimate literal
# data.
def test_csv_name_length_and_injection_strings():
    for name in ("O'Connor", "Robert'); DROP TABLE org_person;--", "<script>alert(1)</script>"):
        content = CSV.replace(b"Root,", name.encode() + b",")
        assert parse_csv(content)[0].full_name == name
    with pytest.raises(CsvFeedError, match="Invalid name or email"):
        parse_csv(CSV.replace(b"Root,", b"a" * 257 + b","))


# Missing profiles remain visible; qualified suppressions retain their exact targets.
def test_reference_findings_suppressions_and_stable_identity_changes():
    from otm.organization.contracts import ReviewDecision

    c = web_case()
    engineer = next(p for p in c.revision.people if p.email == "engineer@example.test")
    reference = engineer.model_copy(update={"profile": "reference", "full_name": None})
    current = c.revision.model_copy(update={"people": (reference,)})
    rows, findings = project(
        c.config, current, None, (("MANAGER_PROFILE_MISSING", engineer.email),)
    )
    assert not rows and findings[0].category == "informational"
    target = "one:" + engineer.email
    decision = ReviewDecision(
        kind="DESIGNEE_INVALID",
        target=target,
        disposition="ignored",
        recorded_at=NOW,
        actor="synthetic",
        reason="fixture",
    )
    config = c.config.model_copy(update={"review_decisions": (decision,)})
    assert not project(config, current, None, (("DESIGNEE_INVALID", target),))[1]
    renamed = engineer.model_copy(update={"email": "renamed@example.test", "full_name": "New name"})
    current = c.revision.model_copy(update={"people": (renamed,)})
    findings = project(c.config, current, c.revision)[1]
    assert len(findings) == 1 and findings[0].code == "METADATA_UPDATED"
    assert "Email" in findings[0].detail


# Enabling local instructions exposes only a flag, never a browser-triggered owner reset operation.
def test_local_reset_control_has_no_command_route(web_http):
    c = web_http
    assert c.client.get("/api/organization").json()["test_reset_enabled"] is False
    c.web.test_reset_enabled = True
    assert c.client.get("/api/organization").json()["test_reset_enabled"] is True
    response = c.client.post("/api/organization/reset", headers=c.headers)
    assert response.status_code == 404
    c.store.configure_initial.assert_not_called()
    c.store.ingest.assert_not_called()


# The browser's excluded-profile toggle must survive HTTP parsing into the scoped directory query.
@pytest.mark.parametrize("include_removed", [False, True])
def test_http_preserves_excluded_profile_visibility(web_http, include_removed):
    c = web_http
    with patch.object(c.web, "directory", wraps=c.web.directory) as directory:
        response = c.client.get(
            "/api/organization", params={"include_removed": str(include_removed).lower()}
        )
    assert response.status_code == 200
    assert directory.call_args.args[1].include_removed is include_removed
