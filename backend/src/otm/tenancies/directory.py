"""Coherent, scoped registry/review projections and exact current-context workflow previews."""

import json
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from otm.organization.contracts import Configuration
from otm.organization.review_rules import has_valid_accountability
from otm.storage.organization import OrganizationConflict, SqlOrganizationStore
from otm.storage.tables import (
    audit_event,
    baseline_version,
    operation,
    org_feed,
    org_person,
    org_recommendation,
    org_version,
    org_workspace,
    tenancy,
    tenancy_configuration,
    tenancy_membership,
)
from otm.tenancies.contracts import OrganizationContext
from otm.tenancies.views import (
    AssociationView,
    PersonOption,
    PersonWorkflow,
    ReviewDirectory,
    ReviewView,
    TenancyDirectory,
    TenancyView,
)


# One short read snapshot supplies labels, registry facts, decisions and revision context together.
@dataclass
class RegistryState:
    workspace: str
    context: OrganizationContext
    config: Configuration
    head: object
    people: dict
    controls: dict
    supplied: set
    tenancies: dict
    links: tuple
    reviews: tuple
    operations: dict
    operation_subjects: dict = field(default_factory=dict)
    operation_effects: dict = field(default_factory=dict)
    feed_version_ids: set = field(default_factory=set)
    segment_labels: dict = field(default_factory=dict)
    operation_kinds: dict = field(default_factory=dict)
    operation_completed: dict = field(default_factory=dict)
    latest_baseline: object = None

    # Pending/removing obligations count until their actual retirement is verified.
    def associations(self, *, person=None, tenant=None, history=False):
        return tuple(
            a
            for a in self.links
            if (history or a["status"] in {"pending", "active", "removing"})
            and (person is None or a["person_id"] == person)
            and (tenant is None or a["tenancy_id"] == tenant)
        )

    # Source rows and managed status jointly establish eligible recipients; names never
    # establish identity.
    def eligible(self, identifier):
        p = self.people.get(identifier)
        control = self.controls.get(identifier)
        return bool(
            p
            and control
            and p.profile == "employee"
            and p.email in self.supplied
            and not p.absence_review
            and control["directory_status"] == "included"
            and not control["pending_operation_id"]
        )

    # Retain readable identity for historical/retired links without synthesizing an employee row.
    def option(self, identifier):
        p = self.people.get(identifier)
        anchor = self.controls.get(identifier)
        if p:
            return PersonOption(id=p.id, name=p.full_name or p.email, email=p.email)
        if anchor:
            return PersonOption(id=identifier, name=anchor["email"], email=anchor["email"])
        raise OrganizationConflict("ORGANIZATION_PERSON_NOT_FOUND")


# Load only one authenticated workspace; caller owns authorization and the coherent transaction.
def registry_state(connection, workspace):
    state = (
        connection.execute(select(org_workspace).where(org_workspace.c.id == workspace))
        .mappings()
        .one_or_none()
    )
    if state is None or state["applied_version_id"] is None:
        raise OrganizationConflict("ORGANIZATION_FEED_REQUIRED")
    head = SqlOrganizationStore._revision(connection, workspace, state["applied_version_id"])
    config = Configuration.model_validate_json(json.dumps(state["configuration"]))
    controls = {
        r["id"]: dict(r)
        for r in connection.execute(
            select(org_person).where(org_person.c.workspace_id == workspace)
        ).mappings()
    }
    source = connection.execute(
        select(org_feed.c.data).where(
            org_feed.c.workspace_id == workspace, org_feed.c.id == head.snapshot_id
        )
    ).scalar_one()
    desired = baseline_version.alias("desired_baseline")
    verified = baseline_version.alias("verified_baseline")
    tenants = {
        r["id"]: dict(r)
        for r in connection.execute(
            select(
                tenancy,
                tenancy_configuration.c.policy_override_statements,
                tenancy_configuration.c.quota_override_statements,
                tenancy_configuration.c.monthly_budget_override_amount,
                desired.c.version_number.label("baseline_version_number"),
                verified.c.version_number.label("verified_baseline_version_number"),
            )
            .outerjoin(
                tenancy_configuration,
                (tenancy_configuration.c.workspace_id == tenancy.c.workspace_id)
                & (tenancy_configuration.c.tenancy_id == tenancy.c.id)
                & (tenancy_configuration.c.id == tenancy.c.desired_configuration_id),
            )
            .outerjoin(
                desired,
                (desired.c.workspace_id == tenancy.c.workspace_id)
                & (desired.c.id == tenancy.c.baseline_version_id),
            )
            .outerjoin(
                verified,
                (verified.c.workspace_id == tenancy.c.workspace_id)
                & (verified.c.id == tenancy.c.verified_baseline_version_id),
            )
            .where(tenancy.c.workspace_id == workspace)
        ).mappings()
    }
    links = tuple(
        dict(r)
        for r in connection.execute(
            select(tenancy_membership).where(tenancy_membership.c.workspace_id == workspace)
        ).mappings()
    )
    reviews = tuple(
        dict(r)
        for r in connection.execute(
            select(org_recommendation).where(org_recommendation.c.workspace_id == workspace)
        ).mappings()
    )
    # Revision provenance groups mapping reapplies with their source feed, not clock timestamps.
    versions = (
        connection.execute(
            select(
                org_version.c.id,
                org_version.c.feed_id,
                org_version.c.base_version_id,
                org_version.c.configuration,
            ).where(org_version.c.workspace_id == workspace)
        )
        .mappings()
        .all()
    )
    feed_versions = {v["id"] for v in versions if v["feed_id"] == head.snapshot_id}
    version_labels = {
        v["id"]: {s["id"]: s["label"] for s in v["configuration"].get("lobs", [])} for v in versions
    }
    segment_labels = {
        v["id"]: {
            "before": version_labels.get(v["base_version_id"], {}),
            "after": version_labels[v["id"]],
        }
        for v in versions
    }
    operation_rows = (
        connection.execute(
            select(
                operation.c.id,
                operation.c.state,
                operation.c.kind,
                operation.c.completed_at,
                operation.c.effect_knowledge,
                audit_event.c.data["intent"]["target"]["person_id"].astext.label("person_id"),
            )
            .outerjoin(
                audit_event,
                (audit_event.c.workspace_id == operation.c.workspace_id)
                & (audit_event.c.id == operation.c.current_intent_event_id),
            )
            .where(operation.c.workspace_id == workspace)
        )
        .mappings()
        .all()
    )
    ops = {row["id"]: row["state"] for row in operation_rows}
    subjects = {row["id"]: UUID(row["person_id"]) for row in operation_rows if row["person_id"]}
    return RegistryState(
        workspace,
        OrganizationContext(
            applied_version_id=state["applied_version_id"],
            proposed_version_id=state["proposed_version_id"],
            configuration_id=state["configuration_id"],
            registry_revision=state["registry_revision"],
        ),
        config,
        head,
        {p.id: p for p in head.people},
        controls,
        {r["email"] for r in source["records"]},
        tenants,
        links,
        reviews,
        ops,
        subjects,
        {row["id"]: row["effect_knowledge"] for row in operation_rows},
        feed_versions,
        segment_labels,
        {row["id"]: row.get("kind") for row in operation_rows},
        {row["id"]: row.get("completed_at") for row in operation_rows},
        connection.execute(
            select(baseline_version.c.id, baseline_version.c.version_number)
            .where(
                baseline_version.c.workspace_id == workspace,
                baseline_version.c.published_at.is_not(None),
            )
            .order_by(baseline_version.c.version_number.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none(),
    )


# Do not infer tenancy ownership from managers; resolve only explicit registry associations.
def tenancy_view(state, row):
    links = state.associations(tenant=row["id"])
    owner = next((a for a in links if a["role"] == "owner"), None)
    person = state.people.get(owner["person_id"]) if owner else None
    by_email = {p.email: p for p in state.head.people}
    manager = by_email.get(person.manager_email) if person else None
    leader = by_email.get(person.accountable_leader_email) if person else None
    lob = next((lob.label for lob in state.config.lobs if person and lob.id == person.lob_id), None)
    return TenancyView(
        has_pending_operation=row["operation_id"] is not None,
        desired_configuration_id=row.get("desired_configuration_id"),
        last_verified_configuration_id=row.get("last_verified_configuration_id"),
        override_categories=tuple(
            category
            for field, category in (
                ("policy_override_statements", "policy"),
                ("quota_override_statements", "quota"),
                ("monthly_budget_override_amount", "budget"),
            )
            if row.get(field) is not None
        ),
        baseline_version_id=row.get("baseline_version_id"),
        baseline_version_number=row.get("baseline_version_number"),
        verified_baseline_version_id=row.get("verified_baseline_version_id"),
        verified_baseline_version_number=row.get("verified_baseline_version_number"),
        configuration_verified_at=row.get("configuration_verified_at"),
        id=row["id"],
        name=row["name"],
        tenancy_ocid=row["tenancy_ocid"],
        parent_tenancy_ocid=row["parent_tenancy_ocid"],
        home_region=row["home_region"],
        kind=row["kind"],
        status=row["status"],
        origin=row["origin"],
        provider_mode=row["provider_mode"],
        owner_person_id=owner["person_id"] if owner else None,
        owner_name=state.option(owner["person_id"]).name if owner else None,
        owner_email=state.option(owner["person_id"]).email if owner else None,
        manager_name=manager.full_name or manager.email
        if manager
        else person.manager_email
        if person
        else None,
        leader_name=leader.full_name or leader.email
        if leader
        else person.accountable_leader_email
        if person
        else None,
        lob_name=lob,
        member_count=len(links),
        operation_id=row["operation_id"] or row["last_operation_id"],
        operation_state=state.operations.get(row["operation_id"] or row["last_operation_id"]),
        operation_completed_at=state.operation_completed.get(
            row["operation_id"] or row["last_operation_id"]
        ),
        verified_at=row["verified_at"],
        created_at=row["created_at"],
        cleanup_count=sum(
            a["cleanup_required"] for a in state.associations(tenant=row["id"], history=True)
        ),
    )


# Per-role choices never offer shared-owner deletion or arbitrary unregistered target actions.
def association_view(state, link):
    row = state.tenancies[link["tenancy_id"]]
    actions = ("keep",)
    if link["status"] == "active" and row["status"] == "active" and not row["operation_id"]:
        actions = (
            ("remove", "keep")
            if link["role"] == "member"
            else (
                ("delete", "transfer", "keep")
                if row["kind"] == "individual" and len(state.associations(tenant=row["id"])) == 1
                else ("transfer", "keep")
            )
        )
    return AssociationView(
        id=link["id"],
        person_id=link["person_id"],
        tenancy_id=row["id"],
        tenancy_name=row["name"],
        tenancy_kind=row["kind"],
        tenancy_status=row["status"],
        role=link["role"],
        status=link["status"],
        compartment_ocid=link["compartment_ocid"],
        compartment_name=link["compartment_name"],
        cleanup_required=link["cleanup_required"],
        operation_id=link["operation_id"],
        actions=actions,
    )


# Public historical facts are bounded stored projections, not raw command or source payloads.
def review_view(row):
    return ReviewView(
        id=row["id"],
        kind=row["kind"],
        category=row["category"],
        status=row["status"],
        person_id=row["person_id"],
        name=row["data"].get("name", "Organization"),
        email=row["data"].get("email", ""),
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        resolved_at=row["resolved_at"],
        resolution=row["resolution"],
        operation_id=row["operation_id"],
        data=row["data"],
    )


# Latest-feed information excludes completed actionable decisions; history remains queryable.
def feed_information(state):
    versions = state.feed_version_ids or {state.head.id}
    return [
        r
        for r in state.reviews
        if r["version_id"] in versions
        and (
            r["category"] == "change"
            or (r["category"] == "informational" and r["status"] == "open")
        )
    ]


# Keep counts independent of search/tab pagination and preserve oldest actionable episode ordering.
def review_directory(state, query):
    active = [r for r in state.reviews if r["category"] == "actionable" and r["status"] == "open"]
    history = [r for r in state.reviews if r["category"] != "actionable" or r["status"] != "open"]
    information = feed_information(state)
    rows = (
        active
        if query.category == "actionable"
        else (information if query.category == "informational" else history)
    )
    rows = [
        r
        for r in rows
        if query.query.casefold()
        in " ".join((r["kind"], r["data"].get("name", ""), r["data"].get("email", ""))).casefold()
    ]
    rows.sort(
        key=lambda r: (
            r["first_seen_at"]
            if query.sort == "first_seen_at"
            else str(r["data"].get("name", "")).casefold()
            if query.sort == "name"
            else r[query.sort].casefold(),
            str(r["id"]),
        ),
        reverse=query.direction == "desc",
    )
    pages = max(1, (len(rows) + query.page_size - 1) // query.page_size)
    page = min(query.page, pages)
    # Current labels come from the pinned head; historical review payloads remain untouched.
    labels = {segment.id: segment.label for segment in state.config.lobs}
    selected = rows[(page - 1) * query.page_size : page * query.page_size]
    projected = [
        dict(
            r,
            data={
                **r["data"],
                "segment_name": labels.get(
                    r["data"].get("segment_id"), r["data"].get("segment_name")
                ),
            },
        )
        if r["status"] == "open" and r["kind"] in {"LOB_LEADER_REVIEW", "DESIGNEE_INVALID"}
        else r
        for r in selected
    ]
    # Readable display values never replace immutable IDs in stored change evidence.
    projected = [
        dict(
            r,
            data={
                **r["data"],
                **{
                    side: {
                        **r["data"][side],
                        "lob_name": state.segment_labels.get(r["version_id"], {})
                        .get(side, labels)
                        .get(
                            r["data"][side].get("lob_id"),
                            "Unknown industry segment" if r["data"][side].get("lob_id") else None,
                        ),
                    }
                    for side in ("before", "after")
                    if isinstance(r["data"].get(side), dict)
                },
            },
        )
        for r in projected
    ]
    return ReviewDirectory(
        items=tuple(review_view(r) for r in projected),
        total=len(rows),
        page=page,
        pages=pages,
        page_size=query.page_size,
        actionable_count=len(active),
        history_count=len(history),
        informational_count=len(information),
    )


# Registry cards count registered nonterminated tenancies and include owner associations in
# membership.
def tenancy_directory(state, query, costs=None):
    all_rows = [
        tenancy_view(state, t)
        for t in state.tenancies.values()
        if t["status"] not in {"terminated", "cancelled"}
    ]
    if costs:
        all_rows = [
            t.model_copy(update={"costs": costs[t.id]}) if t.id in costs else t for t in all_rows
        ]
    rows = [
        t
        for t in all_rows
        if (not query.shared_only or t.kind == "shared")
        and query.query.casefold()
        in " ".join(
            (
                t.name,
                t.owner_name or "",
                t.owner_email or "",
                t.manager_name or "",
                t.lob_name or "",
                t.tenancy_ocid,
            )
        ).casefold()
    ]
    if query.sort in {"actual", "budget", "forecast"}:
        usable = [
            t
            for t in rows
            if t.costs.state in {"current", "partial"} and getattr(t.costs, query.sort) is not None
        ]
        missing = [t for t in rows if t not in usable]
        usable.sort(key=lambda t: str(t.id))
        usable.sort(
            key=lambda t: Decimal(getattr(t.costs, query.sort)), reverse=query.direction == "desc"
        )
        rows = usable + sorted(missing, key=lambda t: str(t.id))
    else:
        rows.sort(
            key=lambda t: (
                getattr(t, query.sort)
                if query.sort == "member_count"
                else (getattr(t, query.sort) or "").casefold(),
                str(t.id),
            ),
            reverse=query.direction == "desc",
        )
    pages = max(1, (len(rows) + query.page_size - 1) // query.page_size)
    page = min(query.page, pages)
    return TenancyDirectory(
        costs_pending_count=sum(t.costs.pending for t in all_rows),
        can_refresh_costs=any(t.costs.can_refresh for t in all_rows),
        latest_baseline_id=state.latest_baseline["id"] if state.latest_baseline else None,
        latest_baseline_version_number=state.latest_baseline["version_number"]
        if state.latest_baseline
        else None,
        items=tuple(rows[(page - 1) * query.page_size : page * query.page_size]),
        total=len(rows),
        page=page,
        pages=pages,
        page_size=query.page_size,
        total_tenancies=len(all_rows),
        individual_count=sum(t.kind == "individual" for t in all_rows),
        shared_count=sum(t.kind == "shared" for t in all_rows),
        pending_count=sum(t.status in {"pending", "terminating"} for t in all_rows),
        issue_count=sum(
            t.status == "failed" or t.operation_state in {"failed", "needs_attention"}
            for t in all_rows
        ),
    )


# A fresh dialog captures the exact context and all active/pending obligations for one stable
# person.
def person_workflow(state, identifier, *, mode, review_id=None):
    person = state.people.get(identifier)
    if person is None:
        raise OrganizationConflict("ORGANIZATION_PERSON_NOT_FOUND")
    control = state.controls[identifier]
    review = (
        next(
            (
                r
                for r in state.reviews
                if r["id"] == review_id
                and r["person_id"] == identifier
                and r["status"] == "open"
                and r["category"] == "actionable"
            ),
            None,
        )
        if review_id
        else None
    )
    if review_id and review is None:
        raise OrganizationConflict("ORGANIZATION_REVIEW_CHANGED")
    associations = tuple(association_view(state, a) for a in state.associations(person=identifier))
    actions = (
        ["cancel_simulation"]
        if control["pending_operation_id"]
        and state.operations.get(control["pending_operation_id"])
        in {"queued", "waiting", "needs_attention", "failed"}
        and state.operation_effects.get(control["pending_operation_id"], "none") == "none"
        and mode == "simulated"
        and state.operation_subjects.get(control["pending_operation_id"]) == identifier
        else []
    )
    if not control["pending_operation_id"]:
        if review and review["kind"] in {"LOB_LEADER_REVIEW", "DESIGNEE_INVALID"}:
            actions = []
        elif review and review["kind"] == "LOB_MAPPING_REVIEW":
            actions = ["ignore"] + (["resolve"] if person.lob_id else [])
        elif review and review["kind"] not in {"TENANCY_SETUP_REVIEW", "PERSON_ABSENCE_REVIEW"}:
            actions = ["resolve"]
        elif (
            control["directory_status"] in {"exempt", "offboarded"}
            and person.email in state.supplied
        ):
            actions = ["reonboard"]
        elif person.absence_review or control["directory_status"] == "outside":
            actions = [] if person.email in state.supplied else ["offboard_person"]
            if person.email in state.supplied:
                actions.append("mark_returned")
            actions.append("merge")
        elif state.eligible(identifier):
            actions = ["create_tenancy", "import_tenancy", "join_shared"]
            if not associations:
                actions += ["no_tenancy_required", "merge"]
                if control["setup_required"]:
                    actions.append("keep_without_tenancy")
    if not control["pending_operation_id"] and not review:
        available = {choice for association in associations for choice in association.actions}
        actions.extend(
            name
            for choice, name in (
                ("delete", "delete_tenancy"),
                ("transfer", "transfer_owner"),
                ("remove", "remove_member"),
            )
            if choice in available
        )
    mapping_required = not has_valid_accountability(person, state.config)
    if mapping_required:
        actions = [
            a for a in actions if a not in {"create_tenancy", "import_tenancy", "join_shared"}
        ]
    if mode != "simulated":
        actions = [
            a
            for a in actions
            if a
            in {
                "ignore",
                "resolve",
                "merge",
                "reonboard",
                "mark_returned",
                "no_tenancy_required",
                "keep_without_tenancy",
            }
            or (a == "offboard_person" and not associations)
        ]
    setup = {
        r["person_id"]
        for r in state.reviews
        if r["kind"] == "TENANCY_SETUP_REVIEW" and r["status"] == "open"
    }
    absent = {
        r["person_id"]
        for r in state.reviews
        if r["kind"] == "PERSON_ABSENCE_REVIEW" and r["status"] == "open"
    }
    partners = setup if person.absence_review else absent
    partners = {
        key
        for key in partners
        if key in state.people
        and key != identifier
        and not state.controls[key]["pending_operation_id"]
        and state.people[key].email != state.config.policy.root_email
        and (
            (person.absence_review and state.people[key].email in state.supplied)
            or (not person.absence_review and state.people[key].email not in state.supplied)
        )
    }
    if "merge" in actions and (identifier not in setup | absent or not partners):
        actions.remove("merge")
    # The reporting boundary may decline a tenancy but cannot leave through employee offboarding.
    if person.email == state.config.policy.root_email:
        actions = [a for a in actions if a not in {"offboard_person", "merge"}]
    eligible = tuple(
        state.option(p.id) for p in state.head.people if state.eligible(p.id) and p.id != identifier
    )
    return PersonWorkflow(
        mapping_required=mapping_required,
        context=state.context,
        person=state.option(identifier),
        review=review_view(review) if review else None,
        source_present=person.email in state.supplied,
        is_manager=person.known_manager,
        directory_status=control["directory_status"],
        pending_operation_id=control["pending_operation_id"],
        provider_mode=mode,
        actions=tuple(actions),
        associations=associations,
        shared_tenancies=tuple(
            tenancy_view(state, t)
            for t in state.tenancies.values()
            if t["kind"] == "shared"
            and t["status"] == "active"
            and not t["operation_id"]
            and not state.associations(person=identifier, tenant=t["id"])
        ),
        transfer_recipients=eligible,
        merge_partners=tuple(
            state.option(p)
            for p in partners
            if p in state.people
            and p != identifier
            and not state.controls[p]["pending_operation_id"]
        ),
    )
