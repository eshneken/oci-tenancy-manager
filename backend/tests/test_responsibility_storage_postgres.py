"""Forward audit vocabulary and narrow responsibility-write authority in real PostgreSQL."""

from uuid import uuid4

import pytest
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_configuration_updates_postgres import children
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import workflow_case

from otm.storage.tables import audit_event

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# The forward kind requires an operation while the API grant cannot rewrite its initiating actor.
def test_responsibility_audit_kind_and_column_authority(workflow_case):
    c = workflow_case
    children(c, 1)
    with c.engine.connect() as connection:
        transaction = connection.begin()
        try:
            event = dict(
                connection.execute(
                    select(audit_event)
                    .where(
                        audit_event.c.workspace_id == c.policy.workspace_id,
                        audit_event.c.operation_id.is_not(None),
                    )
                    .limit(1)
                )
                .mappings()
                .one()
            )
            values = {
                **event,
                "id": uuid4(),
                "kind": "operation_responsibility_changed",
                "intent_revision": None,
                "administrator_id": None,
            }
            connection.execute(audit_event.insert().values(**values))
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(
                    audit_event.insert().values(**{**values, "id": uuid4(), "operation_id": None})
                )
            role = "otm_responsibility_" + uuid4().hex[:12]
            driver = connection.connection.driver_connection
            driver.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
            driver.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
            driver.execute(
                sql.SQL(
                    "GRANT SELECT, UPDATE(responsible_actor_subject,revision) "
                    "ON public.otm_operation TO {}"
                ).format(sql.Identifier(role))
            )
            driver.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
            for column in ("responsible_actor_subject", "revision"):
                assert connection.scalar(
                    text(
                        "SELECT has_column_privilege("
                        "current_user,'public.otm_operation',:c,'UPDATE')"
                    ),
                    {"c": column},
                )
            for column in (
                "initiating_actor_subject",
                "initiating_actor_snapshot",
                "current_intent_event_id",
                "client_request_key",
            ):
                assert not connection.scalar(
                    text(
                        "SELECT has_column_privilege("
                        "current_user,'public.otm_operation',:c,'UPDATE')"
                    ),
                    {"c": column},
                )
        finally:
            # All synthetic events and role privileges disappear with this isolated transaction.
            transaction.rollback()
