"""Start/reuse this workspace's persistent, loopback-only inspection database."""

import json
import os
import secrets
import shlex
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql
from run_postgres_tests import POSTGRES_TEST_IMAGE


# Write local connection secrets with owner-only permissions, including existing files.
def private_file(path: Path, contents: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as target:
        target.write(contents)
    path.chmod(0o600)


# Reuse one local database by stable instance ID and refresh its sample and client files.
def main() -> None:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    directory = root / ".local-dev"
    directory.mkdir(exist_ok=True)
    settings_path = directory / "postgres-connection.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        if not settings.get("instance_id"):
            raise SystemExit("Legacy connection settings need explicit migration; nothing changed.")
    else:
        instance_id = secrets.token_hex(5)
        name = "otm-org-local-" + instance_id
        settings = {
            "host": "127.0.0.1",
            "port": 55432,
            "database": "otm_org_dev",
            "user": "otm_dev",
            "password": secrets.token_urlsafe(24),
            "schema": "otm_sample_demo",
            "container": name,
            "volume": name + "-data",
            "instance_id": instance_id,
        }
        private_file(settings_path, json.dumps(settings, indent=2) + "\n")
    name = settings["container"]
    if (
        name != "otm-org-local-" + settings["instance_id"]
        or settings["host"] != "127.0.0.1"
        or settings["database"] != "otm_org_dev"
        or settings["user"] != "otm_dev"
        or settings["schema"] not in {"otm_sample_demo", "otm_sample_demo_v2"}
    ):
        raise SystemExit("Saved connection is not an OTM local instance; nothing changed.")
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .}}", name],
        capture_output=True,
        text=True,
    )
    existing = json.loads(inspected.stdout) if inspected.returncode == 0 else None
    # A stable ownership label survives directory renames; a matching name alone is insufficient.
    if (
        existing
        and (existing["Config"].get("Labels") or {}).get("com.oci-tenancy-manager.instance")
        != settings["instance_id"]
    ):
        raise SystemExit("Container name belongs to a different workspace; nothing changed.")
    if existing:
        if not existing["State"]["Running"]:
            subprocess.run(["docker", "start", name], check=True, capture_output=True)
    else:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                "com.oci-tenancy-manager.instance=" + settings["instance_id"],
                "--label",
                "com.oci-tenancy-manager.workspace=" + str(root),
                "--restart",
                "unless-stopped",
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=" + settings["user"],
                "--env",
                "POSTGRES_DB=" + settings["database"],
                "--publish",
                f"127.0.0.1:{settings['port']}:5432",
                "--mount",
                f"type=volume,source={settings['volume']},target=/var/lib/postgresql/data",
                POSTGRES_TEST_IMAGE,
            ],
            env={**os.environ, "POSTGRES_PASSWORD": settings["password"]},
            check=True,
            capture_output=True,
        )
    # Preserve the named volume on startup failure; never reset data to force readiness.
    for _attempt in range(60):
        try:
            with psycopg.connect(
                host=settings["host"],
                port=settings["port"],
                dbname=settings["database"],
                user=settings["user"],
                password=settings["password"],
                connect_timeout=2,
            ):
                break
        except psycopg.OperationalError:
            time.sleep(0.5)
    else:
        raise SystemExit("Local database did not become ready; saved data was not removed.")

    url = (
        f"postgresql+psycopg://{settings['user']}:{settings['password']}"
        f"@{settings['host']}:{settings['port']}/{settings['database']}"
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/demo_organization.py",
            "--postgres",
            "--output",
            str(directory / "postgres-sample-report.json"),
        ],
        env={**os.environ, "OTM_TEST_DATABASE_URL": url, "OTM_DEMO_SCHEMA": settings["schema"]},
        check=True,
    )
    with psycopg.connect(
        host=settings["host"],
        port=settings["port"],
        dbname=settings["database"],
        user=settings["user"],
        password=settings["password"],
    ) as connection:
        connection.execute(
            sql.SQL(
                "ALTER ROLE otm_dev IN DATABASE otm_org_dev SET search_path TO {}, public"
            ).format(sql.Identifier(settings["schema"]))
        )
        table_count = connection.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = %s", (settings["schema"],)
        ).fetchone()[0]
        people_count = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.org_person").format(sql.Identifier(settings["schema"]))
        ).fetchone()[0]

    pgpass = directory / "postgres.pgpass"
    private_file(
        pgpass,
        f"{settings['host']}:{settings['port']}:{settings['database']}:"
        f"{settings['user']}:{settings['password']}\n",
    )
    environment = {
        "PGHOST": settings["host"],
        "PGPORT": str(settings["port"]),
        "PGDATABASE": settings["database"],
        "PGUSER": settings["user"],
        "PGPASSFILE": str(pgpass),
    }
    private_file(
        directory / "postgres.env",
        "".join(f"export {key}={shlex.quote(value)}\n" for key, value in environment.items()),
    )
    print(
        f"Ready: {settings['host']}:{settings['port']}/{settings['database']}; "
        f"{table_count} tables, {people_count} people."
    )
    print("Connection/password file: " + str(settings_path))
    print("Shell connection: source .local-dev/postgres.env then run psql")


if __name__ == "__main__":
    main()
