"""Closed execution-1 inspection messages, implementing one capability from design chapter09."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, TypeAdapter

from otm.contracts import Contract, Generation, Text, UtcInstant

TenancyOcid = Annotated[
    str,
    StringConstraints(min_length=15, max_length=256, pattern=r"^ocid1\.tenancy\.[A-Za-z0-9.]+$"),
]


# Identify committed work and its selected binding, without granting authorization itself.
class ExecutionContext(Contract):
    workspace_id: Text
    operation_id: UUID
    step_key: Text
    attempt_id: UUID
    intent_revision: Generation
    execution_generation: Generation
    access_binding_id: UUID
    credential_generation: Generation


# Freeze the expected scope; an OCID shape alone does not establish existence.
class InspectionTarget(Contract):
    organization_id: Text
    parent_tenancy_ocid: TenancyOcid
    tenancy_ocid: TenancyOcid


# Internal read request, not a public API command or permission to provision a tenancy.
class InspectTenancy(Contract):
    contract_version: Literal["execution-1-draft"]
    kind: Literal["inspect_tenancy"]
    context: ExecutionContext
    payload: InspectionTarget


# Observed child facts; the caller separately verifies they match its requested scope.
class TenancyFacts(InspectionTarget):
    actual_name: Text
    home_region_key: Text
    home_region_identifier: Text | None
    role: Literal["CHILD"]
    observed_at: UtcInstant


# Reference a sanitized read observation without embedding raw responses or secret material.
class ReadBackEvidence(Contract):
    code: Literal["READ_BACK"]
    evidence_ref: UUID
    observed_at: UtcInstant


# Capture one attempt and safe correlations common to the three supported read outcomes.
class Observation(Contract):
    contract_version: Literal["execution-1-draft"]
    attempt_id: UUID
    observed_at: UtcInstant
    provider_request_id: Text | None
    provider_operation_id: Text | None


# Confirm only a scoped tenancy inspection, never onboarding, permissions or termination.
class InspectionConfirmed(Observation):
    kind: Literal["confirmed"]
    safe_code: Literal["TENANCY_INSPECTED"]
    milestone: Literal["tenancy_inspected"]
    tenancy: TenancyFacts
    identity: None
    evidence: Annotated[tuple[ReadBackEvidence, ...], Field(min_length=1, max_length=32)]


# Preserve unknown read evidence instead of treating denied/missing/partial data as absence.
class InspectionUnobservable(Observation):
    kind: Literal["unobservable"]
    safe_code: Literal[
        "ACCESS_UNVERIFIED", "ACCESS_DENIED", "READ_TIMEOUT", "READ_DELAYED", "TENANCY_UNOBSERVABLE"
    ]
    continuation: Literal["manual", "observe"]
    evidence: Annotated[tuple[ReadBackEvidence, ...], Field(max_length=32)]


# Expose an unsupported inspection capability without changing signer or identity mode.
class InspectionUnsupported(Observation):
    kind: Literal["unsupported"]
    safe_code: Literal["UNSUPPORTED_CAPABILITY"]
    continuation: Literal["manual"]
    evidence: Annotated[tuple[ReadBackEvidence, ...], Field(max_length=32)]


InspectionResult = Annotated[
    InspectionConfirmed | InspectionUnobservable | InspectionUnsupported,
    Field(discriminator="kind"),
]
RESULT_ADAPTER = TypeAdapter(InspectionResult)
