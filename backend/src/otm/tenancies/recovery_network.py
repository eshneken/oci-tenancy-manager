"""Preview and admit one conditional recovery-perimeter repair through existing durable records."""

import json
from uuid import uuid4

from sqlalchemy import String, and_, select, update

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.recovery_console import InspectRecoveryConsole, observed_fingerprint
from otm.providers.required_user_contracts import RequiredUserReadContext
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import administrator, audit_event, operation, tenancy
from otm.storage.tables import user_presence_check as checks
from otm.tenancies.presence import FRESH_FOR, console_view, presence_views, receipt
from otm.tenancies.recovery_network_contracts import RecoveryNetworkIntent, RecoveryNetworkPreview


# Exact retained captures change only through sealed successful repair evidence, not name matching.
def latest_network_capture(connection, workspace, snapshot, source):
    from otm.tenancies.recovery_network_contracts import RecoveryNetworkEvidence

    origin = audit_event.alias("network_source_intent")
    row = (
        connection.execute(
            select(
                audit_event,
                origin.c.data.label("intent_data"),
                origin.c.data_hash.label("intent_hash"),
            )
            .join(
                operation,
                and_(
                    operation.c.id == audit_event.c.operation_id,
                    operation.c.workspace_id == audit_event.c.workspace_id,
                ),
            )
            .join(
                origin,
                and_(
                    origin.c.id == operation.c.current_intent_event_id,
                    origin.c.workspace_id == operation.c.workspace_id,
                    origin.c.operation_id == operation.c.id,
                    origin.c.intent_revision == operation.c.current_intent_revision,
                    origin.c.kind == "operation_intent",
                ),
            )
            .join(
                checks,
                and_(
                    checks.c.workspace_id == operation.c.workspace_id,
                    checks.c.tenancy_id == snapshot.tenancy_id,
                    checks.c.operation_id.cast(String)
                    == origin.c.data["intent"]["source_check_id"].astext,
                ),
            )
            .where(
                audit_event.c.workspace_id == workspace,
                audit_event.c.kind == "recovery_network_outcome",
                operation.c.kind == "recovery_network_repair",
                audit_event.c.data["tenancy_id"].astext == str(snapshot.tenancy_id),
                audit_event.c.data["effect"].astext == "known",
            )
            # Each later repair needs a new source check; its ordinal survives equal wall clocks.
            .order_by(checks.c.acquisition_sequence.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return source
    proof = RecoveryNetworkEvidence.model_validate_json(json.dumps(row["data"]))
    if canonical_hash(row["data"]) != row["data_hash"] or proof.operation_id != row["operation_id"]:
        raise ValueError("RECOVERY_NETWORK_EVIDENCE_INVALID")
    intent = IntentEventData.model_validate_json(json.dumps(row["intent_data"]))
    if (
        canonical_hash(row["intent_data"]) != row["intent_hash"]
        or not isinstance(intent.intent, RecoveryNetworkIntent)
        or intent.intent.workspace_id != workspace
        or intent.intent.snapshot != proof.snapshot
        or row["actor_subject"] != "otm-worker:recovery-network"
        or row["actor_snapshot"] != {"kind": "worker", "subject": "recovery-network"}
    ):
        raise ValueError("RECOVERY_NETWORK_SOURCE_INVALID")
    excluded = {"tenancy_name", "tenancy_revision", "recovery_console_fingerprint"}
    if proof.snapshot.model_dump(exclude=excluded) != snapshot.model_dump(exclude=excluded):
        return source
    if proof.capture is None or source.recovery_console is None:
        raise ValueError("RECOVERY_NETWORK_CAPTURE_MISSING")
    if proof.capture.binding != source.recovery_console.binding:
        raise ValueError("RECOVERY_NETWORK_BINDINGS_CHANGED")
    return source.model_copy(update={"recovery_console": proof.capture})


# Scope construction never accepts a domain URL, recovery signer or provider target from the SPA.
def network_command(snapshot, capture, desired, operation_id, attempt_id):
    return InspectRecoveryConsole(
        context=RequiredUserReadContext(
            workspace_id=snapshot.subjects[0].workspace_id,
            operation_id=operation_id,
            step_key="recovery_network:" + str(snapshot.tenancy_id),
            attempt_id=attempt_id,
            intent_revision=1,
            execution_generation=1,
            connection_id=snapshot.connection_id,
            connection_revision=snapshot.connection_revision,
        ),
        target=snapshot.subjects[1],
        binding=capture.binding,
        desired=desired,
    )


# Admission shares current session/grant locks and the existing child operation fence.
class RecoveryNetworkRepairs:
    # Explicit host composition supplies the guard for versioned signing credentials.
    signing_guard = None

    # Host-owned source selection and facade factory are explicit; no adapter is auto-discovered.
    def __init__(self, presence, factory, enqueuer):
        self.presence, self.factory, self.enqueuer = presence, factory, enqueuer
        self.store = presence.store

    # Database preparation has no provider I/O and requires current positive recovery presence.
    def prepare(self, connection, workspace, identifier):
        from otm.tenancies.presence_source import load_presence_source

        child = (
            connection.execute(
                select(tenancy).where(
                    tenancy.c.workspace_id == workspace, tenancy.c.id == identifier
                )
            )
            .mappings()
            .one_or_none()
        )
        if child is None:
            raise OrganizationConflict("TENANCY_NOT_FOUND")
        desired = self.presence.console_policy()
        snapshot = self.presence.snapshot(connection, workspace, child)
        if snapshot is None or desired is None or self.enqueuer is None:
            raise OrganizationConflict("RECOVERY_NETWORK_REPAIR_BLOCKED")
        last = (
            connection.execute(
                select(checks)
                .where(checks.c.workspace_id == workspace, checks.c.tenancy_id == identifier)
                .order_by(checks.c.acquisition_sequence.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if last is None or last["state"] not in {"complete", "unavailable"}:
            raise OrganizationConflict("RECOVERY_NETWORK_REPAIR_BLOCKED")
        event = (
            connection.execute(
                select(audit_event).where(audit_event.c.id == last["evidence_event_id"])
            )
            .mappings()
            .one()
        )
        at = self.store.clock()
        policy = console_view(snapshot, last, event, at)
        person = presence_views(snapshot, last, event, at).get("recovery")
        if (
            person is None
            or person.state != "present"
            or person.stale
            or policy.state != "drift"
            or policy.mfa_exemption != "verified"
            or policy.network_boundary != "drift"
            or policy.observed_fingerprint is None
        ):
            raise OrganizationConflict("RECOVERY_NETWORK_REPAIR_BLOCKED")
        source = load_presence_source(connection, snapshot)
        capture = source.recovery_console
        if capture is None:
            raise OrganizationConflict("RECOVERY_NETWORK_REPAIR_BLOCKED")
        digest = canonical_hash(
            {
                "snapshot": snapshot.model_dump(mode="json"),
                "source_hash": canonical_hash(source.model_dump(mode="json")),
                "source_check_id": str(last["operation_id"]),
                "observed": policy.observed_fingerprint,
                "desired": desired.fingerprint,
            }
        )
        # Setup authenticates ownership; the sealed check supplies actual current before-state.
        return child, snapshot, source, desired, last, policy.observed_fingerprint, digest

    # Live capability inspection is outside all database transactions and holds no row locks.
    def preview(self, principal, identifier):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            child, snapshot, source, desired, last, observed, digest = self.prepare(
                connection, workspace, identifier
            )
        command = network_command(snapshot, source.recovery_console, desired, uuid4(), uuid4())
        authority = self.factory(command, source.recovery_console, self.store.clock).preview(
            command
        )
        if observed_fingerprint(authority.facts) != observed:
            raise OrganizationConflict("RECOVERY_NETWORK_PREVIEW_CHANGED")
        return RecoveryNetworkPreview(
            tenancy_id=identifier,
            tenancy_name=child["name"],
            preview_hash=digest,
            desired_fingerprint=desired.fingerprint,
            observed_fingerprint=observed,
            current_network_count=len(authority.facts.perimeter.allowed_cidrs),
            desired_network_count=len(desired.allowed_cidrs),
            expires_at=last["checked_at"] + FRESH_FOR,
        )

    # Receipt replay precedes current-context checks, but a new action always needs fresh consent.
    def start(self, principal, identifier, command):
        if not command.acknowledged:
            raise OrganizationConflict("RECOVERY_NETWORK_CONFIRMATION_REQUIRED")
        digest = canonical_hash({"tenancy_id": str(identifier), **command.model_dump(mode="json")})
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            prior = (
                connection.execute(
                    select(operation).where(
                        operation.c.workspace_id == workspace,
                        operation.c.initiating_actor_subject == principal.actor.key,
                        operation.c.client_request_key == command.client_request_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if prior:
                if prior["kind"] != "recovery_network_repair" or prior["request_digest"] != digest:
                    raise RequestConflict("REQUEST_KEY_REUSED_FOR_DIFFERENT_INTENT")
                return receipt(prior)
            connection.execute(
                select(tenancy.c.id)
                .where(tenancy.c.workspace_id == workspace, tenancy.c.id == identifier)
                .with_for_update()
            ).scalar_one_or_none()
            if self.signing_guard is not None:
                self.signing_guard(connection, workspace, identifier, at)
            child, snapshot, source, desired, last, observed, preview = self.prepare(
                connection, workspace, identifier
            )
            if command.preview_hash != preview:
                raise OrganizationConflict("RECOVERY_NETWORK_PREVIEW_CHANGED")
            grant = (
                connection.execute(
                    select(administrator).where(
                        administrator.c.workspace_id == workspace,
                        administrator.c.issuer == principal.session.issuer,
                        administrator.c.subject == principal.session.subject,
                    )
                )
                .mappings()
                .one()
            )
            key, event = uuid4(), uuid4()
            frozen = RecoveryNetworkIntent(
                workspace_id=workspace,
                administrator_id=grant["id"],
                authorization_revision=grant["authorization_revision"],
                snapshot=snapshot,
                source_check_id=last["operation_id"],
                source_hash=canonical_hash(source.model_dump(mode="json")),
                desired_fingerprint=desired.fingerprint,
                observed_fingerprint=observed,
                preview_hash=preview,
                expires_at=last["checked_at"] + FRESH_FOR,
                target={"tenancy_ocid": child["tenancy_ocid"], "display_name": child["name"]},
            )
            data = IntentEventData(intent=frozen, actor=principal.actor).model_dump(mode="json")
            row = dict(
                id=key,
                workspace_id=workspace,
                kind="recovery_network_repair",
                initiating_actor_subject=principal.actor.key,
                initiating_actor_snapshot=principal.actor.model_dump(mode="json"),
                responsible_actor_subject=principal.actor.key,
                client_request_key=command.client_request_key,
                request_digest=digest,
                current_intent_revision=1,
                current_intent_event_id=event,
                state="queued",
                stage="Repair approved recovery networks",
                effect_knowledge="none",
                revision=1,
                accepted_at=at,
                created_at=at,
                updated_at=at,
            )
            connection.execute(operation.insert().values(**row))
            connection.execute(
                audit_event.insert().values(
                    id=event,
                    workspace_id=workspace,
                    operation_id=key,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="operation_intent",
                    intent_revision=1,
                    at=at,
                    contract_version=frozen.contract_version,
                    data=data,
                    data_hash=canonical_hash(data),
                )
            )
            connection.execute(
                update(tenancy)
                .where(tenancy.c.id == identifier, tenancy.c.workspace_id == workspace)
                .values(operation_id=key)
            )
            self.enqueuer.enqueue(connection, key)
            return receipt(row)
