"""Offline required-user email tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_user_presence_check_units import NOW, case

from otm.email_policy import MailPolicy
from otm.notifications.contracts import RecipientReason, RequiredUserMissingNotice
from otm.notifications.recipients import recipient_still_authorized, required_user_recipients
from otm.notifications.service import decode_intent, list_for_operation
from otm.operations.contracts import canonical_hash
from otm.tenancies.presence_alerts import advance_episodes, delivery_issue, stage_missing
from otm.tenancies.presence_context import subject_scope
from otm.tenancies.presence_contracts import PresenceCheckEvidence, PresenceNoticeEpisode


# Construct current role identities independently of recipient addresses and administrator grants.
def routing_case(c):
    owner, manager, designee = [uuid4() for _ in range(3)]
    people = {
        owner: SimpleNamespace(
            id=owner,
            email="owner@example.test",
            profile="employee",
            absence_review=False,
            manager_email="manager@example.test",
            designee_emails=("designee@example.test",),
        ),
        manager: SimpleNamespace(
            id=manager, email="manager@example.test", profile="employee", absence_review=False
        ),
        designee: SimpleNamespace(
            id=designee, email="designee@example.test", profile="employee", absence_review=False
        ),
    }
    state = SimpleNamespace(
        people=people,
        supplied={p.email for p in people.values()},
        controls={key: {"directory_status": "included"} for key in people},
        context=SimpleNamespace(applied_version_id=uuid4(), configuration_id=uuid4()),
        associations=Mock(
            return_value=({"person_id": owner, "role": "owner", "status": "active"},)
        ),
    )
    grant = {
        "id": uuid4(),
        "email": "admin@example.test",
        "status": "active",
        "authorization_revision": uuid4(),
    }
    c.routing, c.grants, c.owner, c.manager, c.designee = state, [grant], owner, manager, designee
    return c


# Use real closed observations, converting only independently declared simulated presence facts.
def observations(c, a="missing", b="present"):
    result = []
    for observation, state in zip(c.evidence.results, (a, b), strict=True):
        values = observation.model_dump(mode="python")
        if state == "missing":
            values.update(state="missing", safe_code="USER_MISSING", observed=None)
        elif state == "unknown":
            values.update(
                state="unknown",
                safe_code="ACCESS_UNVERIFIED",
                authorized=False,
                complete=False,
                observed=None,
            )
        result.append(type(observation).model_validate(values))
    return tuple(result)


# Build a valid latest sealed record with optional per-subject incident state and immutable proof.
def saved(c, episodes=None, *, results=None, sequence=1):
    if results is None:
        results = (
            observations(c, *("missing" if e.episode_id else "present" for e in episodes))
            if episodes
            else c.evidence.results
        )
    state = "complete" if all(r.state != "unknown" for r in results) else "unavailable"
    evidence = c.evidence.model_copy(
        update={
            "notice_episodes": episodes,
            "results": results,
            "state": state,
            "safe_code": "USER_PRESENCE_CHECK_COMPLETE"
            if state == "complete"
            else "USER_PRESENCE_UNAVAILABLE",
        }
    )
    data = evidence.model_dump(mode="json")
    return {
        **c.check,
        "results": data["results"],
        "state": state,
        "acquisition_sequence": sequence,
        "data": data,
        "data_hash": canonical_hash(data),
    }


# Repeated Missing/Unknown keeps one open episode; Present resolves only its own subject.
@pytest.mark.parametrize(
    "states,existing,changed,opened",
    [
        (("missing", "present"), False, False, ("automation",)),
        (("missing", "missing"), False, False, ("automation", "recovery")),
        (("missing", "unknown"), True, False, ()),
        (("unknown", "unknown"), True, False, ()),
        (("present", "missing"), True, False, ("recovery",)),
        (("missing", "present"), True, True, ("automation",)),
    ],
)
def test_episode_transitions(states, existing, changed, opened):
    c = case()
    previous_id = uuid4()
    prior = tuple(
        PresenceNoticeEpisode(
            purpose=t.purpose,
            scope_hash=subject_scope(c.snapshot, t.purpose),
            episode_id=previous_id if existing and t.purpose == "automation" else None,
        )
        for t in c.snapshot.subjects
    )
    snapshot = c.snapshot.model_copy(update={"connection_revision": 2}) if changed else c.snapshot
    with (
        patch("otm.tenancies.presence_alerts.require_transaction"),
        patch("otm.tenancies.presence_alerts.latest_check", return_value=saved(c, prior)),
    ):
        episodes, started = advance_episodes(
            c.connection,
            c.row,
            {**c.check, "acquisition_sequence": 2},
            snapshot,
            observations(c, *states),
        )
    assert started == opened
    assert (
        episodes[0].episode_id == previous_id
        if existing and not changed and states[0] != "present"
        else episodes[0].episode_id != previous_id
    )
    assert episodes[0].episode_id is None if states[0] == "present" else True


# Initial and legacy head absence is safe; late completions cannot rewrite incident heads or notify.
@pytest.mark.parametrize("mode", ["initial", "legacy", "late", "corrupt", "scope"])
def test_episode_head_guards(mode):
    c = case()
    latest = None if mode == "initial" else saved(c, sequence=3 if mode == "late" else 1)
    if mode == "corrupt":
        latest["data_hash"] = "0" * 64
    if mode == "scope":
        episodes = tuple(
            PresenceNoticeEpisode(purpose=t.purpose, scope_hash="0" * 64, episode_id=None)
            for t in c.snapshot.subjects
        )
        latest = saved(c, episodes)
    with (
        patch("otm.tenancies.presence_alerts.require_transaction"),
        patch("otm.tenancies.presence_alerts.latest_check", return_value=latest),
    ):
        if mode in {"corrupt", "scope"}:
            with pytest.raises(ValueError):
                advance_episodes(
                    c.connection,
                    c.row,
                    {**c.check, "acquisition_sequence": 2},
                    c.snapshot,
                    observations(c),
                )
        else:
            episodes, opened = advance_episodes(
                c.connection,
                c.row,
                {**c.check, "acquisition_sequence": 2},
                c.snapshot,
                observations(c),
            )
            assert (episodes, opened) == (None, ()) if mode == "late" else opened == ("automation",)


# Registry name/revision changes are not a new incident; exact subjects and selected connection are.
def test_subject_incident_scope():
    c = case()
    original = subject_scope(c.snapshot, "automation")
    assert (
        subject_scope(
            c.snapshot.model_copy(update={"tenancy_name": "Renamed", "tenancy_revision": 9}),
            "automation",
        )
        == original
    )
    assert (
        subject_scope(c.snapshot.model_copy(update={"connection_revision": 2}), "automation")
        != original
    )
    assert "notice_policy_version" not in c.intent.model_dump(mode="json")
    assert "notice_episodes" not in c.evidence.model_dump(mode="json")
    with pytest.raises(ValidationError):
        PresenceCheckEvidence.model_validate_json(
            c.evidence.model_copy(
                update={
                    "notice_episodes": tuple(
                        PresenceNoticeEpisode(
                            purpose=t.purpose, scope_hash=original, episode_id=None
                        )
                        for t in reversed(c.snapshot.subjects)
                    )
                }
            ).model_dump_json()
        )


# Multiple roles use one normalized original contact; the test override must not erase provenance.
def test_role_dedup_and_live_entitlement():
    c = routing_case(case())
    owner = c.routing.people[c.owner]
    manager = c.routing.people[c.manager]
    owner.designee_emails = (manager.email,)
    c.grants[0]["email"] = manager.email
    targets, issues = required_user_recipients(c.routing, c.grants, c.snapshot.tenancy_id)
    assert len(targets) == 2 and not issues
    reasons = targets[manager.email]
    assert {r.role for r in reasons} == {"manager", "designee", "administrator"}
    notice = SimpleNamespace(
        tenancy_id=c.snapshot.tenancy_id, original_recipient=manager.email, reasons=reasons
    )
    assert recipient_still_authorized(notice, c.routing, c.grants)
    c.routing.associations.return_value = ()
    c.grants[0]["authorization_revision"] = uuid4()
    assert not recipient_still_authorized(notice, c.routing, c.grants)


# Missing role contacts remain visible and use existing administrator routing without
# inventing people.
@pytest.mark.parametrize(
    "fault",
    [
        "absent",
        "reference",
        "offboarded",
        "merged",
        "no_control",
        "bad_email",
        "missing_owner",
        "no_designees",
        "no_admin",
        "bad_admin",
        "no_admin_email",
        "revoked",
    ],
)
def test_routing_unavailable_contacts(fault):
    c = routing_case(case())
    owner = c.routing.people[c.owner]
    if fault == "absent":
        c.routing.supplied.remove(owner.email)
    if fault == "reference":
        owner.profile = "reference"
    if fault in {"offboarded", "merged"}:
        c.routing.controls[c.owner]["directory_status"] = fault
    if fault == "no_control":
        del c.routing.controls[c.owner]
    if fault == "bad_email":
        c.routing.supplied.remove(owner.email)
        owner.email = "bad address"
        c.routing.supplied.add(owner.email)
    if fault == "missing_owner":
        c.routing.associations.return_value = ()
    if fault == "no_designees":
        owner.designee_emails = ()
    if fault == "no_admin":
        c.grants = []
    if fault == "bad_admin":
        c.grants[0]["email"] = "bad address"
    if fault == "no_admin_email":
        c.grants[0]["email"] = None
    if fault == "revoked":
        c.grants[0]["status"] = "revoked"
    recipients, issues = required_user_recipients(c.routing, c.grants, c.snapshot.tenancy_id)
    assert recipients
    if fault == "no_admin_email":
        assert None in recipients and "administrator_unavailable" in issues
    else:
        assert issues


# Fixed contracts prevent person/admin authority substitution and partial administrator proofs.
@pytest.mark.parametrize(
    "fields",
    [
        {"role": "owner"},
        {"role": "owner", "person_id": uuid4(), "administrator_id": uuid4()},
        {"role": "administrator", "person_id": uuid4()},
        {"role": "administrator", "administrator_id": uuid4()},
    ],
)
def test_recipient_reason_scope(fields):
    with pytest.raises(ValidationError):
        RecipientReason(**fields)


# A complete synthetic notice gives the submission guard real sealed evidence and current role
# facts.
def notice_case():
    c = routing_case(case())
    c.connection = MagicMock()
    c.episodes = tuple(
        PresenceNoticeEpisode(
            purpose=t.purpose,
            scope_hash=subject_scope(c.snapshot, t.purpose),
            episode_id=uuid4() if t.purpose == "automation" else None,
        )
        for t in c.snapshot.subjects
    )
    c.latest = saved(c, c.episodes, results=observations(c))
    policy = MailPolicy(environment="staging", email_override="capture@example.test")
    c.notifier = SimpleNamespace(
        policy=policy,
        enqueuer=Mock(),
        profile_hash="a" * 64,
        application_origin="https://atlas.example.test",
    )
    c.notice = RequiredUserMissingNotice(
        operation_id=c.row["id"],
        tenancy_id=c.snapshot.tenancy_id,
        purpose="automation",
        scope_hash=c.episodes[0].scope_hash,
        episode_id=c.episodes[0].episode_id,
        check_context_hash=c.check["context_hash"],
        organization_version_id=c.routing.context.applied_version_id,
        configuration_id=c.routing.context.configuration_id,
        reasons=(RecipientReason(role="owner", person_id=c.owner),),
        original_recipient="owner@example.test",
        delivery_recipient="capture@example.test",
        route=policy.route("owner@example.test"),
        application_origin=c.notifier.application_origin,
        delivery_profile_hash="a" * 64,
        created_at=NOW,
    )
    c.delivery = SimpleNamespace(
        workspace=c.row["workspace_id"],
        presence_context_loader=Mock(
            return_value=SimpleNamespace(execution_paused=False, policy=c.policy)
        ),
        policy_loader=Mock(return_value=policy),
        application_origin=c.notifier.application_origin,
        transport=SimpleNamespace(profile_hash="a" * 64),
    )
    return c


# Staging binds dedup to incident/original recipient; unknown delivery knowledge is never a
# new send.
@pytest.mark.parametrize("mode", ["new", "repeat", "empty", "blocked", "no_admin"])
def test_stage_notifications(mode):
    c = notice_case()
    c.connection.scalar.return_value = uuid4() if mode == "repeat" else None
    c.connection.execute.return_value.mappings.return_value.all.return_value = c.grants
    if mode == "blocked":
        c.notifier.policy = MailPolicy(environment="local")
    if mode == "no_admin":
        c.grants = []
        c.connection.execute.return_value.mappings.return_value.all.return_value = []
    with (
        patch("otm.tenancies.presence_alerts.require_transaction"),
        patch("otm.tenancies.presence_alerts.registry_state", return_value=c.routing),
        patch("otm.tenancies.presence_alerts.record_evidence") as record,
    ):
        stage_missing(
            c.notifier,
            c.connection,
            c.row,
            c.check,
            c.snapshot,
            c.episodes,
            () if mode == "empty" else ("automation",),
            NOW,
        )
    assert record.call_count == 0 if mode in {"repeat", "empty"} else record.call_count > 0
    assert (
        c.notifier.enqueuer.enqueue.call_count == 0
        if mode in {"repeat", "empty", "blocked"}
        else c.notifier.enqueuer.enqueue.call_count > 0
    )
    # The same decode/list code validates the new family without treating it as lifecycle failure.
    payload = c.notice.model_dump(mode="json")
    row = {
        "id": uuid4(),
        "operation_id": c.row["id"],
        "intent": payload,
        "intent_hash": canonical_hash(payload),
        "state": "pending",
        "created_at": NOW,
        "updated_at": NOW,
        "last_attempt_at": None,
        "attempts": 0,
        "safe_code": None,
    }
    assert decode_intent(row) == c.notice
    c.connection.execute.return_value.mappings.return_value = [row]
    summary = list_for_operation(c.connection, c.row["workspace_id"], c.row["id"])[0]
    assert summary.event == "required_user_missing" and summary.recipient_roles == ("owner",)


# Revalidate sealed subject/incident, live role and all egress policy fences without any
# transport call.
@pytest.mark.parametrize(
    "fault,expected",
    [
        (None, None),
        ("source", "EMAIL_CONTEXT_CHANGED"),
        ("hash", "EMAIL_CONTEXT_CHANGED"),
        ("not_missing", "EMAIL_CONTEXT_CHANGED"),
        ("old_episode", "EMAIL_CONTEXT_CHANGED"),
        ("no_latest", "EMAIL_CONTEXT_CHANGED"),
        ("resolved", "EMAIL_CONTEXT_CHANGED"),
        ("no_loader", "EMAIL_CONTEXT_CHANGED"),
        ("paused", "EMAIL_CONTEXT_CHANGED"),
        ("no_child", "EMAIL_CONTEXT_CHANGED"),
        ("changed_scope", "EMAIL_CONTEXT_CHANGED"),
        ("role", "EMAIL_RECIPIENT_CHANGED"),
        ("route", "EMAIL_ROUTE_BLOCKED"),
        ("origin", "EMAIL_APPLICATION_ORIGIN_CHANGED"),
        ("transport", "EMAIL_TRANSPORT_CHANGED"),
        ("redirect", "NOTIFICATION_ROUTE_INVALID"),
    ],
)
def test_delivery_fences(fault, expected):
    c = notice_case()
    source = c.latest
    latest = c.latest
    snapshot = c.snapshot
    if fault == "source":
        source = None
    if fault == "hash":
        source = {**source, "context_hash": "0" * 64}
    if fault == "not_missing":
        source = saved(c)
    if fault == "old_episode":
        c.notice = c.notice.model_copy(update={"episode_id": uuid4()})
    if fault == "no_latest":
        latest = None
    if fault == "resolved":
        latest = saved(c, tuple(e.model_copy(update={"episode_id": None}) for e in c.episodes))
    if fault == "no_loader":
        c.delivery.presence_context_loader = None
    if fault == "paused":
        c.delivery.presence_context_loader.return_value.execution_paused = True
    if fault == "no_child":
        c.child = None
    if fault == "changed_scope":
        snapshot = snapshot.model_copy(update={"connection_revision": 2})
    if fault == "role":
        c.routing.associations.return_value = ()
    if fault == "route":
        c.delivery.policy_loader.return_value = MailPolicy(environment="local")
    if fault == "origin":
        c.delivery.application_origin = "https://other.example.test"
    if fault == "transport":
        c.delivery.transport.profile_hash = "b" * 64
    if fault == "redirect":
        c.notice = c.notice.model_copy(update={"delivery_recipient": "other@example.test"})
    first = Mock()
    first.mappings.return_value.one_or_none.return_value = source
    second = Mock()
    second.mappings.return_value.one_or_none.return_value = c.child
    third = Mock()
    third.mappings.return_value.all.return_value = c.grants
    c.connection.execute.side_effect = [first, second, third]
    with (
        patch("otm.tenancies.presence_alerts.latest_check", return_value=latest),
        patch("otm.tenancies.presence_alerts.capture_snapshot", return_value=snapshot),
        patch("otm.tenancies.presence_alerts.registry_state", return_value=c.routing),
    ):
        if fault == "redirect":
            with pytest.raises(ValueError, match=expected):
                delivery_issue(c.delivery, c.connection, {}, c.row, c.notice)
        else:
            outcome = delivery_issue(c.delivery, c.connection, {}, c.row, c.notice)
            assert outcome is None if expected is None else outcome[1] == expected


# Legacy reads stay non-alerting; incident evidence advances even while delivery is disabled.
@pytest.mark.parametrize("marker,configured", [(None, True), (1, False), (1, True)])
def test_worker_alert_composition(marker, configured):
    c = case()
    frozen = c.frozen.model_copy(
        update={"intent": c.intent.model_copy(update={"notice_policy_version": marker})}
    )
    check = {**c.check, "state": "reading", "acquisition_sequence": 1}
    c.worker.notifications = Mock() if configured else None
    episodes = tuple(
        PresenceNoticeEpisode(
            purpose=t.purpose,
            scope_hash=subject_scope(c.snapshot, t.purpose),
            episode_id=uuid4() if t.purpose == "automation" else None,
        )
        for t in c.snapshot.subjects
    )
    with (
        patch.object(c.worker, "locked", return_value=(c.row, frozen, c.child, check)),
        patch.object(c.worker, "current", return_value=True),
        patch("otm.tenancies.presence_worker.seal") as sealed,
        patch(
            "otm.tenancies.presence_alerts.advance_episodes",
            return_value=(episodes, ("automation",)),
        ) as advance,
        patch("otm.tenancies.presence_alerts.stage_missing") as staged,
    ):
        c.worker.finish(c.row["id"], check["attempt_id"], c.commands, observations(c))
    assert advance.call_count == int(marker == 1)
    assert staged.call_count == int(marker == 1 and configured)
    assert sealed.call_args.kwargs["notice_episodes"] == (episodes if marker == 1 else None)


# Outbox preparation creates fixed plain text without credentials or editable recipients.
@pytest.mark.parametrize(
    "purpose,origin", [("automation", True), ("recovery", True), ("recovery", False)]
)
def test_missing_email_envelope(purpose, origin):
    from contextlib import nullcontext

    from otm.notifications.worker import NotificationDeliveryWorker

    c = notice_case()
    notice = c.notice.model_copy(
        update={
            "purpose": purpose,
            "application_origin": c.notifier.application_origin if origin else None,
        }
    )
    data = notice.model_dump(mode="json")
    row = {
        "id": uuid4(),
        "operation_id": c.row["id"],
        "intent": data,
        "intent_hash": canonical_hash(data),
        "state": "pending",
        "attempts": 0,
        "next_attempt_at": None,
        "updated_at": NOW,
    }
    engine = Mock()
    engine.begin.side_effect = lambda: nullcontext(c.connection)
    worker = NotificationDeliveryWorker(
        engine, c.row["workspace_id"], lambda: NOW, lambda: c.notifier.policy, Mock(), Mock()
    )
    with (
        patch.object(worker, "_locked", return_value=(row, c.row)),
        patch.object(worker, "_context_issue", return_value=None),
        patch("otm.notifications.worker.record_evidence"),
    ):
        envelope, _ = worker._prepare(row["id"])
    assert (
        envelope.recipient == "capture@example.test"
        and envelope.subject == "Required tenancy user is missing"
    )
    assert purpose in envelope.body and "does not verify permissions" in envelope.body
    assert ("#required-users" in envelope.body) == origin
    with patch(
        "otm.tenancies.presence_alerts.delivery_issue",
        return_value=("blocked", "EMAIL_CONTEXT_CHANGED"),
    ) as guard:
        assert worker._context_issue(c.connection, row, c.row, notice) == (
            "blocked",
            "EMAIL_CONTEXT_CHANGED",
        )
        guard.assert_called_once()


# Incident metadata cannot contradict qualified Present/Missing outcomes even before persistence.
@pytest.mark.parametrize("state,identifier", [("present", uuid4()), ("missing", None)])
def test_episode_result_coherence(state, identifier):
    c = case()
    episodes = tuple(
        PresenceNoticeEpisode(
            purpose=t.purpose,
            scope_hash=subject_scope(c.snapshot, t.purpose),
            episode_id=identifier if t.purpose == "automation" else None,
        )
        for t in c.snapshot.subjects
    )
    with pytest.raises(ValidationError):
        PresenceCheckEvidence.model_validate_json(
            c.evidence.model_copy(
                update={"results": observations(c, state, "present"), "notice_episodes": episodes}
            ).model_dump_json()
        )


# Replacing one account's binding cannot restart the other account's continuing incident.
@pytest.mark.parametrize(
    "field", ["binding_generation", "provider_ocid", "scim_resource_id", "user_name"]
)
def test_incident_scope_is_independent_per_user(field):
    from otm.tenancies.presence_contracts import PresenceSnapshot

    c = case()
    original = c.snapshot.subjects[0]
    value = getattr(original, field)
    replacement = original.model_copy(
        update={field: value + 1 if isinstance(value, int) else value + "new"}
    )
    snapshot = PresenceSnapshot.model_validate_json(
        c.snapshot.model_copy(
            update={"subjects": (replacement, c.snapshot.subjects[1])}
        ).model_dump_json()
    )
    assert subject_scope(snapshot, "automation") != subject_scope(c.snapshot, "automation")
    assert subject_scope(snapshot, "recovery") == subject_scope(c.snapshot, "recovery")
