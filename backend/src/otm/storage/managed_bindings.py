"""Canonical identity mappings from fresh typed onboarding evidence; no access-health authority."""

import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

from otm.operations.contracts import canonical_hash
from otm.providers.lifecycle import OnboardingUsers
from otm.storage.tables import audit_event, operation_step, tenancy
from otm.storage.tables import managed_object_binding as binding
from otm.storage.transaction import require_transaction
from otm.tenancies.onboarding_contracts import OnboardingEvidence


# Retain domain/users together; caller owns the existing locked simulation transition transaction.
def capture_bindings(connection, row, intent, users, event_id, at):
    require_transaction(connection)
    if intent.onboarding_version != 3 or intent.action not in {"create_tenancy", "import_tenancy"}:
        raise ValueError("MANAGED_BINDING_SOURCE_UNVERIFIED")
    users = OnboardingUsers.model_validate(users)
    event = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == intent.workspace_id,
                audit_event.c.operation_id == row["id"],
                audit_event.c.id == event_id,
                audit_event.c.kind == "onboarding_outcome",
            )
        )
        .mappings()
        .one_or_none()
    )
    # Managed ownership comes from the same setup intent's verified creation/access steps.
    setup = operation_step.alias("binding_setup")
    setup_keys = (
        "establish_automation",
        "verify_automation",
        "configure_required",
        "verify_required",
        "configure_baseline",
        "verify_configured_access",
    )
    qualified_setup = (
        select(func.count())
        .select_from(setup)
        .where(
            setup.c.workspace_id == intent.workspace_id,
            setup.c.operation_id == row["id"],
            setup.c.intent_revision == row["current_intent_revision"],
            setup.c.state == "verified",
            setup.c.step_key.in_(setup_keys),
        )
        .scalar_subquery()
    )
    step = connection.execute(
        select(operation_step.c.evidence_event_id).where(
            operation_step.c.workspace_id == intent.workspace_id,
            operation_step.c.operation_id == row["id"],
            operation_step.c.intent_revision == row["current_intent_revision"],
            qualified_setup == len(setup_keys),
            operation_step.c.step_key == "capture_required_users",
            operation_step.c.state == "verified",
        )
    ).scalar_one_or_none()
    child = (
        connection.execute(
            select(tenancy).where(
                tenancy.c.workspace_id == intent.workspace_id,
                tenancy.c.id == intent.pending_tenancy_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if event is None or child is None or step != event_id:
        raise ValueError("MANAGED_BINDING_SOURCE_UNVERIFIED")
    # JSONB arrays represent closed tuple fields; validate their wire representation as JSON.
    evidence = OnboardingEvidence.model_validate_json(json.dumps(event["data"]))
    if (
        canonical_hash(event["data"]) != event["data_hash"]
        or evidence.step != "capture_required_users"
        or evidence.outcome != "verified"
        or evidence.required_users != users
        or event["at"] != at
        or row["workspace_id"] != intent.workspace_id
        or users.workspace_id != intent.workspace_id
        or users.tenancy_ocid != child["tenancy_ocid"]
        or users.tenancy_ocid != intent.target.tenancy_ocid
        or users.parent_tenancy_ocid != child["parent_tenancy_ocid"]
        or users.parent_tenancy_ocid != intent.parent_tenancy_ocid
        or users.organization_id != child["organization_id"]
        or users.organization_id != intent.organization_id
    ):
        raise ValueError("MANAGED_BINDING_SOURCE_UNVERIFIED")
    existing = list(
        connection.execute(
            select(binding).where(
                binding.c.workspace_id == intent.workspace_id,
                binding.c.tenancy_id == child["id"],
            )
        ).mappings()
    )
    expected = {
        "identity/domain": ("identity_domain", users.domain_ocid, None, None, "observed_reference"),
        **{
            "identity/user/" + purpose: (
                "managed_user",
                subject.provider_ocid,
                subject.scim_resource_id,
                subject.user_name,
                "managed",
            )
            for purpose, subject in (("automation", users.automation), ("recovery", users.recovery))
        },
    }
    if existing:
        by_key = {item["logical_key"]: item for item in existing}
        domain = by_key.get("identity/domain")
        if len(existing) != 3 or set(by_key) != set(expected) or domain is None:
            raise ValueError("MANAGED_BINDING_CONFLICT")
        for key, facts in expected.items():
            item = by_key[key]
            if (
                tuple(
                    item[field]
                    for field in (
                        "kind",
                        "provider_ocid",
                        "scim_resource_id",
                        "user_name",
                        "ownership_mode",
                    )
                )
                != facts
                or item["source_evidence_event_id"] != event_id
                or item["created_operation_id"] != row["id"]
                or item["state"] != "active"
                or item["generation"] != 1
                or item["identity_domain_binding_id"]
                != (None if key == "identity/domain" else domain["id"])
            ):
                raise ValueError("MANAGED_BINDING_CONFLICT")
        return tuple(by_key[key]["id"] for key in expected)
    if child["status"] != "pending" or child["operation_id"] != row["id"]:
        raise ValueError("MANAGED_BINDING_SOURCE_UNVERIFIED")
    identifiers = {key: uuid4() for key in expected}
    # A savepoint prevents a caught insert failure from leaving only part of the three-row set.
    try:
        with connection.begin_nested():
            for key, facts in expected.items():
                kind, ocid, scim, name, ownership = facts
                connection.execute(
                    binding.insert().values(
                        id=identifiers[key],
                        workspace_id=intent.workspace_id,
                        tenancy_id=child["id"],
                        logical_key=key,
                        kind=kind,
                        handler_contract_version="required-user-binding-1",
                        generation=1,
                        provider_ocid=ocid,
                        scim_resource_id=scim,
                        user_name=name,
                        ownership_mode=ownership,
                        state="active",
                        created_operation_id=row["id"],
                        source_evidence_event_id=event_id,
                        retired_operation_id=None,
                        identity_domain_binding_id=None
                        if kind == "identity_domain"
                        else identifiers["identity/domain"],
                        created_at=at,
                        updated_at=at,
                    )
                )
    except DBAPIError:
        raise ValueError("MANAGED_BINDING_CONFLICT") from None
    return tuple(identifiers.values())


# Retire local management only after verified termination initiation; preserve all identity history.
def retire_bindings(connection, workspace_id, tenancy_id, operation_id, at):
    require_transaction(connection)
    connection.execute(
        update(binding)
        .where(
            binding.c.workspace_id == workspace_id,
            binding.c.tenancy_id == tenancy_id,
            binding.c.state == "active",
        )
        .values(state="retired", retired_operation_id=operation_id, updated_at=at)
    )
    from otm.storage.user_presence_connections import retire_connection

    retire_connection(connection, workspace_id, tenancy_id, operation_id, at)
