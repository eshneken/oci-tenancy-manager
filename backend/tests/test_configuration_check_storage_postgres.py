"""Real generated observation ordering and append-only worker/API privilege boundaries."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from psycopg import sql
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from test_configuration_updates_postgres import children
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.configuration.drift import ConfigurationChecks
from otm.configuration.drift_contracts import ConfigurationCheckRequest
from otm.configuration.drift_worker import ConfigurationCheckWorker
from otm.operations.contracts import canonical_hash
from otm.providers.configuration_simulator import SimulatedConfigurationFacade
from otm.storage.tables import audit_event, configuration_check

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# The same read flow creates real evidence before SQL-level negative tests inspect its protections.
def test_configuration_check_generated_sequence_and_immutability(workflow_case):
    c = workflow_case
    child = children(c, 1)[0]
    service = ConfigurationChecks(
        c.store, policy=c.loader().policy, policy_loader=c.loader, enqueuer=Mock()
    )
    worker = ConfigurationCheckWorker(
        c.engine,
        c.policy.workspace_id,
        c.clock,
        c.loader,
        SimulatedConfigurationFacade(c.loader().policy),
    )
    receipt = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=child)
    )
    worker.run(receipt.operation_id)
    with c.engine.connect() as connection:
        original = dict(
            connection.execute(
                select(configuration_check).where(
                    configuration_check.c.workspace_id == c.policy.workspace_id,
                    configuration_check.c.operation_id == receipt.operation_id,
                )
            )
            .mappings()
            .one()
        )
    assert original["acquisition_sequence"] > 0
    for statement in (
        update(configuration_check)
        .where(configuration_check.c.id == original["id"])
        .values(state="unavailable"),
        configuration_check.delete().where(configuration_check.c.id == original["id"]),
        text("TRUNCATE public.otm_configuration_check"),
    ):
        with pytest.raises(DBAPIError), c.engine.begin() as connection:
            connection.execute(statement)
    # An independent second operation supplies a valid scoped FK for an explicit-column insert.
    second = service.start(
        c.principal, ConfigurationCheckRequest(client_request_key=uuid4(), tenancy_id=child)
    )
    role = "otm_check_writer_" + uuid4().hex[:12]
    with c.engine.connect() as connection:
        transaction = connection.begin()
        try:
            event = dict(
                connection.execute(
                    select(audit_event).where(audit_event.c.id == original["evidence_event_id"])
                )
                .mappings()
                .one()
            )
            check_id, event_id = uuid4(), uuid4()
            data = {**event["data"], "check_id": str(check_id)}
            connection.execute(
                audit_event.insert().values(
                    **{
                        **event,
                        "id": event_id,
                        "operation_id": second.operation_id,
                        "data": data,
                        "data_hash": canonical_hash(data),
                    }
                )
            )
            driver = connection.connection.driver_connection
            driver.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            driver.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
            names = [
                column.name
                for column in configuration_check.columns
                if column.name != "acquisition_sequence"
            ]
            driver.execute(
                sql.SQL("GRANT SELECT,INSERT ({}) ON public.otm_configuration_check TO {}").format(
                    sql.SQL(",").join(map(sql.Identifier, names)), sql.Identifier(role)
                )
            )
            driver.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            assert not connection.scalar(
                text(
                    "SELECT has_column_privilege(current_user,'public.otm_configuration_check',"
                    "'acquisition_sequence','INSERT')"
                )
            )
            values = {key: value for key, value in original.items() if key in names}
            values.update(id=check_id, operation_id=second.operation_id, evidence_event_id=event_id)
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(
                    configuration_check.insert().values(
                        **values, acquisition_sequence=original["acquisition_sequence"] + 100
                    )
                )
            generated = connection.execute(
                configuration_check.insert()
                .values(**values)
                .returning(configuration_check.c.acquisition_sequence)
            ).scalar_one()
            assert generated > original["acquisition_sequence"]
            for statement in (
                update(configuration_check)
                .where(configuration_check.c.id == check_id)
                .values(state="unavailable"),
                configuration_check.delete().where(configuration_check.c.id == check_id),
            ):
                with pytest.raises(DBAPIError), connection.begin_nested():
                    connection.execute(statement)
        finally:
            # Role/grants and synthetic insertion are test-only and roll back together.
            transaction.rollback()
    with c.engine.connect() as connection:
        assert (
            dict(
                connection.execute(
                    select(configuration_check).where(configuration_check.c.id == original["id"])
                )
                .mappings()
                .one()
            )
            == original
        )
