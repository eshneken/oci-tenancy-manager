"""Mapping eligibility, exact preview fencing and no-observation recalculation regressions."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from test_organization_fixtures import NOW, envelope, example_config, example_records
from test_organization_reconcile import revision

from otm.organization.mapping import MappingService, candidate_configuration, editable
from otm.organization.mapping_contracts import (
    MappingApply,
    MappingCandidate,
    MappingContext,
    MappingRequest,
)
from otm.organization.reconcile import prepare
from otm.organization.role_health import role_health
from otm.storage.organization import OrganizationConflict


# Use an actual graph/source, with persistence stubbed only at the explicit service boundary.
def mapping_case():
    config = example_config()
    records = example_records()
    source = envelope()
    head = revision(prepare(records, source, config, None, NOW))
    context = MappingContext(
        configuration_id=config.id,
        applied_version_id=head.id,
        proposed_version_id=head.id,
        registry_revision=1,
    )
    connection = MagicMock()
    store = Mock(clock=Mock(return_value=NOW + timedelta(hours=1)))
    store._principal.return_value = "fixture-workspace"
    store._write.return_value = nullcontext((connection, "fixture-workspace", store.clock()))
    workflow = Mock()
    service = MappingService(store, config, workflow)
    feed = dict(
        data={
            "envelope": source.model_dump(mode="json"),
            "records": [r.model_dump(mode="json") for r in records],
        },
        digest="",
        source_id=source.source_id,
        population_id=source.population_id,
        external_id=source.external_snapshot_id,
        captured_at=source.captured_at,
    )
    from otm.operations.contracts import canonical_hash

    feed["digest"] = canonical_hash(feed["data"])
    connection.execute.return_value.mappings.return_value.one.return_value = feed
    request = MappingRequest(context=context, candidate=editable(config))
    return SimpleNamespace(**locals())


# Invalid candidates cannot submit policy, duplicate identities, blank names or the root as leader.
@pytest.mark.parametrize(
    "damage", ["empty", "blank", "labels", "leaders", "ids", "root", "email", "policy"]
)
def test_mapping_candidate_validation(damage):
    body = editable(example_config()).model_dump()
    if damage == "empty":
        body["segments"] = []
    elif damage == "blank":
        body["segments"][0]["label"] = "  "
    elif damage == "labels":
        body["segments"][1]["label"] = "  LOB ONE  "
    elif damage == "leaders":
        body["segments"][1]["leader_email"] = body["segments"][0]["leader_email"]
    elif damage == "ids":
        body["segments"][1]["id"] = body["segments"][0]["id"]
    elif damage == "root":
        body["segments"][0]["leader_email"] = body["root_email"]
    elif damage == "email":
        body["segments"][0]["leader_email"] = "not-an-email"
    else:
        body["policy"] = {"authoritative": True}
    with pytest.raises(ValueError):
        MappingCandidate.model_validate(body)


# Server IDs are stable within one preview, never selected from retired or foreign mappings.
def test_server_segment_ids_policy_preservation_and_root_guard():
    c = mapping_case()
    body = editable(c.config).model_dump()
    body["segments"][0]["label"] = " Renamed "
    body["segments"][0]["designee_emails"] = (" DELEGATE@example.test ", "delegate@example.test")
    body["segments"] = (
        *body["segments"],
        dict(id=None, label="Third", leader_email="third@example.test"),
    )
    request = MappingRequest(context=c.context, candidate=MappingCandidate.model_validate(body))
    first = candidate_configuration("w", c.config, None, request)
    assert first == candidate_configuration("w", c.config, None, request)
    assert first.policy == c.config.policy and first.overrides == c.config.overrides
    assert first.lobs[0].id == c.config.lobs[0].id and first.lobs[0].label == "Renamed"
    assert first.lobs[0].designee_emails == ("delegate@example.test",)
    assert first.lobs[-1].id not in {s.id for s in c.config.lobs}
    with pytest.raises(OrganizationConflict, match="ROOT_FIXED"):
        candidate_configuration(
            "w",
            c.config,
            None,
            request.model_copy(
                update={
                    "candidate": request.candidate.model_copy(
                        update={"root_email": "other@example.test"}
                    )
                }
            ),
        )
    with pytest.raises(OrganizationConflict, match="SETUP_UNAVAILABLE"):
        candidate_configuration("w", None, None, request)
    with pytest.raises(OrganizationConflict, match="SEGMENT_CHANGED"):
        candidate_configuration("w", None, c.config, request)


# Retained manager references prevent false departures but are not a current eligible role profile.
@pytest.mark.parametrize(
    "scenario,status",
    [
        ("missing", "profile_missing"),
        ("moved", "branch_changed"),
        ("outside", "ancestry_incomplete"),
        ("departed", "departed"),
    ],
)
def test_leader_eligibility_matrix(scenario, status):
    c = mapping_case()
    rows = list(example_records())
    if scenario == "missing":
        rows = [r for r in rows if r.email != "one@example.test"]
    elif scenario == "moved":
        rows = [
            r.model_copy(update={"manager_email": "two@example.test"})
            if r.email == "one@example.test"
            else r
            for r in rows
        ]
    elif scenario == "outside":
        rows = [
            r.model_copy(update={"manager_email": "unknown@example.test"})
            if r.email == "one@example.test"
            else r
            for r in rows
        ]
    else:
        rows = [
            r.model_copy(update={"manager_email": "two@example.test"})
            if r.manager_email == "one@example.test"
            else r
            for r in rows
            if r.email != "one@example.test"
        ]
    candidate = prepare(
        tuple(rows),
        envelope("next", NOW + timedelta(hours=1)),
        c.config,
        c.head,
        NOW + timedelta(hours=1),
    )
    health = role_health(c.config, {p.email: p for p in candidate.people}, {r.email for r in rows})
    assert (
        next(r for r in health if r["role"] == "leader" and r["segment_id"] == "one")["status"]
        == status
    )
    assert ("LOB_LEADER_REVIEW", "one:one@example.test") in candidate.issues
    assert all(p.accountable_leader_email != "one@example.test" for p in candidate.people)
    if scenario != "departed":
        assert not next(p for p in candidate.people if p.email == "one@example.test").absence_review


# Every nominated role survives invalid leadership, repeated feeds and missing tenancy associations.
def test_multirole_departures_independent_and_unresolved_return():
    c = mapping_case()
    config = c.config.model_copy(
        update={
            "lobs": (
                c.config.lobs[0].model_copy(
                    update={"designee_emails": ("delegate@example.test", "one@example.test")}
                ),
                c.config.lobs[1].model_copy(update={"designee_emails": ("delegate@example.test",)}),
            )
        }
    )
    rows = tuple(
        r.model_copy(update={"manager_email": "two@example.test"})
        if r.manager_email == "one@example.test"
        else r
        for r in example_records()
        if r.email not in {"one@example.test", "delegate@example.test"}
    )
    first = prepare(
        rows,
        envelope("absence", NOW + timedelta(hours=1)),
        config,
        c.head,
        NOW + timedelta(hours=1),
    )
    expected = {
        ("LOB_LEADER_REVIEW", "one:one@example.test"),
        ("DESIGNEE_INVALID", "one:one@example.test"),
        ("DESIGNEE_INVALID", "one:delegate@example.test"),
        ("DESIGNEE_INVALID", "two:delegate@example.test"),
    }
    assert expected <= set(first.issues)
    repeated = prepare(
        rows,
        envelope("repeat", NOW + timedelta(hours=2)),
        config,
        revision(first),
        NOW + timedelta(hours=2),
    )
    assert expected <= set(repeated.issues)
    returning = prepare(
        example_records(),
        envelope("return", NOW + timedelta(hours=3)),
        config,
        revision(repeated),
        NOW + timedelta(hours=3),
    )
    assert expected <= set(returning.issues)
    assert next(p for p in returning.people if p.email == "one@example.test").absence_review


# Reusing fresh/stale source cannot change observation, absence or identity evidence.
@pytest.mark.parametrize("hours", [1, 100])
def test_configuration_only_reapply_does_not_observe_or_infer(hours):
    c = mapping_case()
    # Seed unreviewed omission without qualifying it as an absence in the initial partial source.
    rows = example_records()[:-1]
    initial = prepare(rows, envelope("partial", NOW, "partial"), c.config, c.head, NOW)
    head = revision(initial)
    updated = c.config.model_copy(
        update={
            "id": uuid4(),
            "lobs": (
                c.config.lobs[0].model_copy(update={"label": "Changed", "designee_emails": ()}),
                c.config.lobs[1],
            ),
        }
    )
    result = prepare(
        rows,
        envelope("partial", NOW, "complete"),
        updated,
        head.model_copy(update={"source_captured_at": None}),
        NOW + timedelta(hours=hours),
        trusted_reapply=True,
        configuration_only=True,
    )
    before = {p.id: p for p in head.people}
    for p in result.people:
        old = before[p.id]
        for field in (
            "last_row_observed_at",
            "last_reference_observed_at",
            "last_source_capture_at",
            "last_qualified_census_at",
            "absence_review",
            "absence_review_since",
        ):
            assert getattr(p, field) == getattr(old, field)
    assert not result.absence_eligible and not result.rejected
    assert ("PERSON_ABSENCE_REVIEW", "engineer@example.test") not in result.issues


# A boundary exemption permits a missing root row, not missing segment leader/designee profiles.
def test_root_profile_exemption_and_optional_designees():
    config = example_config(required_root_profile=False)
    result = prepare(example_records()[1:], envelope(), config, None, NOW)
    assert result.absence_eligible and not any(
        kind == "LOB_LEADER_REVIEW" for kind, _ in result.issues
    )
    no_designees = config.model_copy(
        update={"lobs": tuple(s.model_copy(update={"designee_emails": ()}) for s in config.lobs)}
    )
    assert not any(
        kind == "DESIGNEE_INVALID"
        for kind, _ in prepare(example_records(), envelope(), no_designees, None, NOW).issues
    )


# Actual preview computation exposes label/routing changes and rejects different revision fences.
def test_mapping_preview_impact_roles_initial_and_graph_rejection():
    c = mapping_case()
    proposed = c.request.candidate.model_dump()
    proposed["segments"][0]["label"] = "Renamed"
    proposed["segments"][0]["designee_emails"] = ()
    request = c.request.model_copy(update={"candidate": MappingCandidate.model_validate(proposed)})
    view, candidate = c.service._compute(
        c.connection, "w", request, c.config, c.head, c.context, (), NOW + timedelta(hours=1), 99
    )
    assert view.affected_count == 3 and view.page == view.pages == 1
    assert view.changes and candidate.id != c.config.id
    assert next(p for p in view.items if p.email == "engineer@example.test").after_designees == ()
    with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
        c.service._compute(
            c.connection, "w", request, c.config, c.head, MappingContext(), (), NOW, 1
        )
    initial = MappingRequest(
        context=MappingContext(),
        candidate=MappingCandidate.model_validate(
            {
                "root_email": "root@example.test",
                "segments": ({"label": "New", "leader_email": "new@example.test"},),
            }
        ),
    )
    view, _ = c.service._compute(
        c.connection, "w", initial, None, None, MappingContext(), (), NOW, 1
    )
    assert not view.has_feed and view.roles[0].status == "not_verified" and view.affected_count == 0
    with patch("otm.organization.mapping.prepare", return_value=Mock(rejected=True)):
        with pytest.raises(OrganizationConflict, match="INVALID_GRAPH"):
            c.service._compute(c.connection, "w", request, c.config, c.head, c.context, (), NOW, 1)


# Reads/previews authorize scope and use coherent snapshots without writing initial configuration.
def test_mapping_service_read_preview_and_apply_boundaries():
    c = mapping_case()
    with (
        patch("otm.organization.mapping.read_snapshot", return_value=nullcontext(c.connection)),
        patch.object(c.service, "_state", return_value=(c.config, c.head, c.context, ())),
    ):
        view = c.service.read("principal")
        preview = c.service.preview("principal", c.request)
    assert view.configured and not view.root_editable
    command = MappingApply(**c.request.model_dump(), preview_token=preview.preview_token)
    with (
        patch.object(c.service, "_state", return_value=(c.config, c.head, c.context, ())),
        patch("otm.tenancies.directory.registry_state", return_value=Mock()),
        patch.object(c.service, "read", return_value=view),
    ):
        assert c.service.apply(Mock(actor=Mock()), command) == view
        c.workflow._reapply.assert_called_once()
        assert c.workflow._reapply.call_args.kwargs["configuration_only"]
        with pytest.raises(OrganizationConflict, match="PREVIEW_CHANGED"):
            c.service.apply(
                Mock(actor=Mock()), command.model_copy(update={"preview_token": "0" * 64})
            )
    with (
        patch.object(
            c.service, "_state", return_value=(c.config, c.head, c.context, ("PENDING_LIFECYCLE",))
        ),
        pytest.raises(OrganizationConflict, match="PENDING_WORK"),
    ):
        c.service.apply(Mock(actor=Mock()), command)
    # Empty-workspace setup and pre-feed edits still use one audit and the current source policy.
    for config in (None, c.config):
        context = MappingContext(configuration_id=config.id) if config else MappingContext()
        candidate = editable(c.config).model_dump()
        if config is None:
            for s in candidate["segments"]:
                s["id"] = None
        request = MappingRequest(
            context=context, candidate=MappingCandidate.model_validate(candidate)
        )
        preview, _ = c.service._compute(
            c.connection, "w", request, config, None, context, (), NOW, 1
        )
        with (
            patch.object(c.service, "_state", return_value=(config, None, context, ())),
            patch.object(c.service, "read", return_value=view),
        ):
            c.service.apply(
                Mock(actor=Mock()),
                MappingApply(**request.model_dump(), preview_token=preview.preview_token),
            )
    assert c.store._audit.call_count == 3


# Direct Apply cannot bypass recomputed replacement eligibility.
def test_apply_enforces_recomputed_leader_blocker():
    c = mapping_case()
    body = c.request.candidate.model_dump()
    body["segments"][0]["leader_email"] = "not-in-source@example.test"
    request = c.request.model_copy(update={"candidate": MappingCandidate.model_validate(body)})
    view, _ = c.service._compute(
        c.connection, "w", request, c.config, c.head, c.context, (), NOW, 1
    )
    assert "INELIGIBLE_REPLACEMENT_LEADER" in view.blockers
    command = MappingApply(**request.model_dump(), preview_token=view.preview_token)
    with patch.object(c.service, "_state", return_value=(c.config, c.head, c.context, ())):
        with pytest.raises(OrganizationConflict, match="PENDING_WORK"):
            c.service.apply(Mock(actor=Mock()), command)
    c.workflow._reapply.assert_not_called()
    c.store._audit.assert_not_called()


# All nominee defects are assessed while healthy peers remain effective recipients.
def test_designee_peers_partial_stale_and_acknowledged_departures():
    from otm.organization.contracts import ReviewDecision

    config = example_config()
    config = config.model_copy(
        update={
            "lobs": (
                config.lobs[0].model_copy(
                    update={
                        "designee_emails": (
                            "delegate@example.test",
                            "engineer@example.test",
                            "unknown@example.test",
                        )
                    }
                ),
                config.lobs[1],
            )
        }
    )
    initial = revision(prepare(example_records(), envelope(), config, None, NOW))
    rows = tuple(r for r in example_records() if r.email != "delegate@example.test")
    missing = prepare(
        rows,
        envelope("missing", NOW + timedelta(hours=1)),
        config,
        initial,
        NOW + timedelta(hours=1),
    )
    target = "one:delegate@example.test"
    acknowledged = config.model_copy(
        update={
            "review_decisions": (
                ReviewDecision(
                    kind="DESIGNEE_INVALID",
                    target=target,
                    disposition="ignored",
                    recorded_at=NOW,
                    actor="verified-admin",
                    reason="Historical decision",
                ),
            )
        }
    )
    result = prepare(
        rows,
        envelope("again", NOW + timedelta(hours=2)),
        acknowledged,
        revision(missing),
        NOW + timedelta(hours=2),
    )
    assert ("DESIGNEE_INVALID", target) in result.issues
    engineer = next(p for p in result.people if p.email == "engineer@example.test")
    assert engineer.designee_emails == ("engineer@example.test",)
    for completeness, age in (("partial", 1), ("complete", 100)):
        candidate = prepare(
            rows,
            envelope("unqualified", NOW + timedelta(minutes=1), completeness),
            config,
            initial,
            NOW + timedelta(hours=age),
            trusted_reapply=True,
        )
        assert not next(
            p for p in candidate.people if p.email == "delegate@example.test"
        ).absence_review
    assert ("DESIGNEE_INVALID", "one:unknown@example.test") in result.issues


# State distinguishes an applied paired proposal from real pending intake and scoped lifecycle work.
@pytest.mark.parametrize(
    "pending,proposal",
    [(False, "none"), (False, "applied"), (False, "unapplied"), (True, "applied")],
)
def test_mapping_state_head_and_pending_guards(pending, proposal):
    c = mapping_case()
    row = dict(
        configuration=c.config.model_dump(mode="json"),
        configuration_id=c.config.id,
        applied_version_id=c.head.id,
        proposed_version_id=c.head.id if proposal != "none" else None,
        registry_revision=4,
    )
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    c.connection.scalar.return_value = uuid4() if pending else None
    c.store._revision.side_effect = [
        c.head,
        c.head.model_copy(update={"id": uuid4(), "snapshot_id": uuid4()})
        if proposal == "unapplied"
        else c.head,
    ]
    _, _, context, blockers = c.service._state(c.connection, "w", lock=True)
    assert context.registry_revision == 4
    assert ("PENDING_LIFECYCLE" in blockers) == pending
    assert ("UNAPPLIED_ORGANIZATION" in blockers) == (proposal == "unapplied")
    assert "w" in str(c.connection.execute.call_args.args[0].compile().params.values())


# An empty workspace snapshot has neither accidental defaults nor a privileged configuration write.
def test_empty_mapping_state_is_read_only():
    c = mapping_case()
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    c.connection.scalar.return_value = None
    assert c.service._state(c.connection, "w") == (None, None, MappingContext(), ())
    c.store._audit.assert_not_called()


# Historical acknowledgments cannot change current absence flags during a mapping-only edit.
def test_mapping_reapply_preserves_historically_suppressed_absence():
    from otm.organization.contracts import ReviewDecision
    from otm.organization.review_rules import issue_basis
    from otm.organization.reviews import administrative_decision_history

    c = mapping_case()
    people = tuple(
        p.model_copy(update={"absence_review": True, "absence_review_since": NOW})
        if p.email == "engineer@example.test"
        else p
        for p in c.head.people
    )
    previous = c.head.model_copy(update={"people": people})
    person = next(p for p in people if p.email == "engineer@example.test")
    decision = ReviewDecision(
        kind="PERSON_ABSENCE_REVIEW",
        target=person.email,
        disposition="resolved",
        person_id=person.id,
        basis=issue_basis("PERSON_ABSENCE_REVIEW", person.email, people),
        recorded_at=NOW,
        actor="verified-admin",
        reason="Reviewed",
    )
    old = c.config.model_copy(update={"review_decisions": (decision,)})
    edited = old.model_copy(update={"id": uuid4()})
    assert administrative_decision_history(previous, old, edited, {person.email}) == previous
    newly_recorded = administrative_decision_history(previous, c.config, old, {person.email})
    settled = next(p for p in newly_recorded.people if p.id == person.id)
    assert not settled.absence_review and settled.absence_review_since is None
    excluded = c.config.model_copy(update={"managed_exclusions": (person.id,)})
    assert (
        administrative_decision_history(
            previous, excluded, excluded.model_copy(update={"id": uuid4()}), set()
        )
        == previous
    )
    absent = administrative_decision_history(previous, c.config, excluded, set())
    assert not next(p for p in absent.people if p.id == person.id).absence_review
    assert next(p for p in absent.people if p.id == person.id).absence_review_since == NOW


# Explicit preview-bound replacement never invents reporting edges or a census.
@pytest.mark.parametrize("successor", ["successor@example.test", "engineer@example.test"])
def test_explicit_root_replacement_previews_reporting_gaps_without_new_observation(successor):
    c = mapping_case()
    request = MappingRequest(
        context=c.context,
        candidate=c.request.candidate.model_copy(update={"root_email": successor}),
        change_root=True,
    )
    view, candidate = c.service._compute(
        c.connection, "w", request, c.config, c.head, c.context, (), NOW, 1
    )
    assert view.root_before == c.config.policy.root_email
    assert view.root_present == (successor == "engineer@example.test")
    assert view.unresolved_count >= 4
    assert all(i.after_ancestry == "incomplete" for i in view.items if i.email != successor)
    assert (
        view.preview_token
        != c.service._compute(
            c.connection, "w", c.request, c.config, c.head, c.context, (), NOW, 1
        )[0].preview_token
    )
    assert candidate.policy.model_dump(exclude={"root_email"}) == c.config.policy.model_dump(
        exclude={"root_email"}
    )
    assert [s.id for s in candidate.lobs] == [s.id for s in c.config.lobs]
    assert all(r.status == "ancestry_incomplete" for r in view.roles if r.role == "leader")
    # A fresh upload still must give every non-root employee a manager.
    fresh = prepare(example_records(), envelope(), candidate, c.head, NOW)
    assert fresh.rejected and any(
        d.code == "MANAGER_REQUIRED" and d.fatal for d in fresh.diagnostics
    )


# Root display names are bounded and preview-bound, independent of identity and source trust.
def test_root_name_normalization_guard_and_projection():
    from otm.organization.contracts import Configuration
    from otm.organization.web import project

    c = mapping_case()
    body = editable(c.config).model_dump()
    body["root_name"] = "  Organization Director  "
    candidate = MappingCandidate.model_validate(body)
    assert candidate.root_name == "Organization Director"
    request = MappingRequest(context=c.context, candidate=candidate, change_root=True)
    updated = candidate_configuration("w", c.config, None, request)
    assert updated.root_name == "Organization Director" and updated.policy == c.config.policy
    assert (
        Configuration.model_validate(
            {**updated.model_dump(), "root_name": "  Director  "}
        ).root_name
        == "Director"
    )
    with pytest.raises(OrganizationConflict, match="ROOT_FIXED"):
        candidate_configuration(
            "w", c.config, None, request.model_copy(update={"change_root": False})
        )
    for invalid in ("   ", "x" * 257):
        with pytest.raises(ValueError):
            MappingCandidate.model_validate({**body, "root_name": invalid})
        with pytest.raises(ValueError):
            Configuration.model_validate({**updated.model_dump(), "root_name": invalid})
    assert editable(updated).root_name == "Organization Director"
    # Omitted root rows retain their true observation history and configured/reference profile.
    for records in (
        c.records,
        tuple(r for r in c.records if r.email != c.config.policy.root_email),
    ):
        computed = prepare(
            records,
            c.source,
            updated,
            c.head,
            NOW + timedelta(hours=1),
            trusted_reapply=True,
            configuration_only=True,
        )
        root = next(p for p in computed.people if p.email == updated.policy.root_email)
        old = next(p for p in c.head.people if p.email == updated.policy.root_email)
        assert root.full_name == "Organization Director" and root.id == old.id
        assert root.last_row_observed_at == old.last_row_observed_at
        rows, _ = project(updated, revision(computed), c.head)
        assert {
            p.manager_name for p in rows if p.email in {"one@example.test", "two@example.test"}
        } == {"Organization Director"}
    view, _ = c.service._compute(
        c.connection, "w", request, c.config, c.head, c.context, (), NOW, 1
    )
    assert view.root_name_before is None and view.candidate.root_name == "Organization Director"
