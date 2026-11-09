"""Current organization roles become frozen reasons, never an implicit recipient redirect."""

from otm.email_policy import EmailPolicyBlocked, mailbox
from otm.notifications.contracts import RecipientReason


# Shared roles are deduplicated by original contact before applying any staging destination
# override.
def required_user_recipients(state, grants, tenancy_id):
    recipients, issues = {}, []
    owner_link = next(
        (
            a
            for a in state.associations(tenant=tenancy_id)
            if a["role"] == "owner" and a["status"] == "active"
        ),
        None,
    )
    owner = state.people.get(owner_link["person_id"]) if owner_link else None
    by_email = {p.email: p for p in state.people.values()}

    # No-tenancy exemptions do not remove a person's organizational role; actual absence does.
    def person_contact(person):
        if (
            person is None
            or person.profile != "employee"
            or person.email not in state.supplied
            or person.absence_review
        ):
            return None
        control = state.controls.get(person.id)
        if control is None or control["directory_status"] in {"merged", "offboarded"}:
            return None
        try:
            return mailbox(person.email)
        except EmailPolicyBlocked:
            return None

    # Missing/unusable role contacts are explicit routing issues rather than invented addresses.
    def add_person(person, role):
        address = person_contact(person)
        if address is None:
            issues.append(role + "_unavailable")
        else:
            recipients.setdefault(address, []).append(
                RecipientReason(role=role, person_id=person.id)
            )

    add_person(owner, "owner")
    add_person(by_email.get(owner.manager_email) if owner else None, "manager")
    designees = owner.designee_emails if owner else ()
    if not designees:
        issues.append("designee_unavailable")
    for address in designees:
        add_person(by_email.get(address), "designee")
    active = [g for g in grants if g["status"] == "active"]
    usable_admin = False
    for grant in active:
        try:
            address = mailbox(grant["email"].lower() if grant["email"] else None)
        except EmailPolicyBlocked:
            issues.append("administrator_unavailable")
            continue
        if address is None:
            issues.append("administrator_unavailable")
        usable_admin = True
        recipients.setdefault(address, []).append(
            RecipientReason(
                role="administrator",
                administrator_id=grant["id"],
                authorization_revision=grant["authorization_revision"],
            )
        )
    if not usable_admin:
        recipients.setdefault(None, []).append(RecipientReason(role="administrator"))
        issues.append("administrator_unavailable")
    return {
        address: tuple(dict.fromkeys(reasons)) for address, reasons in recipients.items()
    }, tuple(sorted(set(issues)))


# A frozen role must still belong to that exact person/grant and original email before submission.
def recipient_still_authorized(notice, state, grants):
    current, _ = required_user_recipients(state, grants, notice.tenancy_id)
    reasons = current.get(notice.original_recipient, ())
    return any(
        reason in reasons and (reason.person_id is not None or reason.administrator_id is not None)
        for reason in notice.reasons
    )
