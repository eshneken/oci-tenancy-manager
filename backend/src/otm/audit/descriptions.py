"""Human-readable organization audit descriptions use recorded, typed evidence only."""

# Names are allowlisted rather than displaying an arbitrary stored action as a successful workflow.
ACTIONS = {
    "create_tenancy": "Requested tenancy creation",
    "import_tenancy": "Requested tenancy import",
    "join_shared": "Requested shared tenancy membership",
    "offboard_person": "Recorded employee offboarding decision",
    "delete_tenancy": "Requested tenancy termination",
    "remove_member": "Requested shared membership removal",
    "transfer_owner": "Requested tenancy ownership transfer",
    "no_tenancy_required": "Marked no tenancy required",
    "ignore": "Ignored organization review",
    "resolve": "Completed organization review",
    "merge": "Merged employee identity",
    "reonboard": "Re-onboarded employee",
    "mark_returned": "Marked employee returned",
    "cancel_simulation": "Cancelled local simulation",
}


# Historical omissions stay explicit; never reconstruct a change from today's mutable configuration.
def describe_organization(kind, evidence):
    if kind == "organization_configured" and evidence.action == "mapping_apply":
        if evidence.mapping_root_after is None and not evidence.mapping_changes:
            return "Applied organization mappings; change details were not recorded", ()
        details = []
        if evidence.mapping_root_before != evidence.mapping_root_after:
            details.append(
                "Organization leader: "
                f"{evidence.mapping_root_before or 'Not configured'} → "
                f"{evidence.mapping_root_after or 'Not recorded'}"
            )
        if evidence.mapping_root_name_before != evidence.mapping_root_name_after:
            details.append(
                "Organization leader name: "
                f"{evidence.mapping_root_name_before or 'Not configured'} → "
                f"{evidence.mapping_root_name_after or 'Not configured'}"
            )
        for change in evidence.mapping_changes:
            before, after = change.before, change.after
            label = after.label if after else before.label
            if before is None or after is None:
                value = after or before
                details.extend(
                    (
                        f"{'Added' if after else 'Removed'} segment: {label}",
                        f"{label} leader: {value.leader_email}",
                        f"{label} designees: {', '.join(value.designee_emails) or 'None'}",
                    )
                )
                continue
            if before.label != after.label:
                details.append(f"Segment name: {before.label} → {after.label}")
            if before.leader_email != after.leader_email:
                details.append(f"{label} leader: {before.leader_email} → {after.leader_email}")
            if before.designee_emails != after.designee_emails:
                details.extend(
                    (
                        f"{label} previous designees: "
                        f"{', '.join(before.designee_emails) or 'None'}",
                        f"{label} new designees: {', '.join(after.designee_emails) or 'None'}",
                    )
                )
        return (
            "Updated organization mappings"
            if details
            else "Applied unchanged organization mappings",
            tuple(details),
        )
    if kind == "organization_configured":
        return "Configured organization; change details were not recorded for this event", ()
    if kind == "organization_review_decided":
        if evidence.action == "offboard_person" and evidence.receipt:
            return (
                "Requested employee offboarding"
                if evidence.receipt.operation_id
                else "Offboarded employee",
                (),
            )
        return ACTIONS.get(evidence.action, "Recorded organization decision"), ()
    if kind == "organization_feed_received":
        return "Received organization feed", ()
    if kind == "organization_feed_rejected":
        return f"Rejected organization feed: {evidence.diagnostic_count} validation diagnostics", ()
    return f"Applied organization snapshot: {evidence.person_count} organization profiles", ()
