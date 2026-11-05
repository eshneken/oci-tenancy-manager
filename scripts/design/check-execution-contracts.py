"""Validate draft messages and graph consistency without dispatching workflows or OCI calls."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


# Check schema examples and graph consistency without claiming runtime coverage.
def check_contracts(directory):
    schema_path = directory / "oci-execution.schema.json"
    examples_path = directory / "oci-execution-examples.json"
    scenarios_path = directory / "oci-execution-scenarios.json"
    schema = json.loads(schema_path.read_text())
    fixtures = json.loads(examples_path.read_text())
    scenarios = json.loads(scenarios_path.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    # Evolve the root validator so local $defs references retain the same resolver context.
    for example in fixtures["positive_examples"]:
        sub = validator.evolve(schema={"$ref": f"#/$defs/{example['definition']}"})
        errors = list(sub.iter_errors(example["value"]))
        assert not errors, (example["id"], [error.message for error in errors])
        validator.validate(example["value"])
    for example in fixtures["negative_examples"]:
        sub = validator.evolve(schema={"$ref": f"#/$defs/{example['definition']}"})
        assert list(sub.iter_errors(example["value"])), (
            f"Negative control accepted: {example['id']}"
        )
    edges = scenarios["allowed_state_edges"]
    assert set(edges) == set(schema["$defs"]["OperationSnapshot"]["properties"]["state"]["enum"])
    for trace in scenarios["state_traces"]:
        # This checks adjacency, not entitlement, mutation exclusion or completion predicates.
        valid = all(
            right in edges.get(left, [])
            for left, right in zip(trace["states"], trace["states"][1:], strict=False)
        )
        assert valid == trace["valid"], trace["id"]
    assert len({case["id"] for case in scenarios["scenarios"]}) == len(scenarios["scenarios"])
    return {
        "checked_on": "2026-10-20",
        "status": "pass",
        "validation_kind": "design-schema-and-graph-consistency-only",
        "schema_validator": f"jsonschema {importlib.metadata.version('jsonschema')}",
        "positive_shape_examples": len(fixtures["positive_examples"]),
        "negative_shape_examples": len(fixtures["negative_examples"]),
        "state_graph_examples": len(scenarios["state_traces"]),
        "planned_runtime_scenarios": len(scenarios["scenarios"]),
        "workflow_runtime_tests_executed": False,
        "oci_calls": 0,
        "application_dependencies_changed": False,
        "artifact_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [schema_path, examples_path, scenarios_path]
        },
    }


# Write an optional reproducible check receipt for the provided design-artifact directory.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = check_contracts(args.directory)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
