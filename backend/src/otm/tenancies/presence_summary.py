"""Bounded inventory reads reuse the detail view's exact context and evidence validation."""

from collections import defaultdict

from sqlalchemy import and_, func, select

from otm.operations.contracts import canonical_hash
from otm.storage.tables import audit_event
from otm.storage.tables import managed_object_binding as bindings
from otm.storage.tables import user_presence_check as checks
from otm.storage.tables import user_presence_connection as connections
from otm.tenancies.presence import administrator_view, console_view, presence_views
from otm.tenancies.presence_context import bound_snapshot
from otm.tenancies.presence_contracts import RequiredUsersSummary, UserPresenceView
from otm.tenancies.presence_records import decode_intent, operation_rows


# Confirmed fresh absence takes precedence; uncertainty or stale facts can never become green.
def summarize(views, checking=False):
    a, b = (views.get(p, UserPresenceView()) for p in ("automation", "recovery"))
    pair = (a, b)
    invalid = any(
        v.state in {"present", "missing"} and (v.checked_at is None or v.operation_id is None)
        for v in pair
    )
    state = (
        "missing"
        if any(
            v.state == "missing"
            and not v.stale
            and v.checked_at is not None
            and v.operation_id is not None
            for v in pair
        )
        else "unavailable"
        if invalid
        else "stale"
        if any(v.stale for v in pair)
        else "unavailable"
        if any(v.state == "unknown" for v in pair)
        else "present"
        if all(v.state == "present" for v in pair)
        else "not_checked"
    )
    return RequiredUsersSummary(state=state, automation=a, recovery=b, checking=checking)


# All four queries are bound to the authenticated workspace and server-selected visible page IDs.
def summaries(service, connection, workspace, children):
    children = tuple(c for c in children if c["status"] == "active")
    if not children:
        return {}
    if any(c["workspace_id"] != workspace for c in children):
        raise ValueError("PRESENCE_SCOPE_INVALID")
    identifiers = tuple(c["id"] for c in children)
    policy = service.policy_loader() if service.policy is not None else None
    selected = service.policy if policy is not None and policy.policy == service.policy else None
    now = service.store.clock()
    console_policy = service.console_policy()
    current = defaultdict(list)
    for row in connection.execute(
        select(connections).where(
            connections.c.workspace_id == workspace,
            connections.c.tenancy_id.in_(identifiers),
            connections.c.state == "active",
            connections.c.provider_mode == "simulated",
        )
    ).mappings():
        current[row["tenancy_id"]].append(row)
    identities = defaultdict(list)
    for row in connection.execute(
        select(bindings).where(
            bindings.c.workspace_id == workspace,
            bindings.c.tenancy_id.in_(identifiers),
            bindings.c.state == "active",
            bindings.c.logical_key.in_(
                ("identity/domain", "identity/user/automation", "identity/user/recovery")
            ),
        )
    ).mappings():
        identities[row["tenancy_id"]].append(row)
    ranked = (
        select(
            checks,
            func.row_number()
            .over(
                partition_by=checks.c.tenancy_id,
                order_by=checks.c.acquisition_sequence.desc(),
            )
            .label("position"),
        )
        .where(
            checks.c.workspace_id == workspace,
            checks.c.tenancy_id.in_(identifiers),
            checks.c.state.in_(("complete", "unavailable", "superseded")),
        )
        .subquery()
    )
    latest = {
        row["tenancy_id"]: row
        for row in connection.execute(
            select(
                ranked, audit_event.c.data.label("data"), audit_event.c.data_hash.label("data_hash")
            )
            .outerjoin(
                audit_event,
                and_(
                    audit_event.c.workspace_id == workspace,
                    audit_event.c.workspace_id == ranked.c.workspace_id,
                    audit_event.c.operation_id == ranked.c.operation_id,
                    audit_event.c.id == ranked.c.evidence_event_id,
                    audit_event.c.kind == "required_user_check_outcome",
                ),
            )
            .where(ranked.c.position == 1)
        ).mappings()
    }
    pending = defaultdict(list)
    broken = set()
    for row in operation_rows(connection, workspace, pending=True, tenancy_ids=identifiers):
        # A corrupt queued intent must not mask its child with an unchecked default.
        child_id = row["presence_tenancy_id"]
        try:
            intent = decode_intent(row).intent
            if intent.snapshot.tenancy_id != child_id:
                raise ValueError("PRESENCE_SCOPE_INVALID")
            pending[child_id].append(intent.context_hash)
        except (ValueError, KeyError):
            broken.add(child_id)
    result = {}
    for child in children:
        identifier = child["id"]
        try:
            if identifier in broken or len(current[identifier]) > 1:
                raise ValueError("PRESENCE_RECORDS_UNAVAILABLE")
            snapshot = bound_snapshot(
                workspace,
                child,
                selected,
                current[identifier][0] if current[identifier] else None,
                identities[identifier],
                console_policy,
            )
            row = latest.get(identifier)
            views = presence_views(snapshot, row, row, now)
            digest = canonical_hash(snapshot.model_dump(mode="json")) if snapshot else None
            result[identifier] = summarize(
                views, digest is not None and digest in pending[identifier]
            ).model_copy(
                update={
                    "recovery_console": console_view(snapshot, row, row, now),
                    "administrator_access": administrator_view(snapshot, row, row, now),
                }
            )
        except (ValueError, KeyError, TypeError):
            # Preserve the rest of the page without inventing facts for a corrupt child.
            result[identifier] = RequiredUsersSummary(state="unavailable")
    return result
