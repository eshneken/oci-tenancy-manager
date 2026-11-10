"""Audited CURRENT disclosure and original four-hour obligations, never plaintext persistence."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update

from otm.operations.contracts import canonical_hash
from otm.providers.recovery_password import require_password_material
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import (
    administrator,
    audit_event,
    operation,
    tenancy,
)
from otm.storage.tables import (
    recovery_credential as heads,
)
from otm.storage.tables import (
    recovery_grant as grants,
)
from otm.storage.tables import (
    user_presence_check as checks,
)
from otm.tenancies.presence import (
    administrator_view,
    console_view,
    presence_views,
)
from otm.tenancies.recovery_password_contracts import (
    RecoveryDisclosureEvidence,
    RecoveryPasswordEvidence,
    RecoveryPasswordIntent,
    RecoveryPasswordView,
)
from otm.tenancies.recovery_password_records import (
    admit_operation,
    location_of,
    record_event,
    version_of,
)

DURATION = timedelta(hours=4)


# Retrieve exact local rows without provider I/O; a page read never prepares or adopts an account.
def current_head(connection, workspace, tenancy_id, *, lock=False):
    query = select(heads).where(
        heads.c.workspace_id == workspace,
        heads.c.tenancy_id == tenancy_id,
        heads.c.state != "retired",
    )
    return connection.execute(query.with_for_update() if lock else query).mappings().one_or_none()


# Fresh independent presence, assignments and effective console controls all gate human disclosure.
def disclosure_ready(presence, connection, workspace, child, head, at):
    snapshot = presence.snapshot(connection, workspace, child)
    if snapshot is None or location_of(head).target != snapshot.subjects[1]:
        return False
    latest = (
        connection.execute(
            select(checks)
            .where(
                checks.c.workspace_id == workspace,
                checks.c.tenancy_id == child["id"],
            )
            .order_by(checks.c.acquisition_sequence.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if latest is None or latest["state"] != "complete":
        return False
    event = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == workspace,
                audit_event.c.operation_id == latest["operation_id"],
                audit_event.c.id == latest["evidence_event_id"],
                audit_event.c.kind == "required_user_check_outcome",
            )
        )
        .mappings()
        .one()
    )
    subjects = presence_views(snapshot, latest, event, at)
    access = administrator_view(snapshot, latest, event, at, "recovery")
    policy = console_view(snapshot, latest, event, at)
    return (
        set(subjects) == {"automation", "recovery"}
        and all(s.state == "present" and not s.stale for s in subjects.values())
        and access.group == "verified"
        and access.domain_role == "verified"
        and not access.stale
        and policy.state == "verified"
        and policy.mfa_exemption == "verified"
        and policy.network_boundary == "verified"
    )


# The original exposure deadline, current generation and current policy evidence bind confirmation.
def preview_digest(head, child, ready):
    return canonical_hash(
        {
            "credential_id": str(head["id"]),
            "generation": head["generation"],
            "exposure_generation": head["exposure_generation"],
            "current_version_id": str(head["current_version_id"]),
            "child_revision": child["revision"],
            "ready": ready,
            "first_disclosure_at": head["first_disclosure_at"].isoformat()
            if head["first_disclosure_at"]
            else None,
            "rotation_due_at": head["rotation_due_at"].isoformat()
            if head["rotation_due_at"]
            else None,
        }
    )


# One API service uses existing current-entitlement locks, exact custody and native scheduling.
class RecoveryPasswordAccess:
    # No default custody/transport/provider is invented when dependencies are not composed.
    def __init__(self, presence, vault, enqueuer, *, notifier=None):
        self.presence, self.store = presence, presence.store
        self.vault, self.enqueuer, self.notifier = vault, enqueuer, notifier

    # Missing/retired/legacy custody stays visibly unavailable without resolving secret content.
    def view(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return self.project(connection, workspace, identifier, self.store.clock())

    # Derive every availability/consent field from the exact head and dated current observations.
    def project(self, connection, workspace, identifier, at):
        child = (
            connection.execute(
                select(tenancy).where(
                    tenancy.c.workspace_id == workspace,
                    tenancy.c.id == identifier,
                )
            )
            .mappings()
            .one_or_none()
        )
        if child is None:
            raise OrganizationConflict("TENANCY_NOT_FOUND")
        head = current_head(connection, workspace, identifier)
        base = dict(tenancy_id=identifier, tenancy_name=child["name"], available=False)
        if child["status"] == "pending":
            return RecoveryPasswordView(
                **base,
                state="attention" if head and head["state"] == "unknown" else "preparing",
                operation_id=head["rotation_operation_id"] if head else child["operation_id"],
            )
        if child["status"] != "active":
            return RecoveryPasswordView(**base, state="inactive")
        if head is None:
            return RecoveryPasswordView(**base, state="not_prepared")
        location = location_of(head)
        state = (
            "preparing"
            if head["state"] == "staging"
            else "rotating"
            if head["state"] == "rotating"
            else "attention"
            if head["state"] == "unknown"
            else "overdue"
            if head["rotation_due_at"] and at >= head["rotation_due_at"]
            else "exposed"
            if head["rotation_due_at"]
            else "ready"
        )
        ready = (
            location.secret_reference is not None
            and state in {"ready", "exposed"}
            and head["current_version_id"] is not None
            and self.notifier is not None
            and disclosure_ready(self.presence, connection, workspace, child, head, at)
        )
        return RecoveryPasswordView(
            **dict(base, available=ready),
            state=state if ready or state not in {"ready", "exposed"} else "unavailable",
            user_name=location.target.user_name,
            preview_hash=preview_digest(head, child, ready) if ready else None,
            first_disclosure_at=head["first_disclosure_at"],
            rotation_due_at=head["rotation_due_at"],
            operation_id=head["rotation_operation_id"],
        )

    # Audit and queue precede custody reads; a lost response retains its original deadline.
    def disclose(self, principal, identifier, command):
        if not command.acknowledged:
            raise OrganizationConflict("RECOVERY_PASSWORD_CONFIRMATION_REQUIRED")
        digest = canonical_hash({"tenancy_id": str(identifier), **command.model_dump(mode="json")})
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            child = (
                connection.execute(
                    select(tenancy)
                    .where(
                        tenancy.c.workspace_id == workspace,
                        tenancy.c.id == identifier,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if child is None:
                raise OrganizationConflict("TENANCY_NOT_FOUND")
            head = current_head(connection, workspace, identifier, lock=True)
            prior = (
                connection.execute(
                    select(grants).where(
                        grants.c.workspace_id == workspace,
                        grants.c.requesting_subject == principal.actor.key,
                        grants.c.request_key == command.client_request_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if prior is not None:
                if prior["payload_digest"] != digest:
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                request = prior
            else:
                view = self.project(connection, workspace, identifier, at)
                if not view.available:
                    raise OrganizationConflict("RECOVERY_PASSWORD_UNAVAILABLE")
                if command.preview_hash != view.preview_hash:
                    raise OrganizationConflict("RECOVERY_PASSWORD_PREVIEW_CHANGED")
                request = self.accept(
                    connection, workspace, child, head, principal, command, digest, at
                )
                head = current_head(connection, workspace, identifier, lock=True)
            # A retried old grant never releases a new password or opens a replacement window.
            if (
                head is None
                or request["credential_id"] != head["id"]
                or request["disclosed_version_id"] != head["current_version_id"]
                or request["exposure_generation"] != head["exposure_generation"]
            ):
                raise OrganizationConflict("RECOVERY_PASSWORD_REQUEST_CLOSED")
            if (
                head["state"] != "usable"
                or not head["first_disclosure_at"] <= at < head["rotation_due_at"]
                or not disclosure_ready(self.presence, connection, workspace, child, head, at)
            ):
                raise OrganizationConflict("RECOVERY_PASSWORD_UNAVAILABLE")
            location = location_of(head)
            expected = version_of(connection, head, head["current_version_id"])
            request_id = request["id"]
        # CURRENT is deliberately resolved after durable admission, outside every DB transaction.
        try:
            material = require_password_material(self.vault.current(location))
        except Exception:
            # A failed read does not prove a changed password; retain the committed
            # window for retry.
            raise OrganizationConflict("RECOVERY_PASSWORD_READ_UNAVAILABLE") from None
        if material.reference != expected:
            self.hold(workspace, head["id"], head["generation"])
            raise OrganizationConflict("RECOVERY_PASSWORD_UNAVAILABLE")
        # Recheck live authority and exact window after the external read and before release.
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            latest = current_head(connection, workspace, identifier, lock=True)
            view = self.project(connection, workspace, identifier, at)
            if (
                not view.available
                or latest is None
                or latest["id"] != head["id"]
                or latest["generation"] != head["generation"]
                or latest["current_version_id"] != request["disclosed_version_id"]
                or latest["exposure_generation"] != request["exposure_generation"]
                or not latest["first_disclosure_at"] <= at < latest["rotation_due_at"]
            ):
                raise OrganizationConflict("RECOVERY_PASSWORD_UNAVAILABLE")
            result = {
                "request_id": str(request_id),
                "user_name": location.target.user_name,
                "rotation_due_at": latest["rotation_due_at"].isoformat(),
                "first_disclosure_at": latest["first_disclosure_at"].isoformat(),
                "operation_id": str(latest["rotation_operation_id"]),
                "provider_mode": "simulated",
            }
        # This explicit last-mile response is the sole non-redacted conversion in the application.
        result["password"] = material.password.get_secret_value()
        return result

    # First requests open one window; later requests retain its root, version and original due job.
    def accept(self, connection, workspace, child, head, principal, command, digest, at):
        request_id = uuid4()
        if head["first_disclosure_at"] is None:
            due = at + DURATION
            reference = version_of(connection, head, head["current_version_id"])
            intent = RecoveryPasswordIntent(
                workspace_id=workspace,
                phase="rotation",
                credential_id=head["id"],
                generation=head["generation"],
                location=location_of(head),
                target={"tenancy_ocid": child["tenancy_ocid"], "display_name": child["name"]},
                onboarding_operation_id=head["source_operation_id"],
                expected_current=reference.version,
                exposure_generation=head["exposure_generation"] + 1,
                due_at=due,
            )
            rotation = admit_operation(
                connection,
                intent,
                principal.actor,
                at,
                self.enqueuer,
            )
            head = dict(
                head,
                first_disclosure_at=at,
                rotation_due_at=due,
                active_window_grant_id=request_id,
                rotation_operation_id=rotation,
                exposure_generation=intent.exposure_generation,
            )
            connection.execute(
                update(heads)
                .where(
                    heads.c.workspace_id == workspace,
                    heads.c.id == head["id"],
                )
                .values(
                    first_disclosure_at=at,
                    rotation_due_at=due,
                    active_window_grant_id=request_id,
                    rotation_operation_id=rotation,
                    exposure_generation=intent.exposure_generation,
                    updated_at=at,
                )
            )
        request = dict(
            id=request_id,
            workspace_id=workspace,
            tenancy_id=child["id"],
            credential_id=head["id"],
            disclosed_version_id=head["current_version_id"],
            requesting_subject=principal.actor.key,
            requester_snapshot=principal.actor.model_dump(mode="json"),
            request_key=command.client_request_key,
            payload_digest=digest,
            accepted_operation_id=head["rotation_operation_id"],
            window_root_grant_id=head["active_window_grant_id"],
            exposure_generation=head["exposure_generation"],
            accepted_at=at,
            first_disclosure_attempt_at=head["first_disclosure_at"],
            due_at=head["rotation_due_at"],
        )
        connection.execute(grants.insert().values(**request))
        proof = RecoveryDisclosureEvidence(
            grant_id=request_id,
            credential_id=head["id"],
            tenancy_id=child["id"],
            disclosed_version_id=head["current_version_id"],
            window_root_grant_id=head["active_window_grant_id"],
            exposure_generation=head["exposure_generation"],
            first_disclosure_at=head["first_disclosure_at"],
            rotation_due_at=head["rotation_due_at"],
        )
        record_event(
            connection,
            workspace,
            head["rotation_operation_id"],
            "recovery_password_disclosed",
            proof,
            at,
            principal.actor,
        )
        self.notifier.stage_recovery_disclosure(connection, request, child, principal.actor, at)
        return request

    # Unknown CURRENT immediately holds this obligation and alerts without resetting its deadline.
    def hold(self, workspace, credential_id, generation):
        with self.store.engine.begin() as connection:
            connection.execute(
                select(administrator.c.id)
                .where(
                    administrator.c.workspace_id == workspace,
                    administrator.c.identity_kind == "local_recovery",
                    administrator.c.status == "active",
                )
                .with_for_update()
            ).scalar_one()
            self.store._workspace(connection, workspace, lock=True)
            head = (
                connection.execute(
                    select(heads)
                    .where(
                        heads.c.workspace_id == workspace,
                        heads.c.id == credential_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if head["generation"] != generation or head["state"] != "usable":
                return
            at = self.store.clock()
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
                update(heads)
                .where(heads.c.id == credential_id)
                .values(
                    state="unknown",
                    updated_at=at,
                )
            )
            proof = RecoveryPasswordEvidence(
                credential_id=credential_id,
                tenancy_id=head["tenancy_id"],
                operation_id=row["id"],
                phase="rotation",
                state="unknown",
                effect="unknown",
                safe_code="RECOVERY_PASSWORD_UNKNOWN",
                checked_at=at,
            )
            record_event(connection, workspace, row["id"], "recovery_password_outcome", proof, at)
            connection.execute(
                update(operation)
                .where(operation.c.id == row["id"])
                .values(
                    state="needs_attention",
                    effect_knowledge="unknown",
                    wait_reason=None,
                    stage="Reconcile unexpected recovery password CURRENT",
                    updated_at=at,
                    completed_at=at,
                    revision=row["revision"] + 1,
                )
            )
            if self.notifier is not None:
                self.notifier.stage_recovery_failure(connection, row, head, at)
