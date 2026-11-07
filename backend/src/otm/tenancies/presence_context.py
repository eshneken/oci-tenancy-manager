"""Resolve exact registered user identities and one current simulated automation connection."""

from sqlalchemy import select

from otm.configuration.drift_context import registered_child
from otm.operations.contracts import canonical_hash
from otm.providers.required_user_contracts import RequiredUserTarget
from otm.storage.tables import managed_object_binding as bindings
from otm.storage.tables import user_presence_connection as connections
from otm.tenancies.presence_contracts import PresenceSnapshot


# These reads never create connections or infer identity from names/setup labels.
def capture_snapshot(connection, workspace, child, policy):
    if policy is None or policy.workspace_id != workspace or not registered_child(child, policy):
        return None
    if child["status"] != "active" or child["operation_id"]:
        return None
    current = (
        connection.execute(
            select(connections).where(
                connections.c.workspace_id == workspace,
                connections.c.tenancy_id == child["id"],
                connections.c.state == "active",
                connections.c.provider_mode == "simulated",
            )
        )
        .mappings()
        .one_or_none()
    )
    if current is None:
        return None
    rows = list(
        connection.execute(
            select(bindings).where(
                bindings.c.workspace_id == workspace,
                bindings.c.tenancy_id == child["id"],
                bindings.c.state == "active",
                bindings.c.logical_key.in_(
                    ("identity/domain", "identity/user/automation", "identity/user/recovery")
                ),
            )
        ).mappings()
    )
    return bound_snapshot(workspace, child, policy, current, rows)


# Both single-child and batched views validate the same exact current records, never names.
def bound_snapshot(workspace, child, policy, current, rows):
    if policy is None or policy.workspace_id != workspace or not registered_child(child, policy):
        return None
    if child["status"] != "active" or child["operation_id"] or current is None:
        return None
    keyed = {b["logical_key"]: b for b in rows}
    if len(keyed) != 3 or len(rows) != 3:
        raise ValueError("PRESENCE_RECORDS_UNAVAILABLE")
    domain = keyed["identity/domain"]
    automation = keyed["identity/user/automation"]
    if (
        current["automation_binding_id"] != automation["id"]
        or current["domain_binding_id"] != domain["id"]
        or domain["kind"] != "identity_domain"
        or domain["ownership_mode"] != "observed_reference"
    ):
        raise ValueError("PRESENCE_RECORDS_UNAVAILABLE")
    subjects = []
    for purpose in ("automation", "recovery"):
        user = keyed["identity/user/" + purpose]
        if (
            user["kind"] != "managed_user"
            or user["ownership_mode"] != "managed"
            or user["identity_domain_binding_id"] != domain["id"]
            or any(
                b["source_evidence_event_id"] != current["source_evidence_event_id"]
                or b["created_operation_id"] != current["created_operation_id"]
                for b in (user, domain)
            )
        ):
            raise ValueError("PRESENCE_RECORDS_UNAVAILABLE")
        subjects.append(
            RequiredUserTarget(
                workspace_id=workspace,
                tenancy_id=child["id"],
                purpose=purpose,
                subject_binding_id=user["id"],
                binding_generation=user["generation"],
                identity_domain_binding_id=domain["id"],
                domain_ocid=domain["provider_ocid"],
                scim_resource_id=user["scim_resource_id"],
                provider_ocid=user["provider_ocid"],
                user_name=user["user_name"],
                organization_id=child["organization_id"],
                parent_tenancy_ocid=child["parent_tenancy_ocid"],
                tenancy_ocid=child["tenancy_ocid"],
            )
        )
    return PresenceSnapshot(
        tenancy_id=child["id"],
        tenancy_name=child["name"],
        tenancy_revision=child["revision"],
        connection_id=current["id"],
        connection_revision=current["revision"],
        policy_hash=canonical_hash(policy.model_dump(mode="json")),
        subjects=tuple(subjects),
    )


# One incident belongs to one exact subject and selected connection, not mutable registry metadata.
def subject_scope(snapshot, purpose):
    subject = next(s for s in snapshot.subjects if s.purpose == purpose)
    return canonical_hash(
        {
            "subject": subject.model_dump(mode="json"),
            "connection_id": str(snapshot.connection_id),
            "connection_revision": snapshot.connection_revision,
            "policy_hash": snapshot.policy_hash,
        }
    )
