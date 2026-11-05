"""Keep the prototype CLI compatible while using the shared complete-source coverage gate."""

import runpy
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
# Load development tooling by its exact path, without importing either application package.
_GATE = runpy.run_path(str(PROJECT.parent / "scripts/check_unit_coverage.py"))
coverage_result = _GATE["coverage_result"]
junit_result = _GATE["junit_result"]


# Run the shared gate against the preserved prototype's complete backend source.
def main() -> int:
    return _GATE["main"](project=PROJECT, source_directory="backend/otm")


if __name__ == "__main__":
    raise SystemExit(main())
