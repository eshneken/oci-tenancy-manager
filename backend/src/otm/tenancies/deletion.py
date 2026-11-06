"""Whole-child termination reuses admission and preserves every affected person's obligations."""

from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update

from otm.contracts import Contract
from otm.organization.reviews import add_change
from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import org_person, tenancy, tenancy_membership
from otm.tenancies.contracts import FrozenAssociation, OrganizationContext
from otm.tenancies.views import TenancyView


# A tenancy command has a distinct replay shape and never accepts caller-selected member targets.
class TenancyDeletionCommand(Contract):
    kind: Literal["delete_registered_tenancy"] = "delete_registered_tenancy"
    client_request_key: UUID
    tenancy_id: UUID
    context: OrganizationContext
    confirm_manager: bool = False
    confirm_shared: bool = False
    confirm_deletion: bool = False


# Show each person's current scope and the consequence of retiring this one tenancy association.
class DeletionPerson(Contract):
    person_id: UUID
    name: str
    email: str
    role: Literal["owner", "member"]
    is_manager: bool
    other_tenancy_count: int
    leaves_directory: bool


# A fresh read-only preview names the exact child and complete affected membership set.
class TenancyDeletionPreview(Contract):
    context: OrganizationContext
    tenancy: TenancyView
    people: tuple[DeletionPerson, ...]
    manager_warning: bool
    shared_warning: bool


# Reject pending/unregistered/foreign/parent targets and conflicting work before building the plan.
def deletion_plan(state, identifier, policy):
    row = state.tenancies.get(identifier)
    if row is None:
        raise OrganizationConflict("TENANCY_NOT_FOUND")
    links = state.associations(tenant=identifier)
    if (
        row["status"] != "active"
        or row["operation_id"]
        or not links
        or any(a["status"] != "active" or a["operation_id"] for a in links)
        or sum(a["role"] == "owner" for a in links) != 1
        or any(state.controls[a["person_id"]]["pending_operation_id"] for a in links)
    ):
        raise OrganizationConflict("TENANCY_DELETION_UNAVAILABLE")
    if (
        policy is None
        or row["provider_mode"] != "simulated"
        or row["parent_tenancy_ocid"] != policy.parent_tenancy_ocid
        or row["organization_id"] != policy.organization_id
        or row["tenancy_ocid"] == policy.parent_tenancy_ocid
        or not row["tenancy_ocid"].startswith("ocid1.tenancy.oc1..otmsim")
    ):
        raise OrganizationConflict("REGISTERED_CHILD_REQUIRED")
    return tuple(
        FrozenAssociation(
            id=a["id"],
            person_id=a["person_id"],
            person_was_manager=state.people[a["person_id"]].known_manager,
            tenancy_id=identifier,
            tenancy_revision=row["revision"],
            role=a["role"],
            action="delete",
            tenancy_ocid=row["tenancy_ocid"],
            parent_tenancy_ocid=row["parent_tenancy_ocid"],
            user_ocid=a["user_ocid"],
            compartment_ocid=a["compartment_ocid"],
        )
        for a in links
    )


# Recheck the exact full frozen set at dispatch; an added member cannot be silently swept in.
def validate_deletion(state, intent, identifier):
    items = intent.associations
    if intent.action != "delete_tenancy" or not items or any(a.action != "delete" for a in items):
        raise LifecycleBlocked("TARGET_CHANGED")
    identifiers = {a.tenancy_id for a in items}
    if len(identifiers) != 1:
        raise LifecycleBlocked("TARGET_CHANGED")
    row = state.tenancies.get(items[0].tenancy_id)
    links = {a["id"]: a for a in state.associations(tenant=items[0].tenancy_id)}
    if (
        row is None
        or row["status"] != "terminating"
        or row["operation_id"] != identifier
        or row["tenancy_ocid"] != intent.target.tenancy_ocid
        or row["parent_tenancy_ocid"] != intent.parent_tenancy_ocid
        or row["organization_id"] != intent.organization_id
        or row["tenancy_ocid"] == intent.parent_tenancy_ocid
        or row["provider_mode"] != "simulated"
        or len(items) != len(links)
        or {a.id for a in items} != set(links)
        or sum(a.role == "owner" and a.person_id == intent.target.person_id for a in items) != 1
    ):
        raise LifecycleBlocked("TARGET_CHANGED")
    for item in items:
        link, person = links[item.id], state.people.get(item.person_id)
        control = state.controls.get(item.person_id)
        if (
            person is None
            or control is None
            or control["pending_operation_id"] != identifier
            or control["directory_status"] == "merged"
            or (person.known_manager and not item.person_was_manager)
            or (
                link["person_id"],
                link["role"],
                link["status"],
                link["operation_id"],
                link["user_ocid"],
                link["compartment_ocid"],
                row["revision"],
                row["tenancy_ocid"],
                row["parent_tenancy_ocid"],
            )
            != (
                item.person_id,
                item.role,
                "removing",
                identifier,
                item.user_ocid,
                item.compartment_ocid,
                item.tenancy_revision,
                item.tenancy_ocid,
                item.parent_tenancy_ocid,
            )
        ):
            raise LifecycleBlocked("TARGET_CHANGED")


# Verified simulated initiation retires all target links; other tenancies and history remain.
def publish_deletion(connection, state, intent, completion, identifier, at):
    if completion.bindings:
        raise LifecycleBlocked("TARGET_CHANGED")
    from otm.storage.managed_bindings import retire_bindings

    retire_bindings(connection, state.workspace, intent.associations[0].tenancy_id, identifier, at)
    ids = tuple(a.id for a in intent.associations)
    connection.execute(
        update(tenancy_membership)
        .where(
            tenancy_membership.c.workspace_id == state.workspace,
            tenancy_membership.c.id.in_(ids),
            tenancy_membership.c.operation_id == identifier,
        )
        .values(
            status="removed",
            operation_id=None,
            cleanup_required=False,
            updated_at=at,
            revision=tenancy_membership.c.revision + 1,
        )
    )
    connection.execute(
        update(tenancy)
        .where(
            tenancy.c.workspace_id == state.workspace,
            tenancy.c.id == intent.associations[0].tenancy_id,
            tenancy.c.operation_id == identifier,
        )
        .values(
            status="terminated",
            operation_id=None,
            updated_at=at,
            verified_at=at,
            revision=tenancy.c.revision + 1,
        )
    )
    for person_id in {a.person_id for a in intent.associations}:
        person = state.people[person_id]
        remaining = connection.execute(
            select(tenancy_membership.c.id).where(
                tenancy_membership.c.workspace_id == state.workspace,
                tenancy_membership.c.person_id == person_id,
                tenancy_membership.c.status.in_(("active", "pending", "removing")),
            )
        ).first()
        # Removing any tenancy never offboards a person, even after confirmed source absence.
        control = state.controls[person_id]
        needs_setup = (
            remaining is None
            and control["directory_status"] == "included"
            and person.email in state.supplied
        )
        connection.execute(
            update(org_person)
            .where(
                org_person.c.workspace_id == state.workspace,
                org_person.c.id == person_id,
                org_person.c.pending_operation_id == identifier,
            )
            .values(
                directory_status=control["directory_status"],
                pending_operation_id=None,
                removed_capture_at=control["removed_capture_at"],
                **(
                    {"setup_required": True, "setup_episode_id": uuid4()}
                    if needs_setup and not control["setup_required"]
                    else {}
                ),
            )
        )
        add_change(
            connection,
            state.workspace,
            state.head,
            person,
            "LIFECYCLE_COMPLETED",
            at,
            {
                "action": "delete_tenancy",
                "operation_id": str(identifier),
                "provider_mode": "simulated",
            },
        )
