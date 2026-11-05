"""Bounded configuration drafts, honest retry/conflict semantics and protected request parsing."""

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.auth.service import SessionFailure
from otm.configuration.contracts import (
    BaselineContent,
    BaselineDirectory,
    BaselineDraftEvidence,
    SaveBaselineDraft,
    describe_draft,
)
from otm.configuration.http import baseline_router, guarded
from otm.configuration.service import BaselineAuthoring, draft_view
from otm.operations.contracts import ActorIdentity, canonical_hash
from otm.storage.organization import OrganizationConflict

__all__ = ["session_case"]
NOW = datetime(2026, 11, 2, tzinfo=UTC)
PAYLOAD = {
    "policy_statements": [
        "Allow group Example to read all-resources in tenancy\nwhere request.region='example'"
    ],
    "quota_statements": ["set example quota example-count to 8 in tenancy"],
    "monthly_budget_amount": "200",
    "budget_currency": "USD",
    "tag_defaults": [{"key": "Environment", "value": "Test"}],
}


# Use JSON trust-boundary parsing so tuple/decimal strictness matches real request behavior.
def content(**changes):
    return BaselineContent.model_validate_json(json.dumps({**PAYLOAD, **changes}))


# Construct one explicit database row whose hash can be independently checked against its values.
def row(value=None, **changes):
    value = value or content()
    return {
        **value.model_dump(mode="json"),
        "monthly_budget_amount": value.monthly_budget_amount,
        "id": uuid4(),
        "workspace_id": "synthetic",
        "version_number": 1,
        "edit_revision": 1,
        "created_by": "actor",
        "created_at": NOW,
        "content_hash": canonical_hash(value.model_dump(mode="json")),
        **changes,
    }


# Model each returned SQL row set separately; tests still inspect parameterized real SQL
# expressions.
def result(value):
    return Mock(
        mappings=Mock(
            return_value=Mock(
                one_or_none=Mock(return_value=value),
                one=Mock(return_value=value),
                all=Mock(return_value=value if isinstance(value, list) else []),
            )
        )
    )


# Small repository doubles isolate authorization/transaction orchestration from provider-
# independent rules.
def setup(existing=None, saved=None):
    connection = Mock()
    actor = ActorIdentity(issuer="urn:test", subject="operator", display_name="Test operator")
    principal = SimpleNamespace(actor=actor)
    store = Mock(_principal=Mock(return_value="synthetic"))
    store._write.side_effect = lambda user: nullcontext((connection, "synthetic", NOW))
    connection.execute.side_effect = [result(existing), result(saved or row()), Mock()]
    connection.scalar.return_value = 0
    return SimpleNamespace(
        service=BaselineAuthoring(store), store=store, connection=connection, principal=principal
    )


# Equivalent monetary encodings hash identically without flattening complete statement boundaries.
def test_content_canonical_money_and_change_details():
    first = content()
    assert first.monthly_budget_amount == Decimal("200.0000")
    assert first == content(monthly_budget_amount="200.00000")
    assert "\n" in first.policy_statements[0]
    evidence = BaselineDraftEvidence(
        baseline_id=uuid4(), version_number=1, edit_revision=1, before=None, after=first
    )
    assert any("Policy statement 1" in change for change in describe_draft(evidence))
    assert describe_draft(evidence.model_copy(update={"before": first})) == ()
    removed = content(
        policy_statements=["Another complete statement"],
        tag_defaults=[{"key": "Other", "value": "Value"}],
    )
    changes = describe_draft(evidence.model_copy(update={"before": first, "after": removed}))
    assert any("Tag Environment: Test → Not set" in change for change in changes)
    assert any("Tag Other: Not set → Value" in change for change in changes)
    assert any("Policy statement 1" in change for change in changes)


# Draft values are bounded static data; empty lists, embedded credentials and ambiguous tags
# fail closed.
@pytest.mark.parametrize(
    "changes",
    [
        {"policy_statements": []},
        {"quota_statements": []},
        {"policy_statements": [" "]},
        {"quota_statements": ["x\x00"]},
        {"policy_statements": ["-----BEGIN PRIVATE KEY-----"]},
        {"monthly_budget_amount": "0"},
        {"monthly_budget_amount": "-1"},
        {"monthly_budget_amount": "0.00001"},
        {"monthly_budget_amount": "10000000000000000"},
        {"monthly_budget_amount": "NaN"},
        {"budget_currency": "usd"},
        {"budget_period": "YEARLY"},
        {"tag_namespace": "Other"},
        {"tag_defaults": [{"key": "A", "value": "x"}, {"key": "a", "value": "y"}]},
        {"tag_defaults": [{"key": " ", "value": "x"}]},
        {"tag_defaults": [{"key": "A", "value": "\x00"}]},
    ],
)
def test_invalid_authoring_values(changes):
    with pytest.raises(ValueError):
        content(**changes)


# IDs and revisions cannot independently target another record or invent a publication flag.
def test_paired_revision_and_closed_command():
    for values in ({"baseline_id": str(uuid4())}, {"expected_revision": 1}, {"published": True}):
        with pytest.raises(ValueError):
            SaveBaselineDraft.model_validate_json(json.dumps({"content": PAYLOAD, **values}))
    assert SaveBaselineDraft(content=content()).baseline_id is None


# Reads retain honest absence and reject mismatched stored digests instead of echoing corrupt
# evidence.
def test_draft_view_and_scoped_read():
    value = row()
    assert draft_view(value).content == content()
    with pytest.raises(RuntimeError):
        draft_view({**value, "content_hash": "0" * 64})
    c = setup()
    for configured, existing in ((None, None), ("synthetic", value)):
        c.connection.scalar.side_effect = [configured, 0]
        c.connection.execute.side_effect = [
            result(existing),
            result(None),
            result([]),
            result(None),
        ]
        with patch(
            "otm.configuration.service.read_snapshot", return_value=nullcontext(c.connection)
        ):
            view = c.service.read(c.principal)
        assert view.configured is (configured is not None)
        assert bool(view.draft) is bool(existing)


# Stubbed persistence checks orchestration of draft/revision/audit writes and transport retries.
def test_save_create_edit_and_replay():
    original = row()
    c = setup(saved=original)
    saved = c.service.save(c.principal, SaveBaselineDraft(content=content()))
    assert saved.id == original["id"]
    assert c.store._workspace.call_args.kwargs == {"lock": True}
    assert c.connection.execute.call_count == 3
    audit = c.connection.execute.call_args.args[0].compile().params
    assert audit["kind"] == "baseline_draft_saved" and audit["data"]["before"] is None
    assert audit["data_hash"] == canonical_hash(audit["data"])
    c = setup(existing=original)
    assert c.service.save(c.principal, SaveBaselineDraft(content=content())).id == original["id"]
    assert c.connection.execute.call_count == 1
    changed = content(monthly_budget_amount="500")
    c = setup(existing=original, saved=row(changed, id=original["id"], edit_revision=2))
    view = c.service.save(
        c.principal,
        SaveBaselineDraft(baseline_id=original["id"], expected_revision=1, content=changed),
    )
    assert view.edit_revision == 2
    assert c.connection.execute.call_args.args[0].compile().params["data"]["before"]


# Stale/foreign targets and a missing workspace never create another draft or append a
# misleading save.
@pytest.mark.parametrize("case", ["foreign", "stale", "missing", "no-workspace", "corrupt"])
def test_save_conflicts_before_writes(case):
    existing = row()
    c = setup(existing=None if case == "missing" else existing)
    identifier = uuid4() if case == "foreign" else existing["id"]
    if case == "no-workspace":
        c.store._workspace.side_effect = OrganizationConflict("ORGANIZATION_NOT_CONFIGURED")
    if case == "corrupt":
        existing["content_hash"] = "0" * 64
    with pytest.raises((OrganizationConflict, RuntimeError)):
        c.service.save(
            c.principal,
            SaveBaselineDraft(
                baseline_id=identifier,
                expected_revision=2 if case == "stale" else 1,
                content=content(monthly_budget_amount="500"),
            ),
        )
    assert c.connection.execute.call_count <= 1


# Normalized errors never expose SQL, credential-like input or source content to the browser.
@pytest.mark.parametrize(
    "error,status",
    [
        (OrganizationConflict("ORGANIZATION_NOT_CONFIGURED"), 409),
        (OrganizationConflict("changed"), 409),
        (ValueError("private"), 400),
        (RuntimeError("private"), 503),
    ],
)
def test_safe_error_mapping(error, status):
    response = guarded(Mock(side_effect=error))
    assert response.status_code == status and b"private" not in response.body
    with pytest.raises(SessionFailure):
        guarded(Mock(side_effect=SessionFailure(403, "ADMINISTRATOR_REQUIRED")))


# The real middleware authorizes both paths before parsing or invoking the drafting service.
def test_draft_http_boundary(session_case):
    service = Mock()
    service.read.return_value = BaselineDirectory(configured=True)
    service.save.return_value = draft_view(row())
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(baseline_router(service))
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/configuration/baselines").status_code == 401
        headers = {**cookie(session_case), "origin": ORIGIN, "x-otm-request": "1"}
        assert client.get("/api/configuration/baselines", headers=headers).status_code == 200
        assert (
            client.post(
                "/api/configuration/baselines/draft", json={"content": PAYLOAD}, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/configuration/baselines/draft", content="bad", headers=headers
            ).status_code
            == 415
        )
        assert (
            client.post(
                "/api/configuration/baselines/draft",
                content="bad",
                headers={**headers, "content-type": "application/json"},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/configuration/baselines/draft",
                content="x" * 2097153,
                headers={**headers, "content-type": "application/json"},
            ).status_code
            == 413
        )
        assert service.save.call_count == 1
        large_content = content(
            policy_statements=["界" * 2000] * 50,
            quota_statements=["界" * 2000] * 50,
            tag_defaults=[{"key": f"Tag{index}", "value": "界" * 1000} for index in range(100)],
        )
        large_body = json.dumps(
            {"content": large_content.model_dump(mode="json")}, ensure_ascii=False
        ).encode()
        assert 262144 < len(large_body) < 2097152
        assert (
            client.post(
                "/api/configuration/baselines/draft",
                content=large_body,
                headers={**headers, "content-type": "application/json"},
            ).status_code
            == 200
        )
        assert service.save.call_count == 2
        assert len(service.save.call_args.args[1].content.quota_statements) == 50
        for field in ("policy_statements", "quota_statements"):
            assert (
                client.post(
                    "/api/configuration/baselines/draft",
                    json={"content": {**PAYLOAD, field: ["Statement"] * 51}},
                    headers=headers,
                ).status_code
                == 400
            )
        assert service.save.call_count == 2
        fractional = client.post(
            "/api/configuration/baselines/draft",
            json={"content": {**PAYLOAD, "monthly_budget_amount": "250.50"}},
            headers=headers,
        )
        assert fractional.status_code == 400
        assert fractional.json() == {"code": "INVALID_BASELINE_DRAFT"}
        assert (
            client.post(
                "/api/configuration/baselines/draft",
                json={"workspace_id": "foreign", "content": PAYLOAD},
                headers=headers,
            ).status_code
            == 400
        )


# New commands accept equivalent whole amounts while historical content/hash keeps exact decimals.
@pytest.mark.parametrize("amount", ["250", "250.0000", "250.00000"])
def test_save_budget_accepts_whole_units(amount):
    command = SaveBaselineDraft(content=content(monthly_budget_amount=amount))
    assert command.content.monthly_budget_amount == Decimal("250.0000")


# Request validation rejects cents rather than silently truncating or rounding configuration.
@pytest.mark.parametrize("amount", ["250.50", "0.5", "250.0001"])
def test_save_budget_rejects_fractional_units(amount):
    archived = content(monthly_budget_amount=amount)
    assert draft_view(row(archived)).content == archived
    with pytest.raises(ValueError, match="WHOLE_BUDGET_REQUIRED"):
        SaveBaselineDraft(content=archived)


# Both list categories accept fifty entries and reject the next entry at the authoritative boundary.
@pytest.mark.parametrize("field", ["policy_statements", "quota_statements"])
def test_fifty_statement_boundary(field):
    statements = [f"Statement {index}" for index in range(50)]
    accepted = SaveBaselineDraft(content=content(**{field: statements}))
    assert list(getattr(accepted.content, field)) == statements
    with pytest.raises(ValueError):
        content(**{field: statements + ["Statement 51"]})
