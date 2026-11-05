"""Current nomination eligibility is independent of tenancy ownership and review acknowledgment."""

from otm.organization.review_rules import canonical_email


# Evaluate each configured role, even in an empty/invalid branch or an excluded directory profile.
def role_health(config, people, supplied):
    result = []
    excluded = {canonical_email(config, a) for a in config.excluded_emails}
    for segment in config.lobs:
        for role, address in (
            ("leader", segment.leader_email),
            *(("designee", a) for a in segment.designee_emails),
        ):
            person = people.get(address)
            status = (
                "excluded"
                if canonical_email(config, address) in excluded
                else "departed"
                if person and (person.absence_review or person.absence_review_since)
                else "profile_missing"
                if not person or person.profile != "employee" or address not in supplied
                else "ancestry_incomplete"
                if person.ancestry != "resolved"
                else "branch_changed"
                if (role == "leader" and person.manager_email != config.policy.root_email)
                or (
                    role == "designee"
                    and address != segment.leader_email
                    and segment.leader_email not in person.manager_path
                )
                else "healthy"
            )
            result.append(
                dict(
                    segment_id=segment.id,
                    segment_name=segment.label,
                    role=role,
                    email=address,
                    status=status,
                )
            )
    return tuple(result)
