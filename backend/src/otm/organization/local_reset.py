"""Explicit operator-only cleanup for an owned laptop installation, never an HTTP capability."""

import json
from urllib.parse import urlsplit

from sqlalchemy import func, select, text

from otm.maintenance import maintenance_engine
from otm.storage.tables import metadata
from otm.storage.transaction import require_transaction

TABLES = (
    "otm_configuration_check",
    "otm_tenancy_configuration",
    "otm_configuration_plan",
    "otm_configuration_plan_target",
    "otm_baseline_version",
    "org_workspace",
    "org_person",
    "org_feed",
    "org_version",
    "org_member",
    "org_recommendation",
    "otm_tenancy",
    "otm_tenancy_membership",
)


# Require explicit local opt-in and verify Docker ownership/port before opening an owner connection.
def reset_test_organization(state, settings, *, confirmed, inspect, database_url):
    if (
        not confirmed
        or settings.local_server is None
        or not settings.local_server.organization_reset_enabled
        or settings.local_auth is None
        or urlsplit(settings.local_server.public_origin).hostname not in {"localhost", "127.0.0.1"}
    ):
        raise ValueError("LOCAL_ORGANIZATION_RESET_DISABLED")
    info = json.loads(inspect("otm-local-" + state.instance_id.hex[:12]))[0]
    ports = info["NetworkSettings"]["Ports"]["5432/tcp"]
    if (
        info["Config"]["Labels"].get("otm.local.instance") != str(state.instance_id)
        or not info["State"]["Running"]
        or len(ports) != 1
        or ports[0]["HostIp"] != "127.0.0.1"
        or int(ports[0]["HostPort"]) != state.database_port
    ):
        raise ValueError("LOCAL_CONTAINER_OWNERSHIP_MISMATCH")
    engine = maintenance_engine(database_url(state, owner=True), None)
    try:
        with engine.begin() as connection:
            return clear_organization(
                connection, settings.local_auth.workspace_id, settings.local_auth.issuer
            )
    finally:
        engine.dispose()


# Reset only the fixed organization/configuration local model in one transaction, preserving all
# other tables.
# Access-exclusive locks isolate concurrent imports. Trigger changes roll back with any failure;
# no CASCADE or session_replication_role bypass can erase newly introduced dependent resources.
def clear_organization(connection, workspace, issuer):
    require_transaction(connection)
    connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
    owned = connection.scalar(
        text(
            "SELECT current_database()='otm_local' AND current_user='otm_owner' "
            "AND pg_get_userbyid(datdba)=current_user FROM pg_database "
            "WHERE datname=current_database()"
        )
    )
    if not owned:
        raise ValueError("OWNED_LOCAL_DATABASE_REQUIRED")
    tables = set(
        connection.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND (left(tablename,4)='org_' OR left(tablename,11)='otm_tenancy' "
                "OR left(tablename,12)='otm_baseline' OR left(tablename,17)='otm_configuration' "
                ")"
            )
        )
    )
    if tables != set(TABLES):
        raise ValueError("ORGANIZATION_RESET_SCHEMA_REQUIRES_REVIEW")
    # These identifiers are source constants, never CLI, CSV, TOML or browser input.
    names = ",".join("public." + name for name in TABLES)
    connection.exec_driver_sql("LOCK TABLE " + names + " IN ACCESS EXCLUSIVE MODE")
    foreign = connection.scalar(
        text("SELECT EXISTS(SELECT 1 FROM public.org_workspace WHERE id<>:workspace)"),
        {"workspace": workspace},
    )
    authorized = connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM public.otm_administrator "
            "WHERE workspace_id=:workspace AND issuer=:issuer AND identity_kind='local_recovery')"
        ),
        {"workspace": workspace, "issuer": issuer},
    )
    if foreign or not authorized:
        raise ValueError("LOCAL_ORGANIZATION_SCOPE_MISMATCH")
    pending = connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM public.otm_operation WHERE workspace_id=:workspace A"
            "ND kind IN ('organization_action','configurati"
            "on_update','configuration_check') AND state IN "
            "('queued','running','waiting','needs_"
            "attention'))"
        ),
        {"workspace": workspace},
    )
    real = connection.scalar(
        text("SELECT EXISTS(SELECT 1 FROM public.otm_tenancy WHERE provider_mode<>'simulated')")
    )
    email_pending = connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM public.otm_notification_outbox "
            "WHERE workspace_id=:workspace AND state IN ('pending','sending'))"
        ),
        {"workspace": workspace},
    )
    # Delivery evidence survives reset alongside its retained operation/audit history.
    if pending or real or email_pending:
        raise ValueError("ORGANIZATION_RESET_REQUIRES_SETTLED_SIMULATION")
    counts = {
        name: connection.scalar(select(func.count()).select_from(metadata.tables["public." + name]))
        for name in TABLES
    }
    for name in TABLES:
        connection.exec_driver_sql(
            "ALTER TABLE public." + name + " DISABLE TRIGGER " + name + "_no_truncate"
        )
    connection.exec_driver_sql("TRUNCATE TABLE " + names)
    for name in TABLES:
        connection.exec_driver_sql(
            "ALTER TABLE public." + name + " ENABLE TRIGGER " + name + "_no_truncate"
        )
    return counts
