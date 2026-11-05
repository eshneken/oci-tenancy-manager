"""CSV intake and browser API journeys with isolated PostgreSQL organization state."""

import csv
from io import StringIO
from pathlib import Path

import pytest
from conftest import NOW, envelope, example_config, example_records
from fastapi.testclient import TestClient
from otm.organization.csv_feed import CsvFeedError, parse_csv
from otm.organization.local_web import build_local_web
from otm.organization.reconcile import prepare
from sqlalchemy import select

HEADERS = {"content-type": "text/csv", "x-otm-local": "csv-upload"}
JSON_HEADERS = {"content-type": "application/json", "x-otm-local": "csv-upload"}


# Serialize fictional rows with no employee ID, retaining the exact supported CSV headings.
def csv_bytes(records=None):
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["EMPLOYEE_FULL_NAME", "EMAIL", "MGR", "TOP_MGR"])
    for record in records if records is not None else example_records():
        writer.writerow(
            [
                record.full_name,
                record.email,
                record.manager_email or "",
                record.reported_top_manager_email or "",
            ]
        )
    return stream.getvalue().encode()


# CSV quoting, BOM, normalized emails and absent optional manager hints remain lossless.
def test_csv_quotes_unicode_and_email_identity():
    content = (
        "\ufeffEMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\r\n"
        '"Élodie, Example", ELODIE@EXAMPLE.TEST ,boss@example.test,\r\n'
    )
    rows = parse_csv(content.encode())
    assert rows[0].full_name == "Élodie, Example"
    assert rows[0].source_record_id == "email:elodie@example.test"
    assert rows[0].reported_top_manager_email is None


# Malformed, empty, oversized and ambiguous inputs cannot become absence evidence.
@pytest.mark.parametrize(
    "content",
    [
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n",
        b"EMPLOYEE_FULL_NAME,EMAIL,EMAIL,TOP_MGR\nx,a@example.test,b@example.test,\n",
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nx,not-email,,\n",
        b"EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nx,a@example.test,,,extra\n",
        b'EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n"unterminated',
        b"\xff\xfe",
        b"\0",
        b"x" * (2 * 1024 * 1024 + 1),
    ],
)
def test_csv_rejects_unsafe_source_shapes(content):
    with pytest.raises(CsvFeedError):
        parse_csv(content)


# Repeated identities cannot be silently deduplicated into a smaller apparent census.
def test_csv_duplicate_normalized_email_rejected():
    with pytest.raises(CsvFeedError, match="Duplicate employee"):
        parse_csv(csv_bytes((example_records()[0], example_records()[0])))


# Honor the root-profile exemption without weakening missing-manager census gates.
def test_configured_boundary_can_be_omitted_but_other_managers_cannot():
    config = example_config(required_root_profile=False)
    rows = example_records()[1:]
    candidate = prepare(rows, envelope(), config, None, NOW)
    assert candidate.absence_eligible
    missing = prepare(rows[1:], envelope(), config, None, NOW)
    assert not missing.absence_eligible
    assert any(d.code == "MANAGER_PROFILE_MISSING" for d in missing.diagnostics)


# Conflicting top managers create review evidence while manager paths determine the LOB.
def test_top_manager_hint_is_checked_without_overriding_graph():
    rows = tuple(
        r.model_copy(update={"reported_top_manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    candidate = prepare(rows, envelope(), example_config(), None, NOW)
    assert ("TOP_MANAGER_MISMATCH", "engineer@example.test") in candidate.issues
    assert next(p for p in candidate.people if p.email == "engineer@example.test").lob_id == "one"
    leader_rows = tuple(
        r.model_copy(update={"reported_top_manager_email": "root@example.test"})
        if r.email == "one@example.test"
        else r
        for r in example_records()
    )
    leader = prepare(leader_rows, envelope(), example_config(), None, NOW)
    assert not any(kind == "TOP_MANAGER_MISMATCH" for kind, _ in leader.issues)


# Identical uploads publish distinct observations and retain canonical JSON evidence.
@pytest.mark.postgres
def test_web_each_upload_is_a_new_snapshot_with_canonical_storage(store):
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/exceptions").status_code == 200
        assert client.get("/api/local/summary").json()["employees"] == 0
        result = client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        assert result.status_code == 200
        assert result.json()["outcome"]["state"] == "published"
        summary = client.get("/api/local/summary").json()
        assert summary["employees"] == 5 and summary["exceptions"] == 0
        assert summary["absence_eligible"]
        page = client.get(
            "/api/local/employees?page_size=2&page=2&sort=email&direction=desc"
        ).json()
        assert len(page["data"]) == 2 and page["total"] == 5
        assert client.get("/api/local/employees?query=Engineer").json()["total"] == 1
        assert client.get("/api/local/employees?lob=LOB%20One").json()["total"] == 3
        repeat = client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS).json()
        assert repeat["outcome"]["state"] == "published"
        after = client.get("/api/local/summary").json()
        assert after["revision_id"] != summary["revision_id"]
        assert repeat["outcome"]["snapshot_id"] != result.json()["outcome"]["snapshot_id"]
        with store.engine.connect() as connection:
            feeds = connection.execute(select(store.tables["feed"].c.data)).scalars().all()
        assert len(feeds) == 2
        assert feeds[0]["records"] == feeds[1]["records"]
        assert feeds[0]["records"][0]["source_record_id"].startswith("email:")
        assert (
            feeds[0]["envelope"]["external_snapshot_id"]
            != feeds[1]["envelope"]["external_snapshot_id"]
        )
        assert not any(
            row["kind"] == "METADATA_UPDATED"
            for row in client.get("/api/local/exceptions?tab=informational").json()["data"]
        )


# Metadata applies, arrivals/absences become visible reviews, and partial omission is safe.
@pytest.mark.postgres
def test_web_reorg_add_absence_and_partial_do_not_delete(store):
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        original_id = store.head("fixture-org").people[-1].id
        rows = tuple(
            r.model_copy(
                update={"full_name": "Updated Engineer", "manager_email": "two@example.test"}
            )
            if r.email == "engineer@example.test"
            else r
            for r in example_records()
        )
        new = rows[-1].model_copy(update={"email": "new@example.test", "full_name": "New Engineer"})
        result = client.post("/api/local/feeds", content=csv_bytes(rows + (new,)), headers=HEADERS)
        assert result.json()["outcome"]["state"] == "published"
        engineer = client.get("/api/local/employees?query=Updated%20Engineer").json()["data"][0]
        assert engineer["lob_name"] == "LOB Two"
        reviews = client.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()
        assert reviews["total"] == 1 and reviews["data"][0]["email"] == "new@example.test"
        absent = tuple(r for r in rows if r.email != "engineer@example.test") + (new,)
        client.post("/api/local/feeds?complete=false", content=csv_bytes(absent), headers=HEADERS)
        assert client.get("/api/local/summary").json()["absences"] == 0
        client.post("/api/local/feeds?complete=true", content=csv_bytes(absent), headers=HEADERS)
        assert client.get("/api/local/summary").json()["absences"] == 1
        assert client.get("/api/local/employees").json()["total"] == 6
        assert client.get("/api/local/exceptions?kind=PERSON_ABSENCE_REVIEW").json()["total"] == 1
        # An intentional upload of earlier contents is now a fresh authoritative observation.
        current = store.head("fixture-org").id
        result = client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        assert result.json()["outcome"]["state"] == "published"
        assert store.head("fixture-org").id != current
        reverted = next(
            p for p in store.head("fixture-org").people if p.email == "engineer@example.test"
        )
        assert reverted.full_name == "Engineer" and reverted.manager_email == "one@example.test"
        assert original_id in {p.id for p in store.head("fixture-org").people}


# Reject invalid input, cycles and remote writes without publishing organization state.
@pytest.mark.postgres
def test_web_invalid_feed_and_cross_origin_write_preserve_state(store):
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        assert (
            client.post(
                "/api/local/feeds", content=csv_bytes(), headers={"content-type": "text/csv"}
            ).status_code
            == 403
        )
        headers = {**HEADERS, "origin": "https://untrusted.example"}
        assert (
            client.post("/api/local/feeds", content=csv_bytes(), headers=headers).status_code == 403
        )
        assert client.get("/", headers={"host": "untrusted.example"}).status_code == 400
        assert client.post("/api/local/feeds", content=b"bad", headers=HEADERS).status_code == 422
        assert store.head("fixture-org") is None
        cycle = tuple(
            r.model_copy(update={"manager_email": "engineer@example.test"})
            if r.email == "one@example.test"
            else r
            for r in example_records()
        )
        result = client.post("/api/local/feeds", content=csv_bytes(cycle), headers=HEADERS).json()
        assert result["outcome"]["state"] == "rejected"
        assert store.head("fixture-org") is None
        assert client.get("/static/app.js").headers["x-content-type-options"] == "nosniff"


# Use trusted source names and honest email fallback instead of a team-specific root label.
@pytest.mark.postgres
@pytest.mark.parametrize("root_present", [True, False])
def test_directory_uses_observed_root_name_or_email(store, root_present):
    records = example_records() if root_present else example_records()[1:]
    outcome = store.ingest(records, envelope(), NOW)
    assert outcome.state == "published"
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        data = client.get("/api/local/employees").json()["data"]
    leader = next(row for row in data if row["email"] == "one@example.test")
    assert leader["manager_name"] == ("Root" if root_present else "root@example.test")


# Read an invented realistic-size CSV without depending on private HR data or cwd.
def test_synthetic_csv_is_readable_and_has_expected_profiles():
    source = Path(__file__).with_name("fixtures") / "synthetic_organization.csv"
    rows = parse_csv(source.read_bytes())
    assert len(rows) == 242
    assert len({r.email for r in rows}) == 242
    assert all(r.email.endswith("@example.test") for r in rows)
    engineer = next(r for r in rows if r.email == "engineer-0001@example.test")
    assert engineer.full_name == "Example Engineer 0001"
    assert engineer.manager_email == "manager-01-01@example.test"
    assert engineer.reported_top_manager_email == "leader-platform@example.test"
    assert next(r for r in rows if r.email == "org-root@example.test").manager_email is None


# Provide an isolated reset-enabled CSV lab alongside the unrelated fixture workspace.
@pytest.fixture
def reset_lab(store):
    from uuid import uuid4

    original = example_config()
    config = original.model_copy(
        update={
            "id": uuid4(),
            "policy": original.policy.model_copy(
                update={
                    "population_id": "ui-test-reset",
                    "source_id": "local-csv-demo",
                }
            ),
        }
    )
    store.configure_initial(config)
    return build_local_web(
        store, "ui-test-reset", allow_local_prototype=True, allow_clean_workspace=True
    )


# Copy only expected-context fields from the same summary used by the confirmation UI.
def clean_confirmation(client):
    context = client.get("/api/local/summary").json()["context"]
    return {
        field: context[field]
        for field in (
            "workspace_id",
            "applied_version_id",
            "proposed_version_id",
            "configuration_id",
        )
    }


# A clean creates a fresh baseline, retains evidence/config and survives server recreation.
@pytest.mark.postgres
def test_clean_archives_run_preserves_settings_and_reloads_identical_csv(store, reset_lab):
    from sqlalchemy import func

    with TestClient(reset_lab) as client:
        client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        previous = clean_confirmation(client)
        config = store.configuration(previous["workspace_id"])
        with store.engine.connect() as connection:
            counts = {
                key: connection.scalar(select(func.count()).select_from(store.tables[key]))
                for key in ("feed", "version", "member", "recommendation", "notification", "person")
            }
        result = client.post("/api/local/workspace/clean", json=previous, headers=JSON_HEADERS)
        assert result.status_code == 200 and result.json()["history_preserved"]
        summary = client.get("/api/local/summary").json()
        assert summary["employees"] == summary["exceptions"] == 0
        assert summary["workspace_id"] != previous["workspace_id"]
        assert summary["revision_id"] is None
        assert store.head(previous["workspace_id"]) is not None
        assert store.head("fixture-org") is None
        assert store.configuration(summary["workspace_id"]).lobs == config.lobs
        assert client.get("/api/local/exceptions").json()["total"] == 0
        with store.engine.connect() as connection:
            after = {
                key: connection.scalar(select(func.count()).select_from(store.tables[key]))
                for key in counts
            }
        assert after == counts
        # Same bytes must publish into the new run instead of replaying the archived baseline.
        repeat = client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        assert repeat.json()["outcome"]["state"] == "published"
        assert client.get("/api/local/summary").json()["new_employees"] == 0
        active = summary["workspace_id"]
    restarted = build_local_web(
        store, "ui-test-reset", allow_local_prototype=True, allow_clean_workspace=True
    )
    with TestClient(restarted) as client:
        summary = client.get("/api/local/summary").json()
        assert summary["workspace_id"] == active and summary["employees"] == 5


# Changed feeds and prior tabs cannot clean or import into a run the user did not confirm.
@pytest.mark.postgres
def test_clean_detects_stale_confirmations_tabs_and_disabled_workspaces(store, reset_lab):
    with TestClient(reset_lab) as client:
        empty = clean_confirmation(client)
        client.post("/api/local/feeds", content=csv_bytes(), headers=HEADERS)
        assert (
            client.post("/api/local/workspace/clean", json=empty, headers=JSON_HEADERS).status_code
            == 409
        )
        current = clean_confirmation(client)
        assert (
            client.post(
                "/api/local/workspace/clean", json=current, headers=JSON_HEADERS
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/local/workspace/clean", json=current, headers=JSON_HEADERS
            ).status_code
            == 409
        )
        stale_headers = {**HEADERS, "x-otm-workspace": current["workspace_id"]}
        assert (
            client.post("/api/local/feeds", content=csv_bytes(), headers=stale_headers).status_code
            == 409
        )
        assert client.get("/api/local/summary").json()["employees"] == 0
        assert (
            client.post("/api/local/workspace/clean", json=clean_confirmation(client)).status_code
            == 403
        )
    fixed = build_local_web(store, "fixture-org", allow_local_prototype=True)
    with TestClient(fixed) as client:
        assert client.get("/api/local/summary").json()["can_clean_workspace"] is False
        assert (
            client.post(
                "/api/local/workspace/clean", json=clean_confirmation(client), headers=JSON_HEADERS
            ).status_code
            == 403
        )


# Serialize duplicate confirmations so only one fresh run can replace the visible lab.
@pytest.mark.postgres
def test_concurrent_clean_confirmation_starts_only_one_run(store, reset_lab):
    from concurrent.futures import ThreadPoolExecutor

    with TestClient(reset_lab) as client:
        expected = clean_confirmation(client)

        # Submit the same already-confirmed context through an independent HTTP client.
        def clean_once():
            with TestClient(reset_lab) as other:
                return other.post(
                    "/api/local/workspace/clean", json=expected, headers=JSON_HEADERS
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as workers:
            statuses = list(workers.map(lambda _: clean_once(), range(2)))
        assert sorted(statuses) == [200, 409]
        assert client.get("/api/local/summary").json()["employees"] == 0


# An audit failure cannot leave a newly configured but unaudited active test run.
@pytest.mark.postgres
def test_clean_rolls_back_if_archive_audit_cannot_be_written(store, reset_lab, monkeypatch):
    from sqlalchemy import func

    with TestClient(reset_lab, raise_server_exceptions=False) as client:
        expected = clean_confirmation(client)
        with store.engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(store.tables["workspace"]))
        original = store._audit

        # Fail precisely the reset event after the new workspace insert in the transaction.
        def fail_reset_audit(*args, **kwargs):
            if args[2] == "local_lab_cleaned":
                raise RuntimeError("simulated archive audit failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "_audit", fail_reset_audit)
        response = client.post("/api/local/workspace/clean", json=expected, headers=JSON_HEADERS)
        assert response.status_code == 500
        assert clean_confirmation(client) == expected
        with store.engine.connect() as connection:
            assert (
                connection.scalar(select(func.count()).select_from(store.tables["workspace"]))
                == count
            )


# Mario's add/onboard/remove scenario must evaluate an exact previously uploaded CSV anew.
@pytest.mark.postgres
@pytest.mark.parametrize("onboard", [False, True])
def test_reuploading_original_csv_detects_later_employee_absence(store, onboard):
    with TestClient(build_local_web(store, "fixture-org", allow_local_prototype=True)) as client:
        baseline = csv_bytes()
        first = client.post("/api/local/feeds", content=baseline, headers=HEADERS).json()
        mario = example_records()[-1].model_copy(
            update={"email": "mario.brother@example.test", "full_name": "Mario Brother"}
        )
        added = client.post(
            "/api/local/feeds", content=csv_bytes(example_records() + (mario,)), headers=HEADERS
        ).json()
        assert added["outcome"]["state"] == "published"
        if onboard:
            case = client.get("/api/local/exceptions?kind=TENANCY_SETUP_REVIEW").json()["data"][0]
            response = client.post(
                "/api/local/reviews/operate",
                headers=JSON_HEADERS,
                json={
                    "context": clean_confirmation(client),
                    "case_id": case["id"],
                    "operation": "import_tenancy",
                    "reason": "Verified simulated onboarding",
                },
            )
            assert response.status_code == 200 and response.json()["simulated"]
        removed = client.post("/api/local/feeds", content=baseline, headers=HEADERS).json()
        assert removed["outcome"]["state"] == "published"
        assert removed["outcome"]["snapshot_id"] != first["outcome"]["snapshot_id"]
        reviews = client.get("/api/local/exceptions?kind=PERSON_ABSENCE_REVIEW").json()["data"]
        assert len(reviews) == 1 and reviews[0]["email"] == mario.email
        repeated = client.post("/api/local/feeds", content=baseline, headers=HEADERS).json()
        assert repeated["outcome"]["state"] == "published"
        current = client.get("/api/local/exceptions?kind=PERSON_ABSENCE_REVIEW").json()["data"]
        assert len(current) == 1 and current[0]["id"] == reviews[0]["id"]
