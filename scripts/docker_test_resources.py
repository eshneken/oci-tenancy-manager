"""Ownership-checked Docker cleanup for disposable test resources."""

import json
import re
import subprocess


# Remove label-verified test resources and their anonymous volumes. Return the log outcome
# separately from removal so a failed diagnostic cannot prevent cleanup or pass a run.
def remove_owned(client, name, label, owner, *, kind="container", log_path=None):
    inspected = subprocess.run(
        [client, "inspect", "--type", kind, name], capture_output=True, text=True, timeout=30
    )
    if inspected.returncode:
        errors = inspected.stderr.lower().strip()
        missing = {
            "container": (f"no such container: {name}", f"no such object: {name}"),
            "image": (f"no such image: {name}", f"no such image: {name}:latest"),
            "network": (f"network {name} not found",),
            "volume": (f"get {name}: no such volume",),
        }
        if errors.endswith(missing[kind]):
            return True
        raise RuntimeError("DOCKER_RESOURCE_INSPECTION_FAILED")
    records = json.loads(inspected.stdout)
    if len(records) != 1:
        raise ValueError("DOCKER_RESOURCE_OWNERSHIP_MISMATCH")
    record = records[0]
    metadata = record["Config"] if kind in {"container", "image"} else record
    if (metadata.get("Labels") or {}).get(label) != owner:
        raise ValueError("DOCKER_RESOURCE_OWNERSHIP_MISMATCH")
    # Immutable IDs prevent an inspected container or network name being reused before removal.
    target = name
    if kind in {"container", "network"}:
        target = record["Id"]
        if not re.fullmatch(r"[0-9a-f]{64}", target):
            raise ValueError("DOCKER_RESOURCE_ID_INVALID")
    diagnostics_ok = True
    if log_path is not None:
        try:
            result = subprocess.run(
                [client, "logs", target], capture_output=True, check=False, timeout=10
            )
            log_path.write_bytes(result.stdout + result.stderr)
            diagnostics_ok = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            diagnostics_ok = False
    command = (
        [client, "rm", "--force", "--volumes", target]
        if kind == "container"
        else [client, kind, "rm", target]
    )
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    return diagnostics_ok
