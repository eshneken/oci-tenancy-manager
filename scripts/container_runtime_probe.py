"""Exercise native crypto, TLS, configured API and job compatibility inside the installed image."""

import json
import os
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4

import procrastinate
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import make_url

from otm.local_worker import run_worker
from otm.operations.sandbox import sample_sandbox
from otm.providers.bootstrap_keys_local import LocalBootstrapKeys
from otm.settings import load_settings


# Fixed argv, bounded captured diagnostics and throwaway files never expose key/password material.
def checked(arguments):
    return subprocess.run(arguments, check=True, capture_output=True, timeout=30)


# Verify both success and rejection paths using actual native dependencies, never mock libraries.
def main():
    server = None
    stage = "settings"
    try:
        os.umask(0o077)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "application.toml"
            config.write_text(
                Path("/opt/venv/lib/python3.12/site-packages/otm_settings/application.toml")
                .read_text()
                .replace("https://localhost:8443", "https://localhost:8080")
            )
            settings = load_settings(config)
            for name in ("mfa", "recovery-passwords", "bootstrap-key-custody"):
                (root / name).mkdir(mode=0o700)
            sandbox = root / "simulation.json"
            sandbox.write_text(
                sample_sandbox(settings.local_auth.workspace_id, uuid4()).model_dump_json()
            )
            os.environ.update(
                OTM_APPLICATION_CONFIG=str(config),
                OTM_MFA_SECRET_DIRECTORY=str(root / "mfa"),
                OTM_SANDBOX_CONFIG=str(sandbox),
            )
            stage = "password-hashing"
            hasher = PasswordHasher()
            password = uuid4().hex
            verifier = hasher.hash(password)
            assert hasher.verify(verifier, password)
            try:
                hasher.verify(verifier, password + "wrong")
            except VerifyMismatchError:
                pass
            else:
                raise RuntimeError("PASSWORD_REJECTION_FAILED")
            stage = "key-custody"
            keys = LocalBootstrapKeys(root / "bootstrap-key-custody")
            operation = uuid4()
            keys.prepare("container-probe", operation)
            public = keys.public("container-probe", operation)
            keys.prepare("container-probe", operation)
            assert keys.public("container-probe", operation) == public
            assert public.startswith("-----BEGIN PUBLIC KEY-----") and "PRIVATE" not in public
            stage = "tls-api"
            certificate, private = root / "tls.crt", root / "tls.key"
            checked(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                    "-addext",
                    "subjectAltName=DNS:localhost",
                    "-keyout",
                    str(private),
                    "-out",
                    str(certificate),
                ]
            )
            server = subprocess.Popen(
                [
                    "uvicorn",
                    "otm.local_server:create_local_application",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8080",
                    "--no-access-log",
                    "--ssl-keyfile",
                    str(private),
                    "--ssl-certfile",
                    str(certificate),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            stage = "configured-api-startup"
            trusted = ssl.create_default_context(cafile=str(certificate))
            deadline = time.monotonic() + 25
            while True:
                try:
                    with urlopen(
                        "https://localhost:8080/health/live", context=trusted, timeout=2
                    ) as response:
                        assert json.load(response) == {"status": "ok"}
                    break
                except URLError:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("CONFIGURED_API_FAILED") from None
                    time.sleep(0.1)
            stage = "frontend-serving"
            with urlopen("https://localhost:8080/login", context=trusted, timeout=2) as response:
                assert b'<div id="root">' in response.read()
            # Sensitive routes still require authentication in the installed configured API.
            try:
                urlopen("https://localhost:8080/api/operations", context=trusted, timeout=2)
            except HTTPError as error:
                assert error.code == 401
            else:
                raise RuntimeError("UNAUTHENTICATED_API_ACCEPTED")
            stage = "tls-rejection"
            try:
                urlopen("https://localhost:8080/health/live", timeout=2)
            except URLError as error:
                assert isinstance(error.reason, ssl.SSLCertVerificationError)
            else:
                raise RuntimeError("UNTRUSTED_TLS_ACCEPTED")
            try:
                urlopen("https://127.0.0.1:8080/health/live", context=trusted, timeout=2)
            except URLError as error:
                assert isinstance(error.reason, ssl.SSLCertVerificationError)
            else:
                raise RuntimeError("WRONG_TLS_HOSTNAME_ACCEPTED")
            server.terminate()
            server.wait(timeout=10)
            server = None
            os.environ["OTM_DATABASE_URL"] = os.environ["OTM_WORKER_DATABASE_URL"]
            # Compose/drain the actual OTM worker with its restricted login and explicit simulator.
            stage = "application-worker"
            run_worker(once=True)
            url = make_url(os.environ["OTM_DATABASE_URL"])
            conninfo = make_conninfo(
                host="127.0.0.1",
                hostaddr="127.0.0.1",
                port=url.port,
                user=url.username,
                password=url.password,
                dbname=url.database,
                sslmode="disable",
                gssencmode="disable",
                connect_timeout=5,
            )
            stage = "native-job"
            native = procrastinate.App(
                connector=procrastinate.PsycopgConnector(conninfo=conninfo, min_size=1, max_size=2)
            )
            queue = "ct." + uuid4().hex[:20]
            executed = []

            # A real queued job proves native enqueue, acquisition and execution on this C runtime.
            @native.task(name="container.compatibility", queue=queue)
            def compatibility():
                executed.append(True)

            stage = "native-enqueue"
            with native.open():
                compatibility.defer()
            stage = "native-execution"
            native.run_worker(queues=[queue], wait=False, concurrency=1, listen_notify=False)
            assert executed == [True]
        print(
            json.dumps({"status": "pass", "crypto": True, "tls": True, "api": True, "worker": True})
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "code": "CONTAINER_RUNTIME_PROBE_FAILED",
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "cause_type": type(error.__cause__).__name__,
                    "sqlstate": getattr(error.__cause__, "sqlstate", None),
                }
            )
        )
        return 1
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
