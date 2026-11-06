"""Real captured provenance, rollback, retirement and database guards for simulated connections."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, complete_setup, workflow_case

from otm.providers.lifecycle import LifecycleBlocked
from otm.storage.tables import managed_object_binding as bindings
from otm.storage.tables import user_presence_connection as connections
from otm.tenancies.contracts import OrganizationIntent
from otm.tenancies.views import TenancyQuery

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Query a single synthetic workspace; unrelated test workspaces are never fixture state.
def rows(c, table=connections):
    with c.engine.connect() as connection:
        return list(
            connection.execute(
                select(table).where(table.c.workspace_id == c.policy.workspace_id)
            ).mappings()
        )


# Both fresh entry paths commit one connection with three exact identities; no read fabricates it.
@pytest.mark.parametrize("kind", ["create_tenancy", "import_tenancy"])
def test_fresh_connection_and_replay(workflow_case, kind):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    extra = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimconnection"} if kind == "import_tenancy" else {}
    )
    _, receipt = action(c, person.id, kind, **extra)
    assert rows(c) == []
    complete_setup(c, receipt.operation_id)
    (current,) = rows(c)
    identities = {b["logical_key"]: b for b in rows(c, bindings)}
    assert current["automation_binding_id"] == identities["identity/user/automation"]["id"]
    assert current["domain_binding_id"] == identities["identity/domain"]["id"]
    assert (
        current["source_evidence_event_id"]
        == identities["identity/domain"]["source_evidence_event_id"]
    )
    assert current["revision"] == 1 and current["state"] == "active"
    c.worker.run(receipt.operation_id)
    c.workflow.required_users(c.principal, current["tenancy_id"])
    assert rows(c) == [current]


# A pre-marker v3 operation remains unbound across setup, reads and redelivery.
def test_legacy_has_no_connection_backfill(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")

    # Freeze an actual old admission shape rather than changing accepted evidence after admission.
    def legacy(**fields):
        return OrganizationIntent(**{**fields, "presence_connection_contract": None})

    with patch("otm.tenancies.workflows.OrganizationIntent", side_effect=legacy):
        _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id)
    assert len(rows(c, bindings)) == 3 and rows(c) == []
    c.worker.run(receipt.operation_id)
    assert rows(c) == []


# Connection failure rolls back the evidence/identity set and prevents temporary-account cleanup.
def test_capture_rollback_and_retry(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    execute = Connection.execute

    # Inject only this new insert; the real savepoint and all preceding identities still execute.
    def fail_insert(connection, statement, *args, **kwargs):
        if (
            getattr(statement, "is_insert", False)
            and getattr(statement, "table", None) is connections
        ):
            raise DBAPIError("private", {}, Exception(), False)
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", new=fail_insert):
        complete_setup(c, receipt.operation_id, expected_phase="blocked")
    assert rows(c) == [] and rows(c, bindings) == []
    view = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert next(s for s in view.checks if s.key == "retire_temporary").state != "verified"
    from otm.tenancies.onboarding_contracts import OnboardingCommand

    c.workflow.onboarding_action(
        c.principal,
        receipt.operation_id,
        OnboardingCommand(
            client_request_key=uuid4(),
            revision=view.revision,
            action="start_setup",
            confirm_cleanup=True,
        ),
    )
    c.worker.run(receipt.operation_id)
    assert c.workflow.onboarding(c.principal, receipt.operation_id).phase == "complete"
    assert len(rows(c)) == 1 and len(rows(c, bindings)) == 3


# Verified termination retires the connection; provider rejection leaves it active and unchanged.
@pytest.mark.parametrize("blocked", [False, True])
def test_connection_retirement(workflow_case, blocked):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id)
    (before,) = rows(c)
    child = c.workflow.tenancies(c.principal, TenancyQuery()).items[0]
    _, deleted = action(c, person.id, "delete_tenancy", tenancy_id=child.id)
    if blocked:
        with patch.object(c.provider, "apply", side_effect=LifecycleBlocked("TARGET_CHANGED")):
            c.worker.run(deleted.operation_id)
        assert rows(c) == [before]
    else:
        c.worker.run(deleted.operation_id)
        (after,) = rows(c)
        assert after["state"] == "retired" and after["retired_operation_id"] == deleted.operation_id
        assert all(
            after[k] == v
            for k, v in before.items()
            if k not in {"state", "retired_operation_id", "updated_at"}
        )


# Persisted references, provenance and lifecycle cannot be rewritten or bypassed by privileged SQL.
def test_database_guards(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    complete_setup(c, receipt.operation_id)
    (current,) = rows(c)
    # Each failed transaction rolls back independently while reusing one legitimate setup.
    for damage in (
        "signer",
        "domain",
        "source",
        "scope",
        "revision",
        "mode",
        "retirement",
        "delete",
        "truncate",
    ):
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            if damage == "delete":
                connection.execute(connections.delete().where(connections.c.id == current["id"]))
            elif damage == "truncate":
                connection.exec_driver_sql("TRUNCATE public.otm_user_presence_connection")
            else:
                key, value = {
                    "signer": ("automation_binding_id", uuid4()),
                    "domain": ("domain_binding_id", uuid4()),
                    "source": ("source_evidence_event_id", uuid4()),
                    "scope": ("tenancy_id", uuid4()),
                    "revision": ("revision", 2),
                    "mode": ("provider_mode", "oci"),
                    "retirement": ("state", "retired"),
                }[damage]
                connection.execute(
                    update(connections)
                    .where(connections.c.id == current["id"])
                    .values({key: value})
                )
        assert rows(c) == [current]


# Forge inserts during a valid pending capture, so unrelated lifecycle guards cannot mask failures.
def test_pending_capture_rejects_forged_insert(workflow_case):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    execute = Connection.execute
    attempts = []

    # The real guard rejects altered facts inside an isolated, rolled-back savepoint.
    def intercept(connection, statement, *args, **kwargs):
        if (
            getattr(statement, "is_insert", False)
            and getattr(statement, "table", None) is connections
        ):
            for damage in ("signer", "domain", "source"):
                values = statement.compile().params
                bad = {**values, "id": uuid4()}
                if damage == "signer":
                    bad["automation_binding_id"] = values["domain_binding_id"]
                elif damage == "domain":
                    bad["domain_binding_id"] = values["automation_binding_id"]
                else:
                    bad["source_evidence_event_id"] = uuid4()
                with pytest.raises(DBAPIError) as caught:
                    with connection.begin_nested():
                        execute(connection, connections.insert().values(**bad))
                assert (
                    caught.value.orig.diag.message_primary
                    == "PRESENCE_CONNECTION_SOURCE_UNVERIFIED"
                )
                attempts.append(damage)
        return execute(connection, statement, *args, **kwargs)

    with patch.object(Connection, "execute", new=intercept):
        complete_setup(c, receipt.operation_id)
    assert attempts == ["signer", "domain", "source"] and len(rows(c)) == 1


# A caller cannot opt a pre-marker accepted intent into connection selection after admission.
def test_database_rejects_unaccepted_marker(workflow_case):
    from otm.storage.user_presence_connections import capture_connection

    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")

    # Freeze genuinely old accepted bytes instead of rewriting immutable audit data.
    def legacy(**fields):
        return OrganizationIntent(**{**fields, "presence_connection_contract": None})

    with patch("otm.tenancies.workflows.OrganizationIntent", side_effect=legacy):
        _, receipt = action(c, person.id, "create_tenancy")
    rejected = []

    # An in-memory marker cannot replace the exact accepted operation evidence.
    def forged(connection, row, intent, event_id, at):
        try:
            return capture_connection(
                connection,
                row,
                intent.model_copy(
                    update={"presence_connection_contract": "simulated-user-presence-1"}
                ),
                event_id,
                at,
            )
        except ValueError:
            rejected.append(True)
            raise

    with patch("otm.storage.user_presence_connections.capture_connection", new=forged):
        complete_setup(c, receipt.operation_id, expected_phase="blocked")
    assert rejected == [True] and rows(c) == [] and rows(c, bindings) == []
