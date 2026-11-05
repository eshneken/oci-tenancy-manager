"""Run bounded explicit-target database maintenance or render its daily CronJob."""

import argparse
import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from otm.auth.cleanup import cleanup_sessions
from otm.settings import ApplicationSettings, load_settings
from otm.storage.sessions import SqlSessionRepository


# Use explicit credentials, verified remote TLS and a loopback-only development exception.
def maintenance_engine(database_url: str, ca_file: str | None):
    if any(key.startswith("PG") for key in os.environ):
        raise ValueError("LIBPQ_ENVIRONMENT_NOT_ALLOWED")
    url = make_url(database_url)
    if (
        url.drivername != "postgresql+psycopg"
        or not url.host
        or not url.port
        or not url.username
        or not url.password
        or not url.database
        or url.query
    ):
        raise ValueError("INVALID_MAINTENANCE_DATABASE")
    local = url.host in {"127.0.0.1", "localhost", "::1"}
    if not local and not ca_file:
        raise ValueError("DATABASE_CA_REQUIRED")
    options = {
        "connect_timeout": 5,
        "options": "-c timezone=UTC -c statement_timeout=10000 -c lock_timeout=5000",
        "sslmode": "disable" if local else "verify-full",
        "gssencmode": "disable",
    }
    if local:
        options["hostaddr"] = "::1" if url.host == "::1" else "127.0.0.1"
    else:
        options["sslrootcert"] = ca_file
    return create_engine(
        url, connect_args=options, hide_parameters=True, pool_size=1, max_overflow=0
    )


# Refuse operator/owner membership for either local HTTP or worker runtime composition.
def require_runtime_role(engine):
    with engine.connect() as connection:
        unsafe = connection.scalar(
            text(
                "SELECT r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls "
                "OR pg_catalog.pg_has_role(current_user,t.relowner,'MEMBER') "
                "OR pg_catalog.has_schema_privilege(current_user,'public','CREATE') "
                "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_class t "
                "WHERE r.rolname=current_user "
                "AND t.oid='public.otm_administrator'::pg_catalog.regclass"
            )
        )
        if unsafe is not False:
            raise ValueError("RESTRICTED_RUNTIME_ROLE_REQUIRED")


# Render a daily UTC job from the same settings consumed by its bounded cleanup command.
def cleanup_cronjob(settings: ApplicationSettings, image: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("PINNED_MAINTENANCE_IMAGE_REQUIRED")
    settings = ApplicationSettings.model_validate(settings)
    cleanup = settings.sessions.cleanup
    pod = {
        "restartPolicy": "Never",
        "automountServiceAccountToken": False,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "runAsGroup": 10001,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "cleanup",
                "image": image,
                "command": [
                    "otm-maintenance",
                    "cleanup-sessions",
                    "--config",
                    "/etc/otm/application.toml",
                ],
                "env": [
                    {
                        "name": "OTM_DATABASE_URL",
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": "otm-session-maintenance-database",
                                "key": "url",
                            }
                        },
                    },
                    {"name": "OTM_DATABASE_CA_FILE", "value": "/etc/otm-ca/ca.crt"},
                ],
                "volumeMounts": [
                    {"name": "settings", "mountPath": "/etc/otm", "readOnly": True},
                    {"name": "ca", "mountPath": "/etc/otm-ca", "readOnly": True},
                ],
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "readOnlyRootFilesystem": True,
                    "capabilities": {"drop": ["ALL"]},
                },
                "resources": {
                    "requests": {"cpu": "100m", "memory": "128Mi"},
                    "limits": {"cpu": "500m", "memory": "256Mi"},
                },
            }
        ],
        "volumes": [
            {"name": "settings", "configMap": {"name": "otm-application-settings"}},
            {"name": "ca", "secret": {"secretName": "otm-database-ca"}},
        ],
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {"name": "otm-session-cleanup"},
        "spec": {
            "schedule": f"{cleanup.minute_utc} {cleanup.hour_utc} * * *",
            "timeZone": "Etc/UTC",
            "concurrencyPolicy": "Forbid",
            "startingDeadlineSeconds": 3600,
            "successfulJobsHistoryLimit": 1,
            "failedJobsHistoryLimit": 3,
            "jobTemplate": {
                "spec": {"backoffLimit": 1, "activeDeadlineSeconds": 300, "template": {"spec": pod}}
            },
        },
    }


# Keep database URLs out of command arguments, diagnostics and rendered deployment manifests.
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["cleanup-sessions", "render-session-cleanup"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--image")
    args = parser.parse_args(argv)
    engine = None
    try:
        settings = load_settings(args.config)
        if args.command == "render-session-cleanup":
            print(json.dumps(cleanup_cronjob(settings, args.image or ""), indent=2))
        else:
            from datetime import UTC, datetime

            engine = maintenance_engine(
                os.environ.get("OTM_DATABASE_URL", ""), os.environ.get("OTM_DATABASE_CA_FILE")
            )
            result = cleanup_sessions(
                SqlSessionRepository(engine), settings.sessions.cleanup, lambda: datetime.now(UTC)
            )
            print(result.model_dump_json())
        return 0
    except Exception:
        print(json.dumps({"code": "SESSION_MAINTENANCE_FAILED"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
