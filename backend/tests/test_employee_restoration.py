"""Fresh positive-row restoration and independent destructive consent without cloud side effects."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW
from test_tenancy_workflow_units import command, database, person, registry, service

from otm.organization.reviews import returning_people
from otm.storage.organization import OrganizationConflict
from otm.tenancies.contracts import DESTRUCTIVE_ACTIONS

__all__ = ["registry"]


# Explicit fresh positive rows qualify independently of census completeness and prior absence.
@pytest.mark.parametrize("removed", [None, NOW - timedelta(seconds=1), NOW])
def test_return_requires_new_positive_row_not_absence_cycle(registry, removed):
    s, p = registry, person(registry)
    row = {**s.controls[p.id], "directory_status": "offboarded", "removed_capture_at": removed}
    assert returning_people([row], s.head, NOW + timedelta(seconds=1), {p.id}) == {p.id}
    assert returning_people([row], s.head, NOW + timedelta(seconds=1), set()) == set()
    assert returning_people([row], s.head, NOW, {p.id}) == set()


# Exemptions, merged identities, live work, unqualified captures and references are never restored.
@pytest.mark.parametrize(
    "change,capture",
    [
        ({"directory_status": "exempt"}, NOW + timedelta(seconds=1)),
        ({"directory_status": "merged"}, NOW + timedelta(seconds=1)),
        ({"directory_status": "outside"}, NOW + timedelta(seconds=1)),
        ({"pending_operation_id": uuid4()}, NOW + timedelta(seconds=1)),
        ({"removed_capture_at": NOW + timedelta(seconds=2)}, NOW + timedelta(seconds=1)),
        ({}, None),
        ({}, NOW - timedelta(seconds=1)),
    ],
)
def test_return_guards(registry, change, capture):
    s, p = registry, person(registry)
    row = {**s.controls[p.id], "directory_status": "offboarded", **change}
    assert returning_people([row], s.head, capture, {p.id}) == set()
    assert returning_people([row], None, capture, {p.id}) == set()


# Server consent is independent of HTML, manager/shared warnings and association plans.
@pytest.mark.parametrize("action", sorted(DESTRUCTIVE_ACTIONS))
def test_new_destructive_admission_requires_consent_before_mutation(registry, action):
    s, p = registry, person(registry)
    app, connection = service(s), database()
    app.store._write.return_value = nullcontext((connection, s.workspace, NOW))
    request = command(s, p, action, confirm_destructive=False)
    with (
        patch.object(app, "_replay", return_value=None),
        patch("otm.tenancies.workflows.registry_state", return_value=s),
        patch(
            "otm.tenancies.workflows.person_workflow",
            return_value=SimpleNamespace(actions=[action]),
        ),
        patch.object(app, "_admit") as admit,
        patch.object(app, "_merge") as merge,
    ):
        with pytest.raises(OrganizationConflict, match="DESTRUCTIVE_CONFIRMATION_REQUIRED"):
            app.act(Mock(), request)
        admit.assert_not_called()
        merge.assert_not_called()
    connection.execute.assert_not_called()


# An additive omitted-false flag preserves old canonical request bytes and authenticated replays.
def test_old_destructive_request_replay_is_not_a_new_admission(registry):
    s, p = registry, person(registry)
    app, connection = service(s), database()
    app.store._write.return_value = nullcontext((connection, s.workspace, NOW))
    request = command(s, p, "offboard_person", confirm_destructive=False)
    assert "confirm_destructive" not in request.model_dump(mode="json")
    prior = object()
    with (
        patch.object(app, "_replay", return_value=prior),
        patch("otm.tenancies.workflows.registry_state") as state,
    ):
        assert app.act(Mock(), request) is prior
        state.assert_not_called()


# Fixed confirmation guidance is public; no exception text or employee/provider data is reflected.
@pytest.mark.parametrize("code", ["DESTRUCTIVE_CONFIRMATION_REQUIRED", "PERSON_NOT_ABSENT"])
def test_destructive_confirmation_http_guidance_is_explicit(code):
    import json

    from otm.tenancies.http import guarded

    response = guarded(Mock(side_effect=OrganizationConflict(code)))
    assert response.status_code == 409
    assert json.loads(response.body) == {"code": code}
