"""Local publication, immutable lineage and scoped history without provider writes."""

import json
from contextlib import nullcontext
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_sessions import session_case

__all__ = ["session_case"]
from test_baseline_authoring import NOW, content, result, row, setup

from otm.auth.service import SessionFailure
from otm.configuration.contracts import (
    BaselinePublicationEvidence,
    BaselineQuery,
    PublishBaseline,
    SaveBaselineDraft,
)
from otm.configuration.http import guarded
from otm.configuration.service import BaselineAuthoring, draft_view
from otm.providers.baseline import PublicationUnavailable
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.storage.organization import OrganizationConflict


# Derive publication metadata from the actual synthetic publisher rather than a browser claim.
def published_row(original, principal, **changes):
    return {
        **original,
        "published_at": NOW,
        "published_by": principal.actor.key,
        "published_by_name": principal.actor.display_name,
        "publication_mode": "simulated",
        "edit_revision": original["edit_revision"] + 1,
        **changes,
    }


# The row update and fully typed audit contain the same frozen recipe and qualification mode.
def test_publish_and_replay():
    original = row()
    c = setup(existing=original)
    saved = published_row(original, c.principal)
    c.connection.execute.side_effect = [result(original), result(saved), Mock(), Mock()]
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    command = PublishBaseline(baseline_id=original["id"], expected_revision=1)
    version = service.publish(c.principal, command)
    assert version.published_by_name == "Test operator" and version.publication_mode == "simulated"
    update = c.connection.execute.call_args_list[1].args[0].compile().params
    assert update["published_by"] == c.principal.actor.key and update["edit_revision"] == 2
    event = c.connection.execute.call_args_list[3].args[0].compile().params
    assert event["kind"] == "baseline_published"
    evidence = BaselinePublicationEvidence.model_validate_json(json.dumps(event["data"]))
    assert evidence.baseline == version
    c.connection.execute.side_effect = [result(saved)]
    c.connection.execute.reset_mock()
    assert service.publish(c.principal, command) == version
    assert c.connection.execute.call_count == 1
    with pytest.raises(OrganizationConflict):
        c.connection.execute.side_effect = [result(saved)]
        service.publish(
            c.principal, PublishBaseline(baseline_id=original["id"], expected_revision=2)
        )


# Unavailable qualification, stale/absent rows, corrupt evidence and invalid budgets never publish.
@pytest.mark.parametrize(
    "case", ["missing", "stale", "corrupt", "fraction", "currency", "unavailable"]
)
def test_publish_rejects_invalid_transition(case):
    value = (
        content(monthly_budget_amount="250.5")
        if case == "fraction"
        else content(budget_currency="EUR")
        if case == "currency"
        else content()
    )
    existing = row(value, edit_revision=2 if case == "stale" else 1)
    if case == "corrupt":
        existing["content_hash"] = "0" * 64
    c = setup(existing=None if case == "missing" else existing)
    service = BaselineAuthoring(
        c.store, None if case == "unavailable" else SimulatedBaselineQualifier()
    )
    expected = (
        PublicationUnavailable
        if case == "unavailable"
        else OrganizationConflict
        if case in {"missing", "stale"}
        else RuntimeError
        if case == "corrupt"
        else ValueError
    )
    with pytest.raises(expected):
        service.publish(
            c.principal, PublishBaseline(baseline_id=existing["id"], expected_revision=1)
        )
    assert c.connection.execute.call_count <= 1
    assert guarded(Mock(side_effect=PublicationUnavailable())).status_code == 503


# A previously authorized principal cannot replay publication after its live grant is denied.
def test_publish_replay_rechecks_authority():
    c = setup()
    c.store._write.side_effect = SessionFailure(403, "ADMINISTRATOR_REQUIRED")
    with pytest.raises(SessionFailure):
        BaselineAuthoring(c.store, SimulatedBaselineQualifier()).publish(
            c.principal, PublishBaseline(baseline_id=uuid4(), expected_revision=1)
        )


# Invalid metadata or mismatched recipe hashes cannot become published evidence.
def test_publication_closed_evidence():
    c = setup()
    original = row()
    with pytest.raises(ValueError):
        draft_view({**original, "published_at": NOW})
    draft = draft_view(original)
    with pytest.raises(ValueError):
        BaselinePublicationEvidence(
            qualification_version="baseline-structure-simulated-1", baseline=draft
        )
    value = draft_view(published_row(original, c.principal))
    with pytest.raises(ValueError):
        BaselinePublicationEvidence(qualification_version="oci", baseline=value)
    with pytest.raises(ValueError):
        BaselinePublicationEvidence(
            qualification_version="baseline-structure-simulated-1",
            baseline=value.model_copy(update={"content_hash": "0" * 64}),
        )
    with pytest.raises(ValueError):
        PublishBaseline(baseline_id=uuid4(), expected_revision=0)
    with pytest.raises(ValueError):
        BaselineQuery.model_validate_json('{"page_size":15}')
    with pytest.raises(ValueError):
        BaselineQuery.model_validate_json('{"baseline_id":"private"}')


# A copied draft targets the exact latest parent; stale parents and silent reparenting are rejected.
def test_new_draft_parent_fence():
    parent = uuid4()
    created = row(based_on_id=parent, version_number=3)
    c = setup(saved=created)
    c.connection.scalar.side_effect = [parent, 2]
    value = c.service.save(c.principal, SaveBaselineDraft(content=content(), based_on_id=parent))
    assert value.based_on_id == parent and value.version_number == 3
    insert = c.connection.execute.call_args_list[1].args[0].compile().params
    assert insert["based_on_id"] == parent
    c = setup()
    c.connection.scalar.return_value = uuid4()
    with pytest.raises(OrganizationConflict):
        c.service.save(c.principal, SaveBaselineDraft(content=content(), based_on_id=parent))
    c = setup(existing=created)
    with pytest.raises(OrganizationConflict):
        c.service.save(c.principal, SaveBaselineDraft(content=content()))


# Paged publication history, exact selection and latest parent come from a single scoped snapshot.
def test_history_page_and_selected_version():
    c = setup()
    one = published_row(row(), c.principal)
    latest = published_row(row(version_number=11), c.principal)
    draft = row(version_number=12, based_on_id=latest["id"])
    c.connection.scalar.side_effect = ["synthetic", 11]
    c.connection.execute.side_effect = [
        result(draft),
        result(latest),
        result([one]),
        result(one),
    ]
    with patch("otm.configuration.service.read_snapshot", return_value=nullcontext(c.connection)):
        view = BaselineAuthoring(c.store, SimulatedBaselineQualifier()).read(
            c.principal, BaselineQuery(page=2, baseline_id=one["id"])
        )
    assert view.page == view.pages == 2 and view.total == 11 and view.latest.id == latest["id"]
    assert view.draft.id == draft["id"] and view.selected.id == one["id"]
    assert view.items == (draft_view(one),) and view.publication_available
    for call in c.connection.execute.call_args_list:
        assert "synthetic" in call.args[0].compile().params.values()


# The real HTTP boundary never accepts actor/mode/content claims or foreign-origin publication.
def test_publication_http_contract(session_case):
    from fastapi.testclient import TestClient
    from test_auth_http import ORIGIN, cookie

    from otm.app import create_app
    from otm.auth.http import BrowserSettings
    from otm.configuration.http import baseline_router

    c = setup()
    version = draft_view(published_row(row(), c.principal))
    service = Mock(publish=Mock(return_value=version))
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN))
    app.include_router(baseline_router(service))
    command = {"baseline_id": str(version.id), "expected_revision": 1}
    with TestClient(app, base_url=ORIGIN) as client:
        headers = {"origin": ORIGIN, "x-otm-request": "1"}
        assert (
            client.post(
                "/api/configuration/baselines/publish", json=command, headers=headers
            ).status_code
            == 401
        )
        headers.update(cookie(session_case))
        assert (
            client.post(
                "/api/configuration/baselines/publish",
                json={**command, "publication_mode": "oci"},
                headers=headers,
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/configuration/baselines/publish",
                json=command,
                headers={**headers, "origin": "https://attacker.test"},
            ).status_code
            == 403
        )
        assert service.publish.call_count == 0
        published = client.post(
            "/api/configuration/baselines/publish", json=command, headers=headers
        )
        assert published.status_code == 200 and published.json()["publication_mode"] == "simulated"
        assert (
            client.post(
                "/api/configuration/baselines/current",
                json={"baseline_id": str(version.id), "expected_current_id": None},
                headers=headers,
            ).status_code
            == 404
        )
        bad = client.get("/api/configuration/baselines?baseline_id=private-value", headers=headers)
        assert bad.status_code == 400 and "private-value" not in bad.text
        service.publish.side_effect = PublicationUnavailable()
        assert (
            client.post(
                "/api/configuration/baselines/publish", json=command, headers=headers
            ).status_code
            == 503
        )


# Publication cannot be silently enabled on the unconfigured process-only application.
def test_publication_dependency_requires_organization():
    from otm.app import create_app

    with pytest.raises(ValueError, match="BASELINE_PUBLICATION_REQUIRES_ORGANIZATION"):
        create_app(baseline_qualifier=SimulatedBaselineQualifier())
