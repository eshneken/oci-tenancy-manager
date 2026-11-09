"""Presence-check scope, authority, retry fencing, projection and failures without SQL."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_required_user_presence import NOW
from test_required_user_presence import case as provider_case

from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.operations.contracts import (
    ActorIdentity,
    InspectionPolicy,
    IntentEventData,
    canonical_hash,
)
from otm.providers.lifecycle import OnboardingUsers
from otm.providers.presence_simulator import simulated_presence_inspection
from otm.providers.required_user_contracts import (
    InspectRequiredUser,
    ObservedRequiredUser,
    RequiredUserReadContext,
)
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.tenancies.onboarding_contracts import OnboardingEvidence
from otm.tenancies.presence import PresenceChecks
from otm.tenancies.presence_context import capture_snapshot
from otm.tenancies.presence_contracts import (
    PresenceCheckEvidence,
    PresenceCheckIntent,
    PresenceCheckRequest,
    PresenceSnapshot,
)
from otm.tenancies.presence_records import (
    decode_intent,
    decode_result,
    operation_rows,
    seal,
    unknown,
)
from otm.tenancies.presence_worker import UserPresenceWorker
from otm.tenancies.required_users import RequiredUserRecord, RequiredUsersDirectory


# Build closed messages and independent simulator facts without claiming database authority.
def case():
    base = provider_case()
    a = base.target
    b = a.model_copy(
        update={
            "purpose": "recovery",
            "subject_binding_id": uuid4(),
            "scim_resource_id": "recovery-scim",
            "provider_ocid": "ocid1.user.oc1..otmsimrecovery",
            "user_name": "otm-recovery",
        }
    )
    policy = InspectionPolicy(
        workspace_id=a.workspace_id,
        policy_revision=uuid4(),
        organization_id=a.organization_id,
        parent_tenancy_ocid=a.parent_tenancy_ocid,
        access_binding_id=uuid4(),
    )
    snapshot = PresenceSnapshot(
        tenancy_id=a.tenancy_id,
        tenancy_name="Synthetic child",
        tenancy_revision=1,
        connection_id=base.context.connection_id,
        connection_revision=1,
        policy_hash=canonical_hash(policy.model_dump(mode="json")),
        subjects=(a, b),
    )
    actor = ActorIdentity(issuer="urn:unit", subject="admin", display_name="Administrator")
    grant = dict(
        id=uuid4(),
        status="active",
        authorization_revision=uuid4(),
        issuer=actor.issuer,
        subject=actor.subject,
    )
    principal = SimpleNamespace(
        actor=actor, session=SimpleNamespace(issuer=actor.issuer, subject=actor.subject)
    )
    intent = PresenceCheckIntent(
        workspace_id=a.workspace_id,
        administrator_id=grant["id"],
        authorization_revision=grant["authorization_revision"],
        snapshot=snapshot,
        context_hash=canonical_hash(snapshot.model_dump(mode="json")),
        target=ConfigurationOperationTarget(
            tenancy_ocid=a.tenancy_ocid, display_name=snapshot.tenancy_name
        ),
    )
    frozen = IntentEventData(intent=intent, actor=actor)
    data = frozen.model_dump(mode="json")
    row = dict(
        id=uuid4(),
        workspace_id=a.workspace_id,
        kind="required_user_check",
        state="queued",
        current_intent_revision=1,
        current_intent_event_id=uuid4(),
        initiating_actor_subject=actor.key,
        check_context_hash=intent.context_hash,
        intent_data=data,
        intent_hash=canonical_hash(data),
        accepted_at=NOW,
        created_at=NOW,
    )
    commands = tuple(
        InspectRequiredUser(
            target=t,
            context=RequiredUserReadContext(
                workspace_id=a.workspace_id,
                operation_id=row["id"],
                step_key="required_users:" + str(a.tenancy_id),
                attempt_id=base.context.attempt_id,
                intent_revision=1,
                execution_generation=1,
                connection_id=snapshot.connection_id,
                connection_revision=1,
            ),
        )
        for t in snapshot.subjects
    )
    source = OnboardingUsers(
        workspace_id=a.workspace_id,
        tenancy_ocid=a.tenancy_ocid,
        parent_tenancy_ocid=a.parent_tenancy_ocid,
        organization_id=a.organization_id,
        domain_ocid=a.domain_ocid,
        automation=ObservedRequiredUser(
            domain_ocid=a.domain_ocid,
            scim_resource_id=a.scim_resource_id,
            provider_ocid=a.provider_ocid,
            user_name=a.user_name,
        ),
        recovery=ObservedRequiredUser(
            domain_ocid=b.domain_ocid,
            scim_resource_id=b.scim_resource_id,
            provider_ocid=b.provider_ocid,
            user_name=b.user_name,
        ),
    )
    clock = Mock(return_value=NOW)
    inspection = simulated_presence_inspection(snapshot, source, clock)
    results = tuple(inspection.inspect(command) for command in commands)
    evidence = PresenceCheckEvidence(
        tenancy_id=a.tenancy_id,
        operation_id=row["id"],
        context_hash=intent.context_hash,
        state="complete",
        safe_code="USER_PRESENCE_CHECK_COMPLETE",
        started_at=NOW,
        checked_at=NOW,
        results=results,
    )
    payload = evidence.model_dump(mode="json")
    check = dict(
        operation_id=row["id"],
        workspace_id=a.workspace_id,
        tenancy_id=a.tenancy_id,
        context=snapshot.model_dump(mode="json"),
        context_hash=intent.context_hash,
        state="complete",
        attempt_id=commands[0].context.attempt_id,
        attempt_number=1,
        started_at=NOW,
        checked_at=NOW,
        results=payload["results"],
        evidence_event_id=uuid4(),
        created_at=NOW,
    )
    child = dict(
        id=a.tenancy_id,
        name=snapshot.tenancy_name,
        provider_mode="simulated",
        status="active",
        operation_id=None,
        revision=1,
        tenancy_ocid=a.tenancy_ocid,
        parent_tenancy_ocid=a.parent_tenancy_ocid,
        organization_id=a.organization_id,
    )
    connection = MagicMock()
    engine = MagicMock()
    engine.begin.return_value = nullcontext(connection)
    config = SimpleNamespace(policy=policy, execution_paused=False)
    loader = Mock(return_value=config)
    store = Mock(engine=engine, clock=clock)
    store._write.return_value = nullcontext((connection, a.workspace_id, NOW))
    service = PresenceChecks(store, policy=policy, policy_loader=loader, enqueuer=Mock())
    worker = UserPresenceWorker(
        engine, a.workspace_id, clock, loader, policy, simulated_presence_inspection
    )
    directory = RequiredUsersDirectory(
        tenancy_id=a.tenancy_id,
        tenancy_status="active",
        provider_mode="simulated",
        users=tuple(
            RequiredUserRecord(purpose=p, identity_state="not_recorded", identity=None)
            for p in ("automation", "recovery")
        ),
    )
    return SimpleNamespace(**locals())


# Use mapping-shaped SQL results while preserving real statement construction and typed validation.
def result(value):
    mapped = MagicMock()
    mapped.mappings.return_value.one_or_none.return_value = value
    mapped.mappings.return_value.one.return_value = value
    mapped.mappings.return_value.all.return_value = value
    return mapped


# Target fields freeze both exact identities, not just labels or an echoed tenant ID.
@pytest.mark.parametrize("fault", ["order", "child", "domain", "alias", "workspace"])
def test_snapshot_scope_guards(fault):
    c = case()
    raw = c.snapshot.model_dump()
    a, b = raw["subjects"]
    if fault == "order":
        raw["subjects"] = (b, a)
    elif fault == "child":
        raw["tenancy_id"] = uuid4()
    else:
        key = {"domain": "domain_ocid", "alias": "subject_binding_id", "workspace": "workspace_id"}[
            fault
        ]
        raw["subjects"] = (a, {**b, key: a[key] if fault == "alias" else "changed"})
    with pytest.raises(ValueError):
        PresenceSnapshot.model_validate(raw)


# Evidence cannot claim completeness or attach results from a different operation/child/window.
@pytest.mark.parametrize("fault", ["code", "time", "operation", "child", "complete", "superseded"])
def test_evidence_guards(fault):
    c = case()
    raw = c.evidence.model_dump()
    key, value = {
        "code": ("safe_code", "USER_PRESENCE_UNAVAILABLE"),
        "time": ("checked_at", NOW - timedelta(seconds=1)),
        "operation": ("operation_id", uuid4()),
        "child": ("tenancy_id", uuid4()),
        "complete": ("state", "unavailable"),
        "superseded": ("state", "superseded"),
    }[fault]
    raw[key] = value
    with pytest.raises(ValueError):
        PresenceCheckEvidence.model_validate(raw)
    with pytest.raises(ValueError):
        PresenceCheckIntent.model_validate({**c.intent.model_dump(), "workspace_id": "foreign"})


# Authenticated source bytes, actor scope and recomputed context hashes are all mandatory.
@pytest.mark.parametrize("fault", [None, "hash", "workspace", "actor", "context"])
def test_intent_and_result_integrity(fault):
    c = case()
    row = dict(c.row)
    if fault:
        row[
            {
                "hash": "intent_hash",
                "workspace": "workspace_id",
                "actor": "initiating_actor_subject",
                "context": "check_context_hash",
            }[fault]
        ] = "wrong"
    if fault:
        with pytest.raises(ValueError):
            decode_intent(row)
    else:
        assert decode_intent(row) == c.frozen
        assert decode_result(c.check, c.payload, canonical_hash(c.payload)) == c.evidence
    for field, value in [
        ("tenancy_id", uuid4()),
        ("context_hash", "0" * 64),
        ("state", "unavailable"),
        ("attempt_id", uuid4()),
        ("attempt_number", 2),
        ("checked_at", NOW + timedelta(seconds=1)),
    ]:
        with pytest.raises(ValueError):
            decode_result({**c.check, field: value}, c.payload, canonical_hash(c.payload))
    with pytest.raises(ValueError):
        decode_result(c.check, c.payload, "0" * 64)


# Bound predicates, including optional reference/pending filters, cannot select another workspace.
@pytest.mark.parametrize("filtered", [False, True])
def test_scoped_operation_query_and_atomic_seal(filtered):
    c = case()
    c.connection.execute.return_value = result([])
    assert (
        operation_rows(
            c.connection,
            c.row["workspace_id"],
            c.row["id"] if filtered else None,
            c.child["id"] if filtered else None,
            filtered,
        )
        == []
    )
    statement = c.connection.execute.call_args.args[0]
    assert c.row["workspace_id"] in statement.compile().params.values()
    assert statement.is_select
    c.connection.reset_mock()
    seal(c.connection, c.row, c.check, c.results, "complete", NOW)
    statements = [call.args[0] for call in c.connection.execute.call_args_list]
    assert [s.table.name for s in statements] == [
        "audit_event",
        "otm_user_presence_check",
        "otm_operation_step",
        "otm_operation",
    ]
    assert statements[2].compile().params["effect_knowledge"] == "none"
    assert unknown(c.commands[0], NOW).observed is None


# The current connection must refer to these exact active canonical signer/domain/capture rows.
@pytest.mark.parametrize(
    "fault",
    [None, "policy", "inactive", "busy", "unbound", "missing", "signer", "domain", "source"],
)
def test_current_snapshot_resolution(fault):
    c = case()
    a, b = c.snapshot.subjects
    event, op = uuid4(), uuid4()
    domain = dict(
        id=a.identity_domain_binding_id,
        logical_key="identity/domain",
        kind="identity_domain",
        ownership_mode="observed_reference",
        provider_ocid=a.domain_ocid,
        source_evidence_event_id=event,
        created_operation_id=op,
    )
    users = [
        dict(
            id=t.subject_binding_id,
            logical_key="identity/user/" + t.purpose,
            kind="managed_user",
            ownership_mode="managed",
            identity_domain_binding_id=domain["id"],
            provider_ocid=t.provider_ocid,
            scim_resource_id=t.scim_resource_id,
            user_name=t.user_name,
            generation=1,
            source_evidence_event_id=event,
            created_operation_id=op,
        )
        for t in (a, b)
    ]
    conn = dict(
        id=c.snapshot.connection_id,
        automation_binding_id=a.subject_binding_id,
        domain_binding_id=domain["id"],
        revision=1,
        source_evidence_event_id=event,
        created_operation_id=op,
    )
    child = dict(c.child)
    policy = c.policy
    identities = [domain, *users]
    if fault == "policy":
        policy = None
    elif fault == "inactive":
        child["status"] = "terminated"
    elif fault == "busy":
        child["operation_id"] = uuid4()
    elif fault == "unbound":
        conn = None
    elif fault == "missing":
        identities.pop()
    elif fault == "signer":
        conn["automation_binding_id"] = uuid4()
    elif fault == "domain":
        domain["kind"] = "managed_user"
    elif fault == "source":
        users[1]["source_evidence_event_id"] = uuid4()
    first = result(conn)
    second = result(identities)
    second.mappings.return_value = identities
    c.connection.execute.side_effect = [first, second]
    if fault in {"missing", "signer", "domain", "source"}:
        with pytest.raises(ValueError, match="PRESENCE_RECORDS_UNAVAILABLE"):
            capture_snapshot(c.connection, c.row["workspace_id"], child, policy)
        return
    actual = capture_snapshot(c.connection, c.row["workspace_id"], child, policy)
    assert (actual is None) == (fault is not None)
    if actual is not None:
        assert actual == c.snapshot


# Projection reads no provider and uses latest ordered evidence without borrowing old positive
# facts.
@pytest.mark.parametrize(
    "mode",
    [
        "empty",
        "pending",
        "present",
        "stale",
        "failed",
        "changed",
        "paused",
        "inactive",
        "busy",
        "provider",
    ],
)
def test_projection_and_availability(mode):
    c = case()
    child = dict(c.child)
    snapshot = c.snapshot
    pending = []
    latest = None
    if mode == "pending":
        pending = [c.row]
    if mode in {"present", "stale", "failed", "changed", "paused"}:
        latest = c.check
    payload = c.payload
    if mode == "stale":
        c.clock.return_value = NOW + timedelta(hours=24)
    if mode == "failed":
        results = tuple(unknown(command, NOW) for command in c.commands)
        evidence = c.evidence.model_copy(
            update={
                "state": "unavailable",
                "safe_code": "USER_PRESENCE_UNAVAILABLE",
                "results": results,
            }
        )
        payload = evidence.model_dump(mode="json")
        latest = {**c.check, "state": "unavailable", "results": payload["results"]}
    if mode == "changed":
        snapshot = c.snapshot.model_copy(update={"tenancy_revision": 2})
    if mode == "paused":
        c.config.execution_paused = True
    if mode == "inactive":
        child["status"] = "terminated"
        snapshot = None
    if mode == "busy":
        child["operation_id"] = uuid4()
        snapshot = None
    if mode == "provider":
        c.loader.return_value = SimpleNamespace(policy=None, execution_paused=False)
        snapshot = None
    c.connection.execute.side_effect = [
        result(latest),
        result(dict(data=payload, data_hash=canonical_hash(payload))),
    ]
    with (
        patch("otm.tenancies.presence.capture_snapshot", return_value=snapshot),
        patch("otm.tenancies.presence.operation_rows", return_value=pending),
    ):
        view = c.service.project(c.connection, c.row["workspace_id"], child, c.directory)
    assert view.check_available == (mode not in {"paused", "inactive", "busy", "provider"})
    assert bool(view.pending_operation_id) == (mode == "pending")
    expected = (
        "present"
        if mode in {"present", "stale", "paused", "changed"}
        else "unknown"
        if mode == "failed"
        else "not_checked"
    )
    assert all(user.presence.state == expected for user in view.users)
    assert all(user.presence.stale == (mode == "stale") for user in view.users)


# One prior request returns its exact receipt; conflicting digests, targets and missing scope fail
# closed.
@pytest.mark.parametrize(
    "mode", ["new", "prior", "conflict", "kind", "foreign", "unbound", "join", "corrupt"]
)
def test_service_admission(mode):
    c = case()
    command = PresenceCheckRequest(client_request_key=uuid4())
    prior = None
    child = c.child
    if mode in {"prior", "conflict", "kind"}:
        prior = {
            **c.row,
            "request_digest": canonical_hash(
                {
                    "kind": "required_user_check",
                    "tenancy_id": str(child["id"]),
                    **command.model_dump(mode="json"),
                }
            ),
        }
        if mode == "conflict":
            prior["request_digest"] = "different"
        if mode == "kind":
            prior["kind"] = "inspect_import"
    if mode == "foreign":
        child = None
    c.connection.execute.side_effect = [result(prior), result(child), result(c.grant)] + [
        MagicMock() for _ in range(3)
    ]
    snapshot = None if mode == "unbound" else c.snapshot
    with (
        patch.object(
            c.service,
            "snapshot",
            side_effect=ValueError("private") if mode == "corrupt" else None,
            return_value=snapshot,
        ),
        patch(
            "otm.tenancies.presence.operation_rows", return_value=[c.row] if mode == "join" else []
        ),
    ):
        if mode in {"conflict", "kind"}:
            with pytest.raises(RequestConflict):
                c.service.start(c.principal, c.child["id"], command)
        elif mode in {"foreign", "unbound"}:
            with pytest.raises(OrganizationConflict):
                c.service.start(c.principal, c.child["id"], command)
        elif mode == "corrupt":
            with pytest.raises(RuntimeError, match="^REQUIRED_USERS_CHECK_UNAVAILABLE$"):
                c.service.start(c.principal, c.child["id"], command)
        else:
            response = c.service.start(c.principal, c.child["id"], command)
            assert response.state == "queued"
            assert c.service.enqueuer.enqueue.call_count == (mode in {"new", "join"})
    c.service.policy = None
    assert c.service.available_policy() is None


# Current grant identity/revision, provider selection and full canonical snapshot are required
# twice.
@pytest.mark.parametrize(
    "mode", ["valid", "missing", "revoked", "revision", "issuer", "paused", "provider", "context"]
)
def test_worker_current_authority(mode):
    c = case()
    grant = dict(c.grant)
    if mode == "missing":
        grant = None
    if mode == "revoked":
        grant["status"] = "revoked"
    if mode == "revision":
        grant["authorization_revision"] = uuid4()
    if mode == "issuer":
        grant["issuer"] = "different"
    if mode == "paused":
        c.config.execution_paused = True
    if mode == "provider":
        c.loader.return_value = SimpleNamespace(policy=None, execution_paused=False)
    c.connection.execute.return_value = result(grant)
    with patch(
        "otm.tenancies.presence_worker.capture_snapshot",
        return_value=None if mode == "context" else c.snapshot,
    ):
        assert c.worker.current(c.connection, c.frozen, c.child) == (mode == "valid")


# Replaying or unavailable queued work never dispatches before a persisted attempt is selected.
@pytest.mark.parametrize("mode", ["normal", "empty", "terminal", "unqualified", "source_error"])
def test_worker_begin(mode):
    c = case()
    stored = {**c.check, "state": "queued", "attempt_number": 0, "attempt_id": None}
    if mode == "terminal":
        stored = c.check
    with (
        patch.object(
            c.worker,
            "locked",
            return_value=None if mode == "empty" else (c.row, c.frozen, c.child, stored),
        ),
        patch.object(c.worker, "current", return_value=mode != "unqualified"),
        patch.object(
            c.worker,
            "source",
            return_value=c.source,
            side_effect=ValueError("private") if mode == "source_error" else None,
        ),
    ):
        ticket = c.worker.begin(c.row["id"])
    if mode in {"empty", "terminal"}:
        assert ticket is None
    else:
        assert ticket[1]["attempt_number"] == 1 and len(ticket[2]) == 2
        assert (ticket[3] is None) == (mode in {"unqualified", "source_error"})


# Late callbacks, lost authority and slow/backward clocks cannot publish positive evidence.
@pytest.mark.parametrize(
    "mode", ["normal", "empty", "terminal", "late", "revoked", "error", "slow", "backward"]
)
def test_worker_finish_fences(mode):
    c = case()
    check = {**c.check, "state": "reading"}
    if mode == "terminal":
        check = c.check
    attempt = uuid4() if mode == "late" else check["attempt_id"]
    if mode == "slow":
        c.clock.return_value = NOW + timedelta(seconds=31)
    if mode == "backward":
        c.clock.return_value = NOW - timedelta(seconds=1)
    with (
        patch.object(
            c.worker,
            "locked",
            return_value=None if mode == "empty" else (c.row, c.frozen, c.child, check),
        ),
        patch.object(
            c.worker,
            "current",
            return_value=mode != "revoked",
            side_effect=ValueError("private") if mode == "error" else None,
        ),
        patch("otm.tenancies.presence_worker.seal") as sealed,
    ):
        c.worker.finish(c.row["id"], attempt, c.commands, c.results)
    assert sealed.call_count == (mode not in {"empty", "terminal", "late"})
    if sealed.called:
        expected = (
            "superseded"
            if mode in {"revoked", "error"}
            else "unavailable"
            if mode in {"slow", "backward"}
            else "complete"
        )
        assert sealed.call_args.args[4] == expected
        if expected != "complete":
            assert all(r.state == "unknown" for r in sealed.call_args.args[3])


# Adapter exceptions and malformed responses stay independently unknown, without leaking raw text.
@pytest.mark.parametrize("mode", ["normal", "empty", "unconfigured", "factory", "read", "scope"])
def test_worker_run_normalizes(mode):
    c = case()
    check = {**c.check, "state": "reading"}
    if mode == "factory":
        c.worker.inspection_factory = Mock(side_effect=RuntimeError("secret"))
    if mode in {"read", "scope"}:
        inspection = Mock(inspect=Mock(side_effect=RuntimeError("secret")))
        if mode == "scope":
            inspection.inspect = Mock(
                return_value=c.results[0].model_copy(update={"target": c.snapshot.subjects[1]})
            )
        c.worker.inspection_factory = Mock(return_value=inspection)
    ticket = (c.frozen, check, c.commands, None if mode == "unconfigured" else c.source)
    with (
        patch.object(c.worker, "begin", return_value=None if mode == "empty" else ticket),
        patch.object(c.worker, "finish") as finished,
    ):
        c.worker.run(c.row["id"])
    assert finished.call_count == (mode != "empty")
    if finished.called:
        assert all(
            r.state == ("present" if mode == "normal" else "unknown")
            for r in finished.call_args.args[3]
        )


# Source capture hash/type and original scope are independent from the current expected record
# labels.
def test_worker_source_and_simulator_scope():
    c = case()
    proof = OnboardingEvidence(
        step="capture_required_users",
        outcome="verified",
        safe_code="ONBOARDING_VERIFIED",
        required_users=c.source,
    )
    data = proof.model_dump(mode="json")
    source = dict(data=data, data_hash=canonical_hash(data))
    for invalid in (False, True):
        c.connection.execute.side_effect = [
            result(dict(created_operation_id=uuid4(), source_evidence_event_id=uuid4())),
            result({**source, "data_hash": "wrong"} if invalid else source),
            result(None),
        ]
        if invalid:
            with pytest.raises(ValueError):
                c.worker.source(c.connection, c.snapshot)
        else:
            assert c.worker.source(c.connection, c.snapshot) == c.source
    with pytest.raises(ValueError):
        simulated_presence_inspection(
            c.snapshot, c.source.model_copy(update={"workspace_id": "foreign"}), c.clock
        )


# Every lock query is scope-bound; missing anchors/operations never invent work or select provider
# data.
@pytest.mark.parametrize("mode", ["valid", "anchor", "missing", "terminal"])
def test_worker_lock_scope(mode):
    c = case()
    c.connection.scalar.return_value = None if mode == "anchor" else uuid4()
    c.connection.execute.side_effect = [MagicMock(), MagicMock(), result(c.child), result(c.check)]
    row = {**c.row, "state": "succeeded"} if mode == "terminal" else c.row
    with patch(
        "otm.tenancies.presence_worker.operation_rows",
        return_value=[] if mode == "missing" else [row],
    ):
        value = c.worker.locked(c.connection, c.row["id"])
    assert (value is None) == (mode != "valid")


# Registry-only changes cannot erase sealed presence for the same connection and exact subjects.
def test_saved_presence_survives_registry_metadata_changes():
    from otm.tenancies.presence import presence_views

    c = case()
    changed = c.snapshot.model_copy(
        update={"tenancy_revision": 42, "tenancy_name": "Renamed child"}
    )
    views = presence_views(
        changed, c.check, {"data": c.payload, "data_hash": canonical_hash(c.payload)}, NOW
    )
    assert set(views) == {"automation", "recovery"}
    assert all(view.state == "present" and view.checked_at == NOW for view in views.values())


# Ignoring registry metadata never permits changed authority, connections or required identities.
@pytest.mark.parametrize(
    "field",
    [
        "tenancy_id",
        "connection_id",
        "connection_revision",
        "policy_hash",
        "subject_binding_id",
        "binding_generation",
        "identity_domain_binding_id",
        "domain_ocid",
        "scim_resource_id",
        "provider_ocid",
        "user_name",
        "organization_id",
        "parent_tenancy_ocid",
        "tenancy_ocid",
        "workspace_id",
    ],
)
def test_saved_presence_still_requires_exact_current_subject(field):
    from otm.tenancies.presence import presence_views

    c = case()
    if field in {"tenancy_id", "connection_id", "connection_revision", "policy_hash"}:
        prior = getattr(c.snapshot, field)
        changed = c.snapshot.model_copy(
            update={
                field: prior + 1
                if isinstance(prior, int)
                else "0" * 64
                if field == "policy_hash"
                else uuid4()
            }
        )
    else:
        subject = c.snapshot.subjects[0]
        prior = getattr(subject, field)
        value = (
            prior + 1
            if isinstance(prior, int)
            else uuid4()
            if not isinstance(prior, str)
            else prior + "changed"
        )
        changed = c.snapshot.model_copy(
            update={"subjects": (subject.model_copy(update={field: value}), c.snapshot.subjects[1])}
        )
    assert (
        presence_views(
            changed, c.check, {"data": c.payload, "data_hash": canonical_hash(c.payload)}, NOW
        )
        == {}
    )
