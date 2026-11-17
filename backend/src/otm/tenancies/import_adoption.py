"""Adopt verified human identities through existing import steps and membership reservations."""

from uuid import uuid4

from sqlalchemy import select, update

from otm.operations.contracts import canonical_hash
from otm.organization.review_rules import has_valid_accountability
from otm.providers.lifecycle import LifecycleBlocked, LifecycleCompletion, MemberBinding
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, org_person, org_workspace, tenancy_membership
from otm.tenancies.import_contracts import (
    AdoptedIdentity,
    AdoptedMember,
    ExistingAccessInventory,
    ImportedAccessSnapshot,
    ImportManifest,
    ImportPerson,
    ImportReview,
    import_hash,
    stored_import,
)


# Only explicitly opted-in new shared imports can enter the adoption path.
def enabled(intent):
    return intent.import_adoption_contract == "import-adoption-1"


# Ignore only the exact verified temporary/service identities, never whole groups or policies.
def read_inventory(facade, intent, discovery, protected=()):
    inventory = ExistingAccessInventory.model_validate(
        facade.inspect_existing_access(intent.target.tenancy_ocid, discovery["domain_ocid"])
    )
    if (
        not inventory.complete
        or inventory.tenancy_ocid != intent.target.tenancy_ocid
        or inventory.domain_ocid != discovery["domain_ocid"]
    ):
        raise OrganizationConflict("IMPORT_INVENTORY_UNVERIFIED")
    excluded = {discovery["bootstrap_user_ocid"], discovery.get("activation_user_ocid"), *protected}
    scopes = {scope.ocid for scope in facade.compartments(inventory.tenancy_ocid)}
    if any(scope.ocid not in scopes for user in inventory.users for scope in user.scopes):
        raise OrganizationConflict("IMPORT_SCOPE_UNVERIFIED")
    return inventory.model_copy(
        update={"users": tuple(user for user in inventory.users if user.user_ocid not in excluded)}
    )


# The owner has an existing reservation; every other adopted person must be independently eligible.
def eligible(state, person_id, operation_id, owner_id, *, reserved=False):
    person, control = state.people.get(person_id), state.controls.get(person_id)
    return bool(
        person
        and control
        and person.profile == "employee"
        and person.email in state.supplied
        and not person.absence_review
        and has_valid_accountability(person, state.config)
        and control["directory_status"] == "included"
        and control["pending_operation_id"]
        in ((None, operation_id) if reserved or person_id == owner_id else (None,))
    )


# Suggestions and observed scopes stay read-only until a complete owner-inclusive manifest is
# accepted.
def review(state, row, intent, inventory):
    return ImportReview(
        inventory=inventory,
        inventory_hash=import_hash(inventory),
        owner_person_id=intent.target.person_id,
        people=tuple(
            ImportPerson(id=p.id, name=p.full_name or p.email, email=p.email)
            for p in state.people.values()
            if eligible(state, p.id, row["id"], intent.target.person_id)
        ),
    )


# Discovery inputs must agree with the immutable provider-read event before a manifest can use them.
def discovered_inventory(connection, row, inspection):
    event = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == row["workspace_id"],
                audit_event.c.operation_id == row["id"],
                audit_event.c.id == inspection["evidence_event_id"],
                audit_event.c.kind == "onboarding_outcome",
            )
        )
        .mappings()
        .one()
    )
    value = inspection["inputs"].get("import_inventory")
    if (
        value is None
        or canonical_hash(event["data"]) != event["data_hash"]
        or event["data"].get("import_inventory") != value
    ):
        raise ValueError("IMPORT_DISCOVERY_EVIDENCE_INVALID")
    return stored_import(ExistingAccessInventory, value)


# Freeze exact verified identities and server-generated association IDs, never browser-supplied
# scopes.
def plan(state, row, intent, inventory, choice):
    if choice is None or choice.inventory_hash != import_hash(inventory):
        raise OrganizationConflict("IMPORT_MANIFEST_REVIEW_REQUIRED")
    users = {user.user_ocid: user for user in inventory.users}
    selected = {member.user_ocid for member in choice.members}
    owner = intent.target.person_id
    if sum(member.person_id == owner for member in choice.members) != 1:
        raise OrganizationConflict("IMPORT_EXISTING_OWNER_REQUIRED")
    outside = tuple(sorted(set(users) - selected))
    members = []
    for member in choice.members:
        identity = users.get(member.user_ocid)
        if (
            identity is None
            or not eligible(state, member.person_id, row["id"], owner)
            or (member.person_id == owner and not identity.administrator)
        ):
            raise OrganizationConflict("IMPORT_MEMBER_UNVERIFIED")
        members.append(
            AdoptedMember(
                association_id=intent.pending_association_id
                if member.person_id == owner
                else uuid4(),
                person_id=member.person_id,
                access=AdoptedIdentity(
                    domain_ocid=inventory.domain_ocid,
                    identity=identity,
                    known_user_ocids=outside,
                ),
            )
        )
    return ImportManifest(inventory=inventory, members=tuple(members))


# Reserve all participants and pending bindings in the same acceptance transaction as evidence/job.
def reserve(connection, state, row, intent, manifest, at):
    for member in manifest.members:
        identity = member.access.identity
        first = identity.scopes[0]
        values = dict(
            imported_access=member.access.model_dump(mode="json"),
            user_ocid=identity.user_ocid,
            compartment_ocid=first.ocid,
            compartment_name=first.name,
        )
        if member.person_id == intent.target.person_id:
            changed = connection.execute(
                update(tenancy_membership)
                .where(
                    tenancy_membership.c.workspace_id == state.workspace,
                    tenancy_membership.c.id == intent.pending_association_id,
                    tenancy_membership.c.operation_id == row["id"],
                    tenancy_membership.c.status == "pending",
                )
                .values(**values)
            )
            if changed.rowcount != 1:
                raise OrganizationConflict("IMPORT_OWNER_RESERVED")
        else:
            connection.execute(
                tenancy_membership.insert().values(
                    **values,
                    id=member.association_id,
                    workspace_id=state.workspace,
                    tenancy_id=intent.pending_tenancy_id,
                    person_id=member.person_id,
                    role="member",
                    status="pending",
                    operation_id=row["id"],
                    created_at=at,
                    updated_at=at,
                )
            )
            changed = connection.execute(
                update(org_person)
                .where(
                    org_person.c.workspace_id == state.workspace,
                    org_person.c.id == member.person_id,
                    org_person.c.pending_operation_id.is_(None),
                )
                .values(pending_operation_id=row["id"], setup_required=False)
            )
            if changed.rowcount != 1:
                raise OrganizationConflict("IMPORT_MEMBER_RESERVED")
    connection.execute(
        update(org_workspace)
        .where(org_workspace.c.id == state.workspace)
        .values(registry_revision=org_workspace.c.registry_revision + 1)
    )


# Authenticate accepted scope against immutable audit, not a mutable step input alone.
def accepted(connection, row, steps):
    handoff = steps.get("handoff")
    value = handoff["inputs"].get("import_manifest") if handoff else None
    if value is None:
        raise OrganizationConflict("IMPORT_MANIFEST_REVIEW_REQUIRED")
    stored = (
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == row["workspace_id"],
                audit_event.c.operation_id == row["id"],
                audit_event.c.id == handoff["evidence_event_id"],
                audit_event.c.kind == "onboarding_action",
            )
        )
        .mappings()
        .one()
    )
    if (
        canonical_hash(stored["data"]) != stored["data_hash"]
        or stored["data"].get("import_manifest") != value
    ):
        raise ValueError("IMPORT_MANIFEST_EVIDENCE_INVALID")
    return stored_import(ImportManifest, value)


# Every reserved identity must remain exactly the reviewed participant, not a substituted name/user.
def validate_participants(state, intent, manifest, operation_id):
    expected = {member.association_id for member in manifest.members}
    actual = {link["id"] for link in state.links if link["operation_id"] == operation_id}
    if expected != actual:
        raise LifecycleBlocked("TARGET_CHANGED")
    for member in manifest.members:
        control = state.controls.get(member.person_id)
        person = state.people.get(member.person_id)
        link = next((link for link in state.links if link["id"] == member.association_id), None)
        if (
            not eligible(
                state, member.person_id, operation_id, intent.target.person_id, reserved=True
            )
            or not control
            or not person
            or control["pending_operation_id"] != operation_id
            or control["directory_status"] != "included"
            or person.email not in state.supplied
            or person.absence_review
            or link is None
            or link["status"] != "pending"
            or link["tenancy_id"] != intent.pending_tenancy_id
            or link["person_id"] != member.person_id
            or link["role"]
            != ("owner" if member.person_id == intent.target.person_id else "member")
            or link["compartment_ocid"] != member.access.identity.scopes[0].ocid
            or link["user_ocid"] != member.access.identity.user_ocid
            or link.get("imported_access") != member.access.model_dump(mode="json")
        ):
            raise LifecycleBlocked("TARGET_CHANGED")


# Independent readback must preserve all reviewed human grants; only proven setup subjects are
# excluded.
def verify(facade, intent, discovery, manifest, protected=()):
    current = read_inventory(facade, intent, discovery, protected)
    if current != manifest.inventory:
        raise OrganizationConflict("IMPORT_INVENTORY_CHANGED")


# Adoption publishes read-back IDs directly and never invokes human account provisioning.
def completion(intent, manifest):
    return LifecycleCompletion(
        bindings=tuple(
            MemberBinding(
                association_id=member.association_id,
                tenancy_ocid=intent.target.tenancy_ocid,
                person_id=member.person_id,
                user_ocid=member.access.identity.user_ocid,
                compartment_ocid=member.access.identity.scopes[0].ocid,
                parent_compartment_ocid=None,
            )
            for member in manifest.members
        )
    )


# Freeze active associations and explicitly unmanaged initial accounts with ordinary created users.
def membership_snapshot(workspace, child, links):
    members, known = [], set()
    for link in links:
        if link["workspace_id"] != workspace or link["tenancy_id"] != child["id"]:
            raise ValueError("IMPORT_CHECK_SCOPE_INVALID")
        if link["status"] != "active":
            continue
        if link["user_ocid"]:
            known.add(link["user_ocid"])
        if link.get("imported_access") is not None:
            access = stored_import(AdoptedIdentity, link["imported_access"])
            if access.identity.user_ocid != link["user_ocid"]:
                raise ValueError("IMPORT_CHECK_BINDING_INVALID")
            members.append(
                AdoptedMember(association_id=link["id"], person_id=link["person_id"], access=access)
            )
            known.update(access.known_user_ocids)
    if not members:
        return None
    domains = {member.access.domain_ocid for member in members}
    if len(domains) != 1:
        raise ValueError("IMPORT_CHECK_DOMAIN_INVALID")
    return ImportedAccessSnapshot(
        tenancy_ocid=child["tenancy_ocid"],
        domain_ocid=next(iter(domains)),
        members=tuple(sorted(members, key=lambda item: str(item.association_id))),
        known_user_ocids=tuple(sorted(known)),
    )
