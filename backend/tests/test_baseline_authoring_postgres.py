"""Real draft persistence, contention, corruption guards and same-transaction authoring history."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from test_baseline_authoring import content
from test_organization_storage_postgres import factors, login_case, organization_case

from otm.audit.contracts import AuditQuery
from otm.auth.service import SessionFailure
from otm.configuration.contracts import SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, baseline_version

pytestmark = pytest.mark.postgres
__all__ = ["organization_case", "factors", "login_case"]


# Saving recipes never modifies source hierarchy or writes a tenancy/provider operation.
def test_save_draft_exact_values_history_and_noop(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store)
    assert service.read(c.principal).draft is None
    before = c.store.inspection(c.principal)
    command = SaveBaselineDraft(content=content())
    first = service.save(c.principal, command)
    assert first.version_number == first.edit_revision == 1
    assert service.save(c.principal, command) == first
    changed = service.save(
        c.principal,
        SaveBaselineDraft(
            baseline_id=first.id,
            expected_revision=1,
            content=content(monthly_budget_amount="500.0000"),
        ),
    )
    assert changed.edit_revision == 2 and changed.content.monthly_budget_amount == Decimal(
        "500.0000"
    )
    with pytest.raises(OrganizationConflict):
        service.save(
            c.principal,
            SaveBaselineDraft(
                baseline_id=first.id,
                expected_revision=1,
                content=content(monthly_budget_amount="600"),
            ),
        )
    assert c.store.inspection(c.principal) == before
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(baseline_version)
                .where(baseline_version.c.workspace_id == c.policy.workspace_id)
            )
            == 1
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.workspace_id == c.policy.workspace_id,
                    audit_event.c.kind == "baseline_draft_saved",
                )
            )
            == 2
        )
        stored = (
            connection.execute(select(baseline_version).where(baseline_version.c.id == first.id))
            .mappings()
            .one()
        )
        assert stored["published_at"] is None and stored["policy_statements"] == list(
            content().policy_statements
        )
    history = SqlAuditDirectory(c.engine).directory(
        c.policy.workspace_id, AuditQuery(category="administration")
    )
    # Frozen fixture time intentionally ties both events; UUID order is not revision order.
    events = [row for row in history.items if row.kind == "baseline_draft_saved"]
    assert {row.summary for row in events} == {
        "Saved baseline draft v1, revision 1",
        "Saved baseline draft v1, revision 2",
    }
    latest = next(row for row in events if "revision 2" in row.summary)
    assert latest.baseline_id == first.id
    assert any("500.0000" in line for line in latest.changes)


# Competing initial saves serialize into one recipe rather than allocating two editable versions.
def test_concurrent_initial_draft_saves(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store)
    command = SaveBaselineDraft(content=content())
    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = list(pool.map(lambda _: service.save(c.principal, command), range(4)))
    assert len({item.id for item in saved}) == 1
    with c.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.workspace_id == c.policy.workspace_id,
                    audit_event.c.kind == "baseline_draft_saved",
                )
            )
            == 1
        )


# The save must roll back if immutable audit publication fails, including a newly allocated recipe.
def test_draft_audit_failure_rolls_back(organization_case):
    c = organization_case
    from sqlalchemy.engine import Connection

    original = Connection.execute

    # Fail only the event insert; locking and draft SQL still exercise real database work.
    def reject(self, statement, *args, **kwargs):
        if getattr(statement, "table", None) is audit_event and getattr(
            statement, "is_insert", False
        ):
            raise RuntimeError("controlled audit failure")
        return original(self, statement, *args, **kwargs)

    with patch.object(Connection, "execute", reject), pytest.raises(RuntimeError):
        BaselineAuthoring(c.store).save(c.principal, SaveBaselineDraft(content=content()))
    assert BaselineAuthoring(c.store).read(c.principal).draft is None


# Direct database edits cannot change published values or skip editable revision guards.
def test_draft_database_guards_and_corruption(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store)
    saved = service.save(c.principal, SaveBaselineDraft(content=content()))
    with c.engine.begin() as connection:
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    update(baseline_version)
                    .where(baseline_version.c.id == saved.id)
                    .values(version_number=2, edit_revision=2)
                )
        connection.execute(
            update(baseline_version)
            .where(baseline_version.c.id == saved.id)
            .values(edit_revision=2, content_hash="0" * 64)
        )
    with pytest.raises(RuntimeError, match="INVALID_BASELINE_EVIDENCE"):
        service.read(c.principal)
    with c.engine.begin() as connection:
        connection.execute(
            update(baseline_version)
            .where(baseline_version.c.id == saved.id)
            .values(
                edit_revision=3,
                content_hash=saved.content_hash,
                published_at=c.clock(),
                published_by="owner-qualified-fixture",
                published_by_name="Fixture author",
                publication_mode="simulated",
            )
        )
        with pytest.raises(DBAPIError):
            with connection.begin_nested():
                connection.execute(
                    update(baseline_version)
                    .where(baseline_version.c.id == saved.id)
                    .values(edit_revision=4, monthly_budget_amount=Decimal("1"))
                )
    assert service.read(c.principal).draft is None


# Simulated current-authority denial rejects a retained principal even for an identical save.
def test_draft_requires_current_authority(organization_case):
    c = organization_case
    service = BaselineAuthoring(c.store)
    service.save(c.principal, SaveBaselineDraft(content=content()))
    c.sessions.require_admin = lambda *_: (_ for _ in ()).throw(
        SessionFailure(403, "ADMINISTRATOR_REQUIRED")
    )
    with pytest.raises(SessionFailure):
        service.save(c.principal, SaveBaselineDraft(content=content()))


# Previously stored fractional recipes remain readable/auditable until an explicit whole-value edit.
def test_legacy_fractional_budget_retains_hash_and_history(organization_case):
    from otm.operations.contracts import canonical_hash

    c = organization_case
    service = BaselineAuthoring(c.store)
    saved = service.save(c.principal, SaveBaselineDraft(content=content()))
    archived = content(monthly_budget_amount="250.5")
    # Owner-only fixture simulates a draft saved before whole-unit authoring was required.
    with c.engine.begin() as connection:
        connection.execute(
            update(baseline_version)
            .where(baseline_version.c.id == saved.id)
            .values(
                edit_revision=2,
                monthly_budget_amount=archived.monthly_budget_amount,
                content_hash=canonical_hash(archived.model_dump(mode="json")),
            )
        )
    before = service.read(c.principal).draft
    assert before.content.monthly_budget_amount == Decimal("250.5000")
    assert before.edit_revision == 2
    corrected = service.save(
        c.principal,
        SaveBaselineDraft(
            baseline_id=saved.id, expected_revision=2, content=content(monthly_budget_amount="251")
        ),
    )
    assert corrected.content.monthly_budget_amount == Decimal("251.0000")
    assert corrected.edit_revision == 3
    with c.engine.connect() as connection:
        recorded = (
            connection.execute(
                select(audit_event.c.data).where(
                    audit_event.c.workspace_id == c.policy.workspace_id,
                    audit_event.c.kind == "baseline_draft_saved",
                )
            )
            .scalars()
            .all()
        )
    change = next(event for event in recorded if event["edit_revision"] == 3)
    assert change["before"]["monthly_budget_amount"] == "250.5000"
    assert change["after"]["monthly_budget_amount"] == "251.0000"
