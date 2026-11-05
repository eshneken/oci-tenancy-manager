"""Read-only drift proof, generation fences and retained-issue projections."""

import json
from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_configuration_updates import NOW, update_case

from otm.configuration.drift import ConfigurationChecks, check_intent, check_operation, check_rows
from otm.configuration.drift_context import (
    capture_target,
    expected_objects,
    registered_child,
    same_assignment,
)
from otm.configuration.drift_contracts import (
    ConfigurationCheckEvidence,
    ConfigurationCheckIntent,
    ConfigurationCheckRequest,
    ConfigurationDriftQuery,
)
from otm.configuration.drift_records import check_history, decode_check, save_check
from otm.configuration.drift_views import check_summary, drift_directory
from otm.configuration.drift_worker import ConfigurationCheckWorker
from otm.configuration.observation_contracts import ManagedObservation
from otm.configuration.observations import (
    binding_inventory,
    inspect_configuration,
)
from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.configuration import CATEGORIES, desired_objects
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict

__all__ = ["update_case"]


# Freeze a previously verified child and four real fake-cloud identities independently of recipes.
@pytest.fixture
def drift_case(update_case):
    c = update_case
    c.store.clock.return_value = NOW
    c.row.update(
        baseline_version_id=c.baseline.id,
        verified_baseline_version_id=c.baseline.id,
        configuration_verified_at=NOW,
        desired_configuration_id=None,
        last_verified_configuration_id=None,
        assigned_version=1,
        override_categories=(),
    )
    c.desired = desired_objects(c.target, c.baseline)
    c.objects = {key: value.model_dump(mode="json") for key, value in c.desired.items()}
    c.row["configuration_observation"] = c.objects
    with (
        patch("otm.configuration.drift_context.published_baseline", return_value=c.baseline),
        patch("otm.configuration.drift_context.load_configuration", return_value=None),
    ):
        c.target = capture_target(c.connection, c.policy.workspace_id, c.row, c.policy)
    c.service = ConfigurationChecks(
        c.store, policy=c.policy, policy_loader=c.loader, enqueuer=c.queue
    )
    c.intent = ConfigurationCheckIntent(
        workspace_id=c.policy.workspace_id,
        policy_revision=c.policy.policy_revision,
        organization_id=c.policy.organization_id,
        parent_tenancy_ocid=c.policy.parent_tenancy_ocid,
        administrator_id=c.grant["id"],
        authorization_revision=c.grant["authorization_revision"],
        targets=(c.target,),
        target=ConfigurationOperationTarget(
            tenancy_ocid=c.target.tenancy_ocid, display_name=c.row["name"]
        ),
    )
    payload = IntentEventData(intent=c.intent, actor=c.actor.actor).model_dump(mode="json")
    c.operation.update(intent_data=payload, intent_hash=canonical_hash(payload))
    c.worker = ConfigurationCheckWorker(
        Mock(), c.policy.workspace_id, Mock(return_value=NOW), c.loader, c.facade
    )
    return c


# Explicit missing and failed observations retain the original binding independently of actual
# values.
def envelope(c, category, scenario):
    original = c.desired[category]
    observed = original
    state, complete = "present", True
    if scenario == "different":
        observed = original.model_copy(
            update={
                "payload": '{"changed":true}',
                "payload_hash": canonical_hash({"changed": True}),
            }
        )
    elif scenario == "conflict":
        observed = original.model_copy(update={"object_ocid": original.object_ocid + "wrong"})
    elif scenario in {"missing", "unavailable"}:
        state, observed, complete = scenario, None, scenario == "missing"
    return ManagedObservation(
        binding=original, observed=observed, state=state, complete=complete
    ).model_dump(mode="json")


# Seal synthetic records through the same closed evidence type used by PostgreSQL and audit history.
def record(c, state="matching", scenario="matching", at=NOW):
    objects = {**c.objects, "policy": envelope(c, "policy", scenario)}
    results, actual = inspect_configuration(c.target, c.desired, c.facade, objects)
    assert actual == state
    evidence = ConfigurationCheckEvidence(
        check_id=uuid4(),
        tenancy_id=c.target.tenancy_id,
        state=state,
        safe_code="CONFIGURATION_CHECK_UNAVAILABLE"
        if state == "unavailable"
        else "CONFIGURATION_CHECK_COMPLETE",
        checked_at=at,
        context_hash=canonical_hash(c.target.model_dump(mode="json")),
        results=results,
    )
    return ({"operation_id": uuid4()}, c.target, evidence)


# Each category independently distinguishes explicit absence, mismatches, failed reads and
# conflicts.
@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize(
    "scenario,state",
    [
        ("matching", "matching"),
        ("different", "drifted"),
        ("missing", "drifted"),
        ("unavailable", "unavailable"),
        ("conflict", "unavailable"),
    ],
)
def test_read_matrix(drift_case, category, scenario, state):
    c = drift_case
    objects = {**c.objects, category: envelope(c, category, scenario)}
    before = json.dumps(objects, sort_keys=True)
    results, result_state = inspect_configuration(c.target, c.desired, c.facade, objects)
    assert result_state == state
    selected = next(item for item in results if item.category == category)
    assert selected.state == scenario
    assert json.dumps(objects, sort_keys=True) == before
    assert binding_inventory(objects) == c.target.bindings


# Invalid inventories and malformed reads never manufacture Missing or leak provider errors.
@pytest.mark.parametrize(
    "value", [None, {}, {"payload": "secret"}, {"contract_version": "managed-observation-1"}]
)
def test_invalid_inventory_is_unavailable(drift_case, value):
    c = drift_case
    objects = {**c.objects, "policy": value}
    assert "policy" not in binding_inventory(objects)
    results, state = inspect_configuration(c.target, c.desired, c.facade, objects)
    assert state == "unavailable" and results[0].state == "unavailable"
    assert "secret" not in json.dumps([item.model_dump(mode="json") for item in results])


# Provider exceptions and missing coverage proof become unknown, including model-constructed fakes.
@pytest.mark.parametrize(
    "failure",
    [PermissionError("private-key"), TimeoutError("private-key"), ValueError("private-key")],
)
def test_provider_errors_closed(drift_case, failure):
    c = drift_case
    facade = Mock()
    facade.observe.side_effect = failure
    values, state = inspect_configuration(c.target, c.desired, facade, c.objects)
    assert state == "unavailable" and all(not item.complete for item in values)
    assert "private-key" not in str(values)
    facade.apply.assert_not_called()


# An unqualified registry record never reaches the provider and cannot manufacture binding IDs.
def test_unbound_never_reads(drift_case):
    c = drift_case
    facade = Mock()
    target = c.target.model_copy(update={"qualified": False, "bindings": {}})
    values, state = inspect_configuration(target, c.desired, facade, None)
    assert state == "unavailable" and all(item.binding_ocid is None for item in values)
    facade.observe.assert_not_called()
    assert not registered_child(c.row, None)


# Assignment fences include child revision/configuration/parent/policy independently of observed
# data.
@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", 2),
        ("baseline_version_id", uuid4()),
        ("desired_configuration_id", uuid4()),
        ("status", "terminated"),
        ("parent_tenancy_ocid", "ocid1.tenancy.oc1..otmsimwrong"),
        ("provider_mode", "real"),
    ],
)
def test_assignment_fences(drift_case, field, value):
    c = drift_case
    assert same_assignment(c.target, c.row, c.policy)
    assert not same_assignment(c.target, {**c.row, field: value}, c.policy)
    assert not same_assignment(c.target, None, c.policy)


# Fresh complete matching is green; unknown bundles retain confirmed findings but never partial
# greens.
@pytest.mark.parametrize("latest", ["unavailable", "matching", "different", "missing"])
def test_history_retention(drift_case, latest):
    c = drift_case
    old = record(c, "drifted", "missing")
    state = (
        "unavailable"
        if latest == "unavailable"
        else "matching"
        if latest == "matching"
        else "drifted"
    )
    new = record(c, state, latest, NOW + timedelta(minutes=1))
    view = check_summary(
        c.row,
        (new, old),
        {},
        c.policy,
        c.baseline,
        NOW + timedelta(minutes=2),
        include_payload=True,
    )
    assert view.state == state
    assert view.confirmed_issue_count == (0 if latest == "matching" else 1)
    assert view.categories[0].retained == (latest == "unavailable")
    if latest == "unavailable":
        assert all(item.state == "unavailable" for item in view.categories[1:])
        assert view.categories[0].state == "missing"


# Wall clock age cannot create green; newer generations hide all old matching/drift evidence.
def test_stale_pending_and_generation(drift_case):
    c = drift_case
    old = record(c)
    assert check_summary(c.row, (old,), {}, c.policy, c.baseline, NOW + timedelta(days=2)).stale
    assert (
        check_summary(c.row, (old,), {}, c.policy, c.baseline, NOW + timedelta(days=2)).state
        == "not_checked"
    )
    assert (
        check_summary({**c.row, "revision": 2}, (old,), {}, c.policy, c.baseline, NOW).state
        == "not_checked"
    )
    assert (
        check_summary(c.row, (), {c.target.tenancy_id: uuid4()}, c.policy, c.baseline, NOW).state
        == "checking"
    )
    assert check_summary(c.row, (), {}, None, c.baseline, NOW).state == "unavailable"
    stale = check_summary(
        c.row, (record(c, "drifted", "missing"),), {}, c.policy, c.baseline, NOW + timedelta(days=2)
    )
    assert stale.confirmed_issue_count == 1 and stale.categories[0].retained


# Counts precede filters; scope/search/sort/page never change workspace authority or leak payloads.
@pytest.mark.parametrize("sort", ["name", "checked_at", "issue_count"])
def test_directory_filters(drift_case, sort):
    c = drift_case
    healthy = check_summary(c.row, (record(c),), {}, c.policy, c.baseline, NOW)
    issue = healthy.model_copy(
        update={
            "tenancy_id": uuid4(),
            "tenancy_name": "Other",
            "confirmed_issue_count": 1,
            "issue_count": 1,
            "state": "drifted",
        }
    )
    out = drift_directory(
        (healthy, issue),
        ConfigurationDriftQuery(tab="checks", sort=sort, direction="desc", page=99),
    )
    assert out.total == 2 and out.page == 1 and out.confirmed_count == 1
    assert drift_directory((healthy, issue), ConfigurationDriftQuery()).total == 1
    assert drift_directory((healthy, issue), ConfigurationDriftQuery(query="%_'")).total == 0
    assert (
        drift_directory(
            (healthy, issue),
            ConfigurationDriftQuery(tab="checks", tenancy_id=healthy.tenancy_id, state="matching"),
        ).total
        == 1
    )


# Incomplete coverage, duplicate categories and contradictory healthy status fail closed DTO
# validation.
def test_evidence_models(drift_case):
    c = drift_case
    value = record(c)[2].model_dump(mode="json")
    with pytest.raises(ValidationError):
        ConfigurationCheckEvidence.model_validate({**value, "results": [value["results"][0]] * 4})
    with pytest.raises(ValidationError):
        ConfigurationCheckEvidence.model_validate({**value, "state": "drifted"})
    absent = envelope(c, "policy", "missing")
    with pytest.raises(ValidationError):
        ManagedObservation.model_validate({**absent, "complete": False})
    with pytest.raises(ValidationError):
        ManagedObservation.model_validate({**absent, "state": "unavailable", "complete": True})
    with pytest.raises(ValidationError):
        ManagedObservation.model_validate({**absent, "state": "present"})


# Stored audit and context hashes fence every projected field, not just the check's primary key.
def test_record_hash_validation(drift_case):
    c = drift_case
    _, context, evidence = record(c)
    data = evidence.model_dump(mode="json")
    row = dict(
        id=evidence.check_id,
        tenancy_id=evidence.tenancy_id,
        state=evidence.state,
        checked_at=evidence.checked_at,
        context=context.model_dump(mode="json"),
        context_hash=evidence.context_hash,
        results=data["results"],
        audit_data=data,
        audit_hash=canonical_hash(data),
    )
    assert decode_check(row) == (context, evidence)
    for field, value in [
        ("id", uuid4()),
        ("context_hash", "b" * 64),
        ("audit_hash", "a" * 64),
        ("results", []),
    ]:
        with pytest.raises(ValueError):
            decode_check({**row, field: value})
    c.connection.execute.return_value.mappings.return_value.all.return_value = [row]
    assert len(check_history(c.connection, c.policy.workspace_id)) == 1
    save_check(c.connection, c.operation, c.target, evidence.results, evidence.state, NOW, NOW)
    assert c.connection.execute.call_count >= 4


# Qualification uses assigned version and actual binding inventory; omitted or stale inventory
# fails.
def test_capture_and_expected(drift_case):
    c = drift_case
    with (
        patch("otm.configuration.drift_context.published_baseline", return_value=c.baseline),
        patch("otm.configuration.drift_context.load_configuration", return_value=None),
    ):
        assert capture_target(c.connection, c.policy.workspace_id, c.row, c.policy).qualified
        assert not capture_target(
            c.connection,
            c.policy.workspace_id,
            {**c.row, "configuration_observation": None},
            c.policy,
        ).qualified
        assert expected_objects(c.connection, c.policy.workspace_id, c.target) == c.desired
        with pytest.raises(ValueError):
            expected_objects(
                c.connection,
                c.policy.workspace_id,
                c.target.model_copy(update={"baseline_hash": "b" * 64}),
            )
        assert (
            expected_objects(
                c.connection,
                c.policy.workspace_id,
                c.target.model_copy(update={"baseline_id": None}),
            )
            is None
        )
    invalid = c.operation.copy()
    invalid["intent_hash"] = "a" * 64
    with pytest.raises(ValueError):
        check_intent(invalid)
    assert check_intent(c.operation).intent == c.intent
    wrong = c.operation.copy()
    wrong["workspace_id"] = "foreign"
    with pytest.raises(ValueError):
        check_intent(wrong)


# Read projections reuse bounded history and pending contexts while preserving private payload
# scope.
def test_service_reads(drift_case):
    c = drift_case
    with (
        patch("otm.configuration.drift.read_snapshot", return_value=nullcontext(c.connection)),
        patch("otm.configuration.drift.check_rows", return_value=[c.row]),
        patch("otm.configuration.drift.check_history", return_value=()),
        patch.object(c.service, "pending", return_value={}),
    ):
        assert c.service.directory(c.actor, ConfigurationDriftQuery(tab="checks")).total == 1
        assert c.service.detail(c.actor, c.target.tenancy_id).tenancy_id == c.target.tenancy_id
    with patch("otm.configuration.drift.check_rows", return_value=[]):
        with pytest.raises(OrganizationConflict):
            c.service.summaries(c.connection, c.policy.workspace_id, c.target.tenancy_id)
    c.loader.return_value.execution_paused = True
    assert c.service.available_policy() is None
    assert ConfigurationChecks(c.store).available_policy() is None


# Atomic admission freezes one scope, supports exact replay and does not write the tenancy registry.
def test_start_replay_and_guards(drift_case):
    c = drift_case
    command = ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=c.target.tenancy_id)
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    c.connection.execute.return_value.mappings.return_value.one.return_value = c.grant
    with (
        patch("otm.configuration.drift.check_rows", return_value=[c.row]),
        patch.object(c.service, "pending", return_value={}),
        patch("otm.configuration.drift.capture_target", return_value=c.target),
    ):
        receipt = c.service.start(c.actor, command)
        c.queue.enqueue.assert_called_once_with(c.connection, receipt.operation_id)
        c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = dict(
            kind="configuration_check",
            request_digest=canonical_hash(
                {"kind": "configuration_check", **command.model_dump(mode="json")}
            ),
            id=receipt.operation_id,
            state="succeeded",
            accepted_at=NOW,
        )
        assert c.service.start(c.actor, command).operation_id == receipt.operation_id
        with pytest.raises(RequestConflict):
            c.service.start(c.actor, command.model_copy(update={"client_request_key": uuid4()}))
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    c.connection.execute.return_value.mappings.return_value.all.return_value = []
    with patch("otm.configuration.drift.check_rows", return_value=[]):
        with pytest.raises(OrganizationConflict):
            c.service.start(c.actor, command)
        with pytest.raises(OrganizationConflict):
            c.service.start(c.actor, command.model_copy(update={"tenancy_id": None}))
    c.loader.return_value.execution_paused = True
    with pytest.raises(OrganizationConflict):
        c.service.start(c.actor, command)


# Worker fencing is checked immediately before the read; rejected reads publish only unknown
# evidence.
@pytest.mark.parametrize(
    "case,expected",
    [
        ("healthy", "matching"),
        ("revoked", "unavailable"),
        ("paused", "unavailable"),
        ("changed", "superseded"),
        ("busy", "unavailable"),
        ("recipe_changed", "superseded"),
    ],
)
def test_worker_fences(drift_case, case, expected):
    c = drift_case
    row = dict(c.row)
    grant = dict(c.grant)
    if case == "revoked":
        grant["status"] = "revoked"
    if case == "paused":
        c.loader.return_value.execution_paused = True
    if case == "changed":
        row["revision"] += 1
    if case == "busy":
        row["operation_id"] = uuid4()
    connection = Mock()
    connection.scalar.return_value = None
    connection.execute.return_value.mappings.return_value.one.return_value = row
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = grant
    c.worker.engine.begin.return_value = nullcontext(connection)
    with (
        patch.object(c.worker, "_locked", return_value=c.operation),
        patch(
            "otm.configuration.drift_worker.expected_objects",
            side_effect=ValueError("changed") if case == "recipe_changed" else None,
            return_value=c.desired,
        ),
        patch("otm.configuration.drift_worker.save_check") as save,
    ):
        c.worker._target(c.operation["id"], c.target.tenancy_id)
        assert save.call_args.args[4] == expected
        if expected != "matching":
            assert all(not item.complete for item in save.call_args.args[3])
        connection.scalar.return_value = uuid4()
        save.reset_mock()
        c.worker._target(c.operation["id"], c.target.tenancy_id)
        save.assert_not_called()


# Duplicate native deliveries and missing operation authority cannot run or seal any additional
# target.
def test_worker_run_and_locks(drift_case):
    c = drift_case
    connection = Mock()
    connection.scalar.return_value = 1
    c.worker.engine.begin.side_effect = lambda: nullcontext(connection)
    with (
        patch.object(c.worker, "_locked", return_value=c.operation),
        patch.object(c.worker, "_target") as target,
    ):
        c.worker.run(c.operation["id"])
        target.assert_called_once_with(c.operation["id"], c.target.tenancy_id)
        assert connection.execute.call_count == 2
    with patch.object(c.worker, "_locked", return_value=None):
        c.worker.run(c.operation["id"])
    with (
        patch("otm.configuration.drift_worker.require_transaction"),
        patch("otm.configuration.drift_worker.check_operation", return_value=[c.operation]),
    ):
        connection.execute.return_value.scalar_one_or_none.return_value = uuid4()
        assert c.worker._locked(connection, c.operation["id"]) == c.operation
        connection.execute.return_value.scalar_one_or_none.return_value = None
        assert c.worker._locked(connection, c.operation["id"]) is None
    with patch.object(c.worker, "_locked", return_value=None):
        c.worker._target(c.operation["id"], c.target.tenancy_id)


# Pending scope and fixed SQL rows feed deterministic current projections without selecting
# latest recipes.
def test_pending_and_scoped_query_shapes(drift_case):
    c = drift_case
    with patch("otm.configuration.drift.check_operation", return_value=[c.operation]):
        assert c.service.pending(c.connection, c.policy.workspace_id, [c.row], c.policy) == {
            c.target.tenancy_id: c.operation["id"]
        }
    c.connection.execute.return_value.mappings.return_value.all.return_value = [c.operation]
    assert check_operation(c.connection, c.policy.workspace_id, c.operation["id"], True) == [
        c.operation
    ]
    row = {
        **c.row,
        "policy_override_statements": None,
        "quota_override_statements": ["quota"],
        "monthly_budget_override_amount": None,
    }
    c.connection.execute.return_value.mappings.return_value.__iter__ = Mock(
        return_value=iter([row])
    )
    assert check_rows(c.connection, c.policy.workspace_id, c.target.tenancy_id)[0][
        "override_categories"
    ] == ("quota",)
    with (
        patch("otm.configuration.drift.check_rows", return_value=[c.row]),
        patch.object(c.service, "pending", return_value={c.target.tenancy_id: uuid4()}),
    ):
        c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
        with pytest.raises(OrganizationConflict):
            c.service.start(
                c.actor,
                ConfigurationCheckRequest(
                    client_request_key=uuid4(), tenancy_id=c.target.tenancy_id
                ),
            )


# Pausing dispatch disables checks without hiding confirmed drift for the same assignment.
def test_pause_does_not_clear_confirmed_drift(drift_case):
    c = drift_case
    c.loader.return_value.execution_paused = True
    prior = record(c, "drifted", "missing")
    with (
        patch("otm.configuration.drift.check_rows", return_value=[c.row]),
        patch.object(c.service, "pending", return_value={}),
        patch("otm.configuration.drift.check_history", return_value=(prior,)),
    ):
        view = c.service.summaries(c.connection, c.policy.workspace_id)[0]
    assert view.confirmed_issue_count == 1 and not view.can_check
    assert view.state == "unavailable" and view.categories[0].retained
    assert all(item.state != "matching" for item in view.categories)


# Age/read failures are verification concerns; retained complete findings alone count as drift.
@pytest.mark.parametrize(
    "scenario",
    [
        "never",
        "matching",
        "expired",
        "unavailable",
        "checking",
        "drift",
        "drift_expired",
        "drift_unavailable",
        "drift_checking",
    ],
)
def test_shared_drift_and_verification_projection(drift_case, scenario):
    c = drift_case
    confirmed = scenario.startswith("drift")
    old = record(c, "drifted", "missing") if confirmed else record(c)
    records = () if scenario == "never" else (old,)
    now = NOW
    if scenario.endswith("expired") or scenario in {"checking", "drift_checking"}:
        now += timedelta(hours=35)
    if scenario.endswith("unavailable"):
        records = (
            (record(c, "unavailable", "unavailable", NOW + timedelta(minutes=1)), old)
            if confirmed
            else (record(c, "unavailable", "unavailable"),)
        )
        now += timedelta(minutes=2)
    pending = {c.target.tenancy_id: uuid4()} if scenario.endswith("checking") else {}
    view = check_summary(c.row, records, pending, c.policy, c.baseline, now)
    assert view.issue_count == view.confirmed_issue_count == int(confirmed)
    assert view.stale == (scenario.endswith("expired") or scenario.endswith("checking"))
    expected_state = (
        "checking"
        if pending
        else "unavailable"
        if scenario.endswith("unavailable")
        else "not_checked"
        if scenario in {"never", "expired"}
        else "drifted"
        if confirmed
        else "matching"
    )
    assert view.state == expected_state
    confirmed_tab = drift_directory([view], ConfigurationDriftQuery())
    checks_tab = drift_directory([view], ConfigurationDriftQuery(tab="checks"))
    assert confirmed_tab.total == int(confirmed) and checks_tab.total == 1
    assert checks_tab.stale_count == int(view.stale)
    assert checks_tab.unchecked_count == int(scenario == "never")
    if confirmed and scenario != "drift":
        assert view.categories[0].retained


# The daily boundary is exact, and a fresh complete read clears only age/unverified concerns.
@pytest.mark.parametrize(
    "age,expired", [(timedelta(hours=24), False), (timedelta(hours=24, microseconds=1), True)]
)
def test_matching_age_boundary_and_refresh(drift_case, age, expired):
    c = drift_case
    old = record(c)
    now = NOW + age
    before = check_summary(c.row, (old,), {}, c.policy, c.baseline, now)
    assert before.stale == expired and before.issue_count == 0
    fresh = record(c, at=now)
    after = check_summary(c.row, (fresh, old), {}, c.policy, c.baseline, now)
    assert after.state == "matching" and not after.stale and after.issue_count == 0


# Status filters use the same overlapping evidence/freshness distinctions as visible indicators.
def test_check_status_filters_keep_expired_and_unchecked_distinct(drift_case):
    c = drift_case
    old = record(c)
    expired = check_summary(c.row, (old,), {}, c.policy, c.baseline, NOW + timedelta(hours=35))
    never = check_summary({**c.row, "id": uuid4()}, (), {}, c.policy, c.baseline, NOW)
    retained = check_summary(
        {**c.row, "id": uuid4()}, (), {}, c.policy, c.baseline, NOW
    ).model_copy(update={"state": "unavailable", "confirmed_issue_count": 1, "issue_count": 1})
    items = [expired, never, retained]
    stale = drift_directory(items, ConfigurationDriftQuery(tab="checks", state="stale"))
    assert [row.tenancy_id for row in stale.items] == [expired.tenancy_id]
    unchecked = drift_directory(items, ConfigurationDriftQuery(tab="checks", state="not_checked"))
    assert [row.tenancy_id for row in unchecked.items] == [never.tenancy_id]
    drift = drift_directory(items, ConfigurationDriftQuery(tab="checks", state="drifted"))
    assert [row.tenancy_id for row in drift.items] == [retained.tenancy_id]
    unavailable = drift_directory(items, ConfigurationDriftQuery(tab="checks", state="unavailable"))
    assert [row.tenancy_id for row in unavailable.items] == [retained.tenancy_id]


# Starting a check cannot clear a fresh known difference before replacement evidence exists.
def test_pending_check_retains_fresh_confirmed_findings(drift_case):
    c = drift_case
    view = check_summary(
        c.row,
        (record(c, "drifted", "missing"),),
        {c.target.tenancy_id: uuid4()},
        c.policy,
        c.baseline,
        NOW + timedelta(minutes=1),
    )
    assert view.state == "checking" and not view.stale
    assert view.issue_count == view.confirmed_issue_count == 1
    assert view.categories[0].state == "missing"
    assert drift_directory([view], ConfigurationDriftQuery()).total == 1
