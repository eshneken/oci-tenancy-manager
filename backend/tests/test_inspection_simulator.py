"""Stateful inspection scenarios to share with a future qualified real-adapter contract suite."""

from datetime import timedelta
from uuid import uuid4

import pytest

from otm.providers.inspection_contracts import (
    InspectionConfirmed,
    InspectionUnobservable,
    InspectionUnsupported,
)
from otm.providers.inspection_simulator import ManualClock, SimulatedInspectionProvider


# A successful read returns actual facts with an immutable, attempt-linked observation.
def test_confirmation_matches_child_and_resolves_retained_read_evidence(inspection):
    result = inspection.service.inspect(inspection.command)
    assert isinstance(result, InspectionConfirmed)
    assert result.tenancy.tenancy_ocid == inspection.command.payload.tenancy_ocid
    assert result.tenancy.parent_tenancy_ocid == inspection.command.payload.parent_tenancy_ocid
    attempt, facts = inspection.provider.read_evidence(result.evidence[0].evidence_ref)
    assert attempt == inspection.command.context.attempt_id and facts == result.tenancy
    assert result.milestone == "tenancy_inspected" and result.identity is None
    assert inspection.clock.now() == result.observed_at


# Keep delayed provider state unobservable until explicit clock advance.
def test_delayed_visibility_uses_observation_wait_and_explicit_clock_advance(inspection):
    inspection.provider.set_tenancy(
        inspection.tenancy.model_copy(
            update={"visible_at": inspection.clock.now() + timedelta(minutes=1)}
        )
    )
    before = inspection.service.inspect(inspection.command)
    assert isinstance(before, InspectionUnobservable)
    assert before.safe_code == "READ_DELAYED" and before.continuation == "observe"
    inspection.clock.advance(timedelta(minutes=1))
    assert isinstance(inspection.service.inspect(inspection.command), InspectionConfirmed)
    assert before.kind == "unobservable"


# An earlier successful read cannot conceal later loss of the selected binding's access.
def test_revocation_after_success_is_visible_without_cached_confirmation(inspection):
    original = inspection.service.inspect(inspection.command)
    inspection.provider.set_access(inspection.access.model_copy(update={"permitted": False}))
    result = inspection.service.inspect(inspection.command)
    assert isinstance(result, InspectionUnobservable)
    assert result.safe_code == "ACCESS_DENIED" and result.continuation == "manual"
    assert original.kind == "confirmed"


# A context mismatch cannot select a different workspace, binding or credential generation.
@pytest.mark.parametrize(
    "context_field", ["workspace_id", "access_binding_id", "credential_generation"]
)
def test_unknown_or_stale_binding_never_falls_back_to_other_access(inspection, context_field):
    value = (
        "other-workspace"
        if context_field == "workspace_id"
        else uuid4()
        if context_field == "access_binding_id"
        else 2
    )
    command = inspection.command.model_copy(
        update={"context": inspection.command.context.model_copy(update={context_field: value})}
    )
    result = inspection.service.inspect(command)
    assert result.kind == "unobservable" and result.safe_code == "ACCESS_UNVERIFIED"
    assert result.evidence == ()


# A rotated binding is usable only when the caller explicitly resolves its new generation.
def test_changed_credential_generation_requires_matching_attempt_context(inspection):
    inspection.provider.set_access(
        inspection.access.model_copy(update={"credential_generation": 2})
    )
    old = inspection.service.inspect(inspection.command)
    assert old.safe_code == "ACCESS_UNVERIFIED"
    current = inspection.command.model_copy(
        update={
            "context": inspection.command.context.model_copy(
                update={"credential_generation": 2, "attempt_id": uuid4()}
            )
        }
    )
    result = inspection.service.inspect(current)
    assert result.kind == "confirmed"
    assert result.attempt_id != old.attempt_id


# A valid selected binding does not authorize every registered child.
def test_target_not_in_binding_scope_is_denied_without_disclosing_other_state(inspection):
    inspection.provider.set_access(
        inspection.access.model_copy(update={"tenancy_ocids": frozenset()})
    )
    result = inspection.service.inspect(inspection.command)
    assert result.safe_code == "ACCESS_DENIED" and result.evidence == ()


# Lack of a record does not prove absence or authorize deletion/adoption.
def test_absent_provider_record_is_unobservable_not_confirmed_missing(inspection):
    provider = SimulatedInspectionProvider(inspection.clock.now)
    provider.set_access(inspection.access)
    result = provider.inspect_tenancy(inspection.command)
    assert isinstance(result, InspectionUnobservable)
    assert result.safe_code == "TENANCY_UNOBSERVABLE" and result.continuation == "observe"


# Permission, transient-read and unsupported cases stay explicit without stronger fallback.
@pytest.mark.parametrize(
    "fault,kind,code,continuation",
    [
        ("denied", "unobservable", "ACCESS_DENIED", "manual"),
        ("timeout", "unobservable", "READ_TIMEOUT", "observe"),
        ("unsupported", "unsupported", "UNSUPPORTED_CAPABILITY", "manual"),
    ],
)
def test_named_read_faults_retain_safe_distinct_outcomes(
    inspection, fault, kind, code, continuation
):
    inspection.provider.set_tenancy(inspection.tenancy.model_copy(update={"fault": fault}))
    result = inspection.service.inspect(inspection.command)
    assert result.kind == kind and result.safe_code == code and result.continuation == continuation
    assert result.evidence == ()
    assert isinstance(
        result, InspectionUnsupported if fault == "unsupported" else InspectionUnobservable
    )


# Require explicit, monotonic time for reliable freshness checks.
def test_clock_rejects_naive_initial_time_and_backward_advances(inspection):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ManualClock(inspection.clock.now().replace(tzinfo=None))
    with pytest.raises(ValueError, match="backwards"):
        inspection.clock.advance(timedelta(seconds=-1))
    assert inspection.clock.now() == inspection.tenancy.visible_at


# Missing qualified region mapping stays unknown even when the raw OCI key is observed.
def test_raw_region_key_is_preserved_without_inventing_an_sdk_identifier(inspection):
    result = inspection.service.inspect(inspection.command)
    assert result.tenancy.home_region_key == "EXAMPLE-HOME"
    assert result.tenancy.home_region_identifier is None
    facts = inspection.tenancy.facts.model_copy(
        update={
            "home_region_identifier": "us-ashburn-1",
        }
    )
    inspection.provider.set_tenancy(inspection.tenancy.model_copy(update={"facts": facts}))
    mapped = inspection.service.inspect(inspection.command)
    assert mapped.tenancy.home_region_key == "EXAMPLE-HOME"
    assert mapped.tenancy.home_region_identifier == "us-ashburn-1"


# Exact workspace keys isolate reads even when binding, generation and child OCIDs overlap.
def test_populated_workspaces_with_overlapping_identifiers_keep_distinct_provider_facts(inspection):
    workspace = "other-workspace"
    other_parent = "ocid1.tenancy.oc1..otherparent"
    inspection.provider.set_access(inspection.access.model_copy(update={"workspace_id": workspace}))
    other_facts = inspection.tenancy.facts.model_copy(
        update={
            "parent_tenancy_ocid": other_parent,
            "actual_name": "Other sandbox",
        }
    )
    inspection.provider.set_tenancy(
        inspection.tenancy.model_copy(
            update={
                "workspace_id": workspace,
                "facts": other_facts,
            }
        )
    )
    command = inspection.command.model_copy(
        update={
            "context": inspection.command.context.model_copy(
                update={
                    "workspace_id": workspace,
                    "attempt_id": uuid4(),
                }
            ),
            "payload": inspection.command.payload.model_copy(
                update={"parent_tenancy_ocid": other_parent}
            ),
        }
    )
    original = inspection.service.inspect(inspection.command)
    other = inspection.service.inspect(command)
    assert original.tenancy.actual_name == "Example sandbox"
    assert original.tenancy.parent_tenancy_ocid == inspection.command.payload.parent_tenancy_ocid
    assert other.tenancy.actual_name == "Other sandbox"
    assert other.tenancy.parent_tenancy_ocid == other_parent
    assert original.evidence[0].evidence_ref != other.evidence[0].evidence_ref
