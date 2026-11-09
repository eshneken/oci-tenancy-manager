"""Verify exact identity retirement before publishing shared-membership removal."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.tables import managed_object_binding, operation_step


# Missing, duplicate, foreign or unverified receipts never retire a local association.
def validate_removals(intent, completion):
    expected = {a.id: a for a in intent.associations if a.removes_identity}
    receipts = {r.association_id: r for r in completion.removals}
    if len(receipts) != len(completion.removals) or set(receipts) != set(expected):
        raise LifecycleBlocked("TARGET_CHANGED")
    for identifier, receipt in receipts.items():
        source = expected[identifier]
        if (
            not source.user_ocid
            or (receipt.tenancy_ocid, receipt.user_ocid) != (source.tenancy_ocid, source.user_ocid)
            or not receipt.group_memberships_removed
            or not receipt.user_deleted
        ):
            raise LifecycleBlocked("TARGET_CHANGED")


# Reuse existing durable steps and immutable operation evidence for each exact retired identity.
def save_removal_steps(connection, row, receipts, outcome, evidence_id, at):
    for receipt in receipts:
        for prefix in ("remove_member_groups", "delete_member_user"):
            statement = insert(operation_step).values(
                workspace_id=row["workspace_id"],
                operation_id=row["id"],
                intent_revision=row["current_intent_revision"],
                step_key=prefix + ":" + str(receipt.association_id),
                intent_event_id=row["current_intent_event_id"],
                command_kind="organization_action",
                contract_version="organization-action-1",
                inputs=receipt.model_dump(mode="json"),
                state="verified",
                execution_generation=1,
                attempt_number=1,
                current_attempt_id=uuid4(),
                effect_knowledge="known",
                last_outcome=outcome,
                verified_at=at,
                evidence_event_id=evidence_id,
            )
            connection.execute(statement.on_conflict_do_nothing())


# Required managed identities are never a personal-removal target, even through corrupt mappings.
def validate_removal_targets(connection, workspace, intent):
    targets = [item for item in intent.associations if item.removes_identity]
    if not targets:
        return
    protected = set(
        connection.execute(
            select(managed_object_binding.c.provider_ocid).where(
                managed_object_binding.c.workspace_id == workspace,
                managed_object_binding.c.tenancy_id.in_({item.tenancy_id for item in targets}),
                managed_object_binding.c.kind == "managed_user",
            )
        ).scalars()
    )
    if any(item.user_ocid in protected for item in targets):
        raise LifecycleBlocked("TARGET_CHANGED")
