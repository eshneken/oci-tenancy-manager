"""Organization identity, review episodes and trusted-source boundaries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_organization_fixtures import NOW, envelope, example_config, example_records
from test_organization_reconcile import revision

from otm.organization.contracts import (
    Configuration,
    IdentityMerge,
    PersonOverride,
    ReviewDecision,
    SupplementalEdge,
    email,
    require_aware,
)
from otm.organization.reconcile import prepare
from otm.organization.review_rules import canonical_email, issue_basis, suppressed


# Retain the unmodified synthetic profile while selecting the effective row for an assertion.
def person(candidate, address="engineer@example.test"):
    return next(item for item in candidate.people if item.email == address)


# Store an administrator-reviewed condition, not a fabricated completed tenancy operation.
def decision(subject, kind, disposition="resolved"):
    return ReviewDecision(
        kind=kind,
        target=subject.email,
        disposition=disposition,
        person_id=subject.id,
        basis=issue_basis(kind, subject.email, (subject,)),
        recorded_at=NOW,
        actor="verified-administrator-reference",
        reason="Reviewed condition",
    )


# Snapshot fixtures retain independent observation time rather than mutating the previous revision.
def subsequent(config, prior, rows, hour):
    at = NOW + timedelta(hours=hour)
    return prepare(rows, envelope(f"observation-{hour}", at), config, prior, at)


# Silent name and manager metadata updates retain stable person IDs and derive routing again.
def test_metadata_updates_keep_person_identity_and_do_not_mutate_source():
    config = example_config()
    before = revision(prepare(example_records(), envelope(), config, None, NOW))
    original = example_records()[-1]
    changed = original.model_copy(
        update={"full_name": "Renamed Engineer", "manager_email": "two@example.test"}
    )
    after = subsequent(config, before, (*example_records()[:-1], changed), 1)
    assert person(after).id == person(before).id
    assert person(after).full_name == "Renamed Engineer"
    assert (
        person(after).lob_id == "two"
        and person(after).accountable_leader_email == "two@example.test"
    )
    assert original.full_name == "Engineer" and original.manager_email == "one@example.test"


# Missing snapshots keep a review open; settlement is episode-specific and a later departure
# reopens.
def test_absence_review_persists_and_return_starts_a_fresh_departure_episode():
    config = example_config()
    initial = revision(prepare(example_records(), envelope(), config, None, NOW))
    missing = revision(subsequent(config, initial, example_records()[:-1], 1))
    again = revision(subsequent(config, missing, example_records()[:-1], 2))
    assert person(again).absence_review_since == person(missing).absence_review_since
    assert ("PERSON_ABSENCE_REVIEW", "engineer@example.test") in subsequent(
        config, again, example_records()[:-1], 3
    ).issues
    settled_config = config.model_copy(
        update={"review_decisions": (decision(person(again), "PERSON_ABSENCE_REVIEW"),)}
    )
    settled = revision(subsequent(settled_config, again, example_records()[:-1], 4))
    assert not person(settled).absence_review
    still_missing = revision(subsequent(settled_config, settled, example_records()[:-1], 5))
    assert not person(still_missing).absence_review
    returned = revision(subsequent(settled_config, still_missing, example_records(), 6))
    assert person(returned).absence_review_since is None
    departed = subsequent(settled_config, returned, example_records()[:-1], 7)
    assert person(departed).absence_review and person(
        departed
    ).absence_review_since == NOW + timedelta(hours=7)
    assert person(departed).id == person(initial).id


# Exclusions affect only the effective graph; explicit directory return must clear the marker
# upstream.
def test_excluded_profile_is_not_reintroduced_by_repeating_the_same_feed():
    config = example_config()
    prior = revision(prepare(example_records(), envelope(), config, None, NOW))
    excluded = Configuration.model_validate(
        {**config.model_dump(), "excluded_emails": [" ENGINEER@EXAMPLE.TEST "]}
    )
    result = subsequent(excluded, prior, example_records(), 1)
    assert all(row.email != "engineer@example.test" for row in result.people)
    assert len(prior.people) == len(example_records())
    assert example_records()[-1].email == "engineer@example.test"


# A deliberate one-way email remap keeps the survivor UUID and rewrites manager references only.
def test_explicit_merge_preserves_survivor_without_matching_names_automatically():
    config = example_config()
    prior = revision(prepare(example_records(), envelope(), config, None, NOW))
    old = person(prior)
    renamed = example_records()[-1].model_copy(
        update={
            "email": "renamed@example.test",
            "source_record_id": "email:renamed@example.test",
            "full_name": "Changed Name",
        }
    )
    rows = (*example_records()[:-1], renamed)
    proposed = revision(subsequent(config, prior, rows, 1))
    new = person(proposed, renamed.email)
    assert old.id != new.id and person(proposed).absence_review
    merge = IdentityMerge(
        old_email=old.email,
        new_email=renamed.email,
        person_id=old.id,
        retired_person_id=new.id,
        actor="verified-administrator-reference",
        reason="Verified identity change",
    )
    merged_config = config.model_copy(update={"identity_merges": (merge,)})
    merged = subsequent(merged_config, proposed, rows, 2)
    survivor = person(merged, renamed.email)
    assert survivor.id == old.id and survivor.full_name == "Changed Name"
    assert not survivor.absence_review
    assert all(row.email != old.email for row in merged.people)
    rejected = subsequent(merged_config, revision(merged), example_records(), 3)
    assert rejected.rejected and any(
        row.code == "RETIRED_EMAIL_IN_FEED" for row in rejected.diagnostics
    )


# Missing source time/order, superseded source and disabled authority never qualify for publication.
@pytest.mark.parametrize(
    "mode", ["disabled", "undated_after_dated", "superseded", "missing_manager"]
)
def test_publication_gates_remain_stricter_than_metadata_reconstruction(mode):
    config = example_config()
    prior = revision(prepare(example_records(), envelope(), config, None, NOW))
    rows = example_records()
    incoming = envelope("next", NOW + timedelta(hours=1))
    if mode == "disabled":
        config = example_config(allow_metadata=False)
    elif mode == "undated_after_dated":
        config = example_config(authoritative=False, allow_undated_development_metadata=True)
        incoming = incoming.model_copy(update={"captured_at": None})
    elif mode == "superseded":
        incoming = incoming.model_copy(update={"captured_at": NOW})
    else:
        rows = (*rows[:-1], rows[-1].model_copy(update={"manager_email": None}))
    result = prepare(rows, incoming, config, prior, NOW + timedelta(hours=1))
    assert result.rejected and not result.absence_eligible


# Trusted reapplication may inspect old metadata but cannot turn it into fresh absence evidence.
def test_stale_trusted_reapply_is_review_only():
    at = NOW + timedelta(days=3)
    result = prepare(
        example_records(), envelope(), example_config(), None, at, trusted_reapply=True
    )
    assert not result.rejected and not result.absence_eligible
    assert any(item.code == "STALE_SOURCE_REVIEW_ONLY" for item in result.diagnostics)


# An explicitly allowed undated compatibility source can update metadata but never infer departure.
def test_undated_metadata_compatibility_cannot_establish_census():
    config = example_config(authoritative=False, allow_undated_development_metadata=True)
    result = prepare(example_records(), envelope(capture=None), config, None, NOW)
    assert not result.rejected and not result.absence_eligible
    assert all(item.last_source_capture_at is None for item in result.people)


# Supplemental edges repair only declared paths and do not invent a received manager profile.
def test_supplemental_edge_fills_path_without_forging_source_coverage():
    config = example_config().model_copy(
        update={
            "supplemental_edges": (
                SupplementalEdge(
                    employee_email="unlisted@example.test",
                    manager_email="one@example.test",
                    provenance="reviewed-edge",
                ),
            )
        }
    )
    rows = (
        *example_records()[:-1],
        example_records()[-1].model_copy(update={"manager_email": "unlisted@example.test"}),
    )
    result = prepare(rows, envelope(), config, None, NOW)
    manager = person(result, "unlisted@example.test")
    assert manager.manager_provenance == "reviewed-edge" and manager.ancestry == "resolved"
    assert person(result).lob_id == "one" and not result.absence_eligible


# Explicit corrections win while conflicts preserve source values and invalid subjects reject
# safely.
def test_override_conflicts_and_unknown_targets():
    config = example_config()
    override = PersonOverride(
        email="engineer@example.test",
        values={"full_name": "Corrected Name", "manager_email": "new-manager@example.test"},
        actor="verified-administrator-reference",
        reason="Verified correction",
    )
    corrected = config.model_copy(update={"overrides": (override,)})
    result = prepare(example_records(), envelope(), corrected, None, NOW)
    assert person(result).full_name == "Corrected Name"
    assert person(result).source_values["full_name"] == "Engineer"
    assert person(result).manager_provenance == "admin override: Verified correction"
    assert ("OVERRIDE_CONFLICT", "engineer@example.test:manager_email") in result.issues
    assert person(result, "new-manager@example.test").known_manager
    absent = corrected.model_copy(
        update={"overrides": (override.model_copy(update={"email": "unknown@example.test"}),)}
    )
    assert prepare(example_records(), envelope(), absent, None, NOW).rejected


# Unmapped direct reports stay visible, while informational mismatches disappear after source
# repair.
def test_lob_mapping_review_and_corrected_top_manager_hint():
    records = example_records()
    assistant = records[-1].model_copy(
        update={
            "email": "assistant@example.test",
            "source_record_id": "assistant",
            "manager_email": "root@example.test",
            "reported_top_manager_email": "root@example.test",
        }
    )
    mismatched = records[-1].model_copy(update={"reported_top_manager_email": "two@example.test"})
    result = prepare(
        (*records[:-1], mismatched, assistant), envelope(), example_config(), None, NOW
    )
    assert ("LOB_MAPPING_REVIEW", assistant.email) in result.issues
    assert ("TOP_MANAGER_MISMATCH", mismatched.email) in result.issues
    fixed = subsequent(example_config(), revision(result), (*records, assistant), 1)
    assert not any(kind == "TOP_MANAGER_MISMATCH" for kind, _ in fixed.issues)


# An out-of-branch designee loses routing rather than receiving another branch's operational
# notices.
def test_designee_reorg_is_not_silently_accepted():
    rows = tuple(
        row.model_copy(update={"manager_email": "two@example.test"})
        if row.email == "delegate@example.test"
        else row
        for row in example_records()
    )
    result = prepare(rows, envelope(), example_config(), None, NOW)
    assert ("DESIGNEE_INVALID", "one:delegate@example.test") in result.issues
    assert person(result).designee_emails == ()


# Review suppression is tied to exact effective facts, while a permanent ignore survives a reorg.
@pytest.mark.parametrize("disposition", ["resolved", "ignored"])
def test_review_decisions_preserve_conditional_and_permanent_semantics(disposition):
    config = example_config()
    result = prepare(example_records(), envelope(), config, None, NOW)
    subject = person(result)
    closure = decision(subject, "LOB_MAPPING_REVIEW", disposition)
    configured = config.model_copy(update={"review_decisions": (closure,)})
    assert suppressed(configured, closure.kind, subject.email, (subject,))
    changed = subject.model_copy(update={"manager_email": "two@example.test"})
    assert suppressed(configured, closure.kind, subject.email, (changed,)) is (
        disposition == "ignored"
    )
    excluded = config.model_copy(update={"managed_exclusions": (subject.id,)})
    assert suppressed(excluded, "PERSON_ABSENCE_REVIEW", subject.email, (subject,))
    assert not suppressed(excluded, "DESIGNEE_INVALID", subject.email, (subject,))


# Fingerprints distinguish meaningful source/override conflicts and retain legacy absence
# interpretation.
def test_review_fingerprints_and_alias_cycle_guards():
    subject = person(prepare(example_records(), envelope(), example_config(), None, NOW))
    target = subject.email + ":manager_email"
    before = issue_basis("OVERRIDE_CONFLICT", target, (subject,))
    changed = subject.model_copy(update={"source_values": {"manager_email": "two@example.test"}})
    assert issue_basis("OVERRIDE_CONFLICT", target, (changed,)) != before
    assert issue_basis("PERSON_ABSENCE_REVIEW", subject.email, ()) is None
    assert issue_basis("PERSON_ABSENCE_REVIEW", subject.email, (subject,)) == "legacy"
    cyclic = SimpleNamespace(
        identity_merges=(
            SimpleNamespace(old_email="a@example.test", new_email="b@example.test"),
            SimpleNamespace(old_email="b@example.test", new_email="a@example.test"),
        )
    )
    with pytest.raises(ValueError, match="alias cycle"):
        canonical_email(cyclic, "a@example.test")


# Invalid source/configuration identity must fail before any effective graph can be trusted.
@pytest.mark.parametrize(
    "address",
    [
        "invalid",
        "a@@example.test",
        "a@localhost",
        "a@.example.test",
        "a@example.test.",
        "a b@example.test",
        "a" * 321 + "@example.test",
    ],
)
def test_email_validation_rejects_ambiguous_identifiers(address):
    with pytest.raises(ValueError):
        email(address)


# No guessed timezone is allowed for the reconciliation observation clock.
def test_naive_clock_and_blank_corrections_are_rejected():
    with pytest.raises(ValueError, match="aware clock"):
        require_aware(datetime(2026, 10, 12))
    require_aware(datetime(2026, 10, 12, tzinfo=UTC))
    with pytest.raises(ValidationError):
        PersonOverride(
            email="a@example.test", values={}, actor="administrator", reason="Correction"
        )
    with pytest.raises(ValidationError):
        example_records()[-1].__class__(
            source_record_id=" ", full_name="Valid Name", email="a@example.test", manager_email=None
        )


# Trusted configuration cannot contain conflicting branch keys, root edges or cyclic/duplicate
# aliases.
@pytest.mark.parametrize(
    "damage",
    [
        "lob",
        "leader",
        "edge",
        "override",
        "root_override",
        "root_edge",
        "root_excluded",
        "duplicate_alias",
        "cycle",
    ],
)
def test_configuration_rejects_ambiguous_keys_and_root_mutation(damage):
    config = example_config()
    body = config.model_dump()
    if damage in {"lob", "leader"}:
        lob = config.lobs[0].model_copy(
            update={"id": "different"}
            if damage == "leader"
            else {"leader_email": "other@example.test"}
        )
        body["lobs"] = (*config.lobs, lob)
    elif damage in {"edge", "root_edge"}:
        edge = SupplementalEdge(
            employee_email=config.policy.root_email
            if damage == "root_edge"
            else "engineer@example.test",
            manager_email="one@example.test",
            provenance="reviewed",
        )
        body["supplemental_edges"] = (edge,) if damage == "root_edge" else (edge, edge)
    elif damage in {"override", "root_override"}:
        override = PersonOverride(
            email=config.policy.root_email
            if damage == "root_override"
            else "engineer@example.test",
            values={"manager_email": "one@example.test"},
            actor="administrator",
            reason="Reviewed",
        )
        body["overrides"] = (override,) if damage == "root_override" else (override, override)
    elif damage == "root_excluded":
        body["excluded_emails"] = (config.policy.root_email,)
    else:
        first = IdentityMerge(
            old_email="a@example.test",
            new_email="b@example.test",
            person_id=uuid4(),
            retired_person_id=uuid4(),
            actor="administrator",
            reason="Reviewed identity",
        )
        second = (
            first
            if damage == "duplicate_alias"
            else first.model_copy(
                update={"old_email": "b@example.test", "new_email": "a@example.test"}
            )
        )
        body["identity_merges"] = (first, second)
    with pytest.raises(ValidationError):
        Configuration.model_validate(body)


# Closing an active absence after the source returns clears the old episode without losing identity.
def test_resolved_returned_absence_clears_episode_key():
    config = example_config()
    initial = revision(prepare(example_records(), envelope(), config, None, NOW))
    missing = revision(subsequent(config, initial, example_records()[:-1], 1))
    returned = revision(subsequent(config, missing, example_records(), 2))
    configured = config.model_copy(
        update={"review_decisions": (decision(person(returned), "PERSON_ABSENCE_REVIEW"),)}
    )
    settled = subsequent(configured, returned, example_records(), 3)
    assert not person(settled).absence_review and person(settled).absence_review_since is None
    assert person(settled).id == person(initial).id


# Removing a configured or referenced identity must not publish a replacement placeholder UUID.
@pytest.mark.parametrize("reference", ["leader", "designee", "manager", "top_hint"])
def test_excluded_identity_references_reject_candidate(reference):
    config = example_config()
    rows = example_records()
    excluded = {
        "leader": "one@example.test",
        "designee": "delegate@example.test",
        "manager": "removed-manager@example.test",
        "top_hint": "removed-hint@example.test",
    }[reference]
    if reference == "manager":
        rows = (*rows[:-1], rows[-1].model_copy(update={"manager_email": excluded}))
    elif reference == "top_hint":
        rows = (*rows[:-1], rows[-1].model_copy(update={"reported_top_manager_email": excluded}))
    initial = revision(prepare(example_records(), envelope(), config, None, NOW))
    removed = Configuration.model_validate({**config.model_dump(), "excluded_emails": (excluded,)})
    result = subsequent(removed, initial, rows, 1)
    findings = [item for item in result.diagnostics if item.code == "EXCLUDED_IDENTITY_REFERENCED"]
    if reference == "designee":
        assert not result.rejected and not findings
        assert ("DESIGNEE_INVALID", "one:" + excluded) in result.issues
        assert excluded not in {p.email for p in result.people}
    else:
        assert result.rejected and not result.absence_eligible
        assert [(item.affected_email, item.fatal) for item in findings] == [(excluded, True)]
    assert excluded in removed.excluded_emails


# Retained partial-feed references must obey the same exclusion guard without incoming row replay.
@pytest.mark.parametrize("field", ["manager_email", "reported_top_manager_email"])
def test_excluded_identity_references_in_retained_profiles_reject_candidate(field):
    config = example_config()
    excluded = "retained-reference@example.test"
    rows = (*example_records()[:-1], example_records()[-1].model_copy(update={field: excluded}))
    initial = revision(prepare(rows, envelope(), config, None, NOW))
    removed = Configuration.model_validate({**config.model_dump(), "excluded_emails": (excluded,)})
    incoming = envelope("partial", NOW + timedelta(hours=1), "partial")
    result = prepare(example_records()[:1], incoming, removed, initial, NOW + timedelta(hours=1))
    assert result.rejected and not result.absence_eligible
    assert any(
        item.code == "EXCLUDED_IDENTITY_REFERENCED"
        and item.affected_email == excluded
        and item.fatal
        for item in result.diagnostics
    )


# Old email aliases cannot bypass exclusion through trusted branch/edge configuration.
@pytest.mark.parametrize("reference", ["leader", "designee", "supplemental_manager"])
@pytest.mark.parametrize("exclude_alias", [False, True])
def test_aliases_cannot_reintroduce_excluded_configured_identities(reference, exclude_alias):
    config = example_config()
    old = {
        "leader": "one@example.test",
        "designee": "delegate@example.test",
        "supplemental_manager": "prior-manager@example.test",
    }[reference]
    canonical = "renamed-person@example.test"
    merge = IdentityMerge(
        old_email=old,
        new_email=canonical,
        person_id=uuid4(),
        retired_person_id=uuid4(),
        actor="verified-administrator-reference",
        reason="Verified identity change",
    )
    updates = {
        "identity_merges": (merge,),
        "excluded_emails": (old if exclude_alias else canonical,),
    }
    if reference == "supplemental_manager":
        updates["supplemental_edges"] = (
            SupplementalEdge(
                employee_email="configured-reference@example.test",
                manager_email=old,
                provenance="reviewed-edge",
            ),
        )
    removed = Configuration.model_validate({**config.model_dump(), **updates})
    result = prepare(example_records()[:1], envelope(completeness="partial"), removed, None, NOW)
    findings = [item for item in result.diagnostics if item.code == "EXCLUDED_IDENTITY_REFERENCED"]
    if reference == "supplemental_manager":
        assert result.rejected and not result.absence_eligible
        assert [(item.affected_email, item.fatal) for item in findings] == [(canonical, True)]
    else:
        assert not result.rejected and not result.absence_eligible and not findings
        assert old not in {p.email for p in result.people}
        assert (
            "LOB_LEADER_REVIEW" if reference == "leader" else "DESIGNEE_INVALID",
            "one:" + old,
        ) in result.issues
