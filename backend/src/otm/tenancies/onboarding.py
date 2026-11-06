"""Persist guided onboarding in existing operations and steps; no second workflow engine."""

import json
from contextlib import nullcontext
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.storage.admission import RequestConflict
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, operation, operation_step, tenancy
from otm.tenancies.contracts import ActionReceipt, OrganizationIntent
from otm.tenancies.onboarding_contracts import (
    OnboardingCheck,
    OnboardingDiscovery,
    OnboardingEvidence,
    OnboardingHandoff,
    OnboardingView,
)

STEPS = (
    ("inspect_bootstrap", "Verify tenancy and bootstrap access"),
    ("establish_automation", "Create permanent automation access"),
    ("verify_automation", "Verify the permanent signer"),
    ("configure_required", "Create owner and recovery access"),
    ("verify_required", "Verify required access and recovery"),
    ("retire_temporary", "Retire temporary access"),
)


# New onboarding applies the accepted baseline and reprobes access before retiring its bootstrap.
def onboarding_steps(intent):
    if intent.onboarding_version in {2, 3} and intent.baseline is not None:
        return (
            STEPS[:-1]
            + (
                ("configure_baseline", "Apply and verify baseline: policy, quota, budget and tags"),
                (
                    "verify_configured_access",
                    "Reverify automation and recovery access after configuration",
                ),
            )
            + (
                (("capture_required_users", "Record permanent user identities"),)
                if intent.onboarding_version == 3
                else ()
            )
            + STEPS[-1:]
        )
    return STEPS


# Read only the current intent's step graph within the caller's existing transaction.
def step_rows(connection, row):
    return {
        r["step_key"]: r
        for r in connection.execute(
            select(operation_step).where(
                operation_step.c.workspace_id == row["workspace_id"],
                operation_step.c.operation_id == row["id"],
                operation_step.c.intent_revision == row["current_intent_revision"],
            )
        ).mappings()
    }


# Authenticate immutable organization intent; handoff callers additionally require onboarding.
def load_intent(connection, row, *, onboarding_only=True):
    event = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == row["workspace_id"],
                audit_event.c.id == row["current_intent_event_id"],
                audit_event.c.operation_id == row["id"],
                audit_event.c.intent_revision == row["current_intent_revision"],
            )
        )
        .mappings()
        .one()
    )
    frozen = IntentEventData.model_validate_json(json.dumps(event["data"]))
    if (
        canonical_hash(event["data"]) != event["data_hash"]
        or not isinstance(frozen.intent, OrganizationIntent)
        or frozen.actor.key != row["initiating_actor_subject"]
        or frozen.intent.workspace_id != row["workspace_id"]
    ):
        raise ValueError("INVALID_ONBOARDING_INTENT")
    if onboarding_only and frozen.intent.onboarding_version not in {1, 2, 3}:
        raise OrganizationConflict("ONBOARDING_NOT_AVAILABLE")
    return frozen


# A single typed event serves immutable attempt evidence and exact command replay detection.
def evidence(connection, row, at, payload, actor=None):
    data = payload.model_dump(mode="json")
    identifier = uuid4()
    connection.execute(
        audit_event.insert().values(
            id=identifier,
            workspace_id=row["workspace_id"],
            operation_id=row["id"],
            actor=actor.key if actor else "otm-worker:organization",
            actor_subject=actor.key if actor else "otm-worker:organization",
            actor_snapshot=actor.model_dump(mode="json")
            if actor
            else {"kind": "worker", "subject": "organization"},
            kind="onboarding_action" if actor else "onboarding_outcome",
            at=at,
            contract_version="onboarding-1",
            data=data,
            data_hash=canonical_hash(data),
        )
    )
    return identifier


# Reuse each logical step and append every attempt to audit rather than adding attempt tables.
def save_step(connection, row, key, at, *, inputs, payload, state="verified", actor=None):
    event = evidence(connection, row, at, payload, actor)
    statement = insert(operation_step).values(
        workspace_id=row["workspace_id"],
        operation_id=row["id"],
        intent_revision=row["current_intent_revision"],
        step_key=key,
        intent_event_id=row["current_intent_event_id"],
        command_kind="onboarding",
        contract_version="onboarding-1",
        inputs=inputs,
        state=state,
        execution_generation=1,
        attempt_number=1,
        current_attempt_id=uuid4(),
        effect_knowledge="none" if key in {"handoff", "inspect_bootstrap"} else "known",
        last_outcome=payload.model_dump(mode="json"),
        verified_at=at if state == "verified" else None,
        evidence_event_id=event,
    )
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=[
                operation_step.c.workspace_id,
                operation_step.c.operation_id,
                operation_step.c.intent_revision,
                operation_step.c.step_key,
            ],
            set_={
                "inputs": inputs,
                "state": state,
                "last_outcome": statement.excluded.last_outcome,
                "verified_at": statement.excluded.verified_at,
                "evidence_event_id": event,
                "attempt_number": operation_step.c.attempt_number + 1,
                "current_attempt_id": statement.excluded.current_attempt_id,
            },
        )
    )
    return event


# Explicit waits end the job and release transaction locks; the next command enqueues fresh work.
def transition(connection, row, at, state, stage, wait_reason=None):
    connection.execute(
        update(operation)
        .where(operation.c.workspace_id == row["workspace_id"], operation.c.id == row["id"])
        .values(
            state=state,
            stage=stage,
            wait_reason=wait_reason,
            completed_at=None,
            updated_at=at,
            revision=operation.c.revision + 1,
        )
    )


# Derive every action from stored progress; a GET never submits work or reads private keys.
def progress(connection, row, facade):
    frozen = load_intent(connection, row)
    intent = frozen.intent
    steps = step_rows(connection, row)
    handoff = steps.get("handoff")
    inspection = steps.get("inspect_bootstrap")
    phase = (
        "complete"
        if row["state"] == "succeeded"
        else "cancelled"
        if row["state"] == "cancelled"
        else "blocked"
        if row["state"] in {"failed", "needs_attention"}
        else "handoff"
        if row["wait_reason"] == "onboarding_handoff"
        else "review"
        if row["wait_reason"] == "onboarding_review"
        else "configuring"
        if handoff
        else "preparing"
    )
    actions = (
        ("verify_handoff",)
        if phase == "handoff"
        or (phase == "blocked" and (not inspection or inspection["state"] != "verified"))
        else ("start_setup",)
        if phase == "review"
        or (phase == "blocked" and inspection and inspection["state"] == "verified")
        else ()
    )
    issue = next(
        (s["last_outcome"]["safe_code"] for s in steps.values() if s["state"] == "needs_attention"),
        None,
    )
    return OnboardingView(
        operation_id=row["id"],
        baseline=intent.baseline,
        tenancy_id=intent.pending_tenancy_id,
        revision=row["revision"],
        state=row["state"],
        phase=phase,
        origin="create" if intent.action == "create_tenancy" else "import",
        requested_name=intent.name if intent.action == "create_tenancy" else None,
        requested_home_region=intent.home_region if intent.action == "create_tenancy" else None,
        expected_parent_tenancy_ocid=intent.parent_tenancy_ocid,
        owner_name=intent.target.display_name,
        administrator_name=frozen.actor.display_name or "Administrator",
        administrator_email=intent.email_contacts.activation.original_email
        if intent.email_contacts
        else intent.activation_email,
        email_contacts=intent.email_contacts,
        suggested_handoff=facade.onboarding_handoff(intent),
        submitted_handoff=OnboardingHandoff.model_validate(handoff["inputs"]["handoff"])
        if handoff
        else None,
        discovery=OnboardingDiscovery.model_validate(inspection["inputs"]["discovery"])
        if inspection and inspection["state"] == "verified"
        else None,
        bootstrap_username="otm-bootstrap-" + row["id"].hex[:12],
        checks=tuple(
            OnboardingCheck(
                key=k,
                label=label,
                state=steps[k]["state"] if k in steps else "pending",
                verified_at=steps[k]["verified_at"] if k in steps else None,
            )
            for k, label in onboarding_steps(intent)
        ),
        issue_code=issue,
        available_actions=actions,
    )


# Commands run under the organization store's anchor/session/workspace locks and current grant.
def submit(service, connection, state, row, principal, command, at):
    frozen = load_intent(connection, row)
    digest = canonical_hash(command.model_dump(mode="json"))
    if row["responsible_actor_subject"] != principal.actor.key:
        raise OrganizationConflict("ONBOARDING_RESPONSIBLE_ADMIN_REQUIRED")
    previous = (
        connection.execute(
            select(audit_event.c.data, audit_event.c.data_hash).where(
                audit_event.c.workspace_id == state.workspace,
                audit_event.c.operation_id == row["id"],
                audit_event.c.kind == "onboarding_action",
                audit_event.c.data["client_request_key"].astext == str(command.client_request_key),
            )
        )
        .mappings()
        .one_or_none()
    )
    if previous:
        if (
            canonical_hash(previous["data"]) != previous["data_hash"]
            or previous["data"]["request_hash"] != digest
        ):
            raise RequestConflict("REQUEST_KEY_REUSED")
        return ActionReceipt(
            operation_id=row["id"], state=row["state"], provider_mode="simulated", accepted_at=at
        )
    view = progress(connection, row, service.facade)
    if command.revision != row["revision"] or command.action not in view.available_actions:
        raise OrganizationConflict("ONBOARDING_PREVIEW_CHANGED")
    service._require_onboarding_context(state, frozen.intent)
    if command.action == "verify_handoff":
        supplied = command.handoff
        expected = view.suggested_handoff
        if supplied.tenancy_ocid != expected.tenancy_ocid or (view.origin == "create") != (
            supplied.activation_user_ocid is not None
        ):
            raise OrganizationConflict("ONBOARDING_TARGET_CHANGED")
        key, inputs = "handoff", {"handoff": supplied.model_dump(mode="json")}
    else:
        key, inputs = "handoff", dict(step_rows(connection, row)["handoff"]["inputs"])
        inputs["cleanup_confirmed"] = True
    payload = OnboardingEvidence(
        step="handoff",
        outcome="accepted",
        safe_code="ONBOARDING_ACCEPTED",
        client_request_key=command.client_request_key,
        request_hash=digest,
        handoff=command.handoff,
    )
    save_step(connection, row, key, at, inputs=inputs, payload=payload, actor=principal.actor)
    transition(
        connection,
        row,
        at,
        "queued",
        "Verifying handoff" if command.action == "verify_handoff" else "Configuring access",
    )
    service.enqueuer.enqueue(connection, row["id"])
    return ActionReceipt(
        operation_id=row["id"], state="queued", provider_mode="simulated", accepted_at=at
    )


# Execute deterministic facade capabilities in order; never retire access before replacement checks.
def advance(connection, row, intent, facade, at):
    steps = step_rows(connection, row)
    handoff = steps.get("handoff")
    if handoff is None:
        transition(
            connection,
            row,
            at,
            "waiting",
            "Activate tenancy and set up bootstrap access"
            if intent.action == "create_tenancy"
            else "Attach tenancy and set up bootstrap access",
            "onboarding_handoff",
        )
        return False
    current = "inspect_bootstrap"
    try:
        inspection = steps.get(current)
        if inspection is None or inspection["state"] != "verified":
            discovered = facade.inspect_onboarding(
                intent, OnboardingHandoff.model_validate(handoff["inputs"]["handoff"])
            )
            supplied = OnboardingHandoff.model_validate(handoff["inputs"]["handoff"])
            if (
                discovered.tenancy_ocid != intent.target.tenancy_ocid
                or discovered.parent_tenancy_ocid != intent.parent_tenancy_ocid
                or discovered.organization_id != intent.organization_id
                or discovered.bootstrap_user_ocid != supplied.bootstrap_user_ocid
                or discovered.activation_user_ocid != supplied.activation_user_ocid
                or discovered.bootstrap_user_ocid == discovered.activation_user_ocid
                or not discovered.bootstrap_scim_id
                or not discovered.domain_ocid
                or not discovered.name
                or not discovered.home_region
                or (intent.action == "create_tenancy" and not discovered.activation_scim_id)
                or (intent.action == "import_tenancy" and discovered.activation_scim_id is not None)
            ):
                raise ValueError("TARGET_CHANGED")
            save_step(
                connection,
                row,
                current,
                at,
                inputs={"discovery": discovered.model_dump(mode="json")},
                payload=OnboardingEvidence(
                    step=current,
                    outcome="verified",
                    safe_code="ONBOARDING_VERIFIED",
                    discovery=discovered,
                ),
            )
            connection.execute(
                update(tenancy)
                .where(
                    tenancy.c.workspace_id == row["workspace_id"],
                    tenancy.c.id == intent.pending_tenancy_id,
                )
                .values(name=discovered.name, home_region=discovered.home_region, updated_at=at)
            )
            transition(
                connection,
                row,
                at,
                "waiting",
                "Review verified setup and temporary account cleanup",
                "onboarding_review",
            )
            return False
        if not handoff["inputs"].get("cleanup_confirmed"):
            raise ValueError("CLEANUP_CONFIRMATION_REQUIRED")
        # All provider boundaries remain pure simulation. A network adapter must split dispatch
        # and evidence transactions, with qualified reconciliation, before being composed here.
        for current, _ in onboarding_steps(intent)[1:]:
            if current in steps and steps[current]["state"] == "verified":
                continue
            captured = None
            if current == "capture_required_users":
                from otm.tenancies.onboarding_users import capture_users

                captured = capture_users(facade, intent, inspection["inputs"]["discovery"])
            elif current == "configure_baseline":
                from otm.tenancies.onboarding_baseline import configure_baseline

                configure_baseline(connection, row, intent, facade, at)
            elif current == "verify_configured_access":
                # Fresh probes must run after root-policy writes, even if earlier probes passed.
                facade.onboarding_step(
                    intent, "verify_automation", inspection["inputs"]["discovery"]
                )
                facade.onboarding_step(intent, "verify_required", inspection["inputs"]["discovery"])
            else:
                facade.onboarding_step(intent, current, inspection["inputs"]["discovery"])
            # Capture evidence, identities and opted-in connection either all persist or roll back.
            with connection.begin_nested() if captured is not None else nullcontext():
                captured_event = save_step(
                    connection,
                    row,
                    current,
                    at,
                    inputs={},
                    payload=OnboardingEvidence(
                        step=current,
                        outcome="verified",
                        safe_code="ONBOARDING_VERIFIED",
                        required_users=captured,
                    ),
                )
                if captured is not None:
                    from otm.storage.managed_bindings import capture_bindings

                    capture_bindings(connection, row, intent, captured, captured_event, at)
                if captured is not None:
                    from otm.storage.user_presence_connections import capture_connection

                    capture_connection(connection, row, intent, captured_event, at)
            # A known setup effect prevents the no-effect cancellation path from abandoning it.
            connection.execute(
                update(operation)
                .where(operation.c.workspace_id == row["workspace_id"], operation.c.id == row["id"])
                .values(effect_knowledge="known")
            )
        return True
    except ValueError:
        code = {
            "inspect_bootstrap": "BOOTSTRAP_UNVERIFIED",
            "verify_automation": "AUTOMATION_UNVERIFIED",
            "retire_temporary": "CLEANUP_UNVERIFIED",
            "configure_baseline": "BASELINE_UNVERIFIED",
        }.get(current, "REQUIRED_ACCESS_UNVERIFIED")
        save_step(
            connection,
            row,
            current,
            at,
            inputs={},
            state="needs_attention",
            payload=OnboardingEvidence(step=current, outcome="blocked", safe_code=code),
        )
        transition(
            connection,
            row,
            at,
            "needs_attention",
            "Onboarding check needs attention",
            "onboarding_check",
        )
        return False
