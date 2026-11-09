"""Recovery console observations remain independent of presence and current desired revisions."""

from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_onboarding import case as onboarding_case
from test_onboarding import registry
from test_user_presence_check_units import case

from otm.operations.contracts import canonical_hash
from otm.providers.lifecycle import OnboardingUsers
from otm.providers.recovery_console import RecoveryConsoleCapture
from otm.providers.recovery_console_simulator import (
    configured_console_capture,
    simulated_console_inspection,
)
from otm.recovery_console import parse_release_cidrs
from otm.tenancies.onboarding_users import capture_users
from otm.tenancies.presence import console_view, presence_views
from otm.tenancies.presence_contracts import RecoveryConsoleView
from otm.tenancies.presence_records import decode_result

__all__ = ["registry"]
POLICY = parse_release_cidrs("198.51.100.0/24,2001:db8::/32")
OTHER = parse_release_cidrs("203.0.113.0/24")


# Construct exact independent producer facts rather than seeding a read from expected settings.
def configured_case():
    c = case()
    capture = configured_console_capture(
        c.source.domain_ocid, c.source.recovery.scim_resource_id, "synthetic", POLICY
    )
    c.source = c.source.model_copy(update={"recovery_console": capture})
    c.snapshot = c.snapshot.model_copy(update={"recovery_console_fingerprint": POLICY.fingerprint})
    c.worker.recovery_console_loader = Mock(return_value=POLICY)
    c.worker.recovery_inspection_factory = simulated_console_inspection
    return c


# Both onboarding origins bind/read the exact policy before bootstrap cleanup can proceed.
@pytest.mark.parametrize("origin", ["create_tenancy", "import_tenancy"])
def test_onboarding_policy_capture_and_validation(registry, origin):
    app, intent, _, _ = onboarding_case(registry, origin)
    app.facade.recovery_console = POLICY
    intent = intent.model_copy(
        update={"onboarding_version": 3, "recovery_console_fingerprint": POLICY.fingerprint}
    )
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    users = capture_users(app.facade, intent, discovery.model_dump(mode="json"))
    assert users.recovery_console.facts.perimeter == POLICY
    assert users.recovery_console.scim_resource_id == users.recovery.scim_resource_id
    assert "198.51" not in repr(users)
    assert OnboardingUsers.model_validate_json(users.model_dump_json()) == users
    app.facade.recovery_console = OTHER
    with pytest.raises(ValueError):
        capture_users(app.facade, intent, discovery.model_dump(mode="json"))


# Missing/mismatched/incomplete or drifted setup evidence cannot establish recovery access.
@pytest.mark.parametrize("damage", ["absent", "mfa", "network", "incomplete"])
def test_bad_setup_capture_is_rejected(registry, damage):
    app, intent, _, _ = onboarding_case(registry)
    app.facade.recovery_console = POLICY
    intent = intent.model_copy(
        update={"onboarding_version": 3, "recovery_console_fingerprint": POLICY.fingerprint}
    )
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    users = app.facade.capture_onboarding_users(intent, discovery.model_dump(mode="json"))
    capture = users.recovery_console
    if damage == "absent":
        capture = None
    else:
        facts = capture.facts
        changes = (
            {"rules": (facts.rules[0].model_copy(update={"mfa": "required"}), *facts.rules[1:])}
            if damage == "mfa"
            else {"perimeter": OTHER}
            if damage == "network"
            else {"complete": False}
        )
        capture = capture.model_copy(update={"facts": facts.model_copy(update=changes)})
    with patch.object(
        app.facade,
        "capture_onboarding_users",
        return_value=users.model_copy(update={"recovery_console": capture}),
    ):
        with pytest.raises(ValueError, match="RECOVERY_CONSOLE_UNVERIFIED"):
            capture_users(app.facade, intent, discovery.model_dump(mode="json"))


# Read original producer facts; both controls require the matching desired revision.
def test_read_policy_and_changed_desired():
    c = configured_case()
    proof = c.worker.read_console(c.commands[1], c.source, c.snapshot)
    assert proof.result.state == "verified"
    c.worker.recovery_console_loader.return_value = OTHER
    snapshot = c.snapshot.model_copy(update={"recovery_console_fingerprint": OTHER.fingerprint})
    assert c.worker.read_console(c.commands[1], c.source, snapshot).result.state == "drift"
    assert c.worker.read_console(c.commands[1], c.source, c.snapshot).result.state == "unknown"


# Unknown, legacy and missing-adapter paths never turn successful presence into policy proof.
@pytest.mark.parametrize(
    "damage", ["source", "legacy", "adapter", "error", "policy", "unconfigured"]
)
def test_unverified_policy_read(damage):
    c = configured_case()
    source = c.source
    if damage == "source":
        source = None
    elif damage == "legacy":
        source = source.model_copy(update={"recovery_console": None})
    elif damage == "adapter":
        c.worker.recovery_inspection_factory = None
    elif damage == "error":
        c.worker.recovery_inspection_factory = Mock(side_effect=RuntimeError("private"))
    elif damage == "policy":
        c.worker.recovery_console_loader.return_value = None
    else:
        c.snapshot = c.snapshot.model_copy(update={"recovery_console_fingerprint": None})
    result = c.worker.read_console(c.commands[1], source, c.snapshot)
    assert result is None if damage == "unconfigured" else result.result.state == "unknown"


# Bind a sealed safe result to the same immutable row shape used by PostgreSQL publication.
def sealed_case():
    c = configured_case()
    proof = c.worker.read_console(c.commands[1], c.source, c.snapshot)
    digest = canonical_hash(c.snapshot.model_dump(mode="json"))
    c.evidence = c.evidence.model_copy(update={"context_hash": digest, "recovery_console": proof})
    c.check.update(context_hash=digest, context=c.snapshot.model_dump(mode="json"))
    payload = c.evidence.model_dump(mode="json")
    c.event = dict(data=payload, data_hash=canonical_hash(payload))
    return c


# Desired-policy changes and time expiry stale policy without discarding qualified user presence.
def test_shared_projection_policy_freshness():
    c = sealed_case()
    now = c.clock()
    assert console_view(c.snapshot, c.check, c.event, now).state == "verified"
    assert console_view(c.snapshot, c.check, c.event, now + timedelta(days=1)).state == "stale"
    changed = c.snapshot.model_copy(update={"recovery_console_fingerprint": OTHER.fingerprint})
    assert console_view(changed, c.check, c.event, now).state == "stale"
    assert all(
        v.state == "present" for v in presence_views(changed, c.check, c.event, now).values()
    )
    assert console_view(None, c.check, c.event, now).state == "unknown"
    assert console_view(c.snapshot, None, None, now).state == "not_checked"
    legacy = c.evidence.model_copy(update={"recovery_console": None}).model_dump(mode="json")
    event = dict(data=legacy, data_hash=canonical_hash(legacy))
    assert console_view(c.snapshot, c.check, event, now).state == "not_checked"
    altered = c.snapshot.model_copy(update={"connection_revision": 2})
    assert console_view(altered, c.check, c.event, now).state == "not_checked"


# Stored target, attempt, clock or desired fingerprints cannot be substituted in sealed evidence.
@pytest.mark.parametrize("damage", ["target", "context", "time", "fingerprint"])
def test_sealed_proof_scope_guards(damage):
    c = sealed_case()
    payload = c.evidence.model_dump(mode="json")
    proof = payload["recovery_console"]
    if damage == "target":
        proof["target"]["scim_resource_id"] = "other"
    elif damage == "context":
        proof["context"]["attempt_id"] = str(uuid4())
    elif damage == "time":
        proof["checked_at"] = (c.clock() + timedelta(seconds=1)).isoformat()
    else:
        proof["result"]["desired_fingerprint"] = OTHER.fingerprint
    with pytest.raises(ValueError):
        decode_result(c.check, payload, canonical_hash(payload))


# Exact source/domain identities and owned resource references are validated on capture too.
def test_capture_scope_and_public_positive_guards():
    c = configured_case()
    capture = c.source.recovery_console
    with pytest.raises(ValueError):
        RecoveryConsoleCapture.model_validate(
            {
                **capture.model_dump(),
                "scim_resource_id": "other",
                "facts": capture.facts.model_copy(update={"application_id": "foreign"}),
            }
        )
    with pytest.raises(ValueError):
        OnboardingUsers.model_validate(
            c.source.model_copy(
                update={
                    "recovery_console": capture.model_copy(update={"scim_resource_id": "other"})
                }
            )
        )
    with pytest.raises(ValueError):
        RecoveryConsoleView(state="verified", mfa_exemption="verified", network_boundary="verified")
    with pytest.raises(ValueError):
        RecoveryConsoleView(
            state="verified",
            checked_at=c.clock(),
            operation_id=uuid4(),
            desired_fingerprint=POLICY.fingerprint,
        )


# Waiting onboarding cannot configure or retire temporary access using cached obsolete settings.
@pytest.mark.parametrize("step", ["configure_required", "verify_required", "retire_temporary"])
def test_setup_rechecks_current_policy_before_effect(registry, step):
    app, intent, _, _ = onboarding_case(registry)
    app.facade.recovery_console = POLICY
    current = Mock(return_value=POLICY)
    app.facade.recovery_console_loader = current
    intent = intent.model_copy(
        update={"onboarding_version": 3, "recovery_console_fingerprint": POLICY.fingerprint}
    )
    discovery = app.facade.inspect_onboarding(intent, app.facade.onboarding_handoff(intent))
    app.facade.onboarding_step(intent, step, discovery.model_dump(mode="json"))
    for changed in (OTHER, None):
        current.return_value = changed
        with pytest.raises(ValueError, match="TARGET_CHANGED"):
            app.facade.onboarding_step(intent, step, discovery.model_dump(mode="json"))
        with pytest.raises(ValueError):
            capture_users(app.facade, intent, discovery.model_dump(mode="json"))


# Replacement recovery identities cannot inherit an old user's exact selectors or policy proof.
def test_recreated_recovery_needs_new_exact_policy():
    c = configured_case()
    changed = c.source.model_dump()
    changed["recovery"]["scim_resource_id"] = "recreated-recovery"
    with pytest.raises(ValueError):
        OnboardingUsers.model_validate(changed)
