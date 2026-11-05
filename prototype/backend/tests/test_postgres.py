"""PostgreSQL integration coverage for publication, immutable evidence and pinned reads."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from conftest import NOW, envelope, example_records, ingest
from fastapi.testclient import TestClient
from otm.organization.api import build_local_read_api
from otm.organization.reconcile import prepare
from otm.organization.store import PublicationConflict
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgres


# Read a prototype table row count without mutating test evidence.
def count(store, table):
    aliases = {"revision": "version", "state": "member", "receipt": "event"}
    target = store.tables[aliases.get(table, table)]
    statement = select(func.count()).select_from(target)
    if table == "revision":
        statement = statement.where(target.c.kind == "applied")
    elif table == "state":
        version = store.tables["version"]
        statement = statement.join(version, target.c.version_id == version.c.id).where(
            version.c.kind == "applied"
        )
    elif table in {"event", "receipt"}:
        statement = statement.where(
            target.c.kind == ("feed_received" if table == "receipt" else "organization_published")
        )
    with store.engine.connect() as connection:
        return connection.execute(statement).scalar_one()


# Verify duplicate receipts deduplicate publication while later equal-content captures
# refresh evidence.
def test_publication_duplicate_and_fresh_equal_content(store):
    first = ingest(store)
    assert first.state == "published"
    original = store.head("fixture-org")
    assert ingest(store).state == "duplicate"
    assert count(store, "revision") == 1 and count(store, "receipt") == 2
    later = ingest(store, key="later", capture=NOW + timedelta(hours=1))
    fresh = store.revision(later.revision_id)
    assert fresh.id != original.id
    assert [p.id for p in fresh.people] == [p.id for p in original.people]
    assert fresh.people[0].last_row_observed_at > original.people[0].last_row_observed_at
    assert store.revision(original.id) == original


# Verify reusing a snapshot ID for different content preserves the original head and records
# the receipt.
def test_snapshot_content_conflict_preserves_original(store):
    first = ingest(store)
    rows = list(example_records())
    rows[-1] = rows[-1].model_copy(update={"full_name": "Changed"})
    assert ingest(store, tuple(rows)).state == "integrity_conflict"
    assert store.head("fixture-org").id == first.revision_id
    assert count(store, "revision") == 1 and count(store, "receipt") == 2


# Verify partial updates, issue episode deduplication, recovery and recurrence without false
# absence.
def test_d17_partial_publication_alert_dedup_and_no_absence(store):
    ingest(store)
    rows = tuple(
        r
        for r in example_records()
        if r.email
        not in {
            "one@example.test",
            "engineer@example.test",
        }
    )
    rows = tuple(
        r.model_copy(update={"full_name": "Delegate Changed"})
        if r.email == "delegate@example.test"
        else r
        for r in rows
    )
    second = ingest(store, rows, "gap", NOW + timedelta(hours=1))
    result = store.revision(second.revision_id)
    assert not result.absence_eligible and result.assessed_coverage == "partial"
    assert not any(p.absence_review for p in result.people)
    assert (
        next(p for p in result.people if p.email == "delegate@example.test").full_name
        == "Delegate Changed"
    )
    alerts = count(store, "notification")
    assert alerts >= 1
    ingest(store, rows, "same-gap", NOW + timedelta(hours=2))
    assert count(store, "notification") == alerts
    ingest(store, key="recovered", capture=NOW + timedelta(hours=3))
    ingest(store, rows, "new-gap", NOW + timedelta(hours=4))
    assert count(store, "notification") > alerts


# Verify an interruption after intent creation rolls back the entire publication and can be
# retried.
def test_failure_rolls_back_state_audit_and_alert_intent(store, monkeypatch):
    ingest(store)
    old = store.head("fixture-org")
    before = {
        table: count(store, table)
        for table in ("revision", "state", "event", "notification", "person")
    }
    original = store._incidents

    # Inject a failure after incident writes to exercise publication transaction
    # rollback.
    def fail_after_intents(*args):
        original(*args)
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(store, "_incidents", fail_after_intents)
    rows = tuple(r for r in example_records() if r.email != "one@example.test")
    with pytest.raises(RuntimeError):
        ingest(store, rows, "crash", NOW + timedelta(hours=1))
    assert store.head("fixture-org") == old
    assert {table: count(store, table) for table in before} == before
    monkeypatch.setattr(store, "_incidents", original)
    assert ingest(store, rows, "crash", NOW + timedelta(hours=1)).state == "published"


# Verify stale prepared state cannot overwrite an intervening publication and recomputation
# succeeds.
def test_staged_conflict_requires_recompute(store):
    ingest(store)
    old = store.head("fixture-org")
    config = store.configuration("fixture-org")
    incoming = envelope("staged", NOW + timedelta(hours=2))
    sid, _ = store.register(incoming, example_records(), NOW + timedelta(hours=2))
    staged = prepare(example_records(), incoming, config, old, NOW + timedelta(hours=2))
    ingest(store, key="intervening", capture=NOW + timedelta(hours=1))
    with pytest.raises(PublicationConflict):
        store.publish(sid, staged)
    assert store.head("fixture-org").id != old.id
    assert store.ingest(example_records(), incoming, NOW + timedelta(hours=2)).state == "published"


# Verify fatal graph and superseded-capture results leave the trusted publication pointer
# unchanged.
def test_rejected_and_stale_feeds_preserve_head(store):
    ingest(store)
    old = store.head("fixture-org")
    rows = list(example_records())
    rows[1] = rows[1].model_copy(update={"manager_email": "engineer@example.test"})
    assert ingest(store, tuple(rows), "cycle", NOW + timedelta(hours=1)).state == "rejected"
    assert ingest(store, key="old", capture=NOW - timedelta(hours=1)).state == "superseded"
    assert store.head("fixture-org") == old


# Verify SQL triggers reject edits to published revision, state, audit and notification
# evidence.
@pytest.mark.parametrize("table", ["revision", "state", "event", "notification"])
def test_immutable_published_content(store, table):
    ingest(store, example_records()[:-1], "first")
    if table == "notification":
        ingest(store, example_records()[:-2], "gap", NOW + timedelta(hours=1))
    target = store.tables[{"revision": "version", "state": "member"}.get(table, table)]
    assert count(store, table) > 0
    with pytest.raises(DBAPIError), store.engine.begin() as connection:
        column = target.c.data if "data" in target.c else target.c.state
        connection.execute(
            update(target).values({column: {} if column.name == "data" else "changed"})
        )


# Verify list/detail reads remain pinned across reorgs and validate revision/page bounds.
def test_pinned_read_api_and_unknown_revision(store):
    first = ingest(store)
    client = TestClient(build_local_read_api(store, "fixture-org", allow_local_prototype=True))
    first_page = client.get(
        "/api/v1/organization/people",
        params={
            "revision_id": str(first.revision_id),
            "page_size": 2,
        },
    )
    assert first_page.status_code == 200
    pinned = first_page.json()
    engineer_id = next(
        p.id for p in store.revision(first.revision_id).people if p.email == "engineer@example.test"
    )
    changed = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    second = ingest(store, changed, "reorg", NOW + timedelta(hours=1))
    assert client.get("/api/v1/organization/head").json()["organization_revision_id"] == str(
        second.revision_id
    )
    assert (
        client.get(
            "/api/v1/organization/people",
            params={
                "revision_id": str(first.revision_id),
                "page_size": 2,
            },
        ).json()
        == pinned
    )
    path = f"/api/v1/organization/people/{engineer_id}"
    assert (
        client.get(path, params={"revision_id": str(first.revision_id)}).json()["data"]["lob_id"]
        == "one"
    )
    assert (
        client.get(path, params={"revision_id": str(second.revision_id)}).json()["data"]["lob_id"]
        == "two"
    )
    unknown = client.get("/api/v1/organization/people", params={"revision_id": str(uuid4())})
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "REVISION_NOT_FOUND"
    assert client.get("/api/v1/organization/people").status_code == 422
    assert (
        client.get(
            "/api/v1/organization/people",
            params={
                "revision_id": str(first.revision_id),
                "page_size": 1000,
            },
        ).status_code
        == 422
    )
    assert "PeoplePage" in client.get("/openapi.json").json()["components"]["schemas"]


# Verify racing candidates serialize, the loser rebuilds and newest qualified capture
# wins.
def test_competing_publications_then_rebuild_keep_newest_capture(store):
    ingest(store)
    old = store.head("fixture-org")
    config = store.configuration("fixture-org")
    incoming = [
        envelope("parallel-" + str(index), NOW + timedelta(hours=index)) for index in (1, 2)
    ]
    work = []
    for item in incoming:
        snapshot_id, _ = store.register(item, example_records(), item.captured_at)
        work.append((snapshot_id, prepare(example_records(), item, config, old, item.captured_at)))
    barrier = Barrier(2)

    # Synchronize two test publishers and report the expected optimistic publication
    # conflict.
    def publish(item):
        barrier.wait(timeout=10)
        try:
            return store.publish(*item).state
        except PublicationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(publish, work)) == ["conflict", "published"]
    for item in incoming:
        store.ingest(example_records(), item, NOW + timedelta(hours=3))
    assert store.head("fixture-org").source_captured_at == NOW + timedelta(hours=2)


# Verify a sealed revision cannot acquire person states after publication.
def test_sealed_revision_rejects_late_state_insert(store):
    first = ingest(store)
    target = store.tables["member"]
    with store.engine.connect() as connection:
        existing = dict(connection.execute(select(target)).mappings().first())
    with pytest.raises(DBAPIError, match="published revision is sealed"):
        with store.engine.begin() as connection:
            connection.execute(target.insert().values(**existing))
    assert store.head("fixture-org").id == first.revision_id


# Verify global manager identity alone cannot satisfy the same-revision relationship
# constraint.
def test_manager_foreign_key_is_revision_scoped(store):
    first = ingest(store)
    previous = store.revision(first.revision_id)
    states = {p.email: p for p in previous.people}
    new_id = str(uuid4())
    with pytest.raises(DBAPIError, match="manager_same_revision"):
        with store.engine.begin() as connection:
            connection.execute(
                store.tables["version"]
                .insert()
                .values(
                    id=new_id,
                    workspace_id=previous.population_id,
                    kind="applied",
                    base_version_id=str(previous.id),
                    feed_id=str(previous.snapshot_id),
                    configuration=store.configuration(previous.population_id).model_dump(
                        mode="json"
                    ),
                    configuration_id=str(previous.configuration_id),
                    data=previous.model_dump(mode="json", exclude={"people"}),
                )
            )
            engineer = states["engineer@example.test"]
            # Manager identity exists globally, but has no row in this new revision.
            connection.execute(
                store.tables["member"]
                .insert()
                .values(
                    version_id=new_id,
                    person_id=str(engineer.id),
                    profile="employee",
                    evidence="feed_row",
                    full_name=engineer.full_name,
                    manager_email=engineer.manager_email,
                    designee_emails=[],
                    ancestry=engineer.ancestry,
                    absence_review=False,
                    email=engineer.email,
                    manager_person_id=str(states["one@example.test"].id),
                    data=engineer.model_dump(mode="json"),
                )
            )
    assert count(store, "revision") == 1
