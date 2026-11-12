"""Inspect the installed image and its liveness endpoint; this is a disposable test, not hosting."""

import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


# Compare installed wheel assets against independent checkout hashes before starting real HTTP.
def main():
    server = None
    try:
        expected = json.load(sys.stdin)
        assert os.geteuid() == 10001 and sys.version_info[:2] == (3, 12)
        assert sys.prefix == "/opt/venv" and shutil.which("openssl")
        assert importlib.util.find_spec("pytest") is None

        for module in ("otm.local_server", "otm.local_worker", "otm.maintenance"):
            importlib.import_module(module)
        installed = Path(sysconfig.get_path("purelib"))
        for name, digest in expected.items():
            assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == digest
        public = Path(os.environ["OTM_FRONTEND_DIST"])
        assert (public / "index.html").is_file() and list((public / "assets").glob("*.js"))
        assert not Path("/build").exists() and not Path("/opt/otm/.local-dev").exists()
        server = subprocess.Popen(
            [
                "uvicorn",
                "otm.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
                "--no-access-log",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        while True:
            try:
                with urlopen("http://127.0.0.1:8080/health/live", timeout=2) as response:
                    assert json.load(response) == {"status": "ok"}
                break
            except (URLError, TimeoutError):
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("CONTAINER_LIVENESS_FAILED") from None
                time.sleep(0.1)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "uid": os.geteuid(),
                    "wheel_assets": len(expected),
                    "frontend": True,
                    "liveness": True,
                }
            )
        )
        return 0
    except Exception:
        print(json.dumps({"status": "fail", "code": "CONTAINER_PROBE_FAILED"}))
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
