"""Closed message validation and safe result families for the first internal OCI capability."""

import json
from datetime import timedelta, timezone

import pytest
from pydantic import ValidationError

from otm.providers.inspection_contracts import (
    RESULT_ADAPTER,
    ExecutionContext,
    InspectionConfirmed,
    InspectTenancy,
    TenancyFacts,
)


# Typed JSON serialization preserves scope and uses explicit UTC capture timestamps.
def test_request_and_result_json_round_trip_preserve_exact_attempt_and_target(inspection):
    command = inspection.command
    assert InspectTenancy.model_validate_json(command.model_dump_json()) == command
    result = inspection.service.inspect(command)
    assert RESULT_ADAPTER.validate_json(RESULT_ADAPTER.dump_json(result)) == result
    assert result.model_dump(mode="json")["observed_at"].endswith("Z")
    assert result.attempt_id == command.context.attempt_id


# Reject zero/boolean/string generations and unusable identifiers before adapter dispatch.
@pytest.mark.parametrize(
    "field,value",
    [
        ("intent_revision", 0),
        ("intent_revision", True),
        ("intent_revision", "1"),
        ("execution_generation", -1),
        ("credential_generation", 0),
        ("workspace_id", "   "),
        ("step_key", ""),
        ("attempt_id", "invalid"),
    ],
)
def test_invalid_context_cannot_be_coerced_into_dispatch_scope(inspection, field, value):
    raw = inspection.command.context.model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        ExecutionContext.model_validate_json(json.dumps(raw))


# No free-form kwargs/credential field can cross the closed inspection boundary.
@pytest.mark.parametrize("level", ["command", "context", "payload"])
def test_unknown_fields_and_secret_material_are_rejected_without_reflecting_values(
    inspection, level
):
    raw = inspection.command.model_dump(mode="json")
    target = raw if level == "command" else raw[level]
    target["private_key"] = "nonfunctional-sensitive-input-marker"
    with pytest.raises(ValidationError) as error:
        InspectTenancy.model_validate_json(json.dumps(raw))
    assert "nonfunctional-sensitive-input-marker" not in str(error.value)


# A serialized command is self-describing rather than relying on producer-side defaults.
@pytest.mark.parametrize("path", ["contract_version", "kind", "context", "payload"])
def test_required_wire_fields_cannot_be_omitted(inspection, path):
    raw = inspection.command.model_dump(mode="json")
    del raw[path]
    with pytest.raises(ValidationError):
        InspectTenancy.model_validate_json(json.dumps(raw))


# An identifier-shaped field cannot become a service endpoint or newline-bearing value.
@pytest.mark.parametrize(
    "value",
    [
        "ocid1.user.oc1..wrongtype",
        "ocid1.tenancy.",
        "ocid1.tenancy.oc1..bad\n",
        "https://example.test",
    ],
)
def test_tenancy_reference_rejects_wrong_type_and_non_identifier_content(inspection, value):
    raw = inspection.command.model_dump(mode="json")
    raw["payload"]["tenancy_ocid"] = value
    with pytest.raises(ValidationError):
        InspectTenancy.model_validate_json(json.dumps(raw))


# Naive and non-UTC timestamps cannot silently change the observation's time basis.
@pytest.mark.parametrize("clock_fault", ["naive", "non_utc"])
def test_observed_facts_require_explicit_utc_instants(inspection, clock_fault):
    value = inspection.clock.now()
    value = (
        value.replace(tzinfo=None)
        if clock_fault == "naive"
        else value.astimezone(timezone(timedelta(hours=1)))
    )
    raw = inspection.tenancy.facts.model_dump()
    raw["observed_at"] = value
    with pytest.raises(ValidationError):
        TenancyFacts.model_validate(raw)


# A read cannot become termination/onboarding success merely by changing a status string.
def test_confirmed_inspection_cannot_claim_other_milestones_or_empty_evidence(inspection):
    result = inspection.service.inspect(inspection.command)
    raw = result.model_dump(mode="json")
    raw["milestone"] = "termination_initiated"
    with pytest.raises(ValidationError):
        RESULT_ADAPTER.validate_json(json.dumps(raw))
    raw["milestone"] = "tenancy_inspected"
    raw["evidence"] = []
    with pytest.raises(ValidationError):
        RESULT_ADAPTER.validate_json(json.dumps(raw))


# Consumers cannot accidentally edit the target or capture time of retained evidence.
def test_results_and_nested_facts_are_immutable(inspection):
    result = inspection.service.inspect(inspection.command)
    assert isinstance(result, InspectionConfirmed)
    with pytest.raises(ValidationError):
        result.tenancy.actual_name = "Changed"
    with pytest.raises(ValidationError):
        result.observed_at += timedelta(seconds=1)
