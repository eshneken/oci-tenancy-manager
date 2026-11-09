"""Real organization publication, source replay, immutable evidence and authority."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from test_local_auth import factors
from test_local_auth_postgres import command, login_case
from test_organization_fixtures import envelope, example_config, example_records

from otm.audit.contracts import AuditQuery
from otm.auth.service import SessionFailure
from otm.organization.contracts import Intake
from otm.storage.audit_directory import SqlAuditDirectory
from otm.storage.organization import OrganizationConflict, SqlOrganizationStore
from otm.storage.tables import (
    audit_event,
    org_feed,
    org_member,
    org_person,
    org_version,
    org_workspace,
)

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case"]


# Authorize through actual local MFA/grants while the feed population intentionally differs from
# workspace.
@pytest.fixture
def organization_case(login_case):
    c = login_case
    issued = c.service.sign_in(command(c))
    principal = c.sessions.authenticate(issued.handle.get_secret_value())
    store = SqlOrganizationStore(c.engine, c.sessions, c.clock)
    config = example_config()
    store.configure_initial(principal, config)
    return SimpleNamespace(**vars(c), principal=principal, store=store, config=config)


# Build explicit deliveries using a synthetic qualified source clock, not an implicit upload
# timestamp.
def intake(c, key="first", rows=None, *, captured_at=None):
    return Intake(
        envelope=envelope(key, c.clock() if captured_at is None else captured_at),
        records=example_records() if rows is None else rows,
    )


# Read only aggregate counts in this test's unique workspace, never truncate immutable histories.
def counts(c):
    with c.engine.connect() as connection:
        return tuple(
            connection.scalar(
                select(func.count())
                .select_from(table)
                .where(
                    (table.c.id == c.policy.workspace_id)
                    if table is org_workspace
                    else (table.c.workspace_id == c.policy.workspace_id)
                )
            )
            for table in [org_workspace, org_feed, org_person, org_version, org_member, audit_event]
        )


# Both heads use stable scoped people; automatic metadata has a distinct service actor in shared
# audit.
def test_published_heads_source_scope_and_readable_views(organization_case):
    c = organization_case
    result = c.store.ingest(c.principal, intake(c))
    assert result.state == "published"
    applied = c.store.head(c.principal)
    proposed = c.store.head(c.principal, proposed=True)
    assert applied.population_id == c.config.policy.population_id != c.policy.workspace_id
    assert applied.id != proposed.id
    assert {p.email: p.id for p in applied.people} == {p.email: p.id for p in proposed.people}
    with c.engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT * FROM public.current_organization "
                    "WHERE workspace_id=:scope AND email=:email"
                ),
                dict(scope=c.policy.workspace_id, email="engineer@example.test"),
            )
            .mappings()
            .one()
        )
        assert (
            row["manager_name"] == "Leader One" and row["accountable_leader_name"] == "Leader One"
        )
        assert row["lob_name"] == "LOB One" and row["designee_names"] == ["Delegate"]
    history = SqlAuditDirectory(c.engine).directory(
        c.policy.workspace_id, AuditQuery(category="organization")
    )
    assert {e.kind for e in history.items} == {
        "organization_configured",
        "organization_feed_received",
        "organization_published",
    }
    assert (
        next(e for e in history.items if e.kind == "organization_published").actor_name
        == "Organization synchronization"
    )
    assert (
        next(e for e in history.items if e.kind == "organization_feed_received").actor_name
        == c.principal.actor.display_name
    )


# New acquisitions with identical employee data remain new; known-key transport retries are
# exact replays.
def test_delivery_replay_and_changed_key_are_distinct(organization_case):
    c = organization_case
    source = intake(c)
    first = c.store.ingest(c.principal, source)
    before = counts(c)
    replay = c.store.ingest(c.principal, source)
    assert replay.state == "duplicate" and replay.revision_id == first.revision_id
    assert counts(c) == before
    altered = source.model_copy(update={"records": example_records()[:-1]})
    with pytest.raises(OrganizationConflict, match="DELIVERY_CHANGED"):
        c.store.ingest(c.principal, altered)
    assert counts(c) == before
    c.clock.return_value += timedelta(seconds=10)
    again = c.store.ingest(c.principal, intake(c, "new-acquisition"))
    assert again.state == "published" and again.revision_id != first.revision_id
    assert counts(c)[2] == len(example_records())


# Staging stays separate from applied data and compares both current heads at explicit publication.
def test_staged_proposal_cas_and_idempotent_apply(organization_case):
    c = organization_case
    first = c.store.ingest(c.principal, intake(c), stage_only=True)
    assert c.store.head(c.principal) is None
    assert c.store.head(c.principal, proposed=True).id == first.proposed_version_id
    c.clock.return_value += timedelta(seconds=10)
    second = c.store.ingest(c.principal, intake(c, "newer"), stage_only=True)
    with pytest.raises(OrganizationConflict, match="PUBLICATION_CHANGED"):
        c.store.apply(c.principal, first.proposed_version_id)
    result = c.store.apply(c.principal, second.proposed_version_id)
    assert result.state == "published"
    before = counts(c)
    assert c.store.apply(c.principal, second.proposed_version_id).state == "duplicate"
    assert counts(c) == before


# Old staged captures cannot replace a newer proposal even while no applied version exists.
def test_source_order_rejection_preserves_heads(organization_case):
    c = organization_case
    first = c.store.ingest(c.principal, intake(c), stage_only=True)
    before = c.store.head(c.principal, proposed=True)
    stale = c.store.ingest(
        c.principal, intake(c, "stale", captured_at=c.clock() - timedelta(seconds=1))
    )
    assert stale.state == "superseded" and any(
        d.code == "SUPERSEDED_CAPTURE" for d in stale.diagnostics
    )
    assert c.store.head(c.principal, proposed=True).id == before.id == first.proposed_version_id
    assert c.store.head(c.principal) is None


# Valid names/managers update automatically; qualified absence remains a review, never a deletion.
def test_metadata_reorg_absence_and_partial_coverage(organization_case):
    c = organization_case
    c.store.ingest(c.principal, intake(c))
    original = {p.email: p.id for p in c.store.head(c.principal).people}
    c.clock.return_value += timedelta(seconds=10)
    rows = tuple(
        r.model_copy(update={"full_name": "Renamed Engineer", "manager_email": "two@example.test"})
        if r.email == "engineer@example.test"
        else r
        for r in example_records()
    )
    c.store.ingest(c.principal, intake(c, "reorg", rows))
    engineer = next(
        p for p in c.store.head(c.principal).people if p.email == "engineer@example.test"
    )
    assert (
        engineer.full_name == "Renamed Engineer"
        and engineer.lob_id == "two"
        and engineer.id == original[engineer.email]
    )
    c.clock.return_value += timedelta(seconds=10)
    c.store.ingest(c.principal, intake(c, "absence", rows[:-1]))
    assert next(
        p for p in c.store.head(c.principal).people if p.email == engineer.email
    ).absence_review
    c.clock.return_value += timedelta(seconds=10)
    source = intake(c, "partial", rows[:-1]).model_copy(
        update={"envelope": envelope("partial", c.clock(), "partial")}
    )
    c.store.ingest(c.principal, source)
    assert next(
        p for p in c.store.head(c.principal).people if p.email == engineer.email
    ).absence_review


# Fatal graphs retain a rejected delivery and audit but never expose an invalid proposed/applied
# tree.
def test_rejected_graph_never_publishes(organization_case):
    c = organization_case
    rows = tuple(
        r.model_copy(update={"manager_email": r.email}) if r.email == "engineer@example.test" else r
        for r in example_records()
    )
    result = c.store.ingest(c.principal, intake(c, rows=rows))
    assert result.state == "rejected" and any(d.fatal for d in result.diagnostics)
    assert c.store.head(c.principal) is None and c.store.head(c.principal, proposed=True) is None
    assert counts(c)[2:5] == (0, 0, 0)


# Roll back source, identities, both versions and audit together when publication cannot commit.
def test_atomic_rollback_after_snapshot_write(organization_case):
    c = organization_case
    before = counts(c)
    original = c.store._audit

    # Fail at the last publication write after real version/member persistence has executed.
    def fail_publication(*args, **kwargs):
        if args[3] == "organization_published":
            raise RuntimeError("synthetic audit failure")
        return original(*args, **kwargs)

    with patch.object(c.store, "_audit", side_effect=fail_publication), pytest.raises(RuntimeError):
        c.store.ingest(c.principal, intake(c))
    assert counts(c) == before
    assert c.store.head(c.principal) is None


# Neither sealed rows, original identity anchors nor destructive truncation can rewrite evidence.
@pytest.mark.parametrize("table", [org_person, org_feed, org_version, org_member, org_workspace])
def test_organization_history_guards(organization_case, table):
    c = organization_case
    c.store.ingest(c.principal, intake(c))
    with pytest.raises(DBAPIError), c.engine.begin() as connection:
        connection.execute(
            table.delete().where(table.c.id == c.policy.workspace_id)
            if table is org_workspace
            else table.delete().where(table.c.workspace_id == c.policy.workspace_id)
        )
    with pytest.raises(DBAPIError), c.engine.begin() as connection:
        connection.exec_driver_sql("TRUNCATE TABLE public." + table.name + " CASCADE")
    if table is org_member:
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            connection.execute(
                update(table)
                .where(table.c.workspace_id == c.policy.workspace_id)
                .values(full_name="changed")
            )


# Current sessions/grants are required and configured source population cannot select an auth
# workspace.
def test_scope_and_expired_session_fail_closed(organization_case):
    c = organization_case
    with pytest.raises(SessionFailure):
        c.store.head(object())
    bad = intake(c).model_copy(
        update={"envelope": envelope().model_copy(update={"population_id": c.policy.workspace_id})}
    )
    with pytest.raises(OrganizationConflict, match="SOURCE_SCOPE"):
        c.store.ingest(c.principal, bad)
    assert counts(c)[1] == 0
    c.clock.return_value = c.principal.session.expires_at
    with pytest.raises(SessionFailure):
        c.store.ingest(c.principal, intake(c))


# Concurrent complete deliveries serialize without mixed members or losing the newest qualified
# capture.
def test_concurrent_feed_publications(organization_case):
    c = organization_case
    base = c.clock()
    c.clock.return_value += timedelta(seconds=20)
    first = intake(c, "older", captured_at=base)
    second = intake(c, "newer", captured_at=base + timedelta(seconds=10))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda source: c.store.ingest(c.principal, source), [first, second])
        )
    assert all(r.state in {"published", "superseded"} for r in results)
    assert c.store.head(c.principal).source_captured_at == base + timedelta(seconds=10)
    assert len(c.store.head(c.principal).people) == len(example_records())


# Accepted incomplete source diagnostics survive staging/publication for later intake visibility.
def test_nonfatal_diagnostics_are_retained(organization_case):
    c = organization_case
    rows = tuple(r for r in example_records() if r.email != "one@example.test")
    result = c.store.ingest(c.principal, intake(c, rows=rows))
    assert result.state == "published"
    assert any(d.code == "MANAGER_PROFILE_MISSING" for d in result.diagnostics)
    assert not c.store.head(c.principal).absence_eligible
    assert c.store.ingest(c.principal, intake(c, rows=rows)).diagnostics == result.diagnostics


# Direct inserts cannot skip sealing, append members after seal, or publish an incomplete graph.
def test_presealed_and_incomplete_version_inserts_fail(organization_case):
    c = organization_case
    receipt = c.store.ingest(c.principal, intake(c))
    with c.engine.connect() as connection:
        version = dict(
            connection.execute(select(org_version).where(org_version.c.id == receipt.revision_id))
            .mappings()
            .one()
        )
        member = dict(
            connection.execute(
                select(org_member).where(org_member.c.version_id == receipt.revision_id)
            )
            .mappings()
            .first()
        )
        feed = dict(
            connection.execute(select(org_feed).where(org_feed.c.id == receipt.snapshot_id))
            .mappings()
            .one()
        )
    with pytest.raises(DBAPIError, match="must begin unsealed"), c.engine.begin() as connection:
        connection.execute(org_version.insert().values(**{**version, "id": uuid4()}))
    with pytest.raises(DBAPIError, match="sealed"), c.engine.begin() as connection:
        connection.execute(org_member.insert().values(**member))
    identifier = uuid4()
    with pytest.raises(DBAPIError, match="member count"), c.engine.begin() as connection:
        connection.execute(
            org_version.insert().values(**{**version, "id": identifier, "sealed": False})
        )
        connection.execute(
            update(org_version).where(org_version.c.id == identifier).values(sealed=True)
        )
    with pytest.raises(DBAPIError, match="must begin received"), c.engine.begin() as connection:
        connection.execute(
            org_feed.insert().values(**{**feed, "id": uuid4(), "external_id": "bad-terminal"})
        )


# Database scope and head-kind checks do not depend on the repository being the only caller.
def test_foreign_workspace_and_wrong_kind_heads_fail(organization_case):
    c = organization_case
    receipt = c.store.ingest(c.principal, intake(c))
    foreign = "foreign-" + uuid4().hex
    with c.engine.begin() as connection:
        connection.execute(
            org_workspace.insert().values(
                id=foreign,
                configuration_id=c.config.id,
                configuration=c.config.model_dump(mode="json"),
            )
        )
    with pytest.raises(DBAPIError), c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == foreign)
            .values(applied_version_id=receipt.revision_id)
        )
    with pytest.raises(DBAPIError), c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(proposed_version_id=receipt.revision_id)
        )
    with c.engine.connect() as connection:
        assert (
            c.store._revision(connection, c.policy.workspace_id, receipt.revision_id).id
            == receipt.revision_id
        )
        with pytest.raises(OrganizationConflict):
            c.store._revision(connection, foreign, receipt.revision_id)


# A changed configuration revision cannot apply a proposal pinned to old settings.
def test_configuration_advance_invalidates_proposal(organization_case):
    c = organization_case
    receipt = c.store.ingest(c.principal, intake(c), stage_only=True)
    changed = c.config.model_copy(update={"id": uuid4()})
    with c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(configuration_id=changed.id, configuration=changed.model_dump(mode="json"))
        )
    with pytest.raises(OrganizationConflict, match="PUBLICATION_CHANGED"):
        c.store.apply(c.principal, receipt.proposed_version_id)
    assert c.store.head(c.principal) is None


# An override cannot turn fatal source corruption into an automatically published organization.
def test_raw_graph_cannot_be_rescued_by_override(login_case):
    from otm.organization.contracts import PersonOverride

    c = login_case
    issued = c.service.sign_in(command(c))
    principal = c.sessions.authenticate(issued.handle.get_secret_value())
    store = SqlOrganizationStore(c.engine, c.sessions, c.clock)
    config = example_config().model_copy(
        update={
            "overrides": (
                PersonOverride(
                    email="engineer@example.test",
                    values={"manager_email": "one@example.test"},
                    reason="verified correction",
                    actor="verified admin",
                ),
            )
        }
    )
    store.configure_initial(principal, config)
    rows = tuple(
        r.model_copy(update={"manager_email": r.email}) if r.email == "engineer@example.test" else r
        for r in example_records()
    )
    result = store.ingest(principal, Intake(envelope=envelope(capture=c.clock()), records=rows))
    assert result.state == "rejected" and store.head(principal) is None


# A reviewed email merge preserves the old person UUID in both heads and immutable original anchors.
def test_persisted_identity_merge_keeps_survivor(organization_case):
    from otm.organization.contracts import IdentityMerge, Record

    c = organization_case
    c.store.ingest(c.principal, intake(c))
    old = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    renamed = Record(
        source_record_id="renamed",
        full_name="Renamed Engineer",
        email="renamed@example.test",
        manager_email="one@example.test",
    )
    rows = (*example_records()[:-1], renamed)
    c.clock.return_value += timedelta(seconds=10)
    c.store.ingest(c.principal, intake(c, "new-email", rows))
    provisional = next(p for p in c.store.head(c.principal).people if p.email == renamed.email)
    config = c.config.model_copy(
        update={
            "id": uuid4(),
            "identity_merges": (
                IdentityMerge(
                    old_email=old.email,
                    new_email=renamed.email,
                    person_id=old.id,
                    retired_person_id=provisional.id,
                    actor="verified admin",
                    reason="identity verified",
                ),
            ),
        }
    )
    # Simulate a future authorized config update; a feed cannot supply trusted settings.
    with c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(configuration_id=config.id, configuration=config.model_dump(mode="json"))
        )
    c.clock.return_value += timedelta(seconds=10)
    c.store.ingest(c.principal, intake(c, "after-merge", rows))
    for proposed in [False, True]:
        survivor = next(
            p
            for p in c.store.head(c.principal, proposed=proposed).people
            if p.email == renamed.email
        )
        assert survivor.id == old.id and survivor.full_name == renamed.full_name
        assert not survivor.absence_review
    with c.engine.connect() as connection:
        anchor = connection.scalar(select(org_person.c.email).where(org_person.c.id == old.id))
        assert anchor == old.email


# A merge cannot borrow a person UUID belonging to another authenticated workspace.
def test_merge_survivor_scope_rejected(organization_case):
    from otm.organization.contracts import IdentityMerge

    c = organization_case
    c.store.ingest(c.principal, intake(c))
    old = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    foreign = "merge-foreign-" + uuid4().hex
    foreign_person = uuid4()
    with c.engine.begin() as connection:
        connection.execute(
            org_workspace.insert().values(
                id=foreign,
                configuration_id=c.config.id,
                configuration=c.config.model_dump(mode="json"),
            )
        )
        connection.execute(
            org_person.insert().values(
                id=foreign_person, workspace_id=foreign, email="foreign@example.test"
            )
        )
    forged = c.config.model_copy(
        update={
            "id": uuid4(),
            "identity_merges": (
                IdentityMerge(
                    old_email=old.email,
                    new_email="renamed@example.test",
                    person_id=foreign_person,
                    retired_person_id=old.id,
                    actor="verified admin",
                    reason="synthetic scope test",
                ),
            ),
        }
    )
    with c.engine.begin() as connection:
        connection.execute(
            update(org_workspace)
            .where(org_workspace.c.id == c.policy.workspace_id)
            .values(configuration_id=forged.id, configuration=forged.model_dump(mode="json"))
        )
    before = counts(c)
    c.clock.return_value += timedelta(seconds=10)
    with pytest.raises(OrganizationConflict, match="MERGE_SCOPE"):
        rows = (
            *example_records()[:-1],
            example_records()[-1].model_copy(update={"email": "renamed@example.test"}),
        )
        c.store.ingest(c.principal, intake(c, "forged-merge", rows))
    assert counts(c) == before


# A disposable restricted SQL role can publish with column-scoped grants but cannot rewrite history.
def test_minimal_runtime_privileges(organization_case):
    from psycopg import sql
    from sqlalchemy import create_engine, event

    c = organization_case
    role_name = "org_runtime_" + uuid4().hex
    role_engine = create_engine(c.engine.url, hide_parameters=True)
    with c.engine.begin() as connection:
        driver = connection.connection.driver_connection
        driver.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role_name)))
        for statement in [
            "GRANT USAGE ON SCHEMA public TO {}",
            "GRANT SELECT ON public.otm_administrator,public.otm_admin_session,public.audit_event,"
            "public.org_workspace,public.org_person,public.org_feed,public.org_version,"
            "public.org_member TO {}",
            "GRANT UPDATE(id) ON public.otm_administrator,public.otm_admin_session TO {}",
            "GRANT INSERT ON public.audit_event,public.org_workspace,public.org_person,"
            "public.org_feed,public.org_version,public.org_member TO {}",
            "GRANT UPDATE(applied_version_id,proposed_version_id) ON public.org_workspace TO {}",
            "GRANT UPDATE(state,diagnostics,applied_version_id,proposed_version_id) "
            "ON public.org_feed TO {}",
            "GRANT UPDATE(sealed) ON public.org_version TO {}",
            "GRANT SELECT,INSERT ON public.org_recommendation TO {}",
            "GRANT UPDATE(status,resolved_at,resolution,last_seen_at,version_id,operation_id) "
            "ON public.org_recommendation TO {}",
            "GRANT UPDATE(directory_status,setup_required,setup_episode_id,"
            "removed_capture_at,pending_operation_id) ON public.org_person TO {}",
        ]:
            driver.execute(sql.SQL(statement).format(sql.Identifier(role_name)))

    # Only the owned test pool assumes this role; administrator authority remains real.
    @event.listens_for(role_engine, "connect")
    def select_runtime_role(connection, record):
        connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role_name)))
        connection.commit()

    try:
        with role_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == role_name
            assert (
                connection.scalar(
                    text("SELECT has_table_privilege(current_user, 'public.org_person', 'UPDATE')")
                )
                is False
            )
        restricted = SqlOrganizationStore(role_engine, c.sessions, c.clock)
        receipt = restricted.ingest(c.principal, intake(c))
        assert receipt.state == "published" and len(restricted.head(c.principal).people) == 5
        for statement in [
            "UPDATE public.org_person SET email='forged@example.test'",
            "DELETE FROM public.org_feed",
            "UPDATE public.org_version SET data='{}'::jsonb",
            "TRUNCATE public.org_member CASCADE",
        ]:
            with pytest.raises(DBAPIError), role_engine.begin() as connection:
                connection.exec_driver_sql(statement)
    finally:
        role_engine.dispose()
        with c.engine.begin() as connection:
            driver = connection.connection.driver_connection
            driver.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name)))
            driver.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name)))
