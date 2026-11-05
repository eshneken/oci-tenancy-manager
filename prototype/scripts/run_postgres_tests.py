"""Create one disposable loopback container, test, then remove only that container."""

import json
import os
import secrets
import subprocess
import sys
import time
from uuid import uuid4

POSTGRES_TEST_IMAGE = (
    "postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"
)


# Run tests and sample publication in one disposable loopback PostgreSQL container.
#
# Generate isolated credentials and a dynamic local port, wait for readiness, then
# return the child process exit status. Finally stop only this run's container, even
# on test failure; this runner does not operate on the persistent development database.
def main() -> int:
    name = "otm-org-test-" + uuid4().hex[:12]
    password = secrets.token_hex(24)
    env = {**os.environ, "POSTGRES_PASSWORD": password}
    created = False
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=otm_dev",
                "--env",
                "POSTGRES_DB=otm_org_test",
                "--publish",
                "127.0.0.1::5432",
                POSTGRES_TEST_IMAGE,
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        created = True
        for _attempt in range(60):
            probe = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "otm_dev"], capture_output=True
            )
            if probe.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("local PostgreSQL readiness timeout")
        output = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .NetworkSettings.Ports}}",
                name,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        port = json.loads(output)["5432/tcp"][0]["HostPort"]
        env["OTM_TEST_DATABASE_URL"] = (
            f"postgresql+psycopg://otm_dev:{password}@127.0.0.1:{port}/otm_org_test"
        )
        result = subprocess.run([sys.executable, "-m", "pytest", *sys.argv[1:]], env=env).returncode
        if result == 0:
            result = subprocess.run(
                [sys.executable, "scripts/demo_synthetic_organization.py", "--postgres"], env=env
            ).returncode
        return result
    finally:
        if created:
            subprocess.run(["docker", "stop", name], check=True, capture_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
