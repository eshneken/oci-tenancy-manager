"""Applied/proposed/reconciliation journeys, corrections and provenance regression coverage."""

from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import NOW, envelope, example_records, ingest
from fastapi.testclient import TestClient
from otm.organization.api import build_local_read_api
from otm.organization.contracts import PersonOverride, ReviewDecision
from otm.organization.reconcile import prepare
from otm.organization.review_rules import issue_basis
from otm.organization.store import PublicationConflict
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.postgres


# Return a source capture with one changed person and otherwise identical evidence.
def change_name(name="Renamed Engineer"):
    return tuple(
        row.model_copy(update={"full_name": name}) if row.email == "engineer@example.test" else row
        for row in example_records()
    )


# Find a readable SQL-view person by its normalized identity.
def person(rows, address="engineer@example.test"):
    return next(row for row in rows if row["email"] == address)


# Submit a trusted correction with frozen current preview and provenance.
def correct(store, values, *, now=NOW + timedelta(hours=1), old=None):
    config = old or store.configuration("fixture-org")
    updated = config.model_copy(
        update={
            "id": uuid4(),
            "overrides": (
                PersonOverride(
                    email="engineer@example.test",
                    values=values,
                    actor="local:tester",
                    reason="Verified correction",
                ),
            ),
        }
    )
    return store.update_configuration(
        updated,
        expected_version_id=store.head("fixture-org").id,
        expected_configuration_id=config.id,
        expected_proposed_id=store.proposed("fixture-org").id,
        actor="local:tester",
        reason="Verified correction",
        observed_at=now,
    )


# Persist an inspectable proposal and delta while applied state remains unchanged
# until apply.
def test_stage_inspect_then_apply_and_keep_history(store):
    first = ingest(store)
    feed_id, _ = store.register(
        envelope("rename", NOW + timedelta(hours=1)), change_name(), NOW + timedelta(hours=1)
    )
    staged = store.stage(feed_id, NOW + timedelta(hours=1))
    assert staged.state == "staged"
    assert store.head("fixture-org").id == first.revision_id
    assert (
        person(store.inspection_rows("current_organization", "fixture-org"))["full_name"]
        == "Engineer"
    )
    assert (
        person(store.inspection_rows("proposed_organization", "fixture-org"))["full_name"]
        == "Renamed Engineer"
    )
    rows = store.inspection_rows("organization_reconciliation", "fixture-org")
    delta = next(row for row in rows if row["field"] == "full_name" and row["status"] == "ready")
    assert (delta["before_value"], delta["after_value"]) == ("Engineer", "Renamed Engineer")
    result = store.apply(staged.proposed_version_id, NOW + timedelta(hours=1, minutes=1))
    assert (
        person(store.inspection_rows("current_organization", "fixture-org"))["full_name"]
        == "Renamed Engineer"
    )
    assert (
        next(
            p
            for p in store.revision(first.revision_id).people
            if p.email == "engineer@example.test"
        ).full_name
        == "Engineer"
    )
    assert (
        store.apply(staged.proposed_version_id, NOW + timedelta(hours=1, minutes=2)).revision_id
        == result.revision_id
    )


# A fresh proposal invalidates an old preview and replaces pending metadata
# recommendations.
def test_newer_proposal_supersedes_pending_metadata_and_blocks_old_apply(store):
    ingest(store)
    first_id, _ = store.register(
        envelope("first-new", NOW + timedelta(hours=1)),
        change_name("First"),
        NOW + timedelta(hours=1),
    )
    first = store.stage(first_id, NOW + timedelta(hours=1))
    second_id, _ = store.register(
        envelope("second-new", NOW + timedelta(hours=2)),
        change_name("Second"),
        NOW + timedelta(hours=2),
    )
    second = store.stage(second_id, NOW + timedelta(hours=2))
    with pytest.raises(PublicationConflict):
        store.apply(first.proposed_version_id, NOW + timedelta(hours=2))
    deltas = store.inspection_rows("organization_reconciliation", "fixture-org")
    assert any(row["status"] == "superseded" and row["after_value"] == "First" for row in deltas)
    assert any(row["status"] == "ready" and row["after_value"] == "Second" for row in deltas)
    store.apply(second.proposed_version_id, NOW + timedelta(hours=2))


# Reject stale/cyclic input without replacing either usable current view.
def test_invalid_and_out_of_order_feed_preserve_both_views(store):
    ingest(store)
    new_id, _ = store.register(
        envelope("newer", NOW + timedelta(hours=2)), change_name("Newest"), NOW + timedelta(hours=2)
    )
    store.stage(new_id, NOW + timedelta(hours=2))
    proposal = store.proposed("fixture-org").id
    applied = store.head("fixture-org").id
    assert ingest(store, change_name("Old"), "old", NOW + timedelta(hours=1)).state == "superseded"
    bad = tuple(
        row.model_copy(update={"manager_email": "engineer@example.test"})
        if row.email == "one@example.test"
        else row
        for row in example_records()
    )
    assert ingest(store, bad, "cyclic", NOW + timedelta(hours=3)).state == "rejected"
    assert store.proposed("fixture-org").id == proposal
    assert store.head("fixture-org").id == applied


# Close the audit reproduction: different input cannot be published under a recorded
# feed.
def test_source_candidate_mismatch_is_rejected(store):
    feed_id, _ = store.register(envelope("recorded"), example_records(), NOW)
    candidate = prepare(
        change_name("Wrong source"),
        envelope("other"),
        store.configuration("fixture-org"),
        None,
        NOW,
    )
    with pytest.raises(ValueError, match="registered source"):
        store.publish(feed_id, candidate)
    assert store.head("fixture-org") is None and store.proposed("fixture-org") is None


# Apply a manager correction without a new feed and retain it when later source data
# disagrees.
def test_same_feed_admin_override_persists_and_shows_conflict(store):
    first = ingest(store)
    correction = correct(store, {"manager_email": "two@example.test"})
    current = person(store.inspection_rows("current_organization", "fixture-org"))
    proposed = person(store.inspection_rows("proposed_organization", "fixture-org"))
    assert current["manager_email"] == "two@example.test" and current["lob_id"] == "two"
    assert proposed["manager_email"] == "one@example.test"
    assert correction.snapshot_id == first.snapshot_id
    pending = store.inspection_rows("pending_organization_reviews", "fixture-org")
    assert any(row["kind"] == "OVERRIDE_CONFLICT" for row in pending)
    intent_count = len(pending)
    ingest(store, key="next", capture=NOW + timedelta(hours=2))
    assert (
        person(store.inspection_rows("current_organization", "fixture-org"))["manager_email"]
        == "two@example.test"
    )
    assert len(store.inspection_rows("pending_organization_reviews", "fixture-org")) == intent_count
    with store.engine.connect() as connection:
        assert len(connection.execute(select(store.tables["notification"])).all()) == 1
        assert (
            connection.execute(
                select(store.tables["event"].c.actor).where(
                    store.tables["event"].c.kind == "configuration_changed"
                )
            ).scalar_one()
            == "local:tester"
        )


# Source convergence still needs explicit closure; later disagreement alerts anew.
def test_override_conflict_resolves_and_recurrence_starts_new_episode(store):
    ingest(store)
    correct(store, {"full_name": "Correct Name"})
    ingest(store, change_name("Correct Name"), "converged", NOW + timedelta(hours=2))
    pending = store.inspection_rows("pending_organization_reviews", "fixture-org")[0]
    config = store.configuration("fixture-org")
    at = NOW + timedelta(hours=2, minutes=1)
    decision = ReviewDecision(
        kind=pending["kind"],
        target=pending["target"],
        disposition="resolved",
        basis=issue_basis(pending["kind"], pending["target"], store.head("fixture-org").people),
        recorded_at=at,
        actor="local:tester",
        reason="Confirmed corrected source",
    )
    store.update_configuration(
        config.model_copy(update={"id": uuid4(), "review_decisions": (decision,)}),
        expected_version_id=store.head("fixture-org").id,
        expected_proposed_id=store.proposed("fixture-org").id,
        expected_configuration_id=config.id,
        actor="local:tester",
        reason=decision.reason,
        observed_at=at,
    )
    assert not store.inspection_rows("pending_organization_reviews", "fixture-org")
    ingest(store, key="conflict-again", capture=NOW + timedelta(hours=3))
    assert len(store.inspection_rows("pending_organization_reviews", "fixture-org")) == 1
    with store.engine.connect() as connection:
        assert len(connection.execute(select(store.tables["notification"])).all()) == 2


# An override introducing a cycle cannot partially update configuration or applied/proposed
# state.
def test_bad_admin_correction_rolls_back_settings_views_and_audit(store):
    ingest(store)
    before = store.configuration("fixture-org")
    applied, proposed = store.head("fixture-org").id, store.proposed("fixture-org").id
    with pytest.raises(ValueError, match="eligible organization"):
        correct(store, {"manager_email": "engineer@example.test"})
    assert store.configuration("fixture-org") == before
    assert store.head("fixture-org").id == applied and store.proposed("fixture-org").id == proposed
    with store.engine.connect() as connection:
        assert not connection.execute(
            select(store.tables["event"]).where(
                store.tables["event"].c.kind == "configuration_changed"
            )
        ).all()


# Reject corrections prepared before a new publication or trusted-settings generation.
def test_stale_admin_preview_cannot_overwrite_newer_feed(store):
    ingest(store)
    old_config = store.configuration("fixture-org")
    old_applied, old_proposed = store.head("fixture-org").id, store.proposed("fixture-org").id
    ingest(store, key="new-head", capture=NOW + timedelta(hours=1))
    updated = old_config.model_copy(update={"id": uuid4()})
    with pytest.raises(PublicationConflict):
        store.update_configuration(
            updated,
            expected_version_id=old_applied,
            expected_configuration_id=old_config.id,
            expected_proposed_id=old_proposed,
            actor="local:tester",
            reason="Stale preview",
            observed_at=NOW + timedelta(hours=1),
        )


# An admin can acknowledge qualified absence while identity and its last manager are
# retained.
def test_acknowledgment_is_audited_without_fabricating_resolution(store):
    ingest(store)
    rows = tuple(row for row in example_records() if row.email != "engineer@example.test")
    ingest(store, rows, "absent", NOW + timedelta(hours=1))
    pending = store.inspection_rows("pending_organization_reviews", "fixture-org")
    recommendation = next(row for row in pending if row["kind"] == "PERSON_ABSENCE_REVIEW")
    store.acknowledge(
        recommendation["id"],
        expected_version_id=store.head("fixture-org").id,
        expected_proposed_id=store.proposed("fixture-org").id,
        actor="local:tester",
        reason="Investigating transfer",
        observed_at=NOW + timedelta(hours=1),
    )
    assert (
        store.inspection_rows("pending_organization_reviews", "fixture-org")[0]["status"]
        == "acknowledged"
    )
    engineer = person(store.inspection_rows("current_organization", "fixture-org"))
    assert engineer["absence_review"] and engineer["manager_email"] == "one@example.test"
    ingest(store, key="reappeared", capture=NOW + timedelta(hours=2))
    assert (
        store.inspection_rows("pending_organization_reviews", "fixture-org")[0]["status"]
        == "acknowledged"
    )


# Permit processing columns while rejecting source payload corruption and raw-SQL
# deletion.
def test_feed_evidence_is_immutable_but_status_is_operational(store):
    first = ingest(store)
    feed = store.tables["feed"]
    with pytest.raises(DBAPIError), store.engine.begin() as connection:
        connection.execute(update(feed).where(feed.c.id == str(first.snapshot_id)).values(data={}))
    with store.engine.begin() as connection:
        connection.execute(
            update(feed).where(feed.c.id == str(first.snapshot_id)).values(state="published")
        )


# The applied pointer cannot be repointed to a proposal even when its workspace matches.
def test_pointer_scope_and_kind_are_database_constraints(store):
    ingest(store)
    with pytest.raises(DBAPIError), store.engine.begin() as connection:
        connection.execute(
            update(store.tables["workspace"]).values(
                applied_version_id=str(store.proposed("fixture-org").id)
            )
        )


# Inspect all SQL views and new local read routes with version IDs and bounded data.
def test_inspection_views_are_readable_and_api_exposes_proposed_context(store):
    ingest(store)
    with store.engine.connect() as connection:
        assert (
            len(
                connection.execute(
                    text(f'SELECT * FROM "{store.schema}".current_organization')
                ).all()
            )
            == 5
        )
    client = TestClient(build_local_read_api(store, "fixture-org", allow_local_prototype=True))
    response = client.get("/api/v1/organization/workspace")
    assert response.status_code == 200
    assert response.json()["proposal_status"] == "already_applied"
    assert "already been applied" in response.json()["message"]
    assert client.get("/api/v1/organization/reconciliation").status_code == 200


# Recheck freshness when a proposal waits too long, preserving the prior applied
# organization.
def test_staged_source_expiry_blocks_apply_without_partial_changes(store):
    first = ingest(store)
    feed_id, _ = store.register(
        envelope("waiting", NOW + timedelta(hours=1)), change_name(), NOW + timedelta(hours=1)
    )
    staged = store.stage(feed_id, NOW + timedelta(hours=1))
    with pytest.raises(PublicationConflict):
        store.apply(staged.proposed_version_id, NOW + timedelta(days=2))
    assert store.head("fixture-org").id == first.revision_id


# Trusted accountability settings can publish new routing from an already accepted feed.
def test_same_feed_lob_designee_change_publishes_without_a_new_delivery(store):
    first = ingest(store)
    config = store.configuration("fixture-org")
    new_lob = config.lobs[0].model_copy(update={"designee_emails": ("engineer@example.test",)})
    changed = config.model_copy(update={"id": uuid4(), "lobs": (new_lob, config.lobs[1])})
    result = store.update_configuration(
        changed,
        expected_version_id=first.revision_id,
        expected_proposed_id=first.proposed_version_id,
        expected_configuration_id=config.id,
        actor="local:tester",
        reason="New nominated designee",
        observed_at=NOW + timedelta(hours=1),
    )
    assert result.snapshot_id == first.snapshot_id
    assert person(store.inspection_rows("current_organization", "fixture-org"))[
        "designee_emails"
    ] == ["engineer@example.test"]
    assert not store.inspection_rows("pending_organization_reviews", "fixture-org")


# Automatically represent a new employee, retaining identity through subsequent
# source captures.
def test_new_person_gets_stable_identity_without_any_oci_operation(store):
    from otm.organization.contracts import Record

    ingest(store)
    extra = Record(
        source_record_id="new",
        full_name="New Engineer",
        email="new@example.test",
        manager_email="one@example.test",
    )
    rows = (*example_records(), extra)
    ingest(store, rows, "new-person", NOW + timedelta(hours=1))
    before = person(
        store.inspection_rows("current_organization", "fixture-org"), "new@example.test"
    )["person_id"]
    ingest(store, rows, "same-person-later", NOW + timedelta(hours=2))
    assert (
        person(store.inspection_rows("current_organization", "fixture-org"), "new@example.test")[
            "person_id"
        ]
        == before
    )
    assert len(store.metadata.tables) == 10


# Freeze source/before-after recommendation evidence while allowing audited
# lifecycle status changes.
def test_recommendation_evidence_cannot_be_overwritten_through_sql(store):
    ingest(store)
    target = store.tables["recommendation"]
    with pytest.raises(DBAPIError), store.engine.begin() as connection:
        connection.execute(update(target).values(after_value="Corrupted evidence"))


# Re-staging terminal input must explain reuse rather than imply that staging applied it.
def test_stage_already_published_reports_duplicate_without_changing_views(store):
    published = ingest(store)
    before = store.workspace_context("fixture-org")
    result = store.stage(published.snapshot_id, NOW + timedelta(hours=1))
    assert result.state == "duplicate"
    assert result.original_state == "published"
    assert result.revision_id == published.revision_id
    assert store.workspace_context("fixture-org") == before


# The CLI gives explicit guidance for an already-applied feed without changing its views.
def test_cli_stage_only_explains_already_applied_input(store, monkeypatch, tmp_path, capsys):
    import json
    import sys

    from otm.organization.contracts import Intake

    from scripts import organization_cli

    published = ingest(store)
    path = tmp_path / "already-published.json"
    path.write_text(Intake(envelope=envelope(), records=example_records()).model_dump_json())

    # Use the isolated fixture database instead of any private persistent connection.
    def test_store(_schema):
        return store

    monkeypatch.setattr(organization_cli, "local_store", test_store)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "organization_cli.py",
            "--workspace",
            "fixture-org",
            "--at",
            (NOW + timedelta(hours=1)).isoformat(),
            "feed",
            str(path),
            "--stage-only",
        ],
    )
    organization_cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "duplicate" and result["original_state"] == "published"
    assert "already applied" in result["message"].lower()
    assert store.head("fixture-org").id == published.revision_id


# Distinguish a new rejection from replay of that rejection; neither changes usable views.
def test_fresh_invalid_stage_is_rejected_and_only_its_replay_is_duplicate(store):
    invalid = tuple(
        row.model_copy(update={"manager_email": "engineer@example.test"})
        if row.email == "one@example.test"
        else row
        for row in example_records()
    )
    feed_id, _ = store.register(envelope("invalid-staged"), invalid, NOW)
    first = store.stage(feed_id, NOW)
    assert first.state == "rejected" and first.original_state is None
    second = store.stage(feed_id, NOW)
    assert second.state == "duplicate" and second.original_state == "rejected"
    assert store.head("fixture-org") is None and store.proposed("fixture-org") is None


# Concurrent callers recheck terminal feed state after acquiring the workspace lock.
def test_same_feed_concurrent_replay_publishes_once(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(4)

    # Synchronize duplicate deliveries of one source snapshot in the isolated database.
    def deliver(_index):
        barrier.wait(timeout=10)
        return store.ingest(example_records(), envelope(), NOW).state

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(deliver, range(4)))
    assert sorted(results) == ["duplicate", "duplicate", "duplicate", "published"]
    assert store.outcome(store.head("fixture-org").snapshot_id).state == "published"
    with store.engine.connect() as connection:
        assert len(connection.execute(select(store.tables["version"])).all()) == 2


# A configured empty workspace has no pending proposal and nullable publication pointers.
def test_workspace_context_reports_no_proposal_before_first_feed(store):
    result = store.workspace_context("fixture-org")
    assert result["proposal_status"] == "no_proposal"
    assert result["applied_version_id"] is None and result["proposed_version_id"] is None


# Context identifies pending versus completed work despite always-distinct version IDs.
def test_workspace_context_tracks_initial_and_later_stage_apply(store):
    feed_id, _ = store.register(envelope(), example_records(), NOW)
    staged = store.stage(feed_id, NOW)
    assert store.workspace_context("fixture-org")["proposal_status"] == "pending_application"
    applied = store.apply(staged.proposed_version_id, NOW)
    result = store.workspace_context("fixture-org")
    assert result["proposal_status"] == "already_applied"
    assert result["applied_version_id"] != result["proposed_version_id"]
    assert "already been applied" in result["message"]
    feed_id, _ = store.register(
        envelope("next-context", NOW + timedelta(hours=1)), change_name(), NOW + timedelta(hours=1)
    )
    staged = store.stage(feed_id, NOW + timedelta(hours=1))
    assert store.workspace_context("fixture-org")["applied_version_id"] == str(applied.revision_id)
    assert store.workspace_context("fixture-org")["proposal_status"] == "pending_application"
    store.apply(staged.proposed_version_id, NOW + timedelta(hours=1))
    assert store.workspace_context("fixture-org")["proposal_status"] == "already_applied"


# A newer configuration generation cannot make an old pending proposal look ready to apply.
def test_workspace_context_labels_mismatched_settings_stale(store):
    ingest(store)
    feed_id, _ = store.register(
        envelope("stale-context", NOW + timedelta(hours=1)), change_name(), NOW + timedelta(hours=1)
    )
    store.stage(feed_id, NOW + timedelta(hours=1))
    # Simulate an externally changed generation only inside the owned disposable test schema.
    with store.engine.begin() as connection:
        connection.execute(update(store.tables["workspace"]).values(configuration_id=str(uuid4())))
    assert store.workspace_context("fixture-org")["proposal_status"] == "stale"


# Expose named rollups and configured designees without flagging the initial census.
def test_readable_accountability_and_baseline_setup_status(store):
    ingest(store)
    rows = store.inspection_rows("current_organization", "fixture-org")
    engineer = person(rows)
    assert engineer["accountable_leader_name"] == "Leader One"
    assert engineer["lob_name"] == "LOB One"
    assert engineer["designee_names"] == ["Delegate"]
    assert engineer["designee_status"] == "assigned"
    assert engineer["tenancy_association_status"] == "not_tracked"
    assert not any(row["tenancy_setup_review"] for row in rows)
    assert person(rows, "two@example.test")["designee_status"] == "not_configured"
    assert person(rows, "root@example.test")["designee_status"] == "no_lob"


# New engineer/manager profiles remain actionable, with staged metadata kept separate.
def test_new_employee_setup_review_survives_repeat_feeds(store):
    from otm.organization.contracts import Record

    ingest(store)
    records = example_records() + (
        Record(
            source_record_id="new-manager",
            full_name="New Manager",
            email="new-manager@example.test",
            manager_email="two@example.test",
        ),
        Record(
            source_record_id="new-engineer",
            full_name="New Engineer",
            email="new-engineer@example.test",
            manager_email="new-manager@example.test",
        ),
    )
    at = NOW + timedelta(hours=1)
    feed_id, _ = store.register(envelope("add", at), records, at)
    staged = store.stage(feed_id, at)
    assert len(store.inspection_rows("current_organization", "fixture-org")) == 5
    preview = store.inspection_rows("proposed_organization", "fixture-org")
    assert person(preview, "new-manager@example.test")["known_manager"] is True
    assert person(preview, "new-engineer@example.test")["tenancy_setup_review"] is True
    store.apply(staged.proposed_version_id, at + timedelta(minutes=1))
    ingest(store, records, "repeat", NOW + timedelta(hours=2))
    rows = store.inspection_rows("current_organization", "fixture-org")
    for email in ("new-engineer@example.test", "new-manager@example.test"):
        assert person(rows, email)["required_actions"] == ["TENANCY_SETUP_REVIEW"]
    assert person(rows)["required_actions"] == []
    # Refreshing view definitions is safe with existing dependent inspection views and data.
    store.initialize()
    assert (
        person(
            store.inspection_rows("current_organization", "fixture-org"),
            "new-engineer@example.test",
        )["tenancy_setup_review"]
        is True
    )


# A proposed manager change resolves leader/designee names within that same version.
def test_named_rollup_uses_staged_version_configuration(store):
    ingest(store)
    records = tuple(
        row.model_copy(update={"manager_email": "two@example.test"})
        if row.email == "engineer@example.test"
        else row
        for row in example_records()
    )
    at = NOW + timedelta(hours=1)
    feed_id, _ = store.register(envelope("move", at), records, at)
    store.stage(feed_id, at)
    current = person(store.inspection_rows("current_organization", "fixture-org"))
    proposed = person(store.inspection_rows("proposed_organization", "fixture-org"))
    assert current["lob_name"] == "LOB One"
    assert proposed["lob_name"] == "LOB Two"
    assert proposed["accountable_leader_name"] == "Leader Two"
    assert proposed["designee_status"] == "not_configured"
    assert proposed["designee_names"] == []


# Absence investigation is visible as an action without implying automatic deletion.
def test_exception_actions_are_visible_on_people(store):
    ingest(store)
    records = tuple(row for row in example_records() if row.email != "engineer@example.test")
    ingest(store, records, "absence-actions", NOW + timedelta(hours=1))
    engineer = person(store.inspection_rows("current_organization", "fixture-org"))
    assert engineer["absence_review"] is True
    assert "PERSON_ABSENCE_REVIEW" in engineer["required_actions"]
    assert engineer["tenancy_setup_review"] is False
