"""Immediate mapping preview/apply uses existing workspace locks, versions and immutable audit."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from otm.operations.contracts import canonical_hash
from otm.organization.contracts import Configuration, Lob
from otm.organization.mapping_contracts import (
    MappingApply,
    MappingCandidate,
    MappingChange,
    MappingContext,
    MappingImpact,
    MappingPreview,
    MappingRole,
    MappingSegment,
    MappingSettings,
)
from otm.organization.reconcile import prepare
from otm.organization.role_health import role_health
from otm.storage.organization import OrganizationConflict, source_intake
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import operation, org_feed, org_workspace


# Project only permitted editable values; trusted source/absence policy remains server-owned.
def editable(config):
    return MappingCandidate(
        root_email=config.policy.root_email,
        root_name=config.root_name,
        segments=tuple(MappingSegment(**s.model_dump()) for s in config.lobs),
    )


# Construct immutable mapping IDs deterministically for preview/apply, scoped to current settings.
def candidate_configuration(workspace, current, template, request):
    base = current or template
    if base is None:
        raise OrganizationConflict("MAPPING_SETUP_UNAVAILABLE")
    if (
        request.context.applied_version_id
        and (
            request.candidate.root_email != base.policy.root_email
            or request.candidate.root_name != base.root_name
        )
        and not request.change_root
    ):
        raise OrganizationConflict("MAPPING_ROOT_FIXED")
    existing = {s.id for s in current.lobs} if current else set()
    if any(s.id is not None and s.id not in existing for s in request.candidate.segments):
        raise OrganizationConflict("MAPPING_SEGMENT_CHANGED")
    digest = canonical_hash(request.model_dump(mode="json"))
    config_id = uuid5(NAMESPACE_URL, "otm:mapping:" + workspace + ":" + digest)
    segments = tuple(
        Lob(
            id=s.id or str(uuid5(config_id, str(i))),
            label=s.label,
            leader_email=s.leader_email,
            designee_emails=s.designee_emails,
        )
        for i, s in enumerate(request.candidate.segments)
    )
    return Configuration.model_validate(
        {
            **base.model_dump(),
            "id": config_id,
            "root_name": request.candidate.root_name,
            "policy": {**base.policy.model_dump(), "root_email": request.candidate.root_email},
            "lobs": segments,
        }
    )


# Load a consistent settings snapshot; Apply repeats this while holding the workspace write lock.
class MappingService:
    # The legacy profile supplies trusted policy only when explicitly setting up an empty workspace.
    def __init__(self, store, template, workflows):
        self.store, self.template, self.workflows = store, template, workflows

    # Database values always win over deployment bootstrap files; GET performs no initialization.
    def _state(self, connection, workspace, *, lock=False):
        query = select(org_workspace).where(org_workspace.c.id == workspace)
        row = (
            connection.execute(query.with_for_update() if lock else query).mappings().one_or_none()
        )
        config = Configuration.model_validate(row["configuration"]) if row else None
        head = (
            self.store._revision(connection, workspace, row["applied_version_id"])
            if row and row["applied_version_id"]
            else None
        )
        context = (
            MappingContext(**{k: row[k] for k in MappingContext.model_fields})
            if row
            else MappingContext()
        )
        blockers = []
        if connection.scalar(
            select(operation.c.id)
            .where(
                operation.c.workspace_id == workspace,
                operation.c.kind == "organization_action",
                operation.c.state.not_in(("succeeded", "cancelled")),
            )
            .limit(1)
        ):
            blockers.append("PENDING_LIFECYCLE")
        if row and row["proposed_version_id"]:
            proposal = self.store._revision(connection, workspace, row["proposed_version_id"])
            if not head or (
                proposal.id != head.id
                and (proposal.snapshot_id, proposal.configuration_id, proposal.predecessor_id)
                != (head.snapshot_id, head.configuration_id, head.predecessor_id)
            ):
                blockers.append("UNAPPLIED_ORGANIZATION")
        return config, head, context, tuple(blockers)

    # Role health is independent of generic review visibility and excludes absent/excluded nominees.
    def _roles(self, connection, workspace, config, head):
        if config is None:
            return ()
        supplied = set()
        if head:
            feed = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace, org_feed.c.id == head.snapshot_id
                    )
                )
                .mappings()
                .one()
            )
            supplied = {r.email for r in source_intake(feed, config).records}
        values = role_health(config, {p.email: p for p in head.people} if head else {}, supplied)
        return tuple(
            MappingRole(**{**v, **({"status": "not_verified"} if head is None else {})})
            for v in values
        )

    # Settings include current eligibility and pending-work explanations even before the first feed.
    def read(self, principal):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            config, head, context, blockers = self._state(connection, workspace)
            return MappingSettings(
                configured=config is not None,
                available=bool(config or self.template),
                context=context,
                candidate=editable(config) if config and config.lobs else None,
                root_editable=head is None,
                has_feed=head is not None,
                roles=self._roles(connection, workspace, config, head),
                blockers=blockers,
            )

    # Recalculate classification without creating another census or return.
    def _compute(self, connection, workspace, request, config, head, context, blockers, at, page):
        if context != request.context:
            raise OrganizationConflict("MAPPING_PREVIEW_CHANGED")
        candidate = candidate_configuration(workspace, config, self.template, request)
        old = {s.id: MappingSegment(**s.model_dump()) for s in config.lobs} if config else {}
        new = {s.id: MappingSegment(**s.model_dump()) for s in candidate.lobs}
        changes = tuple(
            MappingChange(segment_id=k, before=old.get(k), after=new.get(k))
            for k in sorted(old.keys() | new.keys())
            if old.get(k) != new.get(k)
        )
        impacts = []
        projected = head
        supplied = set()
        if head:
            feed = (
                connection.execute(
                    select(org_feed).where(
                        org_feed.c.workspace_id == workspace, org_feed.c.id == head.snapshot_id
                    )
                )
                .mappings()
                .one()
            )
            source = source_intake(feed, candidate)
            supplied = {r.email for r in source.records}
            computed = prepare(
                source.records,
                source.envelope,
                candidate,
                head.model_copy(update={"source_captured_at": None}),
                at,
                trusted_reapply=True,
                configuration_only=True,
            )
            raw = prepare(
                source.records,
                source.envelope,
                candidate.model_copy(update={"overrides": ()}),
                head.model_copy(update={"source_captured_at": None}),
                at,
                trusted_reapply=True,
                configuration_only=True,
            )
            if computed.rejected or raw.rejected:
                raise OrganizationConflict("MAPPING_INVALID_GRAPH")
            previous = {p.id: p for p in head.people}
            labels = {s.id: s.label for s in config.lobs}
            next_labels = {s.id: s.label for s in candidate.lobs}
            for person in computed.people:
                before = previous.get(person.id)
                if person.profile != "employee" or before is None:
                    continue
                values = dict(
                    person_id=person.id,
                    name=person.full_name or person.email,
                    email=person.email,
                    before_ancestry=before.ancestry,
                    after_ancestry=person.ancestry,
                    before_segment=labels.get(before.lob_id),
                    after_segment=next_labels.get(person.lob_id),
                    before_leader=before.accountable_leader_email,
                    after_leader=person.accountable_leader_email,
                    before_designees=before.designee_emails,
                    after_designees=person.designee_emails,
                )
                if any(
                    values["before_" + key] != values["after_" + key]
                    for key in ("segment", "leader", "designees", "ancestry")
                ):
                    impacts.append(MappingImpact(**values))
            projected = head.model_copy(update={"people": computed.people})
        roles = self._roles(connection, workspace, candidate, projected)
        if head:
            original_leaders = {s.id: s.leader_email for s in config.lobs}
            if any(
                r.role == "leader"
                and r.status != "healthy"
                and original_leaders.get(r.segment_id) != r.email
                for r in roles
            ):
                blockers = (*blockers, "INELIGIBLE_REPLACEMENT_LEADER")
        pages = max(1, (len(impacts) + 9) // 10)
        page = min(max(page, 1), pages)
        view = MappingPreview(
            root_before=config.policy.root_email if config else None,
            root_name_before=config.root_name if config else None,
            root_present=candidate.policy.root_email in supplied,
            unresolved_count=sum(
                p.profile == "employee" and p.ancestry == "incomplete" for p in projected.people
            )
            if projected
            else 0,
            context=context,
            candidate=request.candidate,
            preview_token=canonical_hash(request.model_dump(mode="json")),
            changes=changes,
            roles=roles,
            affected_count=len(impacts),
            unassigned_count=sum(
                i.before_segment is not None and i.after_segment is None for i in impacts
            ),
            items=tuple(impacts[(page - 1) * 10 : page * 10]),
            page=page,
            pages=pages,
            blockers=blockers,
            has_feed=head is not None,
        )
        return view, candidate

    # Read-only preview binds exactly normalized editable values and all current revision fences.
    def preview(self, principal, request, page=1):
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            return self._compute(
                connection,
                workspace,
                request,
                *self._state(connection, workspace),
                self.store.clock(),
                page,
            )[0]

    # Reauthorize and recompute under lock; uncertain responses require a fresh read.
    def apply(self, principal, request: MappingApply):
        from otm.tenancies.directory import registry_state

        with self.store._write(principal) as (connection, workspace, at):
            config, head, context, blockers = self._state(connection, workspace, lock=True)
            preview_request = request.model_dump(exclude={"preview_token"})
            from otm.organization.mapping_contracts import MappingRequest

            command = MappingRequest.model_validate(preview_request)
            view, candidate = self._compute(
                connection, workspace, command, config, head, context, blockers, at, 1
            )
            if request.preview_token != view.preview_token:
                raise OrganizationConflict("MAPPING_PREVIEW_CHANGED")
            if view.blockers:
                raise OrganizationConflict("MAPPING_PENDING_WORK")
            if head:
                self.workflows._reapply(
                    connection,
                    registry_state(connection, workspace),
                    candidate,
                    at,
                    configuration_only=True,
                    allow_root_change=command.change_root,
                )
            elif config:
                connection.execute(
                    org_workspace.update()
                    .where(org_workspace.c.id == workspace)
                    .values(
                        configuration_id=candidate.id,
                        configuration=candidate.model_dump(mode="json"),
                    )
                )
            else:
                connection.execute(
                    insert(org_workspace).values(
                        id=workspace,
                        configuration_id=candidate.id,
                        configuration=candidate.model_dump(mode="json"),
                    )
                )
            self.store._audit(
                connection,
                workspace,
                principal.actor,
                "organization_configured",
                at,
                candidate,
                action="mapping_apply",
                mapping_changes=view.changes,
                mapping_root_before=config.policy.root_email if config else None,
                mapping_root_after=candidate.policy.root_email,
                mapping_root_name_before=config.root_name if config else None,
                mapping_root_name_after=candidate.root_name,
            )
        return self.read(principal)
