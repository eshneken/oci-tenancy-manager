"""Request/result trust-boundary tests independent of any particular OCI adapter implementation."""

import traceback
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from otm.providers.inspection import ProviderContractError, TenancyInspection
from otm.providers.inspection_contracts import InspectionConfirmed


# A provider reporting a different child, parent or organization cannot confirm this target.
@pytest.mark.parametrize("field", ["tenancy_ocid", "parent_tenancy_ocid", "organization_id"])
def test_actual_provider_scope_must_match_every_requested_binding(inspection, field):
    value = "other-organization" if field == "organization_id" else "ocid1.tenancy.oc1..other"
    facts = inspection.tenancy.facts.model_copy(update={field: value})
    if field == "tenancy_ocid":
        good = inspection.provider.inspect_tenancy(inspection.command)
        provider = Mock(
            inspect_tenancy=Mock(return_value=good.model_copy(update={"tenancy": facts}))
        )
        service = TenancyInspection(provider, inspection.clock.now)
    else:
        inspection.provider.set_tenancy(inspection.tenancy.model_copy(update={"facts": facts}))
        service = inspection.service
    with pytest.raises(ProviderContractError, match="TARGET_MISMATCH"):
        service.inspect(inspection.command)


# Even matching request/result identifiers cannot turn the parent into a registered child.
def test_parent_cannot_be_confirmed_as_its_own_child(inspection):
    target = inspection.command.payload.model_copy(
        update={"parent_tenancy_ocid": inspection.command.payload.tenancy_ocid}
    )
    command = inspection.command.model_copy(update={"payload": target})
    facts = inspection.tenancy.facts.model_copy(update={"parent_tenancy_ocid": target.tenancy_ocid})
    inspection.provider.set_tenancy(inspection.tenancy.model_copy(update={"facts": facts}))
    with pytest.raises(ProviderContractError, match="TARGET_MISMATCH"):
        inspection.service.inspect(command)


# Matching tenancy facts cannot substitute for the original attempt correlation.
def test_result_for_another_attempt_is_rejected_even_when_target_matches(inspection):
    result = inspection.provider.inspect_tenancy(inspection.command)
    provider = Mock(
        inspect_tenancy=Mock(return_value=result.model_copy(update={"attempt_id": uuid4()}))
    )
    with pytest.raises(ProviderContractError, match="ATTEMPT_MISMATCH"):
        TenancyInspection(provider, inspection.clock.now).inspect(inspection.command)


# Every timestamp must belong to the actual synchronous read attempt's capture window.
@pytest.mark.parametrize("component", ["result", "facts", "evidence"])
@pytest.mark.parametrize("seconds", [-1, 1])
def test_stale_or_future_capture_times_are_not_relabeled_as_fresh(inspection, component, seconds):
    result = inspection.provider.inspect_tenancy(inspection.command)
    outside = inspection.clock.now() + timedelta(seconds=seconds)
    if component == "result":
        result = result.model_copy(update={"observed_at": outside})
    elif component == "facts":
        result = result.model_copy(
            update={"tenancy": result.tenancy.model_copy(update={"observed_at": outside})}
        )
    else:
        result = result.model_copy(
            update={"evidence": (result.evidence[0].model_copy(update={"observed_at": outside}),)}
        )
    provider = Mock(inspect_tenancy=Mock(return_value=result))
    with pytest.raises(ProviderContractError, match="CAPTURE_OUTSIDE_ATTEMPT"):
        TenancyInspection(provider, inspection.clock.now).inspect(inspection.command)


# Raw SDK objects and provider text cannot become workflow evidence or reflected errors.
@pytest.mark.parametrize(
    "bad", [object(), {"kind": "unknown", "raw_response": "sensitive-provider-marker"}]
)
def test_opaque_or_malformed_provider_results_raise_only_fixed_diagnostic(inspection, bad):
    provider = Mock(inspect_tenancy=Mock(return_value=bad))
    with pytest.raises(ProviderContractError, match="^INVALID_INSPECTION_RESULT$") as error:
        TenancyInspection(provider, inspection.clock.now).inspect(inspection.command)
    assert "sensitive-provider-marker" not in "".join(traceback.format_exception(error.value))


# A frozen model's unchecked copy cannot bypass validation of the milestone at consumption.
def test_copied_instances_are_revalidated_before_they_can_claim_another_goal(inspection):
    good = inspection.provider.inspect_tenancy(inspection.command)
    forged = good.model_copy(update={"milestone": "termination_initiated"})
    provider = Mock(inspect_tenancy=Mock(return_value=forged))
    with pytest.raises(ProviderContractError, match="INVALID_INSPECTION_RESULT"):
        TenancyInspection(provider, inspection.clock.now).inspect(inspection.command)


# The facade rejects an adapter contract violation without interpreting or reflecting it.
def test_unexpected_adapter_exception_cannot_leak_raw_diagnostic(inspection):
    provider = Mock(inspect_tenancy=Mock(side_effect=RuntimeError("sensitive-provider-marker")))
    with pytest.raises(ProviderContractError, match="^INSPECTION_PROVIDER_FAILED$") as error:
        TenancyInspection(provider, inspection.clock.now).inspect(inspection.command)
    assert "sensitive-provider-marker" not in "".join(traceback.format_exception(error.value))


# Freshness permits a bounded read interval rather than requiring all clocks to be frozen.
def test_confirmation_can_capture_facts_during_a_nonzero_read_interval(inspection):
    result = inspection.provider.inspect_tenancy(inspection.command)

    # Advance time as a real read might, retaining evidence captured within this attempt.
    def finish_read(_command):
        inspection.clock.advance(timedelta(seconds=2))
        return result

    provider = Mock(inspect_tenancy=Mock(side_effect=finish_read))
    assert isinstance(
        TenancyInspection(provider, inspection.clock.now).inspect(inspection.command),
        InspectionConfirmed,
    )
