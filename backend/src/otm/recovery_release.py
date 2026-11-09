"""Offline private candidate rendering for the existing configuration release gate."""

import json
import os
from pathlib import Path

from otm.recovery_console import parse_release_cidrs
from otm.settings import ApplicationSettings, load_settings


# Encode only already validated settings values; environment input never becomes shell/TOML code.
def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if type(value) in (int, float):
        return str(value)
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise ValueError("UNSUPPORTED_SETTINGS_VALUE")


# Render from the strict model rather than rewriting arbitrary TOML fragments with regexes.
def settings_toml(settings: ApplicationSettings):
    sections = []

    # Tables are emitted after their scalar fields; empty optional values are omitted by the model.
    def table(values, path):
        lines = ["[" + ".".join(path) + "]"] if path else []
        for key, value in values.items():
            if not isinstance(value, dict):
                if path == ("recovery_console",) and key == "allowed_cidrs":
                    lines.extend(
                        [
                            "# Approved recovery-only console sources: 1–64 IPv4/IPv6 CIDRs.",
                            "# ORed; empty, malformed and unrestricted unions are rejected.",
                        ]
                    )
                lines.append(key + " = " + toml_value(value))
        sections.append("\n".join(lines))
        for key, value in values.items():
            if isinstance(value, dict):
                table(value, (*path, key))

    table(settings.model_dump(mode="json", exclude_none=True), ())
    return "\n\n".join(sections) + "\n\n"


# Validate a full candidate first and write a new owner-only file; never replace a deployed config.
def render_candidate(source: Path, output: Path, value: str, *, validate=None):
    policy = parse_release_cidrs(value)
    settings = load_settings(source)
    values = settings.model_dump()
    values["recovery_console"] = policy
    settings = ApplicationSettings.model_validate(values)
    if validate is not None:
        validate(settings)
    content = settings_toml(settings).encode("utf-8")
    if len(content) > 65536:
        raise ValueError("INVALID_APPLICATION_SETTINGS")
    # Exclusive creation refuses symlinks/existing candidates and preserves the last valid file.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return settings
