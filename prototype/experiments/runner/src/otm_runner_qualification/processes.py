"""Keep qualification imports compatible with the shared owned-process development tool."""

import runpy
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[5]
_TOOL = runpy.run_path(str(_ROOT / "scripts/process_groups.py"))
GroupResult = _TOOL["GroupResult"]
run_python_group = _TOOL["run_python_group"]
