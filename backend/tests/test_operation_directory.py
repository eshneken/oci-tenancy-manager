"""Closed operation reads, coherent snapshots and HTTP scope/error guards without a database."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from test_admission_service import NOW, admission
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.auth.http import BrowserSettings
from otm.operations.contracts import InspectionIntent, IntentEventData, canonical_hash
from otm.operations.execution_contracts import InspectionOutcome
from otm.operations.views import OperationDetail, OperationDirectory, OperationQuery
from otm.storage.operation_directory import SqlOperationDirectory

__all__ = ["session_case", "admission"]


# Reuse the actual closed admission models rather than inventing a competing read fixture format.
@pytest.fixture
def directory_case(admission):
    event = IntentEventData(
        intent=InspectionIntent(
            contract_version="inspect-import-1",
            kind="inspect_import",
            workspace_id=admission.request.workspace_id,
            policy_revision=admission.policy.policy_revision,
            access_binding_id=admission.policy.access_binding_id,
            target={
                "organization_id": admission.policy.organization_id,
                "parent_tenancy_ocid": admission.policy.parent_tenancy_ocid,
                "tenancy_ocid": admission.request.tenancy_ocid,
            },
        ),
        actor=admission.actor,
    )
    data = event.model_dump(mode="json")
    row = dict(
        id=uuid4(),
        workspace_id=event.intent.workspace_id,
        kind="inspect_import",
        state="queued",
        stage="inspect_target",
        current_intent_revision=1,
        initiating_actor_subject=admission.actor.key,
        intent_data=data,
        intent_hash=canonical_hash(data),
        accepted_at=NOW,
        updated_at=NOW,
        completed_at=None,
    )
    connection = MagicMock()
    engine = Mock(
        connect=Mock(
            return_value=SimpleNamespace(
                execution_options=Mock(return_value=nullcontext(connection))
            )
        )
    )
    connection.begin.return_value = nullcontext()
    store = SqlOperationDirectory(engine)
    return SimpleNamespace(row=row, data=data, connection=connection, store=store)


# Page counts, literal searches and typed output share a read-only repeatable snapshot.
@pytest.mark.parametrize("direction,search,state", [("asc", "", ""), ("desc", "%_", "queued")])
def test_directory_query_and_public_fields(directory_case, direction, search, state):
    c = directory_case
    c.connection.scalar.return_value = 1
    c.connection.execute.return_value.mappings.return_value.all.return_value = [c.row]
    result = c.store.directory(
        c.row["workspace_id"],
        OperationQuery(page=100, direction=direction, query=search, state=state),
    )
    assert result.total == 1 and result.page == result.pages == 1
    assert result.items[0].target_tenancy_ocid == c.data["intent"]["target"]["tenancy_ocid"]
    assert result.items[0].provider_mode == "simulated"
    assert "binding" not in result.model_dump_json() and "subject" not in result.model_dump_json()
    c.connection.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
    query = c.connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "workspace_id" in str(query) and "LIMIT" in str(query)
    if search:
        assert "/%/_" in query.params.values() and "ESCAPE" in str(query)


# Missing or foreign detail rows remain indistinguishable and perform no step/history query.
def test_missing_operation_detail(directory_case):
    c = directory_case
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    assert c.store.detail(c.row["workspace_id"], uuid4()) is None
    assert c.connection.execute.call_count == 1


# Bound visible history independently of audit retention; show current-intent steps only.
@pytest.mark.parametrize("history_size", [1, 51])
def test_detail_snapshot_and_bounded_history(directory_case, history_size):
    c = directory_case
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = c.row
    outcome = InspectionOutcome(
        intent_event_id=uuid4(), context=None, safe_code="DISPATCH_NOT_AUTHORIZED", result=None
    )
    data = outcome.model_dump(mode="json")
    step = dict(
        command_kind="inspect_tenancy",
        step_key="inspect_target",
        state="needs_attention",
        attempt_number=1,
        verified_at=None,
        last_outcome=data,
    )
    event = dict(kind="inspection_outcome", at=NOW, data=data, data_hash=canonical_hash(data))
    c.connection.execute.return_value.mappings.return_value.all.side_effect = [
        [step],
        [event] * history_size,
    ]
    result = c.store.detail(c.row["workspace_id"], c.row["id"])
    assert result.steps[0].safe_code == "DISPATCH_NOT_AUTHORIZED"
    assert len(result.events) == min(history_size, 50) and result.events_limited == (
        history_size > 50
    )
    assert "last_outcome" not in result.model_dump_json()
    assert "intent_revision" in str(c.connection.execute.call_args_list[1].args[0])
    assert c.store.step({**step, "last_outcome": None}).safe_code is None
    assert (
        c.store.event(
            dict(kind="operation_intent", at=NOW, data=c.data, data_hash=canonical_hash(c.data))
        ).safe_code
        is None
    )
    with pytest.raises(ValueError, match="INVALID_OPERATION_EVIDENCE"):
        c.store.event({**event, "data_hash": "0" * 64})


# Integrity and scope mismatches are unavailable evidence rather than plausible displayed targets.
@pytest.mark.parametrize("damage", ["hash", "workspace", "actor"])
def test_corrupt_summary_rejected(directory_case, damage):
    c = directory_case
    row = dict(c.row)
    row[
        {"hash": "intent_hash", "workspace": "workspace_id", "actor": "initiating_actor_subject"}[
            damage
        ]
    ] = "wrong"
    with pytest.raises(ValueError, match="INVALID_OPERATION_EVIDENCE"):
        c.store.summary(row)


# Fixed HTTP errors and session-selected workspace protect both reads and guessed operation IDs.
def test_operation_http_boundaries(session_case, directory_case):
    store = Mock()
    summary = directory_case.store.summary(directory_case.row)
    store.directory.return_value = OperationDirectory(
        items=[summary], total=1, page=1, page_size=10, pages=1
    )
    store.detail.return_value = OperationDetail(
        operation=summary, steps=[], events=[], events_limited=False
    )
    app = create_app(session_case.service, BrowserSettings(public_origin=ORIGIN), operations=store)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/operations").status_code == 401
        headers = cookie(session_case)
        response = client.get("/api/operations?workspace_id=foreign", headers=headers)
        assert response.status_code == 200
        assert store.directory.call_args.args[0] == session_case.session.workspace_id
        for query in ("page=0", "page_size=7", "query=" + "x" * 129, "sort=drop", "state=made_up"):
            assert client.get("/api/operations?" + query, headers=headers).status_code == 400
        identifier = uuid4()
        assert client.get(f"/api/operations/{identifier}", headers=headers).status_code == 200
        assert store.detail.call_args.args == (
            session_case.session.workspace_id,
            identifier,
            session_case.service.authenticate(session_case.handle).actor.key,
        )
        store.detail.return_value = None
        assert client.get(f"/api/operations/{identifier}", headers=headers).status_code == 404
        store.detail.side_effect = RuntimeError("private query")
        store.directory.side_effect = RuntimeError("private query")
        for path in ("/api/operations", f"/api/operations/{identifier}"):
            response = client.get(path, headers=headers)
            assert response.status_code == 503 and "private" not in response.text
        assert (
            client.post(
                "/api/operations",
                headers={**headers, "origin": ORIGIN, "x-otm-request": "1"},
                json={},
            ).status_code
            == 405
        )
    with pytest.raises(ValueError, match="ADMINISTRATION_UI_REQUIRES_SESSION_BOUNDARY"):
        create_app(operations=store)


# Attention is workspace-wide and independent of search/state/paging rather than a filtered total.
def test_attention_count_has_independent_scoped_predicate(directory_case):
    c = directory_case
    c.connection.scalar.side_effect = [3, 0]
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    result = c.store.directory(
        c.row["workspace_id"], OperationQuery(state="succeeded", query="missing")
    )
    assert result.attention_count == 3 and result.total == 0
    predicate = c.connection.scalar.call_args_list[0].args[0].compile(dialect=postgresql.dialect())
    assert c.row["workspace_id"] in predicate.params.values()
    assert ["waiting", "needs_attention"] in predicate.params.values()
    assert "organization_action" in predicate.params.values()
    assert ["onboarding_handoff", "onboarding_review"] in predicate.params.values()
    assert "pending_operation_id" in str(predicate) and "EXISTS" in str(predicate)
    assert "missing" not in predicate.params.values()


# Historical sections use recorded outcomes; absent legacy checks remain unchecked.
@pytest.mark.parametrize("extended", [False, True])
def test_required_user_event_sections(directory_case, extended):
    from test_user_presence_check_units import case

    from otm.providers.administrator_access import AdministratorCheck, AdministratorResult
    from otm.providers.recovery_console import RecoveryConsoleCheck, RecoveryConsoleResult
    from otm.tenancies.presence_contracts import PresenceCheckEvidence

    c = case()
    evidence = c.evidence
    if extended:
        assignment = AdministratorCheck(
            context=c.results[0].context,
            target=c.results[0].target,
            checked_at=evidence.checked_at,
            result=AdministratorResult(group="missing", domain_role="verified"),
        )
        policy = RecoveryConsoleCheck(
            context=c.results[1].context,
            target=c.results[1].target,
            checked_at=evidence.checked_at,
            result=RecoveryConsoleResult(
                state="unknown",
                mfa_exemption="unknown",
                network_boundary="unknown",
                desired_fingerprint="a" * 64,
                safe_code="RECOVERY_CONSOLE_UNVERIFIED",
            ),
        )
        evidence = PresenceCheckEvidence.model_validate(
            evidence.model_copy(
                update={
                    "administrator_access": assignment,
                    "recovery_administrator_access": assignment.model_copy(
                        update={"context": c.results[1].context, "target": c.results[1].target}
                    ),
                    "recovery_console": policy,
                }
            ).model_dump()
        )
    data = evidence.model_dump(mode="json")
    row = dict(
        kind="required_user_check_outcome", at=NOW, data=data, data_hash=canonical_hash(data)
    )
    result = directory_case.store.event(row)
    assert [section.anchor for section in result.user_checks] == [
        "automation-presence",
        "automation-assignment",
        "recovery-presence",
        "recovery-assignment",
        "recovery-policy",
    ]
    assert result.user_checks[0].facts[0].state == "present"
    assert result.user_checks[1].facts[0].state == ("missing" if extended else "not_checked")
    assert result.user_checks[-1].facts[0].state == ("unknown" if extended else "not_checked")
    assert result.user_checks[-1].checked_at == (evidence.checked_at if extended else None)
    assert "context" not in result.model_dump_json() and "binding" not in result.model_dump_json()
    with pytest.raises(ValueError, match="INVALID_OPERATION_EVIDENCE"):
        directory_case.store.event({**row, "data_hash": "0" * 64})
