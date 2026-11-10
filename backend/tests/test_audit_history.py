"""Public immutable history projections, actor truthfulness and scoped HTTP/query boundaries."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from test_admission_service import NOW
from test_auth_http import ORIGIN, cookie
from test_sessions import session_case

from otm.app import create_app
from otm.audit.contracts import AuditDirectory, AuditExportEvidence, AuditQuery
from otm.auth.http import BrowserSettings
from otm.operations.contracts import ActorIdentity, canonical_hash
from otm.operations.execution_contracts import InspectionOutcome
from otm.storage.audit_directory import (
    ADMINISTRATION,
    AUTHENTICATION,
    EMAIL_DELIVERY,
    OPERATIONS,
    SqlAuditDirectory,
    entry,
)
from otm.tenancies.contracts import OrganizationActionOutcome
from otm.tenancies.onboarding_contracts import OnboardingEvidence

__all__ = ["session_case"]


# Synthetic rows cover both deployed immutable actor formats without touching a live database.
def event(kind="local_sign_in_succeeded", operator=False):
    actor = ActorIdentity(
        issuer="urn:otm:database-operator" if operator else "urn:otm:local:synthetic",
        subject="synthetic",
        display_name=None if operator else "Example administrator",
    )
    data = {"private_marker": "must-not-escape"}
    if kind == "recovery_password_outcome":
        from otm.tenancies.recovery_password_contracts import RecoveryPasswordEvidence

        data = RecoveryPasswordEvidence(
            credential_id=uuid4(),
            tenancy_id=uuid4(),
            operation_id=uuid4(),
            phase="rotation",
            state="blocked",
            effect="none",
            safe_code="RECOVERY_PASSWORD_BLOCKED",
            checked_at=NOW,
        ).model_dump(mode="json")
    if kind == "recovery_password_disclosed":
        from datetime import timedelta

        from otm.tenancies.recovery_password_contracts import RecoveryDisclosureEvidence

        data = RecoveryDisclosureEvidence(
            grant_id=uuid4(),
            credential_id=uuid4(),
            tenancy_id=uuid4(),
            disclosed_version_id=uuid4(),
            window_root_grant_id=uuid4(),
            exposure_generation=1,
            first_disclosure_at=NOW,
            rotation_due_at=NOW + timedelta(hours=4),
        ).model_dump(mode="json")
    if kind == "recovery_network_outcome":
        from test_user_presence_check_units import case

        from otm.tenancies.recovery_network_contracts import RecoveryNetworkEvidence

        sample = case()
        data = RecoveryNetworkEvidence(
            operation_id=uuid4(),
            tenancy_id=sample.snapshot.tenancy_id,
            snapshot=sample.snapshot,
            effect="none",
            state="blocked",
            safe_code="RECOVERY_NETWORK_BLOCKED",
            checked_at=NOW,
        ).model_dump(mode="json")
    if kind == "required_user_check_outcome":
        from test_user_presence_check_units import case

        data = case().evidence.model_dump(mode="json")
    if kind == "cost_collection_outcome":
        from otm.financial.contracts import CostEvidence

        data = CostEvidence(
            collection_id=uuid4(),
            tenancy_id=uuid4(),
            state="succeeded",
            attempts=1,
            safe_code="COST_READ_COMPLETE",
        ).model_dump(mode="json")
    if kind == "cost_refresh_requested":
        from otm.financial.contracts import CostRefreshReceipt

        data = {
            "receipt": CostRefreshReceipt(
                operation_ids=(uuid4(),),
                accepted_count=1,
                joined_count=0,
                skipped_count=0,
                accepted_at=NOW,
            ).model_dump(mode="json")
        }
    if kind == "email_delivery":
        from otm.notifications.contracts import NotificationEvidence

        data = NotificationEvidence(
            notification_id=uuid4(),
            intent_hash="a" * 64,
            state="sent",
            attempts=1,
            safe_code="SMTP_ACCEPTED",
        ).model_dump(mode="json")
    if kind == "operation_responsibility_changed":
        from otm.operations.responsibility import ResponsibilityEvidence

        data = ResponsibilityEvidence(
            client_request_key=uuid4(),
            request_hash="a" * 64,
            before_subject="previous",
            before_name="Previous administrator",
            after_actor=actor,
            administrator_id=uuid4(),
            authorization_revision=uuid4(),
            intent_event_id=uuid4(),
            intent_hash="b" * 64,
            expected_revision=1,
            operation_revision=2,
        ).model_dump(mode="json")
    if kind == "configuration_review_staged":
        data = {
            "contract_version": "configuration-review-1",
            "plan_id": str(uuid4()),
            "tenancy_id": str(uuid4()),
            "baseline_id": str(uuid4()),
            "proposal_hash": "a" * 64,
            "policy_choice": "keep_override",
        }
    if kind == "baseline_draft_saved":
        data = {
            "baseline_id": str(uuid4()),
            "version_number": 1,
            "edit_revision": 1,
            "before": None,
            "after": {
                "policy_statements": ["Allow sample policy"],
                "quota_statements": ["set example quota"],
                "monthly_budget_amount": "200",
                "budget_currency": "USD",
            },
        }
    if kind in {"baseline_published", "baseline_default_changed"}:
        from test_baseline_authoring import row

        from otm.configuration.contracts import BaselinePublicationEvidence
        from otm.configuration.service import draft_view

        published = draft_view(
            row(
                published_by=actor.key,
                published_by_name=actor.display_name or "Administrator",
                published_at=NOW,
                publication_mode="simulated",
                edit_revision=2,
            )
        )
        data = BaselinePublicationEvidence(
            qualification_version="baseline-structure-simulated-1", baseline=published
        ).model_dump(mode="json")
    if kind == "baseline_default_changed":
        data = {"previous_baseline_id": None, "baseline": data["baseline"]}
    worker = kind in ("inspection_dispatch", "inspection_outcome")
    if kind in {"configuration_outcome", "configuration_retry"}:
        from otm.configuration.rollout_contracts import (
            ConfigurationOutcome,
            ConfigurationRetryEvidence,
        )

        data = (
            ConfigurationOutcome(
                tenancy_id=uuid4(),
                baseline_id=uuid4(),
                safe_code="CONFIGURATION_VERIFIED",
                verified_at=NOW,
            )
            if kind == "configuration_outcome"
            else ConfigurationRetryEvidence(baseline_id=uuid4())
        ).model_dump(mode="json")
    if kind == "configuration_check_outcome":
        from types import SimpleNamespace

        from otm.configuration.drift_contracts import ConfigurationCheckEvidence
        from otm.configuration.observations import unavailable_results

        data = ConfigurationCheckEvidence(
            check_id=uuid4(),
            tenancy_id=uuid4(),
            state="unavailable",
            safe_code="CONFIGURATION_CHECK_UNAVAILABLE",
            checked_at=NOW,
            context_hash="a" * 64,
            results=unavailable_results(SimpleNamespace(bindings={}), None),
        ).model_dump(mode="json")
    if kind == "audit_export":
        data = AuditExportEvidence(
            contract_version="audit-export-1", row_count=1, query_digest="0" * 64
        ).model_dump(mode="json")
    if kind == "inspection_outcome":
        data = InspectionOutcome(
            intent_event_id=uuid4(), context=None, safe_code="DISPATCH_NOT_AUTHORIZED", result=None
        ).model_dump(mode="json")
    if kind == "organization_action_outcome":
        data = OrganizationActionOutcome(
            action="create_tenancy", safe_code="SIMULATED_LIFECYCLE_VERIFIED", verified_at=NOW
        ).model_dump(mode="json")
    if kind in {"onboarding_action", "onboarding_outcome"}:
        data = OnboardingEvidence(
            step="handoff", outcome="accepted", safe_code="ONBOARDING_ACCEPTED"
        ).model_dump(mode="json")
    return dict(
        id=uuid4(),
        workspace_id="audit-org",
        at=NOW,
        kind=kind,
        actor_subject="otm-worker:recovery-password"
        if kind == "recovery_password_outcome"
        else "otm-worker:recovery-network"
        if kind == "recovery_network_outcome"
        else "otm-worker:user-presence"
        if kind == "required_user_check_outcome"
        else "otm-worker:costs"
        if kind == "cost_collection_outcome"
        else "otm-worker:email"
        if kind == "email_delivery"
        else "otm-worker:configuration-check"
        if kind == "configuration_check_outcome"
        else "otm-worker:configuration"
        if kind == "configuration_outcome"
        else "otm-worker:organization"
        if kind in {"organization_action_outcome", "onboarding_outcome"}
        else "otm-worker:inspection"
        if worker
        else actor.key,
        actor_snapshot={"kind": "worker", "subject": "recovery-password"}
        if kind == "recovery_password_outcome"
        else {"kind": "worker", "subject": "recovery-network"}
        if kind == "recovery_network_outcome"
        else {"kind": "worker", "subject": "user-presence"}
        if kind == "required_user_check_outcome"
        else {"kind": "worker", "subject": "costs"}
        if kind == "cost_collection_outcome"
        else {"kind": "worker", "subject": "email"}
        if kind == "email_delivery"
        else {"kind": "worker", "subject": "configuration-check"}
        if kind == "configuration_check_outcome"
        else {"kind": "worker", "subject": "configuration"}
        if kind == "configuration_outcome"
        else {"kind": "worker", "subject": "organization"}
        if kind in {"organization_action_outcome", "onboarding_outcome"}
        else {"kind": "worker", "subject": "inspection"}
        if worker
        else actor.model_dump(mode="json"),
        operation_id=uuid4() if kind in (*OPERATIONS, *EMAIL_DELIVERY) else None,
        administrator_id=None if kind in (*OPERATIONS, *EMAIL_DELIVERY) else uuid4(),
        administrator_name=None
        if kind in (*OPERATIONS, *EMAIL_DELIVERY)
        else "Target administrator",
        data=data,
        data_hash=canonical_hash(data),
    )


# All supported kinds map to an honest actor/category and only approved public fields.
@pytest.mark.parametrize("kind", [*AUTHENTICATION, *ADMINISTRATION, *OPERATIONS, *EMAIL_DELIVERY])
def test_public_projection_all_kinds(kind):
    result = entry(event(kind))
    assert result.category == (
        "email_delivery"
        if kind in EMAIL_DELIVERY
        else "authentication"
        if kind in AUTHENTICATION
        else "administration"
        if kind in ADMINISTRATION
        else "operations"
    )
    assert set(result.model_dump()) == {
        "resources",
        "baseline_id",
        "id",
        "at",
        "kind",
        "category",
        "actor_name",
        "operation_id",
        "administrator_id",
        "administrator_name",
        "safe_code",
        "organization_subject_name",
        "summary",
        "changes",
    }
    assert all(
        value not in result.model_dump_json()
        for value in (
            "private_marker",
            "actor_snapshot",
            "authorization_revision",
            "session_id",
            "issuer",
        )
    )
    if kind == "local_sign_in_failed":
        assert result.actor_name is None
    elif kind == "recovery_password_outcome":
        assert result.actor_name == "Recovery password worker"
    elif kind == "recovery_network_outcome":
        assert result.actor_name == "Recovery network worker"
    elif kind == "required_user_check_outcome":
        assert result.actor_name == "User presence worker"
    elif kind == "cost_collection_outcome":
        assert result.actor_name == "Cost collection worker"
    elif kind == "email_delivery":
        assert result.actor_name == "Email delivery worker"
    elif kind == "configuration_check_outcome":
        assert result.actor_name == "Configuration check worker"
    elif kind == "configuration_outcome":
        assert result.actor_name == "Configuration worker"
    elif kind in {"organization_action_outcome", "onboarding_outcome"}:
        assert result.actor_name == "Organization worker"
    elif kind in ("inspection_dispatch", "inspection_outcome"):
        assert result.actor_name == "Inspection worker"
    else:
        assert result.actor_name == "Example administrator"
    assert result.safe_code == (
        "RECOVERY_PASSWORD_BLOCKED"
        if kind == "recovery_password_outcome"
        else "RECOVERY_NETWORK_BLOCKED"
        if kind == "recovery_network_outcome"
        else "USER_PRESENCE_CHECK_COMPLETE"
        if kind == "required_user_check_outcome"
        else "COST_READ_COMPLETE"
        if kind == "cost_collection_outcome"
        else "CONFIGURATION_VERIFIED"
        if kind == "configuration_outcome"
        else "CONFIGURATION_RETRY_ACCEPTED"
        if kind == "configuration_retry"
        else "ONBOARDING_ACCEPTED"
        if kind in {"onboarding_action", "onboarding_outcome"}
        else "DISPATCH_NOT_AUTHORIZED"
        if kind == "inspection_outcome"
        else "SIMULATED_LIFECYCLE_VERIFIED"
        if kind == "organization_action_outcome"
        else None
    )
    assert (
        entry(event("administrator_bootstrapped", operator=True)).actor_name == "Database operator"
    )


# Hash/actor mismatches cannot fabricate a history row or silently attribute a failed proof.
@pytest.mark.parametrize(
    "damage", ["hash", "identity", "worker_subject", "worker_snapshot", "kind"]
)
def test_projection_integrity_guards(damage):
    row = event("inspection_dispatch" if damage.startswith("worker") else "local_sign_in_succeeded")
    if damage == "hash":
        row["data_hash"] = "0" * 64
    elif damage == "identity":
        row["actor_subject"] = "forged"
    elif damage == "worker_subject":
        row["actor_subject"] = "forged"
    elif damage == "worker_snapshot":
        row["actor_snapshot"] = {"kind": "worker", "subject": "other"}
    else:
        row["kind"] = "unsupported"
    with pytest.raises(ValueError):
        entry(row)


# Count and literal search share one repeatable/read-only snapshot with allowlisted SQL ordering.
@pytest.mark.parametrize(
    "category,direction,query",
    [
        ("", "desc", ""),
        ("authentication", "asc", "%_"),
        ("email_delivery", "desc", ""),
        ("operations", "desc", ""),
    ],
)
def test_audit_directory_queries(category, direction, query):
    connection = MagicMock()
    connection.begin.return_value = nullcontext()
    engine = Mock(
        connect=Mock(
            return_value=SimpleNamespace(
                execution_options=Mock(return_value=nullcontext(connection))
            )
        )
    )
    connection.scalar.return_value = 1
    connection.execute.return_value.mappings.return_value.all.return_value = [event()]
    result = SqlAuditDirectory(engine).directory(
        "audit-org",
        AuditQuery(
            page=100, category=category, direction=direction, sort="actor_name", query=query
        ),
    )
    assert result.total == 1 and result.page == result.pages == 1
    connection.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
    compiled = connection.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "workspace_id" in str(compiled) and "LIMIT" in str(compiled) and "CASE" in str(compiled)
    assert "LEFT OUTER JOIN" in str(compiled)
    assert "otm_administrator.workspace_id = audit_event.workspace_id" in str(compiled).replace(
        "public.", ""
    )
    assert "otm_administrator.id = audit_event.administrator_id" in str(compiled).replace(
        "public.", ""
    )
    if category:
        expected = (
            EMAIL_DELIVERY
            if category == "email_delivery"
            else OPERATIONS
            if category == "operations"
            else AUTHENTICATION
        )
        assert any(
            value == expected or value == list(expected) for value in compiled.params.values()
        )
        assert ("email_delivery" in expected) == (category == "email_delivery")
    if query:
        assert "/%/_" in compiled.params.values() and "ESCAPE" in str(compiled)


# Current session workspace is authoritative; malformed controls and storage errors stay fixed/safe.
def test_audit_http_authorization_and_errors(session_case):
    store = Mock()
    store.directory.return_value = AuditDirectory(
        items=[entry(event())], total=1, page=1, page_size=10, pages=1
    )
    app = create_app(
        session_case.service, BrowserSettings(public_origin=ORIGIN), audit_history=store
    )
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/audit-history").status_code == 401
        headers = cookie(session_case)
        response = client.get("/api/audit-history?workspace_id=other", headers=headers)
        assert (
            response.status_code == 200
            and store.directory.call_args.args[0] == session_case.session.workspace_id
        )
        for query in (
            "page=0",
            "page_size=7",
            "sort=data",
            "category=bad",
            "direction=sideways",
            "query=" + "x" * 129,
        ):
            assert client.get("/api/audit-history?" + query, headers=headers).status_code == 400
        store.directory.side_effect = RuntimeError("private failure")
        response = client.get("/api/audit-history", headers=headers)
        assert response.status_code == 503 and "private" not in response.text
        command_headers = {**headers, "origin": ORIGIN, "x-otm-request": "1"}
        for method in ("post", "delete", "patch"):
            assert (
                getattr(client, method)("/api/audit-history", headers=command_headers).status_code
                == 405
            )
    with pytest.raises(ValueError):
        create_app(audit_history=store)


# Expose selected recorded changes and readable historical organization actions.
@pytest.mark.parametrize(
    "kind,action",
    [
        ("organization_configured", "mapping_apply"),
        ("organization_configured", None),
        ("organization_review_decided", "no_tenancy_required"),
        ("organization_review_decided", "keep_without_tenancy"),
        ("organization_review_decided", "unrecognized"),
        ("organization_feed_received", None),
        ("organization_feed_rejected", None),
        ("organization_published", None),
    ],
)
def test_organization_audit_descriptions(kind, action):
    from otm.organization.persistence_contracts import (
        ORGANIZATION_SERVICE_ACTOR,
        OrganizationEvidence,
    )

    row = event(kind)
    evidence = OrganizationEvidence(
        source_id="fixture",
        population_id="fixture",
        configuration_id=uuid4(),
        action=action,
        person_count=7,
        diagnostic_count=2,
    )
    row.update(data=evidence.model_dump(mode="json"))
    row["data_hash"] = canonical_hash(row["data"])
    if kind in {"organization_published", "organization_feed_rejected"}:
        row.update(
            actor_snapshot=ORGANIZATION_SERVICE_ACTOR.model_dump(mode="json"),
            actor_subject=ORGANIZATION_SERVICE_ACTOR.key,
        )
    view = entry(row)
    assert view.summary and not view.changes
    assert "unrecognized" not in view.model_dump_json()
    if kind == "organization_configured" and action is None:
        assert "not recorded" in view.summary
    if kind == "organization_feed_received":
        assert view.summary == "Received organization feed"
    if kind == "organization_feed_rejected":
        assert "2 validation diagnostics" in view.summary


# Project recorded root/segment/nominee differences without consulting current configuration.
def test_mapping_audit_before_after_and_csv_details():
    import json
    from csv import DictReader
    from io import StringIO

    from otm.organization.mapping_contracts import MappingChange, MappingSegment
    from otm.organization.persistence_contracts import OrganizationEvidence
    from otm.storage.audit_export import csv_document

    before = MappingSegment(
        id="a",
        label="Alpha",
        leader_email="old@example.test",
        designee_emails=("delegate@example.test",),
    )
    after = before.model_copy(
        update={"label": "Updated Alpha", "leader_email": "new@example.test", "designee_emails": ()}
    )
    changes = (
        MappingChange(segment_id="a", before=before, after=after),
        MappingChange(segment_id="b", before=None, after=before),
        MappingChange(segment_id="c", before=after, after=None),
    )
    data = OrganizationEvidence(
        source_id="fixture",
        population_id="fixture",
        configuration_id=uuid4(),
        action="mapping_apply",
        mapping_root_before="root@example.test",
        mapping_root_after="successor@example.test",
        mapping_changes=changes,
    ).model_dump(mode="json")
    row = event("organization_configured")
    row.update(data=data, data_hash=canonical_hash(data))
    view = entry(row)
    assert view.summary == "Updated organization mappings"
    assert "Organization leader: root@example.test → successor@example.test" in view.changes
    assert "Segment name: Alpha → Updated Alpha" in view.changes
    assert "Updated Alpha leader: old@example.test → new@example.test" in view.changes
    assert "Updated Alpha new designees: None" in view.changes
    assert (
        "Added segment: Alpha" in view.changes and "Removed segment: Updated Alpha" in view.changes
    )
    exported = next(DictReader(StringIO(csv_document([row]).decode("utf-8-sig"))))
    assert exported["summary"] == view.summary
    assert json.loads(exported["changes"]) == list(view.changes)
    assert "source_id" not in exported and "configuration_id" not in exported
    # Initial configuration has no prior root and an added mapping without designees.
    data.update(
        mapping_root_before=None,
        mapping_changes=[
            MappingChange(segment_id="c", before=None, after=after).model_dump(mode="json")
        ],
    )
    row.update(data=data, data_hash=canonical_hash(data))
    assert "Not configured" in entry(row).changes[0]


# An accepted asynchronous offboarding is never presented as completed cleanup.
@pytest.mark.parametrize("queued", [True, False])
def test_offboarding_audit_summary_distinguishes_accepted_and_completed(queued):
    from otm.organization.persistence_contracts import OrganizationEvidence
    from otm.tenancies.contracts import ActionReceipt

    row = event("organization_review_decided")
    data = OrganizationEvidence(
        source_id="fixture",
        population_id="fixture",
        configuration_id=uuid4(),
        action="offboard_person",
        receipt=ActionReceipt(
            operation_id=uuid4() if queued else None,
            state="queued" if queued else "succeeded",
            provider_mode="simulated" if queued else "application",
            accepted_at=NOW,
        ),
    ).model_dump(mode="json")
    row.update(data=data, data_hash=canonical_hash(data))
    assert entry(row).summary == (
        "Requested employee offboarding" if queued else "Offboarded employee"
    )


# Cost-worker identity remains strict; recognizing its shape cannot permit actor impersonation.
@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_subject", "otm-worker:other"),
        ("actor_snapshot", {"kind": "worker", "subject": "other"}),
        (
            "actor_snapshot",
            ActorIdentity(issuer="urn:test:other", subject="other").model_dump(mode="json"),
        ),
    ],
)
def test_cost_worker_rejects_forged_audit_actor(field, value):
    row = event("cost_collection_outcome")
    row[field] = value
    with pytest.raises(ValueError, match="INVALID_AUDIT_ACTOR"):
        entry(row)
