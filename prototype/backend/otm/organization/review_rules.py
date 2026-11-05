"""Shared exception classification, identity aliases and durable administrator decision rules."""

import hashlib
import json

ACTIONABLE = frozenset(
    {
        "PERSON_ABSENCE_REVIEW",
        "TENANCY_SETUP_REVIEW",
        "LOB_MAPPING_REVIEW",
        "LOB_LEADER_REVIEW",
        "DESIGNEE_INVALID",
        "OVERRIDE_CONFLICT",
    }
)
INFORMATIONAL = frozenset(
    {"TOP_MANAGER_MISMATCH", "MANAGER_PROFILE_MISSING", "ANCESTRY_UNRESOLVED"}
)


# Follow explicit one-way rename aliases; names alone never establish identity.
def canonical_email(config, address):
    aliases = {merge.old_email: merge.new_email for merge in config.identity_merges}
    seen = set()
    while address in aliases:
        if address in seen:
            raise ValueError("identity alias cycle")
        seen.add(address)
        address = aliases[address]
    return address


# Fingerprint relevant facts; override conflicts include exact source/effective values.
def issue_basis(kind, target, people):
    person = next((p for p in people if p.email in target.split(":")), None)
    if kind == "PERSON_ABSENCE_REVIEW":
        return (
            (person.absence_review_since.isoformat() if person.absence_review_since else "legacy")
            if person
            else None
        )
    facts = {"kind": kind, "target": target}
    if person and kind == "OVERRIDE_CONFLICT":
        field = target.rsplit(":", 1)[-1]
        facts.update(source=person.source_values.get(field), effective=getattr(person, field))
    if person:
        facts.update(
            {
                key: getattr(person, key)
                for key in (
                    "manager_email",
                    "lob_id",
                    "accountable_leader_email",
                    "designee_emails",
                    "ancestry",
                )
            }
        )
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


# Ignore a nominated case permanently, or resolve only its recorded condition/episode.
def suppressed(config, kind, target, people):
    people = tuple(people)
    if kind in {"PERSON_ABSENCE_REVIEW", "LOB_MAPPING_REVIEW"} and any(
        p.id in config.managed_exclusions and p.email in target.split(":") for p in people
    ):
        return True
    basis = issue_basis(kind, target, people)
    return any(
        d.kind == kind
        and d.target == target
        and (d.disposition == "ignored" or d.basis is None or d.basis == basis)
        for d in config.review_decisions
    )
