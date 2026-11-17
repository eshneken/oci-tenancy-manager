"""Verify root administrator promotion and retain only its authorized delta as expected access."""

from hashlib import sha256

from sqlalchemy import select

from otm.operations.contracts import IntentEventData, canonical_hash
from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, managed_object_binding
from otm.tenancies.contracts import OrganizationActionOutcome
from otm.tenancies.import_contracts import (
    AdoptedIdentity,
    ExistingIdentity,
    ExistingScope,
    OwnerExpectation,
    import_hash,
    stored_import,
)


# The simulated qualified admin profile names exact root-policy/group and domain-role resources.
def profile(tenancy, domain):
    suffix = sha256((tenancy + domain).encode()).hexdigest()[:24]
    return {
        "group": "group-admin-" + suffix,
        "role": "role-domain-admin-" + suffix,
        "policy": "policy-admin-" + suffix,
    }


# Merge only the explicitly authorized admin delta, leaving unrelated grants out of the baseline.
def promoted(identity, tenancy, domain):
    grant = profile(tenancy, domain)
    root = ExistingScope(ocid=tenancy, name="Root compartment", kind="root")
    already = (
        identity.administrator
        and grant["group"] in identity.groups
        and grant["role"] in identity.roles
        and root in identity.scopes
    )
    return ExistingIdentity.model_validate(
        dict(
            identity.model_dump(),
            administrator=True,
            groups=tuple(sorted({*identity.groups, grant["group"]})),
            roles=tuple(sorted({*identity.roles, grant["role"]})),
            scopes=tuple(s for s in identity.scopes if s.ocid != tenancy) + (root,),
            policy_hash=identity.policy_hash
            if already
            else import_hash({"previous": identity.policy_hash, "administrator_grant": grant}),
        )
    )


# A typed metadata extension changes current expectations while preserving the original import
# facts.
def expectation(access, operation_id, tenancy):
    previous = access.expected_owner.identity if access.expected_owner else access.identity
    return access.model_copy(
        update={
            "expected_owner": OwnerExpectation(
                operation_id=operation_id, identity=promoted(previous, tenancy, access.domain_ocid)
            )
        }
    )


# New grants require an already verified exact domain, never a guessed name or child-derived real
# ID.
def domain(connection, workspace, tenancy_id):
    rows = (
        connection.execute(
            select(managed_object_binding.c.provider_ocid).where(
                managed_object_binding.c.workspace_id == workspace,
                managed_object_binding.c.tenancy_id == tenancy_id,
                managed_object_binding.c.logical_key == "identity/domain",
                managed_object_binding.c.state == "active",
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != 1 or not rows[0]:
        raise OrganizationConflict("VERIFIED_IDENTITY_DOMAIN_REQUIRED")
    return rows[0]


# Freeze exact provider account IDs before accepting a new transfer; names cannot substitute users.
def prepare(connection, state, plan, facade):
    result = []
    for item in plan:
        if item.action != "transfer":
            result.append(item)
            continue
        if item.recipient_imported_access and item.recipient_imported_access.expected_owner:
            authenticate(
                connection,
                state.workspace,
                state.associations(person=item.recipient_person_id, tenant=item.tenancy_id),
            )
        selected = domain(connection, state.workspace, item.tenancy_id)
        scim = None
        if item.recipient_user_ocid:
            observed = facade.inspect_member(item.tenancy_ocid, selected, item.recipient_user_ocid)
            if observed is None:
                raise OrganizationConflict("RECIPIENT_IDENTITY_UNVERIFIED")
            scim = observed.scim_id
        result.append(
            item.model_copy(
                update={
                    "owner_administration_required": True,
                    "recipient_domain_ocid": selected,
                    "recipient_scim_id": scim,
                }
            )
        )
    return tuple(result)


# Root authorization must link the actual policy to the exact administrator group and user/role.
def verify(item, proof, user_ocid):
    grant = profile(item.tenancy_ocid, item.recipient_domain_ocid)
    identity = proof.identity
    if (
        proof.association_id != item.new_association_id
        or proof.tenancy_ocid != item.tenancy_ocid
        or proof.domain_ocid != item.recipient_domain_ocid
        or (
            item.recipient_imported_access is not None
            and item.recipient_imported_access.domain_ocid != proof.domain_ocid
        )
        or identity.user_ocid != user_ocid
        or (item.recipient_user_ocid is not None and user_ocid != item.recipient_user_ocid)
        or (item.recipient_scim_id is not None and identity.scim_id != item.recipient_scim_id)
        or not proof.authorized
        or not proof.supported
        or not proof.complete
        or not proof.manage_all_resources
        or not proof.domain_administrator
        or not identity.administrator
        or proof.administrator_group_id != grant["group"]
        or proof.administrator_role_id != grant["role"]
        or proof.root_policy_id != grant["policy"]
        or proof.policy_group_id != grant["group"]
        or proof.policy_scope_ocid != item.tenancy_ocid
        or grant["group"] not in identity.groups
        or grant["role"] not in identity.roles
        or not any(s.kind == "root" and s.ocid == item.tenancy_ocid for s in identity.scopes)
    ):
        raise LifecycleBlocked("TARGET_CHANGED")


# Use the same verifier before outgoing identity deletion and again before registry publication.
def validate(intent, completion):
    items = {
        a.new_association_id: a for a in intent.associations if a.owner_administration_required
    }
    receipts = {p.association_id: p for p in completion.owner_administrations}
    bindings = {b.association_id: b for b in completion.bindings}
    if (
        len(bindings) != len(completion.bindings)
        or len(receipts) != len(completion.owner_administrations)
        or set(receipts) != set(items)
    ):
        raise LifecycleBlocked("TARGET_CHANGED")
    for identifier, item in items.items():
        binding = bindings.get(identifier)
        if (
            binding is None
            or binding.tenancy_ocid != item.tenancy_ocid
            or binding.person_id != item.recipient_person_id
            or binding.compartment_ocid != item.tenancy_ocid
            or binding.parent_compartment_ocid is not None
        ):
            raise LifecycleBlocked("TARGET_CHANGED")
        verify(item, receipts[identifier], binding.user_ocid)


# Metadata expectations must reproduce the exact successful audited transfer, not trust mutable
# rows.
def authenticate(connection, workspace, links):
    wanted = {}
    for link in links:
        value = link.get("imported_access")
        if value is not None:
            access = stored_import(AdoptedIdentity, value)
            if access.expected_owner:
                wanted[link["id"]] = (link, access)
    if not wanted:
        return
    ids = {a.expected_owner.operation_id for _, a in wanted.values()}
    events = list(
        connection.execute(
            select(audit_event).where(
                audit_event.c.workspace_id == workspace,
                audit_event.c.operation_id.in_(ids),
                audit_event.c.kind.in_(("operation_intent", "organization_action_outcome")),
            )
        ).mappings()
    )
    for link, access in wanted.values():
        identifier = access.expected_owner.operation_id
        selected = [e for e in events if e["operation_id"] == identifier]
        if any(canonical_hash(e["data"]) != e["data_hash"] for e in selected):
            raise ValueError("OWNER_EXPECTATION_EVIDENCE_INVALID")
        intents = [
            stored_import(IntentEventData, e["data"]).intent
            for e in selected
            if e["kind"] == "operation_intent"
        ]
        outcomes = [
            stored_import(OrganizationActionOutcome, e["data"])
            for e in selected
            if e["kind"] == "organization_action_outcome"
            and e["data"].get("safe_code") == "SIMULATED_LIFECYCLE_VERIFIED"
        ]
        if len(intents) != 1 or len(outcomes) != 1:
            raise ValueError("OWNER_EXPECTATION_EVIDENCE_INVALID")
        if (
            intents[0].workspace_id != workspace
            or outcomes[0].action != intents[0].action
            or outcomes[0].verified_at is None
        ):
            raise ValueError("OWNER_EXPECTATION_EVIDENCE_INVALID")
        item = next(
            (a for a in intents[0].associations if a.new_association_id == link["id"]), None
        )
        proof = next(
            (p for p in outcomes[0].owner_administrations if p.association_id == link["id"]), None
        )
        if (
            item is None
            or proof is None
            or not item.owner_administration_required
            or item.recipient_imported_access is None
            or item.tenancy_id != link["tenancy_id"]
            or item.recipient_person_id != link["person_id"]
        ):
            raise ValueError("OWNER_EXPECTATION_EVIDENCE_INVALID")
        verify(item, proof, link["user_ocid"])
        if expectation(item.recipient_imported_access, identifier, item.tenancy_ocid) != access:
            raise ValueError("OWNER_EXPECTATION_EVIDENCE_INVALID")
