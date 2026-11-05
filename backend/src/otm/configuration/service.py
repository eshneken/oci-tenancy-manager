"""Scoped authoring and immutable, locally qualified publication; no OCI or assignment effects."""

import json
from uuid import uuid4

from sqlalchemy import func, select, update

from otm.configuration.contracts import (
    BaselineContent,
    BaselineDirectory,
    BaselineDraftEvidence,
    BaselinePublicationEvidence,
    BaselineQuery,
    BaselineVersion,
    PublishBaseline,
    SaveBaselineDraft,
)
from otm.operations.contracts import canonical_hash
from otm.providers.baseline import BaselineQualifier, PublicationUnavailable
from otm.storage.organization import OrganizationConflict
from otm.storage.read_snapshot import read_snapshot
from otm.storage.tables import audit_event, baseline_version, org_workspace


# Project explicit columns through the closed contract and encode money without binary floats.
def draft_view(row):
    values = {name: row[name] for name in BaselineContent.model_fields}
    values["monthly_budget_amount"] = str(values["monthly_budget_amount"])
    content = BaselineContent.model_validate_json(json.dumps(values))
    if canonical_hash(content.model_dump(mode="json")) != row["content_hash"]:
        raise RuntimeError("INVALID_BASELINE_EVIDENCE")
    return BaselineVersion(
        id=row["id"],
        version_number=row["version_number"],
        edit_revision=row["edit_revision"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        content_hash=row["content_hash"],
        content=content,
        based_on_id=row.get("based_on_id"),
        published_by=row.get("published_by"),
        published_by_name=row.get("published_by_name"),
        published_at=row.get("published_at"),
        publication_mode=row.get("publication_mode"),
    )


# Reuse current administrator/session transaction guards without creating a second scope authority.
class BaselineAuthoring:
    # The organization repository supplies the verified workspace, clock and live command checks.
    def __init__(self, store, qualifier: BaselineQualifier | None = None):
        self.store = store
        self.qualifier = qualifier

    # Keep draft, latest publication, exact selection and paged history in one read snapshot.
    def read(self, principal, query=None):
        query = BaselineQuery.model_validate(query or BaselineQuery())
        workspace = self.store._principal(principal)
        with read_snapshot(self.store.engine) as connection:
            configured = (
                connection.scalar(select(org_workspace.c.id).where(org_workspace.c.id == workspace))
                is not None
            )
            scoped = select(baseline_version).where(baseline_version.c.workspace_id == workspace)
            draft = (
                connection.execute(scoped.where(baseline_version.c.published_at.is_(None)))
                .mappings()
                .one_or_none()
            )
            history = scoped.where(baseline_version.c.published_at.is_not(None))
            latest = (
                connection.execute(
                    history.order_by(baseline_version.c.version_number.desc()).limit(1)
                )
                .mappings()
                .one_or_none()
            )
            total = connection.scalar(
                select(func.count())
                .select_from(baseline_version)
                .where(
                    baseline_version.c.workspace_id == workspace,
                    baseline_version.c.published_at.is_not(None),
                )
            )
            pages = max(1, (total + query.page_size - 1) // query.page_size)
            page = min(query.page, pages)
            rows = (
                connection.execute(
                    history.order_by(baseline_version.c.version_number.desc())
                    .offset((page - 1) * query.page_size)
                    .limit(query.page_size)
                )
                .mappings()
                .all()
            )
            selected = (
                connection.execute(scoped.where(baseline_version.c.id == query.baseline_id))
                .mappings()
                .one_or_none()
                if query.baseline_id
                else None
            )
            return BaselineDirectory(
                configured=configured,
                draft=draft_view(draft) if draft else None,
                publication_available=self.qualifier is not None,
                latest=draft_view(latest) if latest else None,
                selected=draft_view(selected) if selected else None,
                items=tuple(draft_view(r) for r in rows),
                total=total,
                page=page,
                page_size=query.page_size,
                pages=pages,
            )

    # Workspace locking serializes initial version allocation; exact revisions fence edits.
    def save(self, principal, command):
        command = SaveBaselineDraft.model_validate(command)
        payload = command.content.model_dump(mode="json")
        digest = canonical_hash(payload)
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            row = (
                connection.execute(
                    select(baseline_version).where(
                        baseline_version.c.workspace_id == workspace,
                        baseline_version.c.published_at.is_(None),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row:
                existing = draft_view(row)
                if command.based_on_id != row.get("based_on_id"):
                    raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
                if command.baseline_id != row["id"] and command.baseline_id is not None:
                    raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
                if row["content_hash"] == digest:
                    return existing
                if (
                    command.baseline_id != row["id"]
                    or command.expected_revision != row["edit_revision"]
                ):
                    raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
                before = existing.content
                identifier, version, revision = (
                    row["id"],
                    row["version_number"],
                    row["edit_revision"] + 1,
                )
            else:
                if command.baseline_id is not None:
                    raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
                latest_id = (
                    connection.scalar(
                        select(baseline_version.c.id)
                        .where(
                            baseline_version.c.workspace_id == workspace,
                            baseline_version.c.published_at.is_not(None),
                        )
                        .order_by(baseline_version.c.version_number.desc())
                        .limit(1)
                    )
                    or None
                )
                if command.based_on_id != latest_id:
                    raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
                before = None
                identifier, revision = uuid4(), 1
                version = (
                    connection.scalar(
                        select(func.max(baseline_version.c.version_number)).where(
                            baseline_version.c.workspace_id == workspace
                        )
                    )
                    or 0
                ) + 1
            values = {
                **payload,
                "monthly_budget_amount": command.content.monthly_budget_amount,
                "content_hash": digest,
                "edit_revision": revision,
            }
            if row:
                statement = (
                    update(baseline_version)
                    .where(
                        baseline_version.c.id == identifier,
                        baseline_version.c.workspace_id == workspace,
                    )
                    .values(**values)
                )
            else:
                statement = baseline_version.insert().values(
                    **values,
                    id=identifier,
                    workspace_id=workspace,
                    version_number=version,
                    based_on_id=command.based_on_id,
                    schema_version="baseline-1",
                    created_by=principal.actor.key,
                    created_at=at,
                )
            saved = connection.execute(statement.returning(baseline_version)).mappings().one()
            evidence = BaselineDraftEvidence(
                based_on_id=command.based_on_id,
                baseline_id=identifier,
                version_number=version,
                edit_revision=revision,
                before=before,
                after=command.content,
            ).model_dump(mode="json")
            # Editable recipes need immutable before/after evidence in the same commit as the save.
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    operation_id=None,
                    administrator_id=None,
                    intent_revision=None,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="baseline_draft_saved",
                    at=at,
                    contract_version="baseline-draft-1",
                    data=evidence,
                    data_hash=canonical_hash(evidence),
                )
            )
            return draft_view(saved)

    # Publish row, future-admission default and audit atomically; no provider or assignment effect.
    def publish(self, principal, command):
        command = PublishBaseline.model_validate(command)
        with self.store._write(principal) as (connection, workspace, at):
            self.store._workspace(connection, workspace, lock=True)
            if self.qualifier is None:
                raise PublicationUnavailable()
            row = (
                connection.execute(
                    select(baseline_version).where(
                        baseline_version.c.workspace_id == workspace,
                        baseline_version.c.id == command.baseline_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
            existing = draft_view(row)
            if existing.published_at is not None:
                if existing.edit_revision == command.expected_revision + 1:
                    return existing
                raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
            if existing.edit_revision != command.expected_revision:
                raise OrganizationConflict("BASELINE_DRAFT_CHANGED")
            SaveBaselineDraft(content=existing.content)
            qualification = self.qualifier.qualify(existing.content)
            updated = (
                connection.execute(
                    update(baseline_version)
                    .where(
                        baseline_version.c.workspace_id == workspace,
                        baseline_version.c.id == existing.id,
                        baseline_version.c.edit_revision == command.expected_revision,
                    )
                    .values(
                        published_at=at,
                        published_by=principal.actor.key,
                        published_by_name=principal.actor.display_name or "Administrator",
                        publication_mode="simulated",
                        edit_revision=command.expected_revision + 1,
                    )
                    .returning(baseline_version)
                )
                .mappings()
                .one()
            )
            version = draft_view(updated)
            connection.execute(
                update(org_workspace)
                .where(org_workspace.c.id == workspace)
                .values(
                    registry_revision=org_workspace.c.registry_revision + 1,
                )
            )
            evidence = BaselinePublicationEvidence(
                default_for_new=True, qualification_version=qualification, baseline=version
            ).model_dump(mode="json")
            connection.execute(
                audit_event.insert().values(
                    id=uuid4(),
                    workspace_id=workspace,
                    operation_id=None,
                    administrator_id=None,
                    intent_revision=None,
                    actor=principal.actor.key,
                    actor_subject=principal.actor.key,
                    actor_snapshot=principal.actor.model_dump(mode="json"),
                    kind="baseline_published",
                    at=at,
                    contract_version="baseline-publication-1",
                    data=evidence,
                    data_hash=canonical_hash(evidence),
                )
            )
            return version


# Load exactly one scoped immutable recipe; current selection is never used to resolve a frozen pin.
def published_baseline(connection, workspace, identifier):
    row = (
        connection.execute(
            select(baseline_version).where(
                baseline_version.c.workspace_id == workspace,
                baseline_version.c.id == identifier,
                baseline_version.c.published_at.is_not(None),
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise OrganizationConflict("PUBLISHED_BASELINE_REQUIRED")
    version = draft_view(row)
    BaselinePublicationEvidence(
        qualification_version="baseline-structure-simulated-1", baseline=version
    )
    return version


# The newest published version is always the default; historical selection metadata is ignored.
def current_baseline(connection, workspace):
    row = (
        connection.execute(
            select(baseline_version)
            .where(
                baseline_version.c.workspace_id == workspace,
                baseline_version.c.published_at.is_not(None),
            )
            .order_by(baseline_version.c.version_number.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    version = draft_view(row)
    BaselinePublicationEvidence(
        qualification_version="baseline-structure-simulated-1", baseline=version
    )
    return version
