"""Association-aware simulator, source/managed separation and offboarding safety regressions."""

import pytest
from conftest import example_records
from fastapi.testclient import TestClient
from otm.organization.local_web import build_local_web
from test_csv_web import HEADERS, JSON_HEADERS, clean_confirmation, csv_bytes

pytestmark = pytest.mark.postgres


# Exercise the real API in an isolated PostgreSQL workspace.
@pytest.fixture
def web(store):
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        assert (
            client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS).status_code == 200
        )
        yield client


# Read the complete current registry including unmanaged/source identities.
def registry(web):
    return web.get("/api/local/tenancy-registry").json()


# Resolve an employee by current email without guessing stable UUIDs.
def person(web, address):
    return next(p for p in registry(web)["people"] if p["email"] == address)


# Send a guarded registry intent with a meaningful reason and current preview context.
def operate(web, operation, address="engineer@example.test", **values):
    payload = dict(
        context=clean_confirmation(web),
        operation=operation,
        person_id=person(web, address)["id"],
        reason="Verified registry scenario",
        **values,
    )
    return web.post("/api/local/tenancy-registry/operate", json=payload, headers=JSON_HEADERS)


# Require real local persistence success while excluding any claimed OCI operation.
def succeed(response):
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["oci_performed"] is False
    return result


# Register a simulated tenancy with explicit accountable ownership.
def create(web, address="engineer@example.test", kind="individual", name="Personal tenancy"):
    succeed(operate(web, "create_tenancy", address, kind=kind, name=name))
    return person(web, address)["associations"][-1]


# Publish a full snapshot without one employee, retaining source history.
def missing(web, address="engineer@example.test"):
    rows = tuple(r for r in example_records() if r.email != address)
    result = web.post("/api/local/feeds", content=csv_bytes(rows), headers=HEADERS)
    assert result.status_code == 200 and result.json()["outcome"]["state"] == "published"
    return csv_bytes(rows)


# Individual ownership, shared ownership and shared membership are distinct associations.
def test_person_can_own_multiple_tenancies_and_join_shared(web):
    create(web)
    shared = create(web, "two@example.test", "shared", "Team sandbox")
    succeed(operate(web, "import_tenancy", name="Imported sandbox", kind="individual"))
    succeed(operate(web, "join_shared", tenancy_id=shared["tenancy_id"]))
    links = person(web, "engineer@example.test")["associations"]
    assert len(links) == 3 and sorted(a["role"] for a in links) == ["member", "owner", "owner"]
    assert operate(web, "join_shared", tenancy_id=shared["tenancy_id"]).status_code == 422


# Last-link removal hides the profile without deleting source or the shared tenancy.
def test_complete_offboard_deletes_personal_and_removes_shared_membership(store, web):
    owned = create(web)
    shared = create(web, "two@example.test", "shared", "Shared sandbox")
    succeed(operate(web, "join_shared", tenancy_id=shared["tenancy_id"]))
    p = person(web, "engineer@example.test")
    data = missing(web)
    plan = [
        dict(association_id=a["id"], action="delete" if a["role"] == "owner" else "remove")
        for a in p["associations"]
    ]
    result = succeed(operate(web, "offboard_person", plan=plan))
    assert result["person_removed"] and result["remaining_associations"] == 0
    assert person(web, p["email"])["managed"] is False
    assert not web.get("/api/local/employees?query=engineer@example.test").json()["data"]
    assert web.get("/api/local/exceptions?kind=PERSON_ABSENCE_REVIEW").json()["total"] == 0
    assert any(t["id"] == shared["tenancy_id"] for t in registry(web)["tenancies"])
    assert not any(t["id"] == owned["tenancy_id"] for t in registry(web)["tenancies"])
    assert any(
        str(p.id) == person(web, "engineer@example.test")["id"]
        for p in store.head("fixture-org").people
    )
    web.post("/api/local/feeds", content=data, headers=HEADERS)
    assert not person(web, p["email"])["managed"]


# Deleting one owned tenancy cannot hide another active shared membership.
def test_keep_membership_retains_outside_profile_until_last_link_removed(web):
    create(web)
    shared = create(web, "two@example.test", "shared", "Retained team sandbox")
    succeed(operate(web, "join_shared", tenancy_id=shared["tenancy_id"]))
    missing(web)
    links = person(web, "engineer@example.test")["associations"]
    result = succeed(
        operate(
            web,
            "offboard_person",
            plan=[
                dict(association_id=a["id"], action="delete" if a["role"] == "owner" else "keep")
                for a in links
            ],
        )
    )
    assert not result["person_removed"] and result["remaining_associations"] == 1
    assert "Outside organization" in person(web, "engineer@example.test")["status"]
    assert web.get("/api/local/exceptions?kind=PERSON_ABSENCE_REVIEW").json()["total"] == 0
    result = succeed(operate(web, "remove_member", tenancy_id=shared["tenancy_id"]))
    assert result["person_removed"]


# Shared ownership survives offboarding by moving to another current eligible person.
def test_shared_owner_must_transfer_and_existing_member_is_promoted(web):
    shared = create(web, kind="shared", name="Owned team sandbox")
    succeed(operate(web, "join_shared", "two@example.test", tenancy_id=shared["tenancy_id"]))
    missing(web)
    owner = person(web, "engineer@example.test")["associations"][0]
    assert (
        operate(
            web, "offboard_person", plan=[dict(association_id=owner["id"], action="delete")]
        ).status_code
        == 422
    )
    recipient = person(web, "two@example.test")
    result = succeed(
        operate(
            web,
            "offboard_person",
            plan=[
                dict(
                    association_id=owner["id"],
                    action="transfer",
                    recipient_person_id=recipient["id"],
                )
            ],
        )
    )
    assert result["person_removed"]
    tenancy = next(t for t in registry(web)["tenancies"] if t["id"] == shared["tenancy_id"])
    assert tenancy["owner_person_id"] == recipient["id"] and tenancy["member_count"] == 0
    assert len(recipient["associations"]) == 1


# Unmanaged people stay out across feeds and explicitly re-onboard without access.
def test_no_tenancy_and_reonboarding_do_not_modify_reporting_graph(store, web):
    profile = person(web, "one@example.test")
    result = succeed(operate(web, "no_tenancy_required", "one@example.test"))
    assert result["person_removed"]
    for _ in range(2):
        web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        assert not person(web, "one@example.test")["managed"]
    engineer = next(
        p for p in store.head("fixture-org").people if p.email == "engineer@example.test"
    )
    assert engineer.ancestry == "resolved" and engineer.lob_id == "one"
    succeed(operate(web, "reonboard", "one@example.test"))
    assert person(web, "one@example.test")["managed"]
    reviews = web.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["data"]
    assert any(r["person_id"] == profile["id"] for r in reviews)
    create(web, "one@example.test", name="Re-onboarded manager")
    assert web.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["total"] == 0


# Zero recorded associations alone never silently offboard baseline employees.
def test_no_tenancy_rejects_existing_associations_and_zero_inventory_requires_confirmation(web):
    assert person(web, "engineer@example.test")["managed"]
    assert operate(web, "offboard_person").status_code == 422
    create(web)
    assert operate(web, "no_tenancy_required").status_code == 422
    assert person(web, "engineer@example.test")["managed"]
    result = succeed(
        operate(web, "offboard_person", "delegate@example.test", confirm_no_associations=True)
    )
    assert result["person_removed"]


# Incomplete, duplicated, cross-person and stale plans cannot mutate another association.
def test_plan_validation_and_stale_preview_preserve_registry(web):
    one = create(web)
    two = create(web, name="Second tenancy")
    before = registry(web)
    for plan in (
        [dict(association_id=one["id"], action="delete")],
        [dict(association_id=one["id"], action="delete")] * 2,
    ):
        assert operate(web, "offboard_person", plan=plan).status_code == 422
    assert len(person(web, "engineer@example.test")["associations"]) == 2
    context = clean_confirmation(web)
    succeed(operate(web, "update_tenancy", tenancy_id=one["tenancy_id"], name="Renamed tenancy"))
    response = web.post(
        "/api/local/tenancy-registry/operate",
        headers=JSON_HEADERS,
        json=dict(
            context=context,
            operation="delete_tenancy",
            person_id=before["people"][0]["id"],
            tenancy_id=two["tenancy_id"],
            reason="Stale action preview",
        ),
    )
    assert response.status_code == 409


# Transfers require an eligible owner; shared members prevent individual conversion.
def test_transfer_and_type_change_guards(web):
    shared = create(web, kind="shared", name="Guarded shared tenancy")
    succeed(operate(web, "join_shared", "two@example.test", tenancy_id=shared["tenancy_id"]))
    assert (
        operate(
            web, "update_tenancy", tenancy_id=shared["tenancy_id"], kind="individual"
        ).status_code
        == 422
    )
    assert (
        operate(
            web,
            "transfer_owner",
            tenancy_id=shared["tenancy_id"],
            owner_person_id=person(web, "engineer@example.test")["id"],
        ).status_code
        == 422
    )
    succeed(operate(web, "no_tenancy_required", "delegate@example.test"))
    assert (
        operate(
            web,
            "transfer_owner",
            tenancy_id=shared["tenancy_id"],
            owner_person_id=person(web, "delegate@example.test")["id"],
        ).status_code
        == 422
    )


# A late audit failure rolls back associations, directory state and publication.
def test_transaction_failure_rolls_back_registry_and_directory(store, web, monkeypatch):
    owned = create(web)
    before = clean_confirmation(web)
    original = store._audit

    # Inject failure after both registry and organization writes, before commit.
    def fail_audit(connection, workspace, kind, *args, **kwargs):
        if kind == "tenancy_registry_changed":
            raise RuntimeError("Registry audit failure")
        return original(connection, workspace, kind, *args, **kwargs)

    monkeypatch.setattr(store, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="Registry audit failure"):
        operate(web, "delete_tenancy", tenancy_id=owned["tenancy_id"])
    assert clean_confirmation(web) == before
    assert len(person(web, "engineer@example.test")["associations"]) == 1
    assert person(web, "engineer@example.test")["managed"]


# Name/email remapping retains the survivor's actual ownership and both membership IDs.
def test_identity_merge_preserves_individual_and_two_shared_mappings(store, web):
    create(web)
    for owner, name in [("one@example.test", "Team one"), ("two@example.test", "Team two")]:
        shared = create(web, owner, "shared", name)
        succeed(operate(web, "join_shared", tenancy_id=shared["tenancy_id"]))
    old = person(web, "engineer@example.test")
    rows = tuple(
        r.model_copy(update={"email": "renamed@example.test", "full_name": "Renamed Engineer"})
        if r.email == old["email"]
        else r
        for r in example_records()
    )
    web.post("/api/local/feeds", content=csv_bytes(rows), headers=HEADERS)
    case = web.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["data"][0]
    response = web.post(
        "/api/local/reviews/operate",
        headers=JSON_HEADERS,
        json=dict(
            context=clean_confirmation(web),
            case_id=case["id"],
            operation="merge",
            partner_email=old["email"],
            reason="Confirmed identity change",
        ),
    )
    assert response.status_code == 200, response.text
    merged = person(web, "renamed@example.test")
    assert merged["id"] == old["id"]
    assert {a["id"] for a in merged["associations"]} == {a["id"] for a in old["associations"]}


# Install historical simulator evidence without populating the new registry tables.
def seed_legacy_decisions(store, web, operations):
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

    from otm.organization.contracts import ReviewDecision

    identity = person(web, "engineer@example.test")
    context = clean_confirmation(web)
    config = store.configuration("fixture-org")
    changed = config.model_copy(
        update={
            "id": uuid4(),
            "review_decisions": tuple(
                ReviewDecision(
                    kind="TENANCY_SETUP_REVIEW",
                    target=identity["email"],
                    disposition="resolved",
                    operation=operation,
                    simulation="succeeded",
                    person_id=identity["id"],
                    recorded_at=datetime.now(UTC),
                    actor="local:tester",
                    reason="Legacy migration fixture",
                )
                for operation in operations
            ),
        }
    )
    store.update_configuration(
        changed,
        expected_version_id=UUID(context["applied_version_id"]),
        expected_proposed_id=UUID(context["proposed_version_id"]),
        expected_configuration_id=UUID(context["configuration_id"]),
        actor="local:tester",
        reason="Legacy migration fixture",
        observed_at=datetime.now(UTC),
    )


# Legacy shared membership keeps deterministic IDs and needs an explicit accountable owner.
def test_legacy_projection_is_read_only_and_assign_owner_bootstraps(store, web):
    from sqlalchemy import func, select

    seed_legacy_decisions(store, web, ["shared_membership"])
    first = registry(web)
    again = registry(web)
    assert first["tenancies"] == again["tenancies"]
    assert first["legacy_bootstrap_pending"] and first["warnings"]
    tenancy = first["tenancies"][0]
    assert tenancy["owner_person_id"] is None
    with store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(store.tables["tenancy"])) == 0
    assert (
        operate(web, "join_shared", "two@example.test", tenancy_id=tenancy["id"]).status_code == 422
    )
    succeed(operate(web, "assign_owner", tenancy_id=tenancy["id"]))
    current = registry(web)
    assert not current["legacy_bootstrap_pending"]
    assert current["tenancies"][0]["id"] == tenancy["id"]
    assert person(web, "engineer@example.test")["associations"][0]["role"] == "owner"
    succeed(operate(web, "join_shared", "two@example.test", tenancy_id=tenancy["id"]))


# An old deletion without a tenancy identifier cannot guess which owned tenancy to remove.
def test_legacy_ambiguous_deletion_preserves_all_known_associations(store, web):
    seed_legacy_decisions(store, web, ["create_tenancy", "import_tenancy", "delete_tenancy"])
    assert len(person(web, "engineer@example.test")["associations"]) == 2
    assert len(registry(web)["tenancies"]) == 2
    assert registry(web)["warnings"]


# A returning feed never silently changes the administrator's retained-outside decision.
def test_return_requires_presence_and_explicit_restoration(web):
    owned = create(web)
    missing(web)
    succeed(operate(web, "offboard_person", plan=[dict(association_id=owned["id"], action="keep")]))
    assert operate(web, "return_to_org").status_code == 422
    assert web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS).status_code == 200
    assert "Outside organization" in person(web, "engineer@example.test")["status"]
    assert operate(web, "create_tenancy", name="Premature onboarding").status_code == 422
    succeed(operate(web, "return_to_org"))
    assert person(web, "engineer@example.test")["status"] == "Managed"
    assert len(person(web, "engineer@example.test")["associations"]) == 1


# A real registry list supports name/owner/LOB search, paging and membership counts.
def test_tenancy_directory_lists_only_active_records_with_owner_rollups(web):
    assert web.get("/tenancies").status_code == 200
    assert web.get("/api/local/tenancies").json()["total"] == 0
    individual = create(web, name="Zulu personal")
    shared = create(web, "two@example.test", "shared", "Alpha shared")
    succeed(operate(web, "join_shared", tenancy_id=shared["tenancy_id"]))
    response = web.get("/api/local/tenancies?page_size=1").json()
    assert response["total"] == 2 and response["data"][0]["name"] == "Alpha shared"
    row = response["data"][0]
    assert row["owner_email"] == "two@example.test" and row["lob_name"] == "LOB Two"
    assert row["member_count"] == 2
    assert row["owner_person_id"] == person(web, "two@example.test")["id"]
    assert (
        web.get("/api/local/tenancies?page_size=1&page=2").json()["data"][0]["name"]
        == "Zulu personal"
    )
    for query in ("ALPHA", "Leader Two", "two@example.test", "LOB Two", "shared"):
        result = web.get("/api/local/tenancies", params={"query": query}).json()
        assert result["total"] == 1 and result["data"][0]["id"] == shared["tenancy_id"]
    assert web.get("/api/local/tenancies?lob=LOB%20One").json()["total"] == 1
    sorted_rows = web.get("/api/local/tenancies?sort=member_count&direction=desc").json()["data"]
    assert [row["member_count"] for row in sorted_rows] == [2, 1]
    assert web.get("/api/local/tenancies?query=does-not-exist").json()["total"] == 0
    assert web.get("/api/local/tenancies?page=9").json()["data"] == []
    succeed(operate(web, "delete_tenancy", tenancy_id=individual["tenancy_id"]))
    assert [row["id"] for row in web.get("/api/local/tenancies").json()["data"]] == [
        shared["tenancy_id"]
    ]


# Reorgs move tenancy LOB rollups through stable ownership; metadata edits refresh the list.
def test_tenancy_directory_rollup_follows_org_change_without_transferring_owner(web):
    owned = create(web)
    before = web.get("/api/local/tenancies").json()["data"][0]
    assert before["lob_name"] == "LOB One"
    rows = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    assert web.post("/api/local/feeds", content=csv_bytes(rows), headers=HEADERS).status_code == 200
    after = web.get("/api/local/tenancies").json()["data"][0]
    assert after["lob_name"] == "LOB Two" and after["owner_person_id"] == before["owner_person_id"]
    succeed(
        operate(
            web,
            "update_tenancy",
            tenancy_id=owned["tenancy_id"],
            name="Renamed shared",
            kind="shared",
        )
    )
    result = web.get("/api/local/tenancies?query=Renamed").json()["data"][0]
    assert result["kind"] == "shared" and result["id"] == owned["tenancy_id"]


# Ownerless legacy tenancies remain visible and invalid paging/sort controls are rejected.
def test_tenancy_directory_preserves_unknown_legacy_ownership_and_validates_controls(store, web):
    seed_legacy_decisions(store, web, ["shared_membership"])
    row = web.get("/api/local/tenancies").json()["data"][0]
    assert row["owner_person_id"] is None and row["owner_email"] is None
    assert row["lob_name"] is None and row["member_count"] == 1
    for params in ({"page": 0}, {"page_size": 101}, {"sort": "invalid"}, {"direction": "invalid"}):
        assert web.get("/api/local/tenancies", params=params).status_code == 422


# Repeated absence/delete/return episodes reopen onboarding without recreating old access.
def test_departed_deleted_employee_returns_as_fresh_onboarding_each_cycle(store, web):
    for cycle in range(2):
        owned = create(web, name=f"Cycle {cycle} tenancy")
        missing(web)
        succeed(operate(web, "delete_tenancy", tenancy_id=owned["tenancy_id"]))
        assert not person(web, "engineer@example.test")["managed"]
        for _ in range(2):
            assert (
                web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS).status_code
                == 200
            )
            current = person(web, "engineer@example.test")
            assert current["managed"] and current["onboarding_required"]
            assert current["association_count"] == 0
            reviews = web.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["data"]
            assert len(reviews) == 1 and reviews[0]["person_id"] == current["id"]
        assert store.configuration("fixture-org").pending_onboarding_person_ids
        # A later missing snapshot cannot erase the already-open return episode.
        missing(web)
        assert person(web, "engineer@example.test")["managed"]
        assert web.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["total"] == 1
        web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)


# A deliberate no-tenancy exclusion is not treated as completed employee offboarding.
def test_no_tenancy_exemption_survives_absence_and_return(web):
    succeed(operate(web, "no_tenancy_required"))
    missing(web)
    web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
    assert not person(web, "engineer@example.test")["managed"]
    assert web.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["total"] == 0


# A genuine qualified absence is required; repeated present snapshots do not undo cleanup.
def test_present_deletion_does_not_reonboard_on_unchanged_upload(web):
    owned = create(web)
    succeed(operate(web, "delete_tenancy", tenancy_id=owned["tenancy_id"]))
    web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
    assert not person(web, "engineer@example.test")["managed"]
    missing(web)
    web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
    assert person(web, "engineer@example.test")["onboarding_required"]


# Removing free-text UI fields preserves operation, actor and outcome evidence.
def test_ui_commands_can_omit_reason_but_history_keeps_action_facts(web):
    payload = dict(
        context=clean_confirmation(web),
        operation="create_tenancy",
        person_id=person(web, "engineer@example.test")["id"],
        name="No reason needed",
    )
    response = web.post("/api/local/tenancy-registry/operate", json=payload, headers=JSON_HEADERS)
    succeed(response)
    summary = web.get("/api/local/summary").json()
    assert summary["tenancies"] == {"total": 1, "individual": 1, "shared": 0, "unassigned_owner": 0}
    employee = web.get("/api/local/employees?sort=association_count&direction=desc").json()["data"][
        0
    ]
    assert employee["email"] == "engineer@example.test" and employee["association_count"] == 1
    assert web.get("/api/local/tenancies").json()["data"][0]["member_count"] == 1
    assert "Administrator selected create tenancy" in str(
        web.get("/api/local/exceptions?tab=informational").json()
    )


# Only applied qualified returns reopen onboarding; staging leaves the directory unchanged.
def test_partial_and_staged_return_do_not_publish_onboarding(store, web):
    from datetime import UTC, datetime

    from otm.organization.csv_feed import csv_envelope, parse_csv

    owned = create(web)
    missing(web)
    succeed(operate(web, "delete_tenancy", tenancy_id=owned["tenancy_id"]))
    assert (
        web.post(
            "/api/local/feeds?complete=false", content=csv_bytes(), headers=HEADERS
        ).status_code
        == 200
    )
    assert not person(web, "engineer@example.test")["managed"]
    now = datetime.now(UTC)
    delivery, digest = csv_envelope(store, "fixture-org", csv_bytes(), complete=True, now=now)
    identifier, matches = store.register(delivery, parse_csv(csv_bytes()), now, digest)
    assert matches
    staged = store.stage(identifier, now)
    assert staged.state == "staged"
    assert not person(web, "engineer@example.test")["managed"]
    store.apply(staged.proposed_version_id, now)
    assert person(web, "engineer@example.test")["onboarding_required"]


# A failed automatic return decision leaves the previous feed, exclusion and queue intact.
def test_return_onboarding_audit_failure_rolls_back_publication(store, web, monkeypatch):
    owned = create(web)
    missing(web)
    succeed(operate(web, "delete_tenancy", tenancy_id=owned["tenancy_id"]))
    context = clean_confirmation(web)
    original = store._audit

    # Reject the return decision before its encompassing publication can commit.
    def reject_configuration(connection, workspace, kind, *args, **kwargs):
        if kind == "configuration_changed":
            raise RuntimeError("Return audit unavailable")
        return original(connection, workspace, kind, *args, **kwargs)

    monkeypatch.setattr(store, "_audit", reject_configuration)
    with pytest.raises(RuntimeError, match="Return audit unavailable"):
        web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
    assert clean_confirmation(web)["applied_version_id"] == context["applied_version_id"]
    assert clean_confirmation(web)["configuration_id"] == context["configuration_id"]
    assert not person(web, "engineer@example.test")["managed"]


# Reason-free review commands retain the permanent exclusion and their audit history.
def test_informational_mapping_review_can_be_ignored_without_reason(web):
    rows = tuple(
        r.model_copy(
            update={
                "manager_email": "root@example.test",
                "reported_top_manager_email": "root@example.test",
            }
        )
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    web.post("/api/local/feeds", content=csv_bytes(rows), headers=HEADERS)
    reviews = web.get("/api/local/exceptions?kind=LOB_MAPPING_REVIEW").json()["data"]
    case = next(r for r in reviews if r["email"] == "engineer@example.test")
    result = web.post(
        "/api/local/reviews/operate",
        headers=JSON_HEADERS,
        json=dict(context=clean_confirmation(web), case_id=case["id"], operation="ignore"),
    )
    assert result.status_code == 200, result.text
    assert not any(
        r["email"] == "engineer@example.test"
        for r in web.get("/api/local/exceptions?kind=LOB_MAPPING_REVIEW").json()["data"]
    )


# Delayed cleanup retains departure evidence for the next verified return.
def test_delayed_offboarding_preserves_qualified_absence_for_return(web, monkeypatch):
    from datetime import UTC, datetime, timedelta

    owned = create(web)
    missing(web)

    # Advance administrator and subsequent feed receipt clocks beyond source freshness.
    class Clock(datetime):
        # Keep clock progression real while moving this scenario four days ahead.
        @classmethod
        def now(cls, tz=None):
            return (datetime.now(UTC) + timedelta(days=4)).astimezone(tz or UTC)

    monkeypatch.setattr("otm.organization.associations.datetime", Clock)
    monkeypatch.setattr("otm.organization.local_web.datetime", Clock)
    succeed(operate(web, "delete_tenancy", tenancy_id=owned["tenancy_id"]))
    assert not person(web, "engineer@example.test")["managed"]
    response = web.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
    assert response.status_code == 200, response.text
    assert person(web, "engineer@example.test")["onboarding_required"]
