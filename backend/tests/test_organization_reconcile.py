"""Pure reconciliation tests for identity, evidence, graph and census safety boundaries."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_organization_fixtures import NOW, envelope, example_config, example_records

from otm.organization.contracts import Intake, Revision, SupplementalEdge
from otm.organization.reconcile import prepare


# Wrap a prepared candidate as prior published state for pure reconciliation tests.
def revision(candidate):
    return Revision(
        id=uuid4(),
        predecessor_id=candidate.expected_head_id,
        configuration_id=candidate.expected_configuration_id,
        snapshot_id=uuid4(),
        population_id=candidate.envelope.population_id,
        published_at=candidate.observed_at,
        source_captured_at=candidate.envelope.captured_at,
        declared_completeness=candidate.envelope.declared_completeness,
        assessed_coverage=candidate.assessed_coverage,
        absence_eligible=candidate.absence_eligible,
        people=candidate.people,
    )


# Verify qualified census coverage and configured leader/designee routing.
def test_complete_census_and_lob_routing():
    candidate = prepare(example_records(), envelope(), example_config(), None, NOW)
    assert not candidate.rejected and candidate.absence_eligible
    person = next(p for p in candidate.people if p.email == "engineer@example.test")
    assert person.lob_id == "one"
    assert person.designee_emails == ("delegate@example.test",)


# Verify partial manager changes preserve identity and omitted people without absence
# conclusions.
def test_partial_reorg_keeps_identity_and_missing_people():
    config = example_config()
    old = revision(prepare(example_records(), envelope(), config, None, NOW))
    engineer = example_records()[-1].model_copy(update={"manager_email": "two@example.test"})
    new = prepare(
        (engineer,),
        envelope("reorg", NOW + timedelta(hours=1), "partial"),
        config,
        old,
        NOW + timedelta(hours=1),
    )
    before = next(p for p in old.people if p.email == engineer.email)
    after = next(p for p in new.people if p.email == engineer.email)
    assert after.id == before.id and after.lob_id is None and after.designee_emails == ()
    assert ("LOB_LEADER_REVIEW", "two:two@example.test") in new.issues
    assert len(new.people) == len(old.people)
    assert not new.absence_eligible and not any(p.absence_review for p in new.people)


# Verify trusted historical profiles do not disguise a gap in a supposedly complete incoming
# census.
def test_d17_prior_profiles_cannot_fill_incoming_coverage():
    config = example_config()
    old = revision(prepare(example_records(), envelope(), config, None, NOW))
    new_rows = tuple(r for r in example_records() if r.email != "one@example.test")
    candidate = prepare(
        new_rows,
        envelope("gapped", NOW + timedelta(hours=1)),
        config,
        old,
        NOW + timedelta(hours=1),
    )
    assert not candidate.rejected and not candidate.absence_eligible
    assert candidate.assessed_coverage == "partial"
    assert candidate.envelope.declared_completeness == "complete"
    assert any(d.code == "MANAGER_PROFILE_MISSING" for d in candidate.diagnostics)
    manager = next(p for p in candidate.people if p.email == "one@example.test")
    assert manager.profile == "employee"  # Trusted history retained, coverage still incomplete.
    assert not any(p.absence_review for p in candidate.people)


# Verify reappearance preserves stable identity and leaves the absence decision to an admin.
def test_absence_requires_complete_capture_and_can_reappear():
    config = example_config()
    first = revision(prepare(example_records(), envelope(), config, None, NOW))
    remaining = example_records()[:-1]
    second = revision(
        prepare(
            remaining,
            envelope("missing", NOW + timedelta(hours=1)),
            config,
            first,
            NOW + timedelta(hours=1),
        )
    )
    missing = next(p for p in second.people if p.email == "engineer@example.test")
    assert missing.absence_review
    third = prepare(
        example_records(),
        envelope("back", NOW + timedelta(hours=2)),
        config,
        second,
        NOW + timedelta(hours=2),
    )
    returned = next(p for p in third.people if p.email == missing.email)
    assert returned.id == missing.id and returned.absence_review
    assert returned.absence_review_since == missing.absence_review_since


# Verify new partial edges are checked against retained history and cannot introduce
# reporting cycles.
def test_cycle_through_retained_partial_edges_rejected():
    config = example_config()
    old = revision(prepare(example_records(), envelope(), config, None, NOW))
    one = example_records()[1].model_copy(update={"manager_email": "engineer@example.test"})
    candidate = prepare(
        (one,),
        envelope("cycle", NOW + timedelta(hours=1), "partial"),
        config,
        old,
        NOW + timedelta(hours=1),
    )
    assert candidate.rejected
    assert any(d.code == "REPORTING_CYCLE" for d in candidate.diagnostics)


# Verify duplicate or changed identity keys reject the candidate rather than silently merge
# people.
@pytest.mark.parametrize(
    "change", ["duplicate_email", "duplicate_id", "changed_email", "changed_id"]
)
def test_identity_ambiguity_never_merges(change):
    config = example_config()
    old = revision(prepare(example_records(), envelope(), config, None, NOW))
    rows = list(example_records())
    if change == "duplicate_email":
        rows.append(rows[-1])
    elif change == "duplicate_id":
        rows[-1] = rows[-1].model_copy(update={"source_record_id": "one"})
    elif change == "changed_email":
        rows[-1] = rows[-1].model_copy(update={"email": "renamed@example.test"})
    else:
        rows[-1] = rows[-1].model_copy(update={"source_record_id": "different-id"})
    candidate = prepare(
        tuple(rows),
        envelope("ambiguous", NOW + timedelta(hours=1)),
        config,
        old,
        NOW + timedelta(hours=1),
    )
    assert candidate.rejected
    original_id = next(p.id for p in old.people if p.email == "engineer@example.test")
    assert next(p.id for p in candidate.people if p.email == "engineer@example.test") == original_id


# Verify stale, future, undated or mismatched-scope input cannot qualify for publication or
# absence.
@pytest.mark.parametrize(
    "options",
    [
        {"captured_at": NOW - timedelta(days=2)},
        {"captured_at": NOW + timedelta(days=1)},
        {"captured_at": None},
        {"source_id": "other"},
        {"population_id": "other"},
    ],
)
def test_capture_and_trust_gates(options):
    incoming = envelope().model_copy(update=options)
    result = prepare(example_records(), incoming, example_config(), None, NOW)
    assert result.rejected and not result.absence_eligible


# Verify complete-looking rows do not grant an untrusted source census authority.
def test_no_authority_no_census_even_with_complete_rows():
    candidate = prepare(
        example_records(), envelope(), example_config(authoritative=False), None, NOW
    )
    assert not candidate.rejected and not candidate.absence_eligible


# Verify feed and explicitly configured reporting-edge conflicts are rejected.
def test_supplemental_conflict_is_not_silently_overwritten():
    config = example_config().model_copy(
        update={
            "supplemental_edges": (
                SupplementalEdge(
                    employee_email="engineer@example.test",
                    manager_email="two@example.test",
                    provenance="admin:test",
                ),
            )
        }
    )
    assert prepare(example_records(), envelope(), config, None, NOW).rejected


# Verify configuration validation forbids authoritative undated development input.
def test_source_policy_cannot_enable_undated_authoritative_mode():
    with pytest.raises(ValidationError):
        example_config(allow_undated_development_metadata=True)


# Verify untrusted intake cannot inject authority into the source envelope.
def test_canonical_intake_does_not_accept_trusted_policy_from_source():
    body = Intake(envelope=envelope(), records=example_records()).model_dump(mode="json")
    assert Intake.model_validate(body).records == example_records()
    body["envelope"]["authoritative"] = True
    with pytest.raises(ValidationError):
        Intake.model_validate(body)


# Verify a moved LOB leader raises assignment review and routing follows the effective
# hierarchy.
def test_reorg_of_configured_lob_leader_requires_assignment_review():
    config = example_config()
    old = revision(prepare(example_records(), envelope(), config, None, NOW))
    rows = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.email == "one@example.test"
        else r
        for r in example_records()
    )
    candidate = prepare(
        rows,
        envelope("leader-reorg", NOW + timedelta(hours=1)),
        config,
        old,
        NOW + timedelta(hours=1),
    )
    assert not candidate.rejected
    assert ("LOB_LEADER_REVIEW", "one:one@example.test") in candidate.issues
    assert next(p for p in candidate.people if p.email == "engineer@example.test").lob_id == "two"


# Verify missing referenced manager profiles remain positive evidence and block census
# absence inference.
def test_complete_census_with_reference_only_person_blocks_absence():
    config = example_config()
    old = revision(prepare(example_records(), envelope(), config, None, NOW))
    rows = tuple(
        r.model_copy(update={"manager_email": "new-manager@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    candidate = prepare(
        rows,
        envelope("missing-manager", NOW + timedelta(hours=1)),
        config,
        old,
        NOW + timedelta(hours=1),
    )
    manager = next(p for p in candidate.people if p.email == "new-manager@example.test")
    assert manager.profile == "reference" and manager.known_manager
    assert manager.ancestry == "incomplete"
    assert not candidate.rejected and not candidate.absence_eligible


# Verify reference names enrich placeholders without establishing a received employee
# profile.
def test_manager_reference_name_fills_configured_placeholder_without_faking_a_row():
    rows = tuple(
        r.model_copy(update={"manager_name": "Known Root Name"})
        if r.manager_email == "root@example.test"
        else r
        for r in example_records()[1:]
    )
    candidate = prepare(rows, envelope(), example_config(), None, NOW)
    root = next(p for p in candidate.people if p.email == "root@example.test")
    assert root.full_name == "Known Root Name"
    assert root.profile == "configured" and root.last_row_observed_at is None
    assert not candidate.absence_eligible
