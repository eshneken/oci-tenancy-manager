"""Audited organization reviews with explicitly simulated tenancy success."""

from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from otm.organization.associations import TenancyRegistry
from otm.organization.contracts import IdentityMerge, ReviewDecision
from otm.organization.review_rules import ACTIONABLE, issue_basis
from otm.organization.store import PublicationConflict

COPY = {
    "PERSON_ABSENCE_REVIEW": (
        "Absence review",
        "Review every tenancy association before offboarding. Removing the last association "
        "removes this person from the managed directory; source and reporting history remain.",
    ),
    "TENANCY_SETUP_REVIEW": (
        "New employee",
        "Create or import a tenancy, add shared membership, or record that no tenancy "
        "is required. Each choice closes this review. An email change may require a merge.",
    ),
    "LOB_MAPPING_REVIEW": (
        "LOB mapping review",
        "No configured line of business matches this employee. Dismiss the current "
        "condition or exempt this employee from future LOB mapping reviews.",
    ),
    "LOB_LEADER_REVIEW": (
        "LOB leader review",
        "Review moved/absent leader and branch accountability. Resolve records "
        "completion for the same condition; changed facts reopen it.",
    ),
    "DESIGNEE_INVALID": (
        "Designee review",
        "Review or replace the nominated designee in configuration. Resolve "
        "closes this condition; changed facts reopen it.",
    ),
    "OVERRIDE_CONFLICT": (
        "Override conflict",
        "Administrator correction disagrees with source metadata. Review the "
        "source or correction; resolve records this condition’s disposition.",
    ),
    "TOP_MANAGER_MISMATCH": (
        "Top manager mismatch",
        "Correct TOP_MGR or manager relationships in the source. The active "
        "warning clears automatically when corrected; dated history remains.",
    ),
    "MANAGER_PROFILE_MISSING": (
        "Missing manager profile",
        "Supply the missing manager row. Full-census absence inference remains "
        "blocked; warning clears on sufficient corrected evidence.",
    ),
    "ANCESTRY_UNRESOLVED": (
        "Incomplete reporting chain",
        "Correct missing or incorrect manager relationships. The warning clears when "
        "the chain reaches the configured organization boundary.",
    ),
}
SIMULATED_ACTIONS = {
    "create_tenancy": "Create tenancy",
    "import_tenancy": "Import tenancy",
    "shared_membership": "Add to shared tenancy",
    "delete_tenancy": "Delete tenancy",
    "keep_tenancy": "Keep tenancy",
}


# Expose explicit onboarding and absence decisions; simulated operations close the review.
def allowed_actions(kind, evidence=None):
    if kind == "TENANCY_SETUP_REVIEW":
        return [
            "create_tenancy",
            "import_tenancy",
            "shared_membership",
            "no_tenancy_required",
            "merge",
        ]
    if kind == "PERSON_ABSENCE_REVIEW":
        result = ["offboard_person", "merge"]
        if evidence == "feed_row":
            result.append("keep_returned")
        return result
    return ["resolve", "ignore"] if kind == "LOB_MAPPING_REVIEW" else ["resolve"]


# Read current open actionable cases and warnings without losing original episode dates.
def open_reviews(store, workspace):
    people = store.inspection_rows("current_organization", workspace)
    config = store.configuration(workspace)
    directory = {p["id"]: p for p in TenancyRegistry(store, workspace).read()["people"]}
    by_email = {p["email"]: p for p in people}
    rows = []
    for issue in store.inspection_rows("pending_organization_reviews", workspace):
        # A merged identity's immutable anchor can have an old email; target/version wins.
        address = next(
            (email for email in by_email if email in issue["target"].split(":")),
            issue["person_email"] or issue["target"].split(":")[-1],
        )
        person = by_email.get(address, {})
        title, detail = COPY.get(
            issue["kind"], (issue["kind"], "Administrator investigation required.")
        )
        rows.append(
            {
                "id": str(issue["id"]),
                "kind": issue["kind"],
                "title": title,
                "detail": detail,
                "email": address,
                "target": issue["target"],
                "person_id": str(person["person_id"]) if person else None,
                "name": person.get("full_name") or address,
                "lob_name": person.get("lob_name"),
                "status": issue["status"],
                "category": "actionable" if issue["kind"] in ACTIONABLE else "informational",
                "first_seen": issue["created_at"],
                "last_seen": issue["updated_at"],
                "actions": allowed_actions(issue["kind"], person.get("evidence"))
                if issue["kind"] in ACTIONABLE
                else [],
            }
        )
    versions = store.tables["version"]
    members = store.tables["member"]
    with store.engine.connect() as connection:
        first_seen = dict(
            connection.execute(
                select(members.c.person_id, versions.c.data["published_at"].astext)
                .join(versions, versions.c.id == members.c.version_id)
                .where(
                    versions.c.workspace_id == workspace,
                    versions.c.kind == "applied",
                    members.c.profile == "employee",
                )
                .order_by(versions.c.data["published_at"].astext.desc())
            ).all()
        )
        events = (
            connection.execute(
                select(store.tables["event"])
                .where(
                    store.tables["event"].c.workspace_id == workspace,
                    store.tables["event"].c.kind == "tenancy_action_acknowledged",
                )
                .order_by(store.tables["event"].c.at)
            )
            .mappings()
            .all()
        )
    for p in people:
        if (
            p["tenancy_setup_review"]
            or directory.get(str(p["person_id"]), {}).get("onboarding_required")
            or str(p["person_id"]) in {str(i) for i in config.pending_onboarding_person_ids}
        ):
            rows.append(
                {
                    "id": "setup:" + str(p["person_id"]),
                    "person_id": str(p["person_id"]),
                    "kind": "TENANCY_SETUP_REVIEW",
                    "title": COPY["TENANCY_SETUP_REVIEW"][0],
                    "detail": COPY["TENANCY_SETUP_REVIEW"][1],
                    "email": p["email"],
                    "target": p["email"],
                    "name": p["full_name"] or p["email"],
                    "lob_name": p["lob_name"],
                    "status": "open",
                    "category": "actionable",
                    "first_seen": first_seen.get(str(p["person_id"])),
                    "last_seen": None,
                    "actions": allowed_actions("TENANCY_SETUP_REVIEW"),
                }
            )
    for row in rows:
        acknowledgments = [e for e in events if e["data"].get("case_id") == row["id"]]
        if acknowledgments:
            row["status"] = "acknowledged"
            row["last_action"] = acknowledgments[-1]["data"]["operation"]
    rows = [
        r
        for r in rows
        if r["kind"] not in {"TENANCY_SETUP_REVIEW", "PERSON_ABSENCE_REVIEW", "LOB_MAPPING_REVIEW"}
        or directory.get(r.get("person_id"), {}).get("managed", True)
    ]
    return sorted(rows, key=lambda row: (row["title"], row["name"], row["id"]))


# Keep warning episodes, grouped per-employee publication changes and administrator history.
def informational_history(store, workspace):
    active = {
        row["id"]: row
        for row in open_reviews(store, workspace)
        if row["category"] == "informational"
    }
    rows = []
    for issue in store.inspection_rows("organization_reconciliation", workspace):
        if issue["category"] != "exception" or issue["kind"] in ACTIONABLE:
            continue
        row = active.get(str(issue["id"]))
        if row is None:
            title, detail = COPY.get(issue["kind"], (issue["kind"], "Source warning history."))
            row = {
                "id": str(issue["id"]),
                "kind": issue["kind"],
                "title": title,
                "detail": detail,
                "email": issue["target"],
                "name": issue["target"],
                "status": issue["status"],
                "first_seen": issue["created_at"],
                "last_seen": issue["updated_at"],
                "resolved_at": issue["resolved_at"],
            }
        rows.append({**row, "category": "informational", "actions": []})
    table = store.tables["event"]
    with store.engine.connect() as connection:
        events = (
            connection.execute(
                select(table).where(table.c.workspace_id == workspace).order_by(table.c.at)
            )
            .mappings()
            .all()
        )
    known_names = {}
    for event in events:
        data = event["data"]
        if event["kind"] == "organization_published":
            grouped = defaultdict(list)
            fields = {
                "email",
                "full_name",
                "manager_email",
                "lob_id",
                "accountable_leader_email",
                "designee_emails",
            }
            for change in data.get("changes", []):
                if change["field"] in fields:
                    grouped[(change["person_id"], change["email"])].append(change)
            # First census is one baseline event, not hundreds of name/manager changes.
            version = store.revision(UUID(event["version_id"]))
            known_names.update({p.email: p.full_name or p.email for p in version.people})
            if version.predecessor_id is None:
                rows.append(
                    {
                        "id": str(event["id"]),
                        "kind": "BASELINE_LOADED",
                        "title": "Initial baseline loaded",
                        "detail": (
                            f"{sum(p.profile == 'employee' for p in version.people)} "
                            "employee profiles established."
                        ),
                        "name": "Organization",
                        "email": "",
                        "status": "applied",
                        "first_seen": event["at"],
                    }
                )
                continue
            names = {str(p.id): p.full_name or p.email for p in version.people}
            for (person_id, address), changes in grouped.items():
                rows.append(
                    {
                        "id": f"change:{event['id']}:{person_id}",
                        "kind": "METADATA_UPDATED",
                        "title": "Employee metadata updated",
                        "name": names.get(person_id, address),
                        "email": address,
                        "status": "applied",
                        "first_seen": event["at"],
                        "detail": "; ".join(
                            f"{c['field']}: {c['before']} → {c['after']}" for c in changes
                        ),
                        "changes": changes,
                    }
                )
        elif event["kind"] == "configuration_changed":
            before = data["before"]
            after = data["after"]
            added_decisions = after.get("review_decisions", [])[
                len(before.get("review_decisions", [])) :
            ]
            merges = after.get("identity_merges", [])[len(before.get("identity_merges", [])) :]
            if added_decisions or merges:
                subject = merges[-1]["new_email"] if merges else added_decisions[-1]["target"]
                address = next((part for part in subject.split(":") if "@" in part), subject)
                decision = added_decisions[-1] if added_decisions else {}
                simulated = decision.get("simulation") == "succeeded"
                operation = decision.get("operation")
                rows.append(
                    {
                        "id": str(event["id"]),
                        "kind": "TENANCY_ACTION_SIMULATED" if simulated else "REVIEW_DECISION",
                        "title": (SIMULATED_ACTIONS[operation] + " — simulated success")
                        if simulated
                        else "No tenancy required"
                        if operation == "no_tenancy_required"
                        else "Administrator decision",
                        "name": known_names.get(address, address),
                        "email": address,
                        "status": "simulated_success"
                        if simulated
                        else "merged"
                        if merges
                        else added_decisions[-1]["disposition"],
                        "operation": operation,
                        "simulation": "succeeded" if simulated else None,
                        "oci_performed": False if simulated else None,
                        "person_id": decision.get("person_id"),
                        "detail": (
                            "Simulated success. No OCI resources or memberships were changed. "
                            "Organization review closed. " + data["reason"]
                        )
                        if simulated
                        else data["reason"],
                        "first_seen": event["at"],
                    }
                )
        elif event["kind"] == "tenancy_registry_changed":
            rows.append(
                {
                    "id": str(event["id"]),
                    "kind": "TENANCY_ACTION_SIMULATED" if data["simulated"] else "REVIEW_DECISION",
                    "title": data["operation"].replace("_", " ").capitalize(),
                    "name": data["name"],
                    "email": data["email"],
                    "person_id": data["person_id"],
                    "operation": data["operation"],
                    "status": "simulated_success" if data["simulated"] else "resolved",
                    "simulation": "succeeded" if data["simulated"] else None,
                    "oci_performed": False,
                    "detail": (
                        "Simulated success. No OCI resources were changed. "
                        if data["simulated"]
                        else ""
                    )
                    + (
                        "Removed from managed directory. "
                        if data["person_removed"]
                        else "Managed profile retained. "
                    )
                    + f"{data['remaining_associations']} active associations remain. "
                    + data["reason"],
                    "first_seen": event["at"],
                }
            )
        elif event["kind"] == "tenancy_action_acknowledged":
            rows.append(
                {
                    "id": str(event["id"]),
                    "kind": "ACTION_ACKNOWLEDGED",
                    "title": "Prototype action acknowledged",
                    "name": known_names.get(data["email"], data["email"]),
                    "email": data["email"],
                    "status": "acknowledged",
                    "detail": (
                        f"{SIMULATED_ACTIONS[data['operation']]} — acknowledgment only; "
                        f"no OCI operation. {data['reason']}"
                    ),
                    "first_seen": event["at"],
                }
            )
        elif event["kind"] in {"feed_rejected", "feed_superseded"} or (
            event["kind"] == "feed_received" and data.get("disposition") == "integrity_conflict"
        ):
            rows.append(
                {
                    "id": str(event["id"]),
                    "kind": "FEED_REJECTED",
                    "title": "Feed rejected",
                    "name": "Organization feed",
                    "email": "",
                    "status": "blocked",
                    "detail": str(data),
                    "first_seen": event["at"],
                }
            )
    return sorted(rows, key=lambda row: str(row["first_seen"] or ""), reverse=True)


# Version-bound commands preserving source evidence and original identity anchors.
class ReviewWorkflow:
    # Scope every command to one active run selected by the local web boundary.
    def __init__(self, store, workspace):
        self.store = store
        self.workspace = workspace

    # Atomically audit simulated success and closure, or apply removal/identity decisions.
    def operate(
        self,
        case_id,
        operation,
        expected,
        reason=None,
        partner_email=None,
        *,
        tenancy_id=None,
        name=None,
        kind=None,
    ):
        reason = (
            reason.strip()
            if reason is not None
            else "Administrator selected " + operation.replace("_", " ") + "."
        )
        if len(reason) < 3:
            raise ValueError("A meaningful administrator reason is required.")
        store = self.store
        actual = store.workspace_context(self.workspace)
        if any(
            str(actual[key]) != str(expected[key])
            for key in (
                "workspace_id",
                "applied_version_id",
                "proposed_version_id",
                "configuration_id",
            )
        ):
            raise PublicationConflict("Review context changed. Refresh and confirm again.")
        cases = open_reviews(store, self.workspace)
        head = store.head(self.workspace)
        people = {p.email: p for p in head.people} if head else {}
        case = next(
            (row for row in cases if row["id"] == case_id and row["category"] == "actionable"), None
        )
        if not case or operation not in case["actions"]:
            raise ValueError("This review/action is no longer available.")
        if operation in {
            "create_tenancy",
            "import_tenancy",
            "shared_membership",
            "no_tenancy_required",
        }:
            return TenancyRegistry(store, self.workspace).operate(
                {
                    "context": expected,
                    "operation": "join_shared" if operation == "shared_membership" else operation,
                    "person_id": case["person_id"],
                    "tenancy_id": str(tenancy_id) if tenancy_id else None,
                    "name": name,
                    "kind": kind,
                    "reason": reason,
                }
            )
        config = store.configuration(self.workspace)
        now = datetime.now(UTC)
        if case["kind"] == "OVERRIDE_CONFLICT":
            # Enrich legacy versions that predate source_values before fingerprinting.
            with store.engine.connect() as connection:
                payload = connection.execute(
                    select(store.tables["feed"].c.data).where(
                        store.tables["feed"].c.id == str(head.snapshot_id)
                    )
                ).scalar_one()
            for source in payload["records"]:
                person = people.get(source["email"])
                if person and not person.source_values:
                    people[person.email] = person.model_copy(
                        update={
                            "source_values": {
                                "full_name": source["full_name"],
                                "manager_email": source["manager_email"],
                            }
                        }
                    )
        # Resolving a review must not implicitly publish a different staged source feed.
        if actual["proposal_status"] != "already_applied":
            raise ValueError("Apply the pending organization proposal before resolving reviews.")
        decisions = list(config.review_decisions)
        updates = {}
        if operation == "merge":
            other = people.get(partner_email)
            subject = people[case["email"]]
            old, new = (subject, other) if subject.absence_review else (other, subject)
            new_case = next(
                (
                    row
                    for row in cases
                    if row["kind"] == "TENANCY_SETUP_REVIEW" and new and row["email"] == new.email
                ),
                None,
            )
            if (
                not old
                or not new
                or not old.absence_review
                or new.absence_review
                or not new_case
                or old.id == new.id
            ):
                raise ValueError("Choose an absent employee and an unresolved new employee.")
            if config.policy.root_email in {old.email, new.email}:
                raise ValueError("The configured root cannot participate in an identity merge.")
            raw = store.tables["feed"]
            with store.engine.connect() as connection:
                payload = connection.execute(
                    select(raw.c.data).where(raw.c.id == str(head.snapshot_id))
                ).scalar_one()
            emails = {row["email"] for row in payload["records"]}
            if old.email in emails or new.email not in emails:
                raise ValueError(
                    "Merge requires old email absent and new email present in the latest feed."
                )
            merge = IdentityMerge(
                old_email=old.email,
                new_email=new.email,
                person_id=old.id,
                retired_person_id=new.id,
                actor="local:admin",
                reason=reason,
            )
            updates["identity_merges"] = (*config.identity_merges, merge)

            # Rebase trusted references as part of the same atomic identity decision.
            # Replace precisely the confirmed old address in configuration references.
            def renamed(address):
                return new.email if address == old.email else address

            updates["lobs"] = tuple(
                lob.model_copy(
                    update={
                        "leader_email": renamed(lob.leader_email),
                        "designee_emails": tuple(renamed(e) for e in lob.designee_emails),
                    }
                )
                for lob in config.lobs
            )
            updates["supplemental_edges"] = tuple(
                e.model_copy(
                    update={
                        "employee_email": renamed(e.employee_email),
                        "manager_email": renamed(e.manager_email),
                    }
                )
                for e in config.supplemental_edges
            )
            updates["overrides"] = tuple(
                o.model_copy(
                    update={
                        "email": renamed(o.email),
                        "values": {
                            k: renamed(v) if k == "manager_email" else v
                            for k, v in o.values.items()
                        },
                    }
                )
                for o in config.overrides
            )
            decisions = [
                d.model_copy(update={"target": ":".join(renamed(e) for e in d.target.split(":"))})
                for d in decisions
            ]
            decisions.append(
                ReviewDecision(
                    kind="TENANCY_SETUP_REVIEW",
                    target=new.email,
                    disposition="resolved",
                    recorded_at=now,
                    actor="local:admin",
                    reason=reason,
                )
            )
        else:
            if operation == "remove_user":
                person = people[case["email"]]
                protected = (
                    {config.policy.root_email}
                    | {lob.leader_email for lob in config.lobs}
                    | {e for lob in config.lobs for e in lob.designee_emails}
                )
                if person.email in protected or any(
                    p.manager_email == person.email for p in head.people
                ):
                    raise ValueError(
                        "Reassign reporting/configuration references before removing this person."
                    )
                updates["excluded_emails"] = (*config.excluded_emails, person.email)
            decisions.append(
                ReviewDecision(
                    kind=case["kind"],
                    target=case["target"],
                    disposition="ignored" if operation == "ignore" else "resolved",
                    operation=operation,
                    simulation="succeeded" if operation in SIMULATED_ACTIONS else None,
                    person_id=case["person_id"],
                    basis=None
                    if case["kind"] == "TENANCY_SETUP_REVIEW" or operation == "ignore"
                    else issue_basis(case["kind"], case["target"], people.values()),
                    recorded_at=now,
                    actor="local:admin",
                    reason=reason,
                )
            )
        updates.update(id=uuid4(), review_decisions=tuple(decisions))
        result = store.update_configuration(
            config.model_copy(update=updates),
            expected_version_id=UUID(expected["applied_version_id"]),
            expected_proposed_id=UUID(expected["proposed_version_id"]),
            expected_configuration_id=UUID(expected["configuration_id"]),
            actor="local:admin",
            reason=reason,
            observed_at=now,
        )
        return {
            "resolved": True,
            "simulated": operation in SIMULATED_ACTIONS,
            "operation": operation,
            "status": "succeeded" if operation in SIMULATED_ACTIONS else "resolved",
            "oci_performed": False,
            "outcome": result.model_dump(mode="json"),
        }
