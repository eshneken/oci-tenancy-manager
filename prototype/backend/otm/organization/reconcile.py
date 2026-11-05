"""Pure candidate construction; no database, OCI or notification side effects."""

from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from otm.organization.contracts import (
    Candidate,
    Completeness,
    Configuration,
    Diagnostic,
    Envelope,
    PersonState,
    Record,
    Revision,
    require_aware,
)
from otm.organization.review_rules import canonical_email, suppressed


# Construct a candidate from normalized rows, trusted configuration and prior state.
#
# Retain stable identities and omitted trusted metadata, validate the whole effective
# reporting graph, then derive accountability and review issues. Absence requires a
# fresh authoritative complete census with current profile/path coverage. Fatal
# diagnostics mark the candidate rejected; this function never publishes or sends alerts.
def prepare(
    records: tuple[Record, ...],
    envelope: Envelope,
    config: Configuration,
    previous: Revision | None,
    observed_at: datetime,
    *,
    trusted_reapply: bool = False,
) -> Candidate:
    require_aware(observed_at)
    observed_at = observed_at.astimezone(UTC)
    policy = config.policy
    diagnostics: list[Diagnostic] = []

    # Append a safe finding, optionally marking publication unsafe.
    def diagnose(code: str, affected: str | None = None, *, fatal: bool = False) -> None:
        diagnostics.append(Diagnostic(code=code, affected_email=affected, fatal=fatal))

    if (envelope.source_id, envelope.population_id) != (policy.source_id, policy.population_id):
        diagnose("SOURCE_SCOPE_MISMATCH", fatal=True)
    if not policy.allow_metadata:
        diagnose("SOURCE_NOT_CONFIGURED_FOR_METADATA", fatal=True)
    capture = envelope.captured_at
    if capture is None:
        if not policy.allow_undated_development_metadata:
            diagnose("CAPTURE_TIME_REQUIRED", fatal=True)
        if previous and previous.source_captured_at:
            diagnose("CAPTURE_ORDER_UNKNOWN", fatal=True)
    else:
        age = (observed_at - capture).total_seconds()
        if age < 0:
            diagnose("FUTURE_CAPTURE", fatal=True)
        elif age > policy.max_age_seconds:
            # An explicit administrator decision may use already-published evidence after
            # freshness expires. It cannot turn that old source into a new absence census.
            diagnose(
                "STALE_SOURCE_REVIEW_ONLY" if trusted_reapply else "STALE_CAPTURE",
                fatal=not trusted_reapply,
            )
        if previous and previous.source_captured_at and capture <= previous.source_captured_at:
            diagnose("SUPERSEDED_CAPTURE", fatal=True)

    # Source JSON remains immutable. Explicit administrator aliases normalize only the
    # effective graph; two source rows collapsing to one identity are still rejected.
    # Normalize identity/reference emails only through verified administrator merge rules.
    def canonical_record(record):
        address = canonical_email(config, record.email)
        if address != record.email:
            diagnose("RETIRED_EMAIL_IN_FEED", record.email, fatal=True)
        return record.model_copy(
            update={
                "email": address,
                "source_record_id": "email:" + address
                if record.source_record_id.startswith("email:")
                else record.source_record_id,
                "manager_email": canonical_email(config, record.manager_email),
                "reported_top_manager_email": canonical_email(
                    config, record.reported_top_manager_email
                ),
            }
        )

    # Exclusions filter only current/future effective organization rows. Original feed
    # JSON, historical versions and OCI users are never deleted by an org-removal decision.
    excluded = {canonical_email(config, address) for address in config.excluded_emails}
    records = tuple(
        canonical_record(record)
        for record in records
        if canonical_email(config, record.email) not in excluded
    )
    # Identity ambiguity rejects the whole candidate; neither key authorizes a silent merge.
    for key in ("email", "source_record_id"):
        counts = Counter(getattr(record, key) for record in records)
        for value, count in counts.items():
            if count > 1:
                diagnose("DUPLICATE_" + key.upper(), value if key == "email" else None, fatal=True)

    # Seed the effective graph from trusted history. Omission in partial input is not removal.
    people = {}
    if previous:
        # Prefer the observed new profile over the retained absent profile, then attach
        # the survivor UUID. Historical versions and the provisional identity remain intact.
        for person in sorted(
            previous.people, key=lambda p: p.email == canonical_email(config, p.email)
        ):
            address = canonical_email(config, person.email)
            if address in excluded:
                continue
            people[address] = person.model_copy(
                update={
                    "email": address,
                    "source_record_id": "email:" + address
                    if (person.source_record_id or "").startswith("email:")
                    else person.source_record_id,
                    "manager_email": canonical_email(config, person.manager_email),
                    "reported_top_manager_email": canonical_email(
                        config, person.reported_top_manager_email
                    ),
                }
            )
        for merge in config.identity_merges:
            address = canonical_email(config, merge.new_email)
            if address in people:
                updates = {"id": merge.person_id}
                if any(p.email == merge.old_email for p in previous.people):
                    updates.update(absence_review=False, absence_review_since=None)
                people[address] = people[address].model_copy(update=updates)
    old_ids = {
        person.source_record_id: person.email
        for person in people.values()
        if person.source_record_id is not None
    }
    rows = {record.email: record for record in records}
    references: set[str] = set()
    direct_managers: set[str] = set()

    # Create a stable placeholder or enrich a missing name without pretending a feed row
    # exists.
    def ensure(address: str, name: str | None = None, *, configured: bool = False) -> None:
        if address not in people:
            people[address] = PersonState(
                id=uuid4(),
                email=address,
                full_name=name,
                profile="configured" if configured else "reference",
            )
        elif name is not None and people[address].full_name is None:
            people[address] = people[address].model_copy(update={"full_name": name})

    ensure(policy.root_email, configured=True)
    for lob in config.lobs:
        ensure(lob.leader_email, configured=True)
        for address in lob.designee_emails:
            ensure(address, configured=True)

    for record in records:
        ensure(record.email)
        old = people[record.email]
        if record.source_record_id in old_ids and old_ids[record.source_record_id] != record.email:
            diagnose("AMBIGUOUS_SOURCE_ID_EMAIL", record.email, fatal=True)
        if old.source_record_id and old.source_record_id != record.source_record_id:
            diagnose("SOURCE_ID_CHANGED", record.email, fatal=True)
        if record.email != policy.root_email and record.manager_email is None:
            diagnose("MANAGER_REQUIRED", record.email, fatal=True)
        people[record.email] = old.model_copy(
            update={
                "full_name": record.full_name,
                "source_values": {
                    "full_name": record.full_name,
                    "manager_email": record.manager_email,
                },
                "source_record_id": record.source_record_id,
                "profile": "employee",
                "manager_email": None
                if record.email == policy.root_email
                else record.manager_email,
                "manager_provenance": "feed",
                "last_row_observed_at": observed_at,
                "last_source_capture_at": capture,
                "reported_top_manager_email": record.reported_top_manager_email,
                "territory": record.territory,
            }
        )
        if record.email != policy.root_email and record.manager_email:
            ensure(record.manager_email, record.manager_name)
            direct_managers.add(record.manager_email)
            references.add(record.manager_email)
        if record.reported_top_manager_email:
            ensure(record.reported_top_manager_email)
            references.add(record.reported_top_manager_email)

    for address in references:
        people[address] = people[address].model_copy(
            update={
                "last_reference_observed_at": observed_at,
                "known_manager": people[address].known_manager or address in direct_managers,
            }
        )
    people[policy.root_email] = people[policy.root_email].model_copy(
        update={
            "manager_email": None,
            "known_manager": True,
        }
    )

    for edge in config.supplemental_edges:
        ensure(edge.employee_email, configured=True)
        ensure(edge.manager_email, configured=True)
        current = people[edge.employee_email]
        if current.manager_email and current.manager_email != edge.manager_email:
            diagnose("SUPPLEMENTAL_EDGE_CONFLICT", edge.employee_email, fatal=True)
        elif not current.manager_email:
            people[edge.employee_email] = current.model_copy(
                update={
                    "manager_email": edge.manager_email,
                    "manager_provenance": edge.provenance,
                }
            )
        people[edge.manager_email] = people[edge.manager_email].model_copy(
            update={"known_manager": True}
        )

    override_issues: set[tuple[str, str]] = set()
    for override in config.overrides:
        if override.email not in people:
            diagnose("OVERRIDE_PERSON_UNKNOWN", override.email, fatal=True)
            continue
        person = people[override.email]
        for field, value in override.values.items():
            if override.email in rows and getattr(rows[override.email], field) != value:
                override_issues.add(("OVERRIDE_CONFLICT", f"{override.email}:{field}"))
            if field == "manager_email":
                ensure(value)
                people[value] = people[value].model_copy(update={"known_manager": True})
        updates = dict(override.values)
        if "manager_email" in updates:
            updates["manager_provenance"] = "admin override: " + override.reason
        people[override.email] = person.model_copy(update=updates)

    # Validate the whole effective graph, including retained partial-feed edges.
    finished: set[str] = set()
    for address in people:
        trail: set[str] = set()
        cursor: str | None = address
        while cursor is not None and cursor in people and cursor not in finished:
            if cursor in trail:
                diagnose("REPORTING_CYCLE", cursor, fatal=True)
                break
            trail.add(cursor)
            cursor = people[cursor].manager_email
        finished.update(trail)

    # Coverage describes this capture, not profiles retained from an older publication.
    missing_managers = direct_managers - rows.keys()
    if policy.required_root_profile and policy.root_email not in rows:
        missing_managers.add(policy.root_email)
    elif not policy.required_root_profile:
        # Some exports intentionally enumerate only the root's descendants. Exempt the
        # configured boundary alone; every other referenced manager still needs a row.
        missing_managers.discard(policy.root_email)
    for address in sorted(missing_managers):
        diagnose("MANAGER_PROFILE_MISSING", address)

    paths: dict[str, tuple[str, ...]] = {policy.root_email: ()}

    # Memoize direct-manager-first ancestry using iterative walks.
    #
    # Stop at known paths or missing edges; cycles remain unresolved because the
    # earlier effective-graph validation already makes their candidate unpublishable.
    def path_for(address: str) -> tuple[str, ...]:
        trail: list[str] = []
        visited: set[str] = set()
        cursor: str | None = address
        while cursor and cursor in people and cursor not in paths:
            if cursor in visited:
                # Already rejected by graph validation; do not invent a resolved path.
                paths.update((item, ()) for item in trail)
                return ()
            visited.add(cursor)
            trail.append(cursor)
            cursor = people[cursor].manager_email
        for item in reversed(trail):
            manager = people[item].manager_email
            paths[item] = (manager, *paths.get(manager, ())) if manager in people else ()
        return paths.get(address, ())

    for address, person in tuple(people.items()):
        path = path_for(address)
        ancestry = (
            "root"
            if address == policy.root_email
            else "resolved"
            if path and path[-1] == policy.root_email
            else "incomplete"
        )
        people[address] = person.model_copy(update={"manager_path": path, "ancestry": ancestry})
    incoming_unresolved = any(people[address].ancestry == "incomplete" for address in rows)
    if incoming_unresolved:
        diagnose("INCOMING_ROOT_PATH_INCOMPLETE")

    # A completeness declaration alone cannot establish a census: authority, freshness,
    # required profiles and rooted incoming paths must all support absence inference.
    absence_eligible = (
        policy.authoritative
        and policy.census_contract_confirmed
        and capture is not None
        and (observed_at - capture).total_seconds() <= policy.max_age_seconds
        and envelope.declared_completeness == Completeness.COMPLETE
        and not missing_managers
        and not incoming_unresolved
        and not any(d.fatal for d in diagnostics)
    )
    assessed = (
        Completeness.COMPLETE
        if absence_eligible
        else Completeness.PARTIAL
        if missing_managers
        or incoming_unresolved
        or envelope.declared_completeness == Completeness.PARTIAL
        else Completeness.UNCONFIRMED
    )
    # A referenced person is positive presence evidence even without their own employee row.
    positive = rows.keys() | references
    for address, person in tuple(people.items()):
        updates: dict[str, object] = {}
        # Once detected, absence is a human decision even if the employee reappears.
        # Returning presence is evidence for Resolve/keep, not permission to close a review.
        if (
            not person.absence_review
            and absence_eligible
            and address not in positive
            and (person.last_row_observed_at or person.last_reference_observed_at)
        ):
            updates.update(
                absence_review=True,
                absence_review_since=person.absence_review_since or observed_at,
            )
        current = person.model_copy(update=updates)
        if current.absence_review and suppressed(
            config, "PERSON_ABSENCE_REVIEW", address, (current,)
        ):
            updates.update(absence_review=False)
            # Closure settles this continuous absence, not the next genuine departure.
            # Keep its key while absent; positive evidence permits a fresh later episode.
            if address in positive:
                updates["absence_review_since"] = None
        elif not current.absence_review and address in positive:
            updates["absence_review_since"] = None
        if absence_eligible:
            updates["last_qualified_census_at"] = capture
        people[address] = person.model_copy(update=updates)

    issues: set[tuple[str, str]] = override_issues | {
        ("MANAGER_PROFILE_MISSING", a) for a in missing_managers
    }
    # A moved/absent leader cannot retain an active LOB assignment merely by configuration.
    leader_lobs = {}
    for lob in config.lobs:
        leader = people[lob.leader_email]
        if (
            leader.ancestry == "resolved"
            and leader.manager_email == policy.root_email
            and not leader.absence_review
            and not leader.absence_review_since
        ):
            leader_lobs[lob.leader_email] = lob
        else:
            issues.add(("LOB_LEADER_REVIEW", f"{lob.id}:{lob.leader_email}"))
    for address, person in tuple(people.items()):
        lob = None
        if person.ancestry == "resolved":
            # LOB designation is explicit, not inferred for every root direct report.
            lob = next(
                (leader_lobs[a] for a in (address, *person.manager_path) if a in leader_lobs), None
            )
        designees: list[str] = []
        if lob:
            for designee in lob.designee_emails:
                state = people[designee]
                if (
                    state.ancestry == "resolved"
                    and not state.absence_review
                    and not state.absence_review_since
                    and (designee == lob.leader_email or lob.leader_email in state.manager_path)
                ):
                    designees.append(designee)
                else:
                    issues.add(("DESIGNEE_INVALID", f"{lob.id}:{designee}"))
        if person.ancestry == "incomplete" and address in rows:
            issues.add(("ANCESTRY_UNRESOLVED", address))
        if person.absence_review:
            issues.add(("PERSON_ABSENCE_REVIEW", address))
        if address in rows and person.reported_top_manager_email:
            expected_top = lob.leader_email if lob else None
            # Leaders themselves report TOP_MGR=Organization leader in the real CSV. This boundary
            # convention is valid; for descendants compare the hint against graph truth.
            boundary_report = (
                person.manager_email == policy.root_email
                and person.reported_top_manager_email == policy.root_email
            )
            if (
                expected_top
                and person.reported_top_manager_email != expected_top
                and not boundary_report
            ):
                issues.add(("TOP_MANAGER_MISMATCH", address))
            if not lob and person.ancestry == "resolved":
                issues.add(("LOB_MAPPING_REVIEW", address))
        people[address] = person.model_copy(
            update={
                "lob_id": lob.id if lob else None,
                "accountable_leader_email": lob.leader_email if lob else None,
                "designee_emails": tuple(designees),
            }
        )

    return Candidate(
        envelope=envelope,
        expected_head_id=previous.id if previous else None,
        expected_configuration_id=config.id,
        observed_at=observed_at,
        people=tuple(people[a] for a in sorted(people)),
        diagnostics=tuple(diagnostics),
        assessed_coverage=assessed,
        absence_eligible=absence_eligible,
        issues=tuple(sorted(issues)),
        employee_row_emails=tuple(sorted(rows)),
    )
