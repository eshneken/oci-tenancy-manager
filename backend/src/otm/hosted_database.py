"""Verified hosted database pools, schema/role readiness and single-owner forward migrations."""

import ipaddress
import re
import ssl
from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from otm.maintenance import database_connection_options
from otm.release_validation import validate_release_settings
from otm.settings import ApplicationSettings


# Require independently selected hosted release settings, never infer the environment from TOML.
def hosted_settings(settings, environment):
    settings = ApplicationSettings.model_validate(settings)
    validate_release_settings(settings, environment, "application")
    if environment not in {"staging", "production"} or settings.hosted is None:
        raise ValueError("HOSTED_CONFIGURATION_REQUIRED")
    host = urlsplit(settings.hosted.public_origin).hostname.rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("HOSTED_PUBLIC_ORIGIN_REQUIRED")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if address.is_loopback or address.is_unspecified:
            raise ValueError("HOSTED_PUBLIC_ORIGIN_REQUIRED")
    return settings


# Use a managed DNS endpoint and explicit valid CA; no local TLS exception or libpq env overrides.
def hosted_connection_options(database_url, ca_file, *, role):
    if role not in {"api", "worker", "migration"}:
        raise ValueError("HOSTED_DATABASE_ROLE_INVALID")
    url, options = database_connection_options(database_url, ca_file)
    host = url.host.rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("HOSTED_DATABASE_DNS_REQUIRED")
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or "." not in host
        or re.fullmatch(
            r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+",
            host,
        )
        is None
    ):
        raise ValueError("HOSTED_DATABASE_DNS_REQUIRED")
    if (
        not ca_file
        or not Path(ca_file).is_absolute()
        or not 0 < Path(ca_file).stat().st_size <= 1048576
    ):
        raise ValueError("HOSTED_DATABASE_CA_REQUIRED")
    ssl.create_default_context(cafile=ca_file)
    options.update(
        connect_timeout=2,
        sslmode="verify-full",
        sslrootcert=ca_file,
        keepalives=1,
        keepalives_idle=10,
        keepalives_interval=3,
        keepalives_count=3,
        tcp_user_timeout=5000,
    )
    if role == "migration":
        options["options"] = "-c timezone=UTC -c statement_timeout=300000 -c lock_timeout=5000"
    return url, options


# Runtime pools have no overflow; migrations have one connection and independent owner credentials.
def hosted_engine(database_url, ca_file, *, role, pool_size=2):
    if type(pool_size) is not int or not 1 <= pool_size <= 16:
        raise ValueError("HOSTED_DATABASE_POOL_INVALID")
    url, options = hosted_connection_options(database_url, ca_file, role=role)
    return create_engine(
        url,
        connect_args=options,
        hide_parameters=True,
        pool_size=1 if role == "migration" else pool_size,
        max_overflow=0,
        pool_timeout=1,
    ).execution_options(otm_hosted_role=role)


# Locate only frozen installed migration assets or this source checkout, never a CWD/env override.
def migration_configuration():
    installed = Path(__file__).resolve().parents[1] / "otm_migrations" / "alembic.ini"
    source = Path(__file__).resolve().parents[2] / "alembic.ini"
    selected = installed if installed.is_file() else source
    if not selected.is_file() or not (selected.parent / "migrations/sql/manifest.json").is_file():
        raise ValueError("HOSTED_MIGRATION_ASSETS_UNAVAILABLE")
    return Config(str(selected))


# Check current schema and non-owner runtime role in one bounded read; failures stay generic.
def database_ready(engine):
    try:
        expected = ScriptDirectory.from_config(migration_configuration()).get_current_head()
        with engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout='1000ms'")
            connection.exec_driver_sql("SET LOCAL lock_timeout='1000ms'")
            row = (
                connection.execute(
                    text(
                        "SELECT (SELECT ssl FROM pg_catalog.pg_stat_ssl "
                        "WHERE pid=pg_backend_pid()) AS transport_secure, "
                        "(SELECT count(*)=1 AND bool_and(version_num=:revision) "
                        "FROM public.alembic_version) AS schema_current, "
                        "NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls "
                        "OR pg_catalog.has_schema_privilege(current_user,'public','CREATE') "
                        "OR pg_catalog.pg_has_role(current_user,t.relowner,'MEMBER')) AS safe_role "
                        "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_class t "
                        "WHERE r.rolname=current_user "
                        "AND t.oid=to_regclass('public.otm_administrator')"
                    ),
                    {"revision": expected},
                )
                .mappings()
                .one_or_none()
            )
        return (
            row is not None
            and row["schema_current"] is True
            and row["safe_role"] is True
            and row["transport_secure"] is True
        )
    except Exception:
        return False


# Reuse Alembic's owned-connection transaction; no downgrade, reset, alternate revision or API DDL.
def migrate_database(engine):
    configuration = migration_configuration()
    with engine.begin() as connection:
        allowed = connection.scalar(
            text(
                "SELECT NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls) "
                "AND pg_catalog.pg_has_role(current_user,n.nspowner,'MEMBER') "
                "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_namespace n "
                "WHERE r.rolname=current_user AND n.nspname='public'"
            )
        )
        if allowed is not True:
            raise ValueError("DEDICATED_MIGRATION_OWNER_REQUIRED")
        if connection.scalar(text("SELECT pg_try_advisory_xact_lock(5198925,1)")) is not True:
            raise ValueError("SCHEMA_MIGRATION_ALREADY_RUNNING")
        configuration.attributes["connection"] = connection
        command.upgrade(configuration, "head")
    return ScriptDirectory.from_config(configuration).get_current_head()
