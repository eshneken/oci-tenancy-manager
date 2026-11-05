"""Day-by-day review closure, source correction and explicit identity-merge regression journeys."""

from uuid import UUID

import pytest
from conftest import example_records
from fastapi.testclient import TestClient
from otm.organization.local_web import build_local_web
from sqlalchemy import select
from test_csv_web import HEADERS, JSON_HEADERS, clean_confirmation, csv_bytes
from test_tenancy_registry import create
from test_tenancy_registry import operate as registry_act
from test_tenancy_registry import person as registry_person

pytestmark = pytest.mark.postgres


# Expose the real review API on a disposable, fixed organization workspace.
@pytest.fixture
def web(store):
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        yield client


# Upload a scenario observation; day padding varies fixtures but does not define identity.
def load(web, rows=None, day=0, complete=True):
    return web.post(
        f"/api/local/feeds?complete={str(complete).lower()}",
        content=csv_bytes(rows) + b"\n" * day,
        headers=HEADERS,
    )


# Read the selected queue without losing historical informational warning episodes.
def cases(web, kind=None, tab="actionable"):
    params = {"tab": tab, "page_size": 100}
    if kind:
        params["kind"] = kind
    response = web.get("/api/local/exceptions", params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# Submit an explicit review decision with the current expected context and audit reason.
def act(web, case, operation, partner=None, expected=None, tenancy=None):
    return web.post(
        "/api/local/reviews/operate",
        headers=JSON_HEADERS,
        json={
            "context": expected or clean_confirmation(web),
            "case_id": case["id"],
            "operation": operation,
            "partner_email": partner,
            "reason": "Verified scenario decision",
            "tenancy_id": tenancy,
        },
    )


# Assert a successful mutation and expose its result for meaningful journey assertions.
def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


# A completed plan hides zero-association profiles while retained access stays visible.
@pytest.mark.parametrize("keep", [False, True])
def test_absence_action_removes_only_after_last_association(store, web, keep):
    ok(load(web))
    owned = create(web)
    rows = example_records()[:-1]
    ok(load(web, rows, day=1))
    assert cases(web, "PERSON_ABSENCE_REVIEW")
    result = ok(
        registry_act(
            web,
            "offboard_person",
            plan=[
                {
                    "association_id": owned["id"],
                    "action": "keep" if keep else "delete",
                }
            ],
        )
    )
    assert result["person_removed"] is not keep
    assert not cases(web, "PERSON_ABSENCE_REVIEW")
    for day in (2, 3):
        ok(load(web, rows, day=day))
        assert not cases(web, "PERSON_ABSENCE_REVIEW")
    if keep:
        assert registry_person(web, "engineer@example.test")["association_count"] == 1
        ok(registry_act(web, "delete_tenancy", tenancy_id=owned["tenancy_id"]))
    assert not registry_person(web, "engineer@example.test")["managed"]
    assert any(p.email == "engineer@example.test" for p in store.head("fixture-org").people)
    ok(load(web, day=7))
    assert registry_person(web, "engineer@example.test")["onboarding_required"]
    assert len(cases(web, "TENANCY_SETUP_REVIEW")) == 1


# Returning presence enables keep resolution; another later departure opens a new review.
def test_return_requires_resolution_and_later_absence_is_a_new_episode(web):
    ok(load(web))
    ok(load(web, example_records()[:-1], day=1))
    first = cases(web, "PERSON_ABSENCE_REVIEW")[0]
    ok(load(web, day=2))
    returned = cases(web, "PERSON_ABSENCE_REVIEW")[0]
    assert returned["id"] == first["id"] and "keep_returned" in returned["actions"]
    ok(act(web, returned, "keep_returned"))
    assert not cases(web, "PERSON_ABSENCE_REVIEW")
    ok(load(web, example_records()[:-1], day=3))
    assert cases(web, "PERSON_ABSENCE_REVIEW")[0]["id"] != first["id"]


# Each onboarding action closes once, audits simulated success and stays closed on feeds.
@pytest.mark.parametrize("operation", ["create_tenancy", "import_tenancy", "shared_membership"])
def test_new_employee_actions_simulate_success_and_close_review(web, operation):
    ok(load(web))
    new = example_records()[-1].model_copy(
        update={"email": "new@example.test", "full_name": "New Person"}
    )
    rows = example_records() + (new,)
    ok(load(web, rows, day=1))
    shared = (
        create(web, "two@example.test", "shared", "Onboarding team")
        if operation == "shared_membership"
        else None
    )
    case = cases(web, "TENANCY_SETUP_REVIEW")[0]
    assert "resolve" not in case["actions"] and "no_tenancy_required" in case["actions"]
    expected = clean_confirmation(web)
    result = ok(
        act(
            web,
            case,
            operation,
            expected=expected,
            tenancy=shared["tenancy_id"] if shared else None,
        )
    )
    assert result["resolved"] and result["simulated"] and result["status"] == "succeeded"
    assert result["oci_performed"] is False
    assert not cases(web, "TENANCY_SETUP_REVIEW")
    assert act(web, case, operation, expected=expected).status_code == 409
    for day in (2, 3):
        ok(load(web, rows, day=day))
        assert not cases(web, "TENANCY_SETUP_REVIEW")
    assert web.get("/api/local/summary").json()["new_employees"] == 0
    assert any(r["email"] == new.email for r in web.get("/api/local/employees").json()["data"])
    history = cases(web, tab="informational")
    actions = [
        r for r in history if r["kind"] == "TENANCY_ACTION_SIMULATED" and r["email"] == new.email
    ]
    assert len(actions) == 1 and actions[0]["operation"] == (
        "join_shared" if operation == "shared_membership" else operation
    )
    assert actions[0]["simulation"] == "succeeded"


# Onboarding can finish without simulating an infrastructure operation or removing a user.
def test_no_tenancy_required_is_a_distinct_audited_decision(web):
    ok(load(web))
    new = example_records()[-1].model_copy(update={"email": "new@example.test"})
    rows = example_records() + (new,)
    ok(load(web, rows, day=1))
    case = cases(web, "TENANCY_SETUP_REVIEW")[0]
    assert act(web, case, "resolve").status_code == 422
    result = ok(act(web, case, "no_tenancy_required"))
    assert result["resolved"] and not result["simulated"]
    ok(load(web, rows, day=2))
    assert not cases(web, "TENANCY_SETUP_REVIEW")
    assert any(r.get("operation") == "no_tenancy_required" for r in cases(web, tab="informational"))


# Retained access needs explicit return, then a later genuine absence gets a fresh review.
def test_settled_absence_reappearance_allows_a_new_later_departure(web):
    ok(load(web))
    owned = create(web)
    missing = example_records()[:-1]
    ok(load(web, missing, day=1))
    first = cases(web, "PERSON_ABSENCE_REVIEW")[0]
    ok(
        registry_act(
            web, "offboard_person", plan=[{"association_id": owned["id"], "action": "keep"}]
        )
    )
    ok(load(web, missing, day=2))
    assert not cases(web, "PERSON_ABSENCE_REVIEW")
    ok(load(web, day=3))
    ok(registry_act(web, "return_to_org"))
    ok(load(web, missing, day=4))
    second = cases(web, "PERSON_ABSENCE_REVIEW")[0]
    assert second["id"] != first["id"]


# A recurring assistant row can stay in the directory without recurring LOB mapping work.
def test_lob_ignore_is_permanent_and_scoped_to_person_and_kind(web):
    assistant = example_records()[-1].model_copy(
        update={
            "email": "assistant@example.test",
            "full_name": "Executive Assistant",
            "manager_email": "root@example.test",
            "reported_top_manager_email": "root@example.test",
        }
    )
    rows = example_records() + (assistant,)
    ok(load(web, rows))
    case = cases(web, "LOB_MAPPING_REVIEW")[0]
    ok(act(web, case, "ignore"))
    ok(load(web, rows, day=1))
    assert not cases(web, "LOB_MAPPING_REVIEW")
    assert any(
        r["email"] == assistant.email for r in web.get("/api/local/employees").json()["data"]
    )
    assert any(r["status"] == "ignored" for r in cases(web, tab="informational"))


# Warnings are separate from work and retain dated history after a corrected feed.
def test_corrected_top_manager_auto_resolves_and_changes_group_per_employee(web):
    ok(load(web))
    wrong = tuple(
        r.model_copy(update={"reported_top_manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    ok(load(web, wrong, day=1))
    assert not cases(web)
    warning = cases(web, "TOP_MANAGER_MISMATCH", "informational")[0]
    assert warning["status"] == "open"
    fixed = tuple(
        r.model_copy(
            update={
                "full_name": "Renamed Engineer",
                "manager_email": "two@example.test",
                "reported_top_manager_email": "two@example.test",
            }
        )
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    ok(load(web, fixed, day=2))
    history = cases(web, tab="informational")
    corrected = next(r for r in history if r["id"] == warning["id"])
    assert corrected["status"] == "resolved" and corrected["resolved_at"]
    changes = [
        r for r in history if r["kind"] == "METADATA_UPDATED" and r["name"] == "Renamed Engineer"
    ]
    assert len(changes) == 1
    assert {"full_name", "manager_email"} <= {c["field"] for c in changes[0]["changes"]}


# Retire the provisional identity while preserving stable relationship keys.
def test_identity_merge_keeps_survivor_uuid_and_manager_links_across_future_feeds(store, web):
    rows = tuple(
        r.model_copy(update={"manager_email": "engineer@example.test"})
        if r.email == "delegate@example.test"
        else r
        for r in example_records()
    )
    ok(load(web, rows))
    initial = store.head("fixture-org")
    old = next(p for p in initial.people if p.email == "engineer@example.test")
    renamed = tuple(
        r.model_copy(update={"email": "jones@example.test", "full_name": "Karen Jones"})
        if r.email == old.email
        else r.model_copy(update={"manager_email": "jones@example.test"})
        if r.email == "delegate@example.test"
        else r
        for r in rows
    )
    ok(load(web, renamed, day=1))
    assert cases(web, "PERSON_ABSENCE_REVIEW")
    new = cases(web, "TENANCY_SETUP_REVIEW")[0]
    provisional = UUID(new["person_id"])
    result = ok(act(web, new, "merge", old.email))
    assert result["resolved"]
    for day in (2, 3):
        ok(load(web, renamed, day=day))
        merged = next(
            p for p in store.head("fixture-org").people if p.email == "jones@example.test"
        )
        assert (
            merged.id == old.id and merged.id != provisional and merged.full_name == "Karen Jones"
        )
        assert not cases(web, "TENANCY_SETUP_REVIEW") and not cases(web, "PERSON_ABSENCE_REVIEW")
        assert (
            next(
                p for p in store.head("fixture-org").people if p.email == "delegate@example.test"
            ).manager_email
            == merged.email
        )
    assert next(p for p in store.revision(initial.id).people if p.id == old.id).email == old.email
    with store.engine.connect() as connection:
        member = store.tables["member"]
        manager_id = connection.scalar(
            select(member.c.manager_person_id).where(
                member.c.version_id == str(store.head("fixture-org").id),
                member.c.email == "delegate@example.test",
            )
        )
        assert manager_id == str(old.id)
    current = store.head("fixture-org").id
    stale = load(web, rows, day=4)
    assert stale.json()["outcome"]["state"] == "rejected"
    assert store.head("fixture-org").id == current


# Reject stale context, arbitrary pair selection and informational action attempts.
def test_stale_decisions_and_invalid_merge_cannot_mutate_org(store, web):
    ok(load(web))
    ok(load(web, example_records()[:-1], day=1))
    case = cases(web, "PERSON_ABSENCE_REVIEW")[0]
    expected = clean_confirmation(web)
    ok(load(web, example_records()[:-1], day=2))
    assert act(web, case, "remove_user", expected=expected).status_code == 409
    assert act(web, case, "merge", "one@example.test").status_code == 422
    assert act(web, case, "resolve").status_code == 422
    assert next(p for p in store.head("fixture-org").people if p.email == case["email"])


# Correct source rows resolve informational episodes without an administrator close action.
def test_missing_manager_and_incomplete_chain_auto_resolve_as_information(web):
    ok(load(web))
    broken = tuple(
        r.model_copy(update={"manager_email": "unknown@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    ok(load(web, broken, day=1))
    warnings = [
        r
        for r in cases(web, tab="informational")
        if r["kind"] in {"MANAGER_PROFILE_MISSING", "ANCESTRY_UNRESOLVED"}
    ]
    assert len(warnings) == 2 and all(r["status"] == "open" for r in warnings)
    manager = example_records()[-1].model_copy(
        update={
            "email": "unknown@example.test",
            "full_name": "Known Manager",
            "manager_email": "one@example.test",
        }
    )
    ok(load(web, broken + (manager,), day=2))
    closed = [r for r in cases(web, tab="informational") if r["id"] in {w["id"] for w in warnings}]
    assert len(closed) == 2 and all(r["status"] == "resolved" for r in closed)


# Removal cannot orphan a configured designee reference even when source absence is valid.
def test_protected_designee_cannot_be_removed_without_updating_configuration(web):
    ok(load(web))
    rows = tuple(r for r in example_records() if r.email != "delegate@example.test")
    ok(load(web, rows, day=1))
    absent = next(
        c for c in cases(web, "PERSON_ABSENCE_REVIEW") if c["email"] == "delegate@example.test"
    )
    assert act(web, absent, "remove_user").status_code == 422
    assert any(
        r["email"] == "delegate@example.test"
        for r in web.get("/api/local/employees").json()["data"]
    )


# Waiving one name conflict cannot accidentally waive all later different conflicting names.
def test_override_resolution_reopens_for_a_different_conflicting_source_value(store, web):
    from datetime import UTC, datetime
    from uuid import uuid4

    from otm.organization.contracts import PersonOverride

    ok(load(web))
    config = store.configuration("fixture-org")
    context = clean_confirmation(web)
    changed = config.model_copy(
        update={
            "id": uuid4(),
            "overrides": (
                PersonOverride(
                    email="engineer@example.test",
                    values={"full_name": "Admin Name"},
                    actor="local:tester",
                    reason="Test verified correction",
                ),
            ),
        }
    )
    store.update_configuration(
        changed,
        expected_version_id=UUID(context["applied_version_id"]),
        expected_proposed_id=UUID(context["proposed_version_id"]),
        expected_configuration_id=UUID(context["configuration_id"]),
        actor="local:tester",
        reason="Verified correction",
        observed_at=datetime.now(UTC),
    )
    initial = cases(web, "OVERRIDE_CONFLICT")[0]
    ok(act(web, initial, "resolve"))
    ok(load(web, day=1))
    assert not cases(web, "OVERRIDE_CONFLICT")
    other = tuple(
        r.model_copy(update={"full_name": "Different Source Name"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    ok(load(web, other, day=2))
    assert cases(web, "OVERRIDE_CONFLICT")[0]["id"] != initial["id"]


# Chained rare name/email changes keep the first stable identity through both merges.
def test_second_identity_change_preserves_original_survivor(store, web):
    ok(load(web))
    survivor = next(
        p.id for p in store.head("fixture-org").people if p.email == "engineer@example.test"
    )
    previous_email = "engineer@example.test"
    for day, address in ((1, "jones@example.test"), (2, "brown@example.test")):
        renamed = tuple(
            r.model_copy(update={"email": address, "full_name": "Renamed Engineer"})
            if r.email == "engineer@example.test"
            else r
            for r in example_records()
        )
        ok(load(web, renamed, day=day))
        new = cases(web, "TENANCY_SETUP_REVIEW")[0]
        ok(act(web, new, "merge", previous_email))
        person = next(p for p in store.head("fixture-org").people if p.email == address)
        assert person.id == survivor
        previous_email = address
    assert not cases(web, "TENANCY_SETUP_REVIEW") and not cases(web, "PERSON_ABSENCE_REVIEW")


# Rejected feeds are dated information and cannot bury or change actionable work.
def test_parse_rejection_history_and_actionable_closure_do_not_hide_each_other(web):
    ok(load(web))
    ok(load(web, example_records()[:-1], day=1))
    assert web.post("/api/local/feeds", content=b"bad headers", headers=HEADERS).status_code == 422
    assert cases(web, "PERSON_ABSENCE_REVIEW")
    assert any(r["kind"] == "FEED_REJECTED" for r in cases(web, tab="informational"))


# Allow day-six decisions on unchanged evidence without fabricating source freshness.
def test_admin_can_resolve_old_published_evidence_without_asserting_fresh_census(
    store, web, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    import otm.organization.review_workflow as workflow

    ok(load(web))
    new = example_records()[-1].model_copy(
        update={"email": "new@example.test", "full_name": "New Person"}
    )
    ok(load(web, example_records() + (new,), day=1))
    before = store.head("fixture-org").source_captured_at
    future = datetime.now(UTC) + timedelta(days=6)

    # Advance only the administrator clock; the persisted source capture stays unchanged.
    class ScenarioClock(datetime):
        # Return the later action time while preserving aware timestamp semantics.
        @classmethod
        def now(cls, tz=None):
            return future.astimezone(tz or UTC)

    monkeypatch.setattr(workflow, "datetime", ScenarioClock)
    import otm.organization.associations as associations

    monkeypatch.setattr(associations, "datetime", ScenarioClock)
    case = cases(web, "TENANCY_SETUP_REVIEW")[0]
    ok(act(web, case, "no_tenancy_required"))
    current = store.head("fixture-org")
    assert current.source_captured_at == before and current.absence_eligible is False
    assert not cases(web, "TENANCY_SETUP_REVIEW")


# Closing a current case cannot implicitly apply a different source staged through the CLI.
def test_review_resolution_cannot_publish_a_separate_pending_proposal(store, web):
    from datetime import UTC, datetime
    from uuid import uuid4

    from otm.organization.contracts import Envelope
    from otm.organization.csv_feed import parse_csv

    ok(load(web))
    new = example_records()[-1].model_copy(
        update={"email": "new@example.test", "full_name": "New Person"}
    )
    rows = example_records() + (new,)
    ok(load(web, rows, day=1))
    original = store.head("fixture-org").id
    now = datetime.now(UTC)
    source = Envelope(
        source_id="fixture",
        population_id="fixture-org",
        external_snapshot_id=str(uuid4()),
        captured_at=now,
        declared_completeness="complete",
    )
    feed, _ = store.register(source, parse_csv(csv_bytes(rows)), now)
    staged = store.stage(feed, now)
    assert staged.state == "staged"
    case = cases(web, "TENANCY_SETUP_REVIEW")[0]
    assert act(web, case, "no_tenancy_required").status_code == 409
    assert store.head("fixture-org").id == original


# A failed publication cannot leave a simulated-success log or a closed review behind.
def test_simulated_success_and_review_closure_roll_back_together(store, web, monkeypatch):
    ok(load(web))
    new = example_records()[-1].model_copy(update={"email": "new@example.test"})
    ok(load(web, example_records() + (new,), day=1))
    case = cases(web, "TENANCY_SETUP_REVIEW")[0]
    before = store.workspace_context("fixture-org")
    original_audit = store._audit

    # Interrupt publication to verify rollback of the complete decision transaction.
    def fail_publication(connection, workspace, kind, *args, **kwargs):
        if kind == "organization_published":
            raise RuntimeError("Simulated publication failure")
        return original_audit(connection, workspace, kind, *args, **kwargs)

    monkeypatch.setattr(store, "_audit", fail_publication)
    with pytest.raises(RuntimeError, match="Simulated publication failure"):
        act(web, case, "create_tenancy")
    assert store.workspace_context("fixture-org") == before
    assert cases(web, "TENANCY_SETUP_REVIEW")[0]["id"] == case["id"]
    assert not any(r["kind"] == "TENANCY_ACTION_SIMULATED" for r in cases(web, tab="informational"))


# A fabricated directory cleanup identifier must never remove a present employee.
def test_retained_cleanup_rejects_a_present_employee(store, web):
    ok(load(web))
    person = next(p for p in store.head("fixture-org").people if p.email == "engineer@example.test")
    before = store.workspace_context("fixture-org")
    assert act(web, {"id": "retained:" + str(person.id)}, "remove_user").status_code == 422
    assert store.workspace_context("fixture-org") == before


# Closing tenancy disposition cannot make a still-missing leader or designee active again.
@pytest.mark.parametrize(
    "address,review_kind",
    [
        ("two@example.test", "LOB_LEADER_REVIEW"),
        ("delegate@example.test", "DESIGNEE_INVALID"),
    ],
)
def test_settling_absence_does_not_restore_absent_accountability(store, web, address, review_kind):
    ok(load(web))
    rows = tuple(row for row in example_records() if row.email != address)
    ok(load(web, rows, day=1))
    assert any(case["email"] == address for case in cases(web, "PERSON_ABSENCE_REVIEW"))
    ok(registry_act(web, "offboard_person", address, confirm_no_associations=True))
    assert not cases(web, "PERSON_ABSENCE_REVIEW")
    assert cases(web, review_kind)
    current = next(p for p in store.head("fixture-org").people if p.email == address)
    assert not current.absence_review and current.absence_review_since
    if review_kind == "DESIGNEE_INVALID":
        engineer = next(
            p for p in store.head("fixture-org").people if p.email == "engineer@example.test"
        )
        assert address not in engineer.designee_emails
