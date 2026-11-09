"""Explicit audited onboarding responsibility and frozen continuation authority."""

import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from sqlalchemy import Integer, cast, select, update

from otm.contracts import Contract, Text
from otm.operations.contracts import ActorIdentity, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import administrator, audit_event, operation
from otm.tenancies.contracts import ActionReceipt, OrganizationIntent
from otm.tenancies.onboarding import load_intent


# A claimant supplies only replay identity and the displayed operation revision, never another
# actor.
class ResponsibilityCommand(Contract):
    client_request_key: UUID
    expected_revision: Annotated[int, Field(ge=1)]


# A durable authority snapshot preserves provider intent while authorizing an explicit continuation.
class ResponsibilityEvidence(Contract):
    contract_version: Literal["operation-responsibility-1"] = "operation-responsibility-1"
    client_request_key: UUID
    request_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    before_name: Text | None = None
    before_subject: Text
    after_actor: ActorIdentity
    administrator_id: UUID
    authorization_revision: UUID
    intent_event_id: UUID
    intent_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    expected_revision: Annotated[int, Field(ge=1)]
    operation_revision: Annotated[int, Field(ge=2)]

    # One claim advances exactly once; no snapshot can silently certify an unrelated revision.
    @model_validator(mode="after")
    def next_revision(self):
        if self.operation_revision != self.expected_revision + 1:
            raise ValueError("INVALID_RESPONSIBILITY_REVISION")
        return self


# Only paused guided create/import work can be explicitly claimed; reading never transfers
# authority.
def eligible(row, intent):
    return bool(
        row["state"] in {"waiting", "needs_attention"}
        and isinstance(intent, OrganizationIntent)
        and intent.action in {"create_tenancy", "import_tenancy"}
        and intent.onboarding_version in {1, 2, 3}
    )


# Verify original bytes before using an audit record as current authority or a replay receipt.
def decode_evidence(row):
    if canonical_hash(row["data"]) != row["data_hash"]:
        raise ValueError("INVALID_RESPONSIBILITY_EVIDENCE")
    proof = ResponsibilityEvidence.model_validate_json(json.dumps(row["data"]))
    if (
        proof.after_actor.key != row["actor_subject"]
        or proof.after_actor.model_dump(mode="json") != row["actor_snapshot"]
    ):
        raise ValueError("INVALID_RESPONSIBILITY_ACTOR")
    return proof


# Numeric operation revisions, rather than tied wall clocks, order immutable claims on a locked row.
def latest_claim(connection, row):
    return (
        connection.execute(
            select(audit_event)
            .where(
                audit_event.c.workspace_id == row["workspace_id"],
                audit_event.c.operation_id == row["id"],
                audit_event.c.kind == "operation_responsibility_changed",
            )
            .order_by(cast(audit_event.c.data["operation_revision"].astext, Integer).desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )


# Fresh grant validation still happens at dispatch; a revoke/regrant cannot revive captured
# authority.
def execution_authority(connection, row, frozen):
    if frozen.intent.onboarding_version not in {1, 2, 3}:
        if row["responsible_actor_subject"] != frozen.actor.key:
            raise ValueError("RESPONSIBILITY_PROOF_REQUIRED")
        return frozen.intent.administrator_id, frozen.intent.authorization_revision, frozen.actor
    recorded = latest_claim(connection, row)
    if recorded is None:
        if row["responsible_actor_subject"] != frozen.actor.key:
            raise ValueError("RESPONSIBILITY_PROOF_REQUIRED")
        return frozen.intent.administrator_id, frozen.intent.authorization_revision, frozen.actor
    proof = decode_evidence(recorded)
    if (
        not isinstance(frozen.intent, OrganizationIntent)
        or frozen.intent.onboarding_version not in {1, 2, 3}
        or frozen.intent.action not in {"create_tenancy", "import_tenancy"}
        or proof.after_actor.key != row["responsible_actor_subject"]
        or proof.operation_revision > row["revision"]
        or proof.intent_event_id != row["current_intent_event_id"]
        or proof.intent_hash != canonical_hash(frozen.model_dump(mode="json"))
    ):
        raise ValueError("RESPONSIBILITY_CONTEXT_CHANGED")
    return proof.administrator_id, proof.authorization_revision, proof.after_actor


# Use the existing session/administrator/workspace/operation lock order and commit evidence
# atomically.
def take_responsibility(service, principal, identifier, command):
    digest = canonical_hash(command.model_dump(mode="json"))
    with service.store._write(principal) as (connection, workspace, at):
        service.store._workspace(connection, workspace, lock=True)
        row = (
            connection.execute(
                select(operation)
                .where(
                    operation.c.workspace_id == workspace,
                    operation.c.id == identifier,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OrganizationConflict("RESPONSIBILITY_OPERATION_NOT_FOUND")
        previous = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.workspace_id == workspace,
                    audit_event.c.operation_id == identifier,
                    audit_event.c.kind == "operation_responsibility_changed",
                    audit_event.c.actor_subject == principal.actor.key,
                    audit_event.c.data["client_request_key"].astext
                    == str(command.client_request_key),
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous:
            proof = decode_evidence(previous)
            if proof.request_hash != digest:
                raise RequestConflict("REQUEST_KEY_REUSED")
            return ActionReceipt(
                operation_id=identifier,
                state=row["state"],
                provider_mode="simulated",
                accepted_at=previous["at"],
            )
        if row["kind"] != "organization_action":
            raise OrganizationConflict("RESPONSIBILITY_PREVIEW_CHANGED")
        frozen = load_intent(connection, row)
        if (
            not eligible(row, frozen.intent)
            or row["revision"] != command.expected_revision
            or row["responsible_actor_subject"] == principal.actor.key
        ):
            raise OrganizationConflict("RESPONSIBILITY_PREVIEW_CHANGED")
        current = service.policy_loader() if service.policy_loader else None
        if (
            service.mode != "simulated"
            or current
            and (current.execution_paused or current.policy != service.policy)
        ):
            raise OrganizationConflict("LIFECYCLE_PROVIDER_UNAVAILABLE")
        grant = (
            connection.execute(
                select(administrator).where(
                    administrator.c.workspace_id == workspace,
                    administrator.c.issuer == principal.actor.issuer,
                    administrator.c.subject == principal.actor.subject,
                    administrator.c.status == "active",
                )
            )
            .mappings()
            .one()
        )
        _, _, prior_actor = execution_authority(connection, row, frozen)
        proof = ResponsibilityEvidence(
            before_name=prior_actor.display_name,
            client_request_key=command.client_request_key,
            request_hash=digest,
            before_subject=row["responsible_actor_subject"],
            after_actor=principal.actor,
            administrator_id=grant["id"],
            authorization_revision=grant["authorization_revision"],
            intent_event_id=row["current_intent_event_id"],
            intent_hash=canonical_hash(frozen.model_dump(mode="json")),
            expected_revision=row["revision"],
            operation_revision=row["revision"] + 1,
        )
        connection.execute(
            update(operation)
            .where(operation.c.workspace_id == workspace, operation.c.id == identifier)
            .values(
                responsible_actor_subject=principal.actor.key,
                revision=proof.operation_revision,
                updated_at=at,
            )
        )
        data = proof.model_dump(mode="json")
        connection.execute(
            audit_event.insert().values(
                id=uuid4(),
                workspace_id=workspace,
                operation_id=identifier,
                actor=principal.actor.key,
                actor_subject=principal.actor.key,
                actor_snapshot=principal.actor.model_dump(mode="json"),
                kind="operation_responsibility_changed",
                at=at,
                contract_version=proof.contract_version,
                data=data,
                data_hash=canonical_hash(data),
            )
        )
        if service.notifications:
            updated = {
                **row,
                "responsible_actor_subject": principal.actor.key,
                "revision": proof.operation_revision,
                "updated_at": at,
            }
            service.notifications.stage(connection, updated, at)
        return ActionReceipt(
            operation_id=identifier, state=row["state"], provider_mode="simulated", accepted_at=at
        )
