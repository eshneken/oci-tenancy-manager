"""Read-only signing-key progress and explicit preview-bound maintenance requests."""

import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update

from otm.operations.contracts import canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import audit_event, operation, signing_credential, tenancy
from otm.tenancies.presence import receipt
from otm.tenancies.signing_key_contracts import SigningKeyRequestEvidence, SigningKeyView
from otm.tenancies.signing_key_records import current_key


# Only new admissions use this gate; previously accepted recovery closure can drain independently.
def require_signing_admission(connection, workspace, identifier, at):
    row = (
        connection.execute(
            select(signing_credential)
            .where(
                signing_credential.c.workspace_id == workspace,
                signing_credential.c.tenancy_id == identifier,
            )
            .order_by(
                (signing_credential.c.state == "retired").asc(),
                signing_credential.c.created_at.desc(),
            )
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        current_key(row)
    if row is not None and (
        row["state"] != "usable" or row["retire_at"] is None or at >= row["retire_at"]
    ):
        raise OrganizationConflict("SIGNING_KEY_MAINTENANCE_REQUIRED")


# Pending/due rotation cannot acquire another four-hour window; ordinary reads use the lighter gate.
def require_signing_window_admission(connection, workspace, identifier, at):
    require_signing_admission(connection, workspace, identifier, at)
    pending = (
        connection.execute(
            select(operation.c.state, operation.c.wait_reason, signing_credential.c.retire_at)
            .join(
                signing_credential,
                (signing_credential.c.workspace_id == operation.c.workspace_id)
                & (signing_credential.c.rotation_operation_id == operation.c.id),
            )
            .where(
                signing_credential.c.workspace_id == workspace,
                signing_credential.c.tenancy_id == identifier,
                signing_credential.c.state != "retired",
            )
        )
        .mappings()
        .one_or_none()
    )
    if pending is not None and not (
        pending["state"] == "waiting"
        and pending["wait_reason"] == "signing_rotation_due"
        and at < pending["retire_at"] - timedelta(days=1)
    ):
        raise OrganizationConflict("SIGNING_KEY_MAINTENANCE_REQUIRED")


# Normal metadata GETs cannot enroll, stage, rotate or fetch secret material.
class SigningKeys:
    # Trusted store/policy/queue composition, never client credential or target selections.
    def __init__(self, store, policy_loader, enqueuer):
        self.store, self.policy_loader, self.enqueuer = store, policy_loader, enqueuer

    # Scope both rows to the authenticated workspace, with the standard child row lock for writes.
    def rows(self, connection, workspace, identifier, *, lock=False):
        statement = select(tenancy).where(
            tenancy.c.workspace_id == workspace, tenancy.c.id == identifier
        )
        child = (
            connection.execute(statement.with_for_update() if lock else statement)
            .mappings()
            .one_or_none()
        )
        if child is None:
            raise OrganizationConflict("TENANCY_NOT_FOUND")
        statement = (
            select(signing_credential)
            .where(
                signing_credential.c.workspace_id == workspace,
                signing_credential.c.tenancy_id == identifier,
            )
            .order_by(
                (signing_credential.c.state == "retired").asc(),
                signing_credential.c.created_at.desc(),
            )
            .limit(1)
        )
        head = (
            connection.execute(statement.with_for_update() if lock else statement)
            .mappings()
            .one_or_none()
        )
        return child, head

    # Bind preview to generation, job revision, actor and child, without secret locators.
    def project(self, connection, principal, child, head):
        base = dict(tenancy_id=child["id"], tenancy_name=child["name"])
        if child["status"] not in {"active", "pending"}:
            return SigningKeyView(**base, state="inactive")
        if head is None:
            return SigningKeyView(**base, state="not_prepared")
        if head["state"] == "retired":
            return SigningKeyView(**base, state="unavailable")
        key = current_key(head)
        row = (
            connection.execute(
                select(operation).where(
                    operation.c.workspace_id == head["workspace_id"],
                    operation.c.id == head["rotation_operation_id"],
                )
            )
            .mappings()
            .one()
        )
        state = (
            "preparing"
            if head["state"] == "staging"
            else "attention"
            if head["state"] == "attention"
            else "rotating"
            if head["state"] == "rotating"
            else "waiting"
            if row["state"] == "queued"
            or (
                row["state"] == "waiting"
                and row["wait_reason"] in {"signing_drain", "signing_recovery"}
            )
            else "scheduled"
        )
        if (
            state in {"scheduled", "waiting", "rotating"}
            and head["retire_at"] is not None
            and self.store.clock() >= head["retire_at"]
        ):
            state = "overdue"
        policy = self.policy_loader()
        available = (
            child["status"] == "active"
            and not policy.execution_paused
            and child["tenancy_ocid"] != policy.policy.parent_tenancy_ocid
            and child["parent_tenancy_ocid"] == policy.policy.parent_tenancy_ocid
            and child["organization_id"] == policy.policy.organization_id
            and (child["operation_id"] is None or child["operation_id"] == row["id"])
            and head["state"] in {"usable", "attention"}
            and state in {"scheduled", "attention", "overdue"}
            and (
                row["state"] == "needs_attention"
                if head["state"] == "attention"
                else row["state"] == "waiting" and row["wait_reason"] == "signing_rotation_due"
            )
        )
        preview = canonical_hash(
            {
                "tenancy_id": str(child["id"]),
                "tenancy_revision": child["revision"],
                "credential_id": str(head["id"]),
                "generation": head["generation"],
                "head_state": head["state"],
                "current_hash": head["current_hash"],
                "operation_id": str(row["id"]),
                "operation_revision": row["revision"],
                "actor": principal.actor.key,
            }
        )
        from datetime import timedelta

        completed = None
        if key is not None and key.version.generation > 1:
            completed = (
                connection.execute(
                    select(operation).where(
                        operation.c.workspace_id == head["workspace_id"],
                        operation.c.id == key.version.created_operation_id,
                        operation.c.state == "succeeded",
                    )
                )
                .mappings()
                .one_or_none()
            )

        return SigningKeyView(
            **base,
            state=state,
            generation=head["generation"],
            available=available,
            preview_hash=preview,
            operation_id=row["id"],
            starts_at=key.retire_at - timedelta(days=1) if key else None,
            retire_at=head["retire_at"],
            last_rotation_operation_id=completed["id"] if completed else None,
            last_rotated_at=completed["completed_at"] if completed else None,
        )

    # A coherent SQL snapshot reports only persisted progress; no adapter or Vault read occurs.
    def view(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            child, head = self.rows(connection, workspace, identifier)
            return self.project(connection, principal, child, head)

    # Historical request replay cannot accidentally rotate the next generation.
    def request(self, principal, identifier, command):
        digest = canonical_hash({"tenancy_id": str(identifier), **command.model_dump(mode="json")})
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            previous = (
                connection.execute(
                    select(audit_event).where(
                        audit_event.c.workspace_id == workspace,
                        audit_event.c.actor_subject == principal.actor.key,
                        audit_event.c.kind == "signing_key_requested",
                        audit_event.c.data["client_request_key"].astext
                        == str(command.client_request_key),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if previous:
                proof = SigningKeyRequestEvidence.model_validate_json(json.dumps(previous["data"]))
                if (
                    canonical_hash(previous["data"]) != previous["data_hash"]
                    or proof.request_digest != digest
                    or proof.tenancy_id != identifier
                ):
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                row = (
                    connection.execute(
                        select(operation).where(
                            operation.c.workspace_id == workspace,
                            operation.c.id == proof.operation_id,
                        )
                    )
                    .mappings()
                    .one()
                )
                return receipt(row)
            if not command.acknowledged:
                raise OrganizationConflict("SIGNING_KEY_CONFIRMATION_REQUIRED")
            child, head = self.rows(connection, workspace, identifier, lock=True)
            preview = self.project(connection, principal, child, head)
            if not preview.available or head is None:
                raise OrganizationConflict("SIGNING_KEY_ROTATION_UNAVAILABLE")
            if command.preview_hash != preview.preview_hash:
                raise OrganizationConflict("SIGNING_KEY_PREVIEW_CHANGED")
            if (command.action == "resume") != (preview.state == "attention"):
                raise OrganizationConflict("SIGNING_KEY_PREVIEW_CHANGED")
            row = (
                connection.execute(
                    select(operation)
                    .where(
                        operation.c.workspace_id == workspace,
                        operation.c.id == head["rotation_operation_id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            connection.execute(
                update(operation)
                .where(operation.c.workspace_id == workspace, operation.c.id == row["id"])
                .values(
                    state="queued",
                    wait_reason=None,
                    completed_at=None,
                    stage="Resume original signing-key operation"
                    if command.action == "resume"
                    else "Requested automation key rotation",
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
            connection.execute(
                update(signing_credential)
                .where(
                    signing_credential.c.workspace_id == workspace,
                    signing_credential.c.id == head["id"],
                )
                .values(
                    state="rotating" if command.action == "resume" else head["state"], updated_at=at
                )
            )
            proof = SigningKeyRequestEvidence(
                operation_id=row["id"],
                tenancy_id=identifier,
                client_request_key=command.client_request_key,
                request_digest=digest,
                action=command.action,
            )
            data = proof.model_dump(mode="json")
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    operation_id=row["id"],
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="signing_key_requested",
                    at=at,
                    contract_version=proof.contract_version,
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            self.enqueuer.enqueue(connection, row["id"])
            return receipt(dict(row) | {"state": "queued"})

    # Owned maintenance rescues persisted due work without another business job.
    def enqueue_due(self, connection, workspace, at, limit=100):
        from datetime import timedelta

        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("SIGNING_KEY_SCAN_LIMIT_INVALID")
        from otm.storage.tables import administrator, org_workspace
        from otm.storage.transaction import require_transaction

        require_transaction(connection)
        connection.execute(
            select(administrator.c.id)
            .where(
                administrator.c.workspace_id == workspace,
                administrator.c.identity_kind == "local_recovery",
                administrator.c.status == "active",
            )
            .with_for_update()
        ).scalar_one()
        connection.execute(
            select(org_workspace.c.id).where(org_workspace.c.id == workspace).with_for_update()
        ).scalar_one()
        rows = list(
            connection.execute(
                select(signing_credential)
                .join(
                    operation,
                    (operation.c.workspace_id == signing_credential.c.workspace_id)
                    & (operation.c.id == signing_credential.c.rotation_operation_id),
                )
                .where(
                    operation.c.state == "waiting",
                    operation.c.wait_reason == "signing_rotation_due",
                    signing_credential.c.workspace_id == workspace,
                    signing_credential.c.state == "usable",
                    signing_credential.c.retire_at <= at + timedelta(days=1),
                )
                .order_by(signing_credential.c.retire_at, signing_credential.c.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).mappings()
        )
        for head in rows:
            connection.execute(
                update(operation)
                .where(
                    operation.c.workspace_id == workspace,
                    operation.c.id == head["rotation_operation_id"],
                )
                .values(
                    state="queued",
                    wait_reason=None,
                    stage="Due automation key rotation queued",
                    updated_at=at,
                    revision=operation.c.revision + 1,
                )
            )
            self.enqueuer.enqueue(connection, head["rotation_operation_id"])
        return len(rows)


# Accepted work may drain, but overdue material never authorizes ordinary dispatch.
def signing_dispatch_allowed(connection, workspace, identifier, at):
    row = (
        connection.execute(
            select(signing_credential)
            .where(
                signing_credential.c.workspace_id == workspace,
                signing_credential.c.tenancy_id == identifier,
            )
            .order_by(
                (signing_credential.c.state == "retired").asc(),
                signing_credential.c.created_at.desc(),
            )
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return True
    current_key(row)
    return (
        row["state"] in {"usable", "rotating"}
        and row["retire_at"] is not None
        and at < row["retire_at"]
    )
