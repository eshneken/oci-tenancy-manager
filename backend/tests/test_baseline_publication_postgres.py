"""Real local publication, immutable versions, parent fencing and same-commit audit evidence."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_baseline_authoring import content
from test_organization_storage_postgres import factors, login_case, organization_case

from otm.audit.contracts import AuditQuery
from otm.configuration.contracts import BaselineQuery, PublishBaseline, SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, baseline_version, org_workspace

pytestmark = pytest.mark.postgres
__all__ = ["organization_case", "factors", "login_case"]


# Publication creates a frozen snapshot; only a fresh latest-derived draft accepts subsequent edits.
def test_publish_history_and_derived_versions(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    first = service.save(c.principal, SaveBaselineDraft(content=content()))
    published = service.publish(
        c.principal, PublishBaseline(baseline_id=first.id, expected_revision=1)
    )
    assert published.edit_revision == 2 and published.publication_mode == "simulated"
    assert published.published_by_name == c.principal.actor.display_name
    assert (
        service.publish(c.principal, PublishBaseline(baseline_id=first.id, expected_revision=1))
        == published
    )
    directory = service.read(c.principal)
    assert (
        directory.draft is None
        and directory.latest == published
        and directory.items == (published,)
    )
    second = service.save(
        c.principal,
        SaveBaselineDraft(content=content(monthly_budget_amount="500"), based_on_id=published.id),
    )
    assert second.version_number == 2 and second.based_on_id == published.id
    pub2 = service.publish(c.principal, PublishBaseline(baseline_id=second.id, expected_revision=1))
    old = service.read(c.principal, BaselineQuery(page=99, baseline_id=published.id))
    assert old.selected == published and old.latest == pub2 and old.page == 1 and old.total == 2
    assert old.selected.content.monthly_budget_amount != pub2.content.monthly_budget_amount
    with pytest.raises(OrganizationConflict):
        service.save(c.principal, SaveBaselineDraft(content=content(), based_on_id=published.id))
    with pytest.raises(OrganizationConflict):
        service.save(
            c.principal,
            SaveBaselineDraft(baseline_id=published.id, expected_revision=2, content=content()),
        )
    events = SqlAuditDirectory(c.engine).directory(
        c.policy.workspace_id, AuditQuery(category="administration")
    )
    pub_events = [e for e in events.items if e.kind == "baseline_published"]
    assert len(pub_events) == 2 and all("simulated validation" in e.summary for e in pub_events)
    assert {e.baseline_id for e in pub_events} == {published.id, pub2.id}


# Concurrent retries publish one version/event, never a second publication or an implicit new draft.
def test_publication_concurrent_replay(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = service.save(c.principal, SaveBaselineDraft(content=content()))
    command = PublishBaseline(baseline_id=draft.id, expected_revision=draft.edit_revision)
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda _: service.publish(c.principal, command), range(4)))
    assert all(v == versions[0] for v in versions)
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.workspace_id == c.policy.workspace_id,
                    audit_event.c.kind == "baseline_published",
                )
            )
            == 1
        )


# Audit failure rolls back publication metadata/revision and preserves the editable draft.
def test_publication_audit_rollback(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = service.save(c.principal, SaveBaselineDraft(content=content()))
    execute = Connection.execute

    # Let real locking and row mutation run, then fail only the new immutable audit publication.
    def reject_audit(connection, statement, *args, **kwargs):
        if getattr(statement, "table", None) is audit_event and getattr(
            statement, "is_insert", False
        ):
            raise RuntimeError("controlled publication audit failure")
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", reject_audit), pytest.raises(RuntimeError):
        service.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    assert service.read(c.principal).draft == draft
    assert service.read(c.principal).total == 0


# Profile rejection has no effects; published recipes reject SQL owner DML edits.
def test_rejected_qualification_and_published_guards(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = service.save(c.principal, SaveBaselineDraft(content=content(budget_currency="EUR")))
    with pytest.raises(ValueError):
        service.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    assert service.read(c.principal).draft == draft
    fixed = service.save(
        c.principal, SaveBaselineDraft(baseline_id=draft.id, expected_revision=1, content=content())
    )
    version = service.publish(
        c.principal, PublishBaseline(baseline_id=fixed.id, expected_revision=2)
    )
    with c.engine.begin() as connection:
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(
                update(baseline_version)
                .where(baseline_version.c.id == version.id)
                .values(published_by_name="changed", edit_revision=4)
            )
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(baseline_version.delete().where(baseline_version.c.id == version.id))
    assert service.read(c.principal).latest == version


# Actual foreign rows remain invisible and cannot be published, parented or substituted by UUID.
def test_publication_foreign_scope(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = service.save(c.principal, SaveBaselineDraft(content=content()))
    own = service.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    foreign = "foreign-" + uuid4().hex
    foreign_id = uuid4()
    with c.engine.begin() as connection:
        workspace = dict(
            connection.execute(
                select(org_workspace).where(org_workspace.c.id == c.policy.workspace_id)
            )
            .mappings()
            .one()
        )
        workspace.update(
            id=foreign, applied_version_id=None, proposed_version_id=None, current_baseline_id=None
        )
        connection.execute(org_workspace.insert().values(**workspace))
        row = dict(
            connection.execute(select(baseline_version).where(baseline_version.c.id == own.id))
            .mappings()
            .one()
        )
        row.update(id=foreign_id, workspace_id=foreign)
        connection.execute(baseline_version.insert().values(**row))
    assert service.read(c.principal, BaselineQuery(baseline_id=foreign_id)).selected is None
    with pytest.raises(OrganizationConflict):
        service.publish(c.principal, PublishBaseline(baseline_id=foreign_id, expected_revision=1))
    with pytest.raises(OrganizationConflict):
        service.save(c.principal, SaveBaselineDraft(content=content(), based_on_id=foreign_id))
    assert service.read(c.principal).total == 1


# Narrow runtime-style SQL grants reject null/unsupported publication metadata.
def test_restricted_publication_grants_require_complete_mode(organization_case):
    from psycopg import sql

    c = organization_case
    service = BaselineAuthoring(c.store, SimulatedBaselineQualifier())
    draft = service.save(c.principal, SaveBaselineDraft(content=content()))
    role = "otm_publication_" + uuid4().hex[:12]
    with c.engine.connect() as connection:
        transaction = connection.begin()
        try:
            driver = connection.connection.driver_connection
            driver.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            driver.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
            driver.execute(
                sql.SQL(
                    "GRANT SELECT,UPDATE(published_by,published_at,published_by_name,"
                    "publication_mode,"
                    "edit_revision) ON public.otm_baseline_version TO {}"
                ).format(sql.Identifier(role))
            )
            driver.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            for mode, name in ((None, "Publisher"), ("oci", "Publisher"), ("simulated", None)):
                with pytest.raises(DBAPIError), connection.begin_nested():
                    connection.execute(
                        update(baseline_version)
                        .where(
                            baseline_version.c.workspace_id == c.policy.workspace_id,
                            baseline_version.c.id == draft.id,
                        )
                        .values(
                            published_by=c.principal.actor.key,
                            published_at=c.clock(),
                            published_by_name=name,
                            publication_mode=mode,
                            edit_revision=2,
                        )
                    )
        finally:
            # Roll back this test role, grants and attempted effects together.
            transaction.rollback()
    assert service.read(c.principal).draft == draft
