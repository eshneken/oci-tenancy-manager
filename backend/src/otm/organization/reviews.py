"""Durable review episodes, baseline/change history and managed-directory transitions."""

import hashlib
import json
from uuid import uuid4

from sqlalchemy import select, update

from otm.organization.review_rules import (
    ACTIONABLE,
    has_valid_accountability,
    issue_basis,
    suppressed,
)
from otm.storage.tables import org_person, org_recommendation

CHANGE_FIELDS = (
    "full_name",
    "email",
    "manager_email",
    "lob_id",
    "accountable_leader_email",
    "designee_emails",
)


# Freeze a small before/after projection, not a whole source feed or administrative configuration.
def profile(person):
    return {
        key: list(getattr(person, key)) if key == "designee_emails" else getattr(person, key)
        for key in CHANGE_FIELDS
    }


# Initialize only later additions as onboarding; returning offboarded people require qualified
# evidence.
def directory_transitions(connection, workspace, current, previous, supplied):
    rows = {
        row["id"]: row
        for row in connection.execute(
            select(org_person).where(org_person.c.workspace_id == workspace)
        ).mappings()
    }
    old = {p.id: p for p in previous.people} if previous else {}
    for person in current.people:
        state = rows[person.id]
        if person.profile != "employee" or state["directory_status"] == "merged":
            continue
        # A deletion while still present becomes return-eligible only after a later full absence.
        if (
            state["directory_status"] == "offboarded"
            and state["removed_capture_at"] is None
            and current.absence_eligible
            and person.email not in supplied
            and current.source_captured_at is not None
        ):
            connection.execute(
                update(org_person)
                .where(org_person.c.workspace_id == workspace, org_person.c.id == person.id)
                .values(removed_capture_at=current.source_captured_at)
            )
            state = {**state, "removed_capture_at": current.source_captured_at}
            rows[person.id] = state
        returning = (
            state["directory_status"] == "offboarded"
            and state["removed_capture_at"] is not None
            and current.absence_eligible
            and person.email in supplied
            and current.source_captured_at
            and current.source_captured_at > state["removed_capture_at"]
        )
        added = previous is not None and (
            person.id not in old or old[person.id].profile != "employee"
        )
        if returning or (
            added and state["directory_status"] == "included" and not state["pending_operation_id"]
        ):
            values = dict(
                directory_status="included", setup_required=True, setup_episode_id=uuid4()
            )
            connection.execute(
                update(org_person)
                .where(org_person.c.workspace_id == workspace, org_person.c.id == person.id)
                .values(**values)
            )
            rows[person.id] = {**state, **values}
    return rows


# Close repaired mapping/diagnostic conditions without settling human lifecycle decisions.
def reconcile_reviews(
    connection,
    workspace,
    current,
    previous,
    candidate,
    config,
    *,
    supplied,
    at,
    baseline=False,
    configuration_only=False,
):
    states = (
        {
            r["id"]: r
            for r in connection.execute(
                select(org_person).where(org_person.c.workspace_id == workspace)
            ).mappings()
        }
        if configuration_only
        else directory_transitions(connection, workspace, current, previous, supplied)
    )
    existing = (
        connection.execute(
            select(org_recommendation).where(org_recommendation.c.workspace_id == workspace)
        )
        .mappings()
        .all()
    )
    open_cases = {(r["kind"], r["target"]): r for r in existing if r["status"] == "open"}
    prior = {p.id: p for p in previous.people} if previous else {}
    people = {p.email: p for p in current.people}
    people_by_id = {p.id: p for p in current.people}
    conditions = set(candidate.issues)
    for person in current.people:
        state = states[person.id]
        if (
            person.profile == "employee"
            and person.email in supplied
            and state["directory_status"] == "included"
            and state["setup_required"]
            and not state["pending_operation_id"]
            and not person.absence_review
        ):
            conditions.add(("TENANCY_SETUP_REVIEW", person.email))
    active = set()
    for kind, target in sorted(conditions):
        person = next((people[address] for address in target.split(":") if address in people), None)
        role_review = kind in {"LOB_LEADER_REVIEW", "DESIGNEE_INVALID"}
        if person is None and role_review:
            from types import SimpleNamespace

            anchor = next((r for r in states.values() if r["email"] in target.split(":")), None)
            if anchor:
                person = SimpleNamespace(
                    id=anchor["id"], email=anchor["email"], full_name=anchor["email"]
                )
        if person is None:
            continue
        state = states[person.id]
        if kind in {
            "PERSON_ABSENCE_REVIEW",
            "LOB_MAPPING_REVIEW",
            "TENANCY_SETUP_REVIEW",
        } and state["directory_status"] in {"exempt", "offboarded", "merged"}:
            continue
        if not role_review and suppressed(config, kind, target, current.people):
            continue
        basis = (
            str(state["setup_episode_id"])
            if kind == "TENANCY_SETUP_REVIEW"
            else issue_basis(kind, target, current.people)
        )
        key = kind, target
        active.add(key)
        found = open_cases.get(key)
        if found:
            connection.execute(
                update(org_recommendation)
                .where(
                    org_recommendation.c.id == found["id"],
                    org_recommendation.c.workspace_id == workspace,
                )
                .values(last_seen_at=at, version_id=current.id)
            )
        else:
            connection.execute(
                org_recommendation.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    person_id=person.id,
                    kind=kind,
                    category="actionable" if kind in ACTIONABLE else "informational",
                    target=target,
                    basis=basis or "legacy",
                    status="open",
                    first_seen_at=at,
                    last_seen_at=at,
                    version_id=current.id,
                    data={
                        "name": person.full_name or person.email,
                        "email": person.email,
                        **(
                            {
                                "segment_id": target.split(":")[0],
                                "segment_name": next(
                                    (
                                        segment.label
                                        for segment in config.lobs
                                        if segment.id == target.split(":")[0]
                                    ),
                                    target.split(":")[0],
                                ),
                            }
                            if role_review
                            else {}
                        ),
                    },
                )
            )
    for key, row in open_cases.items():
        if key not in active and (
            row["category"] == "informational"
            or row["kind"] in {"LOB_LEADER_REVIEW", "DESIGNEE_INVALID"}
            or (
                row["kind"] == "LOB_MAPPING_REVIEW"
                and has_valid_accountability(people_by_id.get(row["person_id"]), config)
            )
        ):
            # Missing-manager warnings need a genuinely supplied profile before clearing.
            if row["kind"] == "MANAGER_PROFILE_MISSING" and row["target"] not in supplied:
                continue
            connection.execute(
                update(org_recommendation)
                .where(
                    org_recommendation.c.id == row["id"],
                    org_recommendation.c.workspace_id == workspace,
                )
                .values(
                    status="resolved",
                    resolved_at=at,
                    resolution="mapping_corrected"
                    if row["kind"] == "LOB_MAPPING_REVIEW"
                    else "source_corrected",
                )
            )
    if baseline or previous is None:
        if not any(r["kind"] == "ORGANIZATION_BASELINE" for r in existing):
            add_change(
                connection,
                workspace,
                current,
                None,
                "ORGANIZATION_BASELINE",
                at,
                {"count": sum(p.profile == "employee" for p in current.people)},
            )
        return
    for person in current.people:
        if person.profile != "employee" or person.email not in supplied:
            continue
        old = prior.get(person.id)
        if old is None or old.profile != "employee":
            add_change(
                connection,
                workspace,
                current,
                person,
                "EMPLOYEE_ADDED",
                at,
                {"after": profile(person)},
            )
        elif profile(old) != profile(person):
            add_change(
                connection,
                workspace,
                current,
                person,
                "METADATA_UPDATED",
                at,
                {"before": profile(old), "after": profile(person)},
            )


# Append one dated baseline/change record per publication and stable person, retaining immutable
# facts.
def add_change(connection, workspace, revision, person, kind, at, data):
    target = person.email if person else workspace
    basis = hashlib.sha256(
        (str(revision.id) + ":" + (str(person.id) if person else "baseline")).encode()
    ).hexdigest()
    connection.execute(
        org_recommendation.insert().values(
            id=uuid4(),
            workspace_id=workspace,
            person_id=person.id if person else None,
            kind=kind,
            category="change",
            target=target,
            basis=basis,
            status="resolved",
            first_seen_at=at,
            last_seen_at=at,
            resolved_at=at,
            version_id=revision.id,
            data={
                "name": person.full_name or person.email if person else "Organization baseline",
                "email": person.email if person else "",
                **json.loads(json.dumps(data)),
            },
        )
    )


# Explicit operator setup adopts existing snapshots conservatively without inventing tenancy
# mappings.
def initialize_existing_reviews(connection):
    from otm.organization.contracts import Configuration
    from otm.organization.reconcile import prepare
    from otm.storage.organization import SqlOrganizationStore, source_intake
    from otm.storage.tables import org_feed, org_workspace

    for row in connection.execute(
        select(org_workspace).where(org_workspace.c.applied_version_id.is_not(None))
    ).mappings():
        if connection.scalar(
            select(org_recommendation.c.id)
            .where(org_recommendation.c.workspace_id == row["id"])
            .limit(1)
        ):
            continue
        current = SqlOrganizationStore._revision(connection, row["id"], row["applied_version_id"])
        config = Configuration.model_validate_json(json.dumps(row["configuration"]))
        feed = (
            connection.execute(
                select(org_feed).where(
                    org_feed.c.workspace_id == row["id"], org_feed.c.id == current.snapshot_id
                )
            )
            .mappings()
            .one()
        )
        source = source_intake(feed, config)
        candidate = prepare(
            source.records,
            source.envelope,
            config,
            current.model_copy(update={"source_captured_at": None}),
            current.published_at,
            trusted_reapply=True,
        )
        reconcile_reviews(
            connection,
            row["id"],
            current,
            None,
            candidate,
            config,
            supplied={r.email for r in source.records},
            at=current.published_at,
            baseline=True,
        )


# Settle an already-offboarded identity's old absence only after a qualified later return.
# Reconciliation uses this working copy; the persisted predecessor remains immutable.
def qualified_return_history(connection, workspace, previous, candidate, supplied):
    if previous is None or not candidate.absence_eligible or candidate.envelope.captured_at is None:
        return previous
    controls = connection.execute(
        select(org_person).where(
            org_person.c.workspace_id == workspace,
            org_person.c.directory_status == "offboarded",
            org_person.c.removed_capture_at.is_not(None),
        )
    ).mappings()
    returned = {
        row["id"]
        for row in controls
        if row["removed_capture_at"] is not None
        and candidate.envelope.captured_at > row["removed_capture_at"]
    }
    settled = tuple(
        p.model_copy(update={"absence_review": False, "absence_review_since": None})
        if p.id in returned and p.email in supplied
        else p
        for p in previous.people
    )
    return (
        previous.model_copy(update={"people": settled}) if settled != previous.people else previous
    )


# Only a newly recorded administrator decision may settle an old absence during reclassification.
# Existing suppressions must not change flags when an unrelated mapping edit reuses the same source.
def administrative_decision_history(previous, old_config, new_config, supplied):
    added_exclusions = set(new_config.managed_exclusions) - set(old_config.managed_exclusions)
    targets = {
        d.target
        for d in new_config.review_decisions
        if d.kind == "PERSON_ABSENCE_REVIEW" and d not in old_config.review_decisions
    }
    people = tuple(
        person.model_copy(
            update={
                "absence_review": False,
                "absence_review_since": None
                if person.email in supplied
                else person.absence_review_since,
            }
        )
        if person.absence_review
        and (person.id in added_exclusions or person.email in targets)
        and suppressed(new_config, "PERSON_ABSENCE_REVIEW", person.email, (person,))
        else person
        for person in previous.people
    )
    return previous.model_copy(update={"people": people})
