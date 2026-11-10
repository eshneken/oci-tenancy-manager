"""Admit password custody in the onboarding transaction before temporary cleanup."""

import json
from uuid import uuid4

from sqlalchemy import select

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.recovery_password import PasswordLocation
from otm.providers.required_user_contracts import RequiredUserTarget
from otm.storage.tables import audit_event, managed_object_binding, recovery_credential, tenancy
from otm.tenancies.recovery_password_contracts import RecoveryPasswordIntent
from otm.tenancies.recovery_password_records import admit_operation


# DB-only admission closes the enqueue gap while custody/provider work occurs after commit.
class RecoveryPasswordSetup:
    # Only the explicitly composed fixed password queue capability can admit setup.
    def __init__(self, enqueuer):
        self.enqueuer = enqueuer

    # Replays retain the original credential; page navigation cannot prepare legacy accounts.
    def admit(self, connection, row, intent, at):
        if intent.onboarding_version != 4:
            raise ValueError("RECOVERY_PASSWORD_REQUIRES_CURRENT_ONBOARDING")
        existing = connection.scalar(
            select(recovery_credential.c.id).where(
                recovery_credential.c.workspace_id == row["workspace_id"],
                recovery_credential.c.source_operation_id == row["id"],
            )
        )
        if existing is not None:
            return existing
        binding = (
            connection.execute(
                select(managed_object_binding).where(
                    managed_object_binding.c.workspace_id == row["workspace_id"],
                    managed_object_binding.c.tenancy_id == intent.pending_tenancy_id,
                    managed_object_binding.c.logical_key == "identity/user/recovery",
                    managed_object_binding.c.state == "active",
                    managed_object_binding.c.created_operation_id == row["id"],
                )
            )
            .mappings()
            .one()
        )
        domain = (
            connection.execute(
                select(managed_object_binding).where(
                    managed_object_binding.c.workspace_id == row["workspace_id"],
                    managed_object_binding.c.id == binding["identity_domain_binding_id"],
                    managed_object_binding.c.created_operation_id == row["id"],
                    managed_object_binding.c.state == "active",
                )
            )
            .mappings()
            .one()
        )
        child = (
            connection.execute(
                select(tenancy).where(
                    tenancy.c.workspace_id == row["workspace_id"],
                    tenancy.c.id == intent.pending_tenancy_id,
                    tenancy.c.operation_id == row["id"],
                )
            )
            .mappings()
            .one()
        )
        origin = connection.scalar(
            select(audit_event.c.data).where(
                audit_event.c.workspace_id == row["workspace_id"],
                audit_event.c.id == row["current_intent_event_id"],
            )
        )
        actor = IntentEventData.model_validate_json(json.dumps(origin)).actor
        credential, setup_operation = uuid4(), uuid4()
        location = PasswordLocation(
            credential_id=credential,
            secret_reference=None,
            target=RequiredUserTarget(
                workspace_id=row["workspace_id"],
                tenancy_id=child["id"],
                purpose="recovery",
                subject_binding_id=binding["id"],
                binding_generation=binding["generation"],
                identity_domain_binding_id=domain["id"],
                domain_ocid=domain["provider_ocid"],
                scim_resource_id=binding["scim_resource_id"],
                provider_ocid=binding["provider_ocid"],
                user_name=binding["user_name"],
                organization_id=child["organization_id"],
                parent_tenancy_ocid=child["parent_tenancy_ocid"],
                tenancy_ocid=child["tenancy_ocid"],
            ),
        )
        connection.execute(
            recovery_credential.insert().values(
                id=credential,
                workspace_id=row["workspace_id"],
                tenancy_id=child["id"],
                principal_binding_id=binding["id"],
                source_operation_id=row["id"],
                location=location.model_dump(mode="json"),
                location_hash=canonical_hash(location.model_dump(mode="json")),
                state="staging",
                generation=1,
                exposure_generation=0,
                rotation_operation_id=setup_operation,
                created_at=at,
                updated_at=at,
            )
        )
        command = RecoveryPasswordIntent(
            workspace_id=row["workspace_id"],
            phase="setup",
            credential_id=credential,
            generation=1,
            location=location,
            onboarding_operation_id=row["id"],
            target={"tenancy_ocid": child["tenancy_ocid"], "display_name": child["name"]},
            exposure_generation=0,
        )
        admit_operation(connection, command, actor, at, self.enqueuer, identifier=setup_operation)
        return credential
