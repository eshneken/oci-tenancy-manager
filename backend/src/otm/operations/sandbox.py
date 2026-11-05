"""Explicit laptop simulation policy and real admission/dispatch authority; no OCI credentials."""

import os
import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator
from sqlalchemy.engine import Engine

from otm.contracts import Contract, Text
from otm.operations.acceptance import AcceptInspection
from otm.operations.contracts import InspectImportRequest, InspectionPolicy, canonical_hash
from otm.operations.execution_contracts import CommittedInspection, DispatchGrant
from otm.providers.inspection_contracts import InspectTenancy, TenancyFacts, TenancyOcid
from otm.providers.inspection_simulator import (
    SimulatedAccess,
    SimulatedInspectionProvider,
    SimulatedTenancy,
)
from otm.storage.admission import SqlAdmissionStore
from otm.storage.enqueue import InspectionEnqueuer, workspace_queue


# Accept a child and request identity only; actor, workspace, parent and binding are server-owned.
class InspectionSubmission(Contract):
    client_request_key: UUID
    tenancy_ocid: TenancyOcid


# Describe an explicitly configured virtual child and one deterministic read scenario.
class SandboxTarget(Contract):
    # Virtual child OCID, 15–256 characters; syntax never proves real OCI membership.
    tenancy_ocid: TenancyOcid
    # Display name, 1–256 nonblank characters, used only in the explicit simulator catalog.
    name: Text
    # Select a read scenario; no option creates, modifies or deletes OCI resources.
    scenario: Literal["healthy", "access_denied", "timeout", "unsupported", "unobservable"]


# Keep virtual provider state independent of accepted operations and allow no secret fields.
class SandboxConfig(Contract):
    # Exactly version1; unknown schema or fields fail closed before accepting/dispatching work.
    schema_version: Annotated[int, Field(ge=1, le=1)]
    # Fixed simulated mode; this configuration can never select a real OCI adapter.
    provider_mode: Literal["simulated"]
    # Trusted workspace/org text, parent OCID and policy/binding UUIDs; never browser inputs.
    policy: InspectionPolicy
    # True blocks new admissions and provider dispatch; no background unpause is performed.
    execution_paused: bool
    # Between1and20 unique virtual children; no child may equal the configured parent.
    targets: Annotated[list[SandboxTarget], Field(min_length=1, max_length=20)]

    # Reject ambiguous fixture identities instead of silently overwriting one provider record.
    @model_validator(mode="after")
    def unique_children(self):
        identifiers = [target.tenancy_ocid for target in self.targets]
        if (
            len(set(identifiers)) != len(identifiers)
            or self.policy.parent_tenancy_ocid in identifiers
        ):
            raise ValueError("INVALID_SANDBOX_TARGETS")
        return self


# Return only selectable virtual targets and pause status, never internal policy/binding fields.
class SandboxCatalog(Contract):
    provider_mode: Literal["simulated"] = "simulated"
    execution_paused: bool
    targets: list[SandboxTarget]


# Distinguish an unavailable/paused operator configuration from a rejected browser command.
class SandboxUnavailable(ValueError):
    pass


# Bound regular-file reads; refuse final-component symlinks/FIFOs and private parser diagnostics.
def load_sandbox(path: Path, workspace: str) -> SandboxConfig:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("REGULAR_CONFIGURATION_REQUIRED")
            content = stream.read(65537)
        if len(content) > 65536:
            raise ValueError("SANDBOX_CONFIGURATION_TOO_LARGE")
        config = SandboxConfig.model_validate_json(content)
        if config.policy.workspace_id != workspace:
            raise ValueError("SANDBOX_SCOPE_MISMATCH")
        return config
    except (OSError, ValueError):
        raise SandboxUnavailable("INSPECTION_SANDBOX_UNAVAILABLE") from None


# Bind real session admission to the explicit simulator policy without a permissive authorizer.
class SandboxAdmission:
    # Construct no worker/provider and perform no database/schema writes at application startup.
    def __init__(
        self, engine: Engine, sessions, path: Path, workspace: str, clock: Callable[[], datetime]
    ):
        self.store = SqlAdmissionStore(engine, InspectionEnqueuer(queue=workspace_queue(workspace)))
        self.sessions, self.path, self.workspace, self.clock = sessions, path, workspace, clock

    # Require current application administration before exposing even the selectable fixture list.
    def catalog(self, principal) -> SandboxCatalog:
        self.sessions.require_admin(principal, self.workspace)
        config = load_sandbox(self.path, self.workspace)
        return SandboxCatalog(execution_paused=config.execution_paused, targets=config.targets)

    # Compatible committed replays precede policy reload, preserving acceptance under config
    # changes.
    def submit(self, principal, command: InspectionSubmission):
        command = InspectionSubmission.model_validate(command)
        request = InspectImportRequest(workspace_id=self.workspace, **command.model_dump())

        # New work must match a registered virtual child; parent/binding never come from the
        # browser.
        def policy(workspace):
            config = load_sandbox(self.path, workspace)
            if config.execution_paused:
                raise SandboxUnavailable("INSPECTION_SANDBOX_PAUSED")
            if request.tenancy_ocid not in {target.tenancy_ocid for target in config.targets}:
                raise ValueError("INVALID_SANDBOX_TARGET")
            return config.policy

        return AcceptInspection(self.store, self.sessions, policy, self.clock).accept(
            request, principal
        )


# Revalidate live database grants and current file policy for each worker boundary, independent of
# UI.
class SandboxAuthority:
    # A worker has no browser session; it uses the original issuer-qualified actor and current
    # grant.
    def __init__(self, grants, path: Path, workspace: str):
        self.grants, self.path, self.workspace = grants, path, workspace

    # Any revocation, pause or policy/binding change blocks or supersedes the read; never retarget
    # it.
    def require_inspection(self, committed: CommittedInspection) -> DispatchGrant:
        config = load_sandbox(self.path, self.workspace)
        self.grants.require_admin(committed.actor.issuer, committed.actor.subject, self.workspace)
        if config.execution_paused:
            raise PermissionError("EXECUTION_PAUSED")
        policy = config.policy
        if (
            committed.intent.workspace_id != self.workspace
            or committed.intent.policy_revision != policy.policy_revision
            or committed.intent.access_binding_id != policy.access_binding_id
            or committed.intent.target.organization_id != policy.organization_id
            or committed.intent.target.parent_tenancy_ocid != policy.parent_tenancy_ocid
            or committed.intent.target.tenancy_ocid
            not in {target.tenancy_ocid for target in config.targets}
        ):
            raise PermissionError("DISPATCH_CONTEXT_CHANGED")
        return DispatchGrant(
            workspace_id=self.workspace,
            actor_key=committed.actor.key,
            policy_revision=policy.policy_revision,
            runtime_policy_revision=uuid5(
                NAMESPACE_URL, canonical_hash(config.model_dump(mode="json"))
            ),
            access_binding_id=policy.access_binding_id,
            credential_generation=1,
        )


# Read virtual state afresh for each facade call; this adapter never imports an OCI SDK or opens a
# socket.
class SandboxProvider:
    # Share a server UTC clock; fixture changes cannot rewrite an already committed operation
    # intent.
    def __init__(self, path: Path, workspace: str, clock: Callable[[], datetime]):
        self.path, self.workspace, self.clock = path, workspace, clock

    # Reuse the qualified simulator's access/error/evidence semantics rather than invent fake
    # success.
    def inspect_tenancy(self, command: InspectTenancy):
        config = load_sandbox(self.path, self.workspace)
        provider = SimulatedInspectionProvider(self.clock)
        provider.set_access(
            SimulatedAccess(
                workspace_id=self.workspace,
                access_binding_id=config.policy.access_binding_id,
                credential_generation=1,
                permitted=True,
                tenancy_ocids=frozenset(target.tenancy_ocid for target in config.targets),
            )
        )
        at = self.clock()
        for target in config.targets:
            if target.scenario == "unobservable":
                continue
            fault = {
                "healthy": None,
                "access_denied": "denied",
                "timeout": "timeout",
                "unsupported": "unsupported",
            }[target.scenario]
            provider.set_tenancy(
                SimulatedTenancy(
                    workspace_id=self.workspace,
                    visible_at=at,
                    fault=fault,
                    facts=TenancyFacts(
                        organization_id=config.policy.organization_id,
                        parent_tenancy_ocid=config.policy.parent_tenancy_ocid,
                        tenancy_ocid=target.tenancy_ocid,
                        actual_name=target.name,
                        home_region_key="SIM-HOME",
                        home_region_identifier=None,
                        role="CHILD",
                        observed_at=at,
                    ),
                )
            )
        return provider.inspect_tenancy(command)


# Create configuration only; no operation/job/activity is seeded until an administrator submits
# work.
def sample_sandbox(workspace: str, instance: UUID) -> SandboxConfig:
    scenarios = [
        ("healthy", "Healthy sandbox"),
        ("access_denied", "Access denied"),
        ("timeout", "Read timeout"),
        ("unsupported", "Unsupported inspection"),
        ("unobservable", "Unobservable tenancy"),
    ]
    return SandboxConfig(
        schema_version=1,
        provider_mode="simulated",
        execution_paused=False,
        policy=InspectionPolicy(
            workspace_id=workspace,
            policy_revision=uuid5(instance, "simulation-policy"),
            access_binding_id=uuid5(instance, "simulation-binding"),
            organization_id="otm-simulated-organization",
            parent_tenancy_ocid="ocid1.tenancy.oc1..otmsimparent",
        ),
        targets=[
            SandboxTarget(
                tenancy_ocid="ocid1.tenancy.oc1..otmsim" + scenario.replace("_", ""),
                name=name,
                scenario=scenario,
            )
            for scenario, name in scenarios
        ],
    )
