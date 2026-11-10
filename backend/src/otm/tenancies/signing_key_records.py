"""Signing-key admission and nonsecret current-head/evidence authentication."""

import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select

from otm.configuration.rollout_contracts import ConfigurationOperationTarget
from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.required_user_contracts import RequiredUserTarget
from otm.providers.signing_key_rotation import ManagedSigningKey
from otm.storage.tables import (
    audit_event,
    managed_object_binding,
    operation,
    signing_credential,
    tenancy,
)
from otm.storage.tables import user_presence_connection as connections
from otm.tenancies.signing_key_contracts import SigningKeyIntent


# Resolve authenticated exact current references; inventory never grants custody.
def current_key(head):
    if canonical_hash(head["target"]) != head["target_hash"]:
        raise ValueError("SIGNING_KEY_CUSTODY_CHANGED")
    if head["current_key"] is None:
        return None
    key = ManagedSigningKey.model_validate_json(json.dumps(head["current_key"]))
    if (
        canonical_hash(head["current_key"]) != head["current_hash"]
        or key.version.credential_id != head["id"]
        or key.version.generation != head["generation"]
        or key.version.target.model_dump(mode="json") != head["target"]
        or key.version.target.workspace_id != head["workspace_id"]
        or key.version.target.tenancy_id != head["tenancy_id"]
        or key.version.target.subject_binding_id != head["principal_binding_id"]
        or head["retire_at"] > key.retire_at
        or head["state"] == "usable"
        and head["retire_at"] != key.retire_at
    ):
        raise ValueError("SIGNING_KEY_CUSTODY_CHANGED")
    return key


# Reference-only native deferral is committed together with immutable scoped operation intent.
def admit(connection, intent, actor, at, enqueuer, *, identifier=None):
    identifier, event = identifier or uuid4(), uuid4()
    data = IntentEventData(intent=intent, actor=actor).model_dump(mode="json")
    future = intent.due_at is not None and intent.due_at > at
    connection.execute(
        operation.insert().values(
            id=identifier,
            workspace_id=intent.workspace_id,
            kind=intent.kind,
            initiating_actor_subject=actor.key,
            initiating_actor_snapshot=actor.model_dump(mode="json"),
            responsible_actor_subject=actor.key,
            client_request_key=uuid4(),
            request_digest=canonical_hash(data),
            current_intent_revision=1,
            current_intent_event_id=event,
            state="waiting" if future else "queued",
            wait_reason="signing_rotation_due" if future else None,
            stage="Rotate automation signing key"
            if intent.phase == "rotation"
            else "Prepare automation signing credential",
            effect_knowledge="none",
            revision=1,
            accepted_at=at,
            created_at=at,
            updated_at=at,
        )
    )
    connection.execute(
        audit_event.insert().values(
            id=event,
            workspace_id=intent.workspace_id,
            operation_id=identifier,
            actor=actor.key,
            actor_subject=actor.key,
            actor_snapshot=actor.model_dump(mode="json"),
            kind="operation_intent",
            intent_revision=1,
            at=at,
            contract_version=intent.contract_version,
            data=data,
            data_hash=canonical_hash(data),
        )
    )
    delay = max(0, int((intent.due_at - at).total_seconds()) + 1) if future else 0
    enqueuer.enqueue(connection, identifier, delay_seconds=delay, scheduled_rotation=future)
    return identifier


# Fresh setup registers custody only after committed exact identity/source bindings exist.
class SigningKeySetup:
    # Fixed selected queue and trusted sandbox policy are host-owned dependencies.
    def __init__(self, enqueuer, policy_loader):
        self.enqueuer, self.policy_loader = enqueuer, policy_loader

    # Stable allocation IDs preserve the original private namespace on admission replay.
    def admit(self, connection, row, intent, at):
        if intent.signing_key_rotation_contract is None:
            raise ValueError("SIGNING_KEY_SETUP_NOT_SELECTED")
        existing = (
            connection.execute(
                select(signing_credential).where(
                    signing_credential.c.workspace_id == intent.workspace_id,
                    signing_credential.c.source_operation_id == row["id"],
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if existing["state"] == "attention":
                from sqlalchemy import update

                connection.execute(
                    update(operation)
                    .where(
                        operation.c.workspace_id == intent.workspace_id,
                        operation.c.id == existing["rotation_operation_id"],
                    )
                    .values(
                        state="queued",
                        wait_reason=None,
                        updated_at=at,
                        revision=operation.c.revision + 1,
                    )
                )
                connection.execute(
                    update(signing_credential)
                    .where(signing_credential.c.id == existing["id"])
                    .values(state="staging", updated_at=at)
                )
                self.enqueuer.enqueue(connection, existing["rotation_operation_id"])
            return existing["id"]
        child = (
            connection.execute(
                select(tenancy).where(
                    tenancy.c.workspace_id == intent.workspace_id,
                    tenancy.c.id == intent.pending_tenancy_id,
                )
            )
            .mappings()
            .one()
        )
        binding = (
            connection.execute(
                select(connections).where(
                    connections.c.workspace_id == intent.workspace_id,
                    connections.c.tenancy_id == intent.pending_tenancy_id,
                    connections.c.state == "active",
                )
            )
            .mappings()
            .one()
        )
        rows = list(
            connection.execute(
                select(managed_object_binding).where(
                    managed_object_binding.c.workspace_id == intent.workspace_id,
                    managed_object_binding.c.tenancy_id == intent.pending_tenancy_id,
                    managed_object_binding.c.state == "active",
                )
            ).mappings()
        )
        keys = {item["logical_key"]: item for item in rows}
        user, domain = keys["identity/user/automation"], keys["identity/domain"]
        if (
            child["operation_id"] != row["id"]
            or child["status"] != "pending"
            or binding["created_operation_id"] != row["id"]
            or user["source_evidence_event_id"] != binding["source_evidence_event_id"]
            or domain["id"] != binding["domain_binding_id"]
            or user["id"] != binding["automation_binding_id"]
        ):
            raise ValueError("SIGNING_KEY_ENROLLMENT_UNVERIFIED")
        target = RequiredUserTarget(
            workspace_id=intent.workspace_id,
            tenancy_id=child["id"],
            purpose="automation",
            subject_binding_id=user["id"],
            binding_generation=user["generation"],
            identity_domain_binding_id=domain["id"],
            domain_ocid=domain["provider_ocid"],
            scim_resource_id=user["scim_resource_id"],
            provider_ocid=user["provider_ocid"],
            user_name=user["user_name"],
            organization_id=child["organization_id"],
            parent_tenancy_ocid=child["parent_tenancy_ocid"],
            tenancy_ocid=child["tenancy_ocid"],
        )
        credential = uuid5(
            NAMESPACE_URL, "otm-signing:" + intent.workspace_id + ":" + str(row["id"])
        )
        identifier = uuid5(credential, "initial-signing-key")
        source = (
            connection.execute(
                select(audit_event).where(
                    audit_event.c.workspace_id == intent.workspace_id,
                    audit_event.c.id == row["current_intent_event_id"],
                )
            )
            .mappings()
            .one()
        )
        if canonical_hash(source["data"]) != source["data_hash"]:
            raise ValueError("SIGNING_KEY_ENROLLMENT_UNVERIFIED")
        actor = IntentEventData.model_validate_json(json.dumps(source["data"])).actor
        setup = SigningKeyIntent(
            phase="setup",
            workspace_id=intent.workspace_id,
            credential_id=credential,
            subject=target,
            connection_id=binding["id"],
            connection_revision=binding["revision"],
            policy_hash=canonical_hash(self.policy_loader().policy.model_dump(mode="json")),
            expected_generation=0,
            source_operation_id=row["id"],
            source_evidence_event_id=binding["source_evidence_event_id"],
            target=ConfigurationOperationTarget(
                tenancy_ocid=child["tenancy_ocid"], display_name=child["name"]
            ),
        )
        admit(connection, setup, actor, at, self.enqueuer, identifier=identifier)
        scope = target.model_dump(mode="json")
        connection.execute(
            signing_credential.insert().values(
                id=credential,
                workspace_id=intent.workspace_id,
                tenancy_id=child["id"],
                principal_binding_id=user["id"],
                connection_id=binding["id"],
                source_operation_id=row["id"],
                source_evidence_event_id=binding["source_evidence_event_id"],
                target=scope,
                target_hash=canonical_hash(scope),
                generation=0,
                state="staging",
                rotation_operation_id=identifier,
                created_at=at,
                updated_at=at,
            )
        )
        return credential
