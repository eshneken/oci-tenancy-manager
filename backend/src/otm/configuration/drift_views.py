"""Derive current confirmed issues without rewriting history or clearing them on failed reads."""

from datetime import timedelta
from math import ceil

from otm.configuration.drift_context import registered_child, same_assignment
from otm.configuration.drift_contracts import (
    ConfigurationCheckSummary,
    ConfigurationDriftDirectory,
    ConfigurationIssue,
)
from otm.providers.configuration import CATEGORIES

# Evidence older than one daily interval cannot make a matching state appear freshly healthy.
MAX_CHECK_AGE = timedelta(hours=24)


# Keep old confirmed differences visible after unknown reads; unrelated generations never count.
def check_summary(
    row, records, pending, policy, baseline, now, *, include_payload=False, read_available=True
):
    current = [
        (stored, context, evidence)
        for stored, context, evidence in records
        if context.tenancy_id == row["id"] and same_assignment(context, row, policy)
    ]
    latest = current[0] if current else None
    complete = next((value for value in current if value[2].state in {"matching", "drifted"}), None)
    evidence = latest[2] if latest else None
    confirmed = (
        {
            item.category: item
            for item in complete[2].results
            if item.state in {"missing", "different"}
        }
        if complete
        else {}
    )
    stale = bool(evidence and now - evidence.checked_at > MAX_CHECK_AGE)
    qualified = registered_child(row, policy)
    state = evidence.state if evidence else "not_checked"
    if state == "superseded":
        state = "not_checked"
    if not qualified or not read_available:
        state = "unavailable"
    elif stale and not confirmed:
        state = "not_checked"
    active = pending.get(row["id"]) or (
        row["operation_id"]
        if row.get("reserved_operation_state") in {"queued", "running"}
        else None
    )
    if active:
        state = "checking"
    issues = []
    latest_results = {item.category: item for item in evidence.results} if evidence else {}
    for category in CATEGORIES:
        previous = confirmed.get(category)
        retained = bool(
            previous
            and (
                not evidence
                or evidence.state not in {"matching", "drifted"}
                or stale
                or not read_available
            )
        )
        source = previous if retained else latest_results.get(category)
        category_state = source.state if source else "not_checked"
        code = source.safe_code if source else None
        if not qualified:
            category_state, code = "unavailable", "PROVIDER_UNAVAILABLE"
        elif (
            stale
            or not read_available
            or (evidence and evidence.state not in {"matching", "drifted"})
        ) and not previous:
            category_state = "unavailable"
            code = (
                "PROVIDER_UNAVAILABLE"
                if not read_available
                else "CHECK_STALE"
                if stale
                else (source.safe_code if source and not source.complete else "READ_UNAVAILABLE")
            )
        issues.append(
            ConfigurationIssue(
                category=category,
                state=category_state,
                safe_code=code,
                binding_ocid=source.binding_ocid if source else None,
                expected=source.expected if source and include_payload else None,
                observed=source.observed if source and include_payload else None,
                evidence_at=complete[2].checked_at
                if retained
                else evidence.checked_at
                if evidence
                else None,
                retained=retained,
            )
        )
    # Unknown or expired reads need verification; only complete findings count as drift.
    issue_count = len(confirmed)
    override_categories = row.get("override_categories", ())
    return ConfigurationCheckSummary(
        tenancy_id=row["id"],
        tenancy_name=row["name"],
        baseline_id=row["baseline_version_id"],
        baseline_version_number=baseline.version_number if baseline else None,
        override_categories=override_categories,
        state=state,
        checked_at=evidence.checked_at if evidence else None,
        issue_count=issue_count,
        confirmed_issue_count=len(confirmed),
        stale=stale,
        can_check=qualified and read_available and not row["operation_id"] and not active,
        pending_operation_id=active,
        last_operation_id=latest[0]["operation_id"] if latest else None,
        categories=tuple(issues),
    )


# Filter current child projections before pagination; counters always describe the full
# authorized set.
def drift_directory(items, query):
    confirmed_count = sum(item.confirmed_issue_count > 0 for item in items)
    unavailable_count = sum(item.state == "unavailable" for item in items)
    unchecked_count = sum(item.state == "not_checked" and not item.stale for item in items)
    stale_count = sum(item.stale for item in items)
    checking_count = sum(item.state == "checking" for item in items)
    filtered = [
        item
        for item in items
        if (query.tab != "confirmed" or item.confirmed_issue_count)
        and (
            query.state == "all"
            or (query.state == "stale" and item.stale)
            or (query.state == "drifted" and item.confirmed_issue_count > 0)
            or (
                query.state in {"matching", "not_checked"}
                and item.state == query.state
                and not item.stale
            )
            or (query.state in {"unavailable", "checking"} and item.state == query.state)
        )
        and (not query.tenancy_id or item.tenancy_id == query.tenancy_id)
        and query.query.casefold() in item.tenancy_name.casefold()
    ]
    key = (
        (lambda item: item.tenancy_name.casefold())
        if query.sort == "name"
        else (
            (lambda item: item.issue_count)
            if query.sort == "issue_count"
            else (lambda item: item.checked_at.isoformat() if item.checked_at else "")
        )
    )
    filtered.sort(
        key=lambda item: (key(item), str(item.tenancy_id)), reverse=query.direction == "desc"
    )
    total = len(filtered)
    pages = max(1, ceil(total / query.page_size))
    page = min(query.page, pages)
    return ConfigurationDriftDirectory(
        items=tuple(filtered[(page - 1) * query.page_size : page * query.page_size]),
        total=total,
        page=page,
        pages=pages,
        page_size=query.page_size,
        confirmed_count=confirmed_count,
        unavailable_count=unavailable_count,
        unchecked_count=unchecked_count,
        checking_count=checking_count,
        stale_count=stale_count,
    )
