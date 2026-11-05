"""Exercise D31's pure batch gate; never persist jobs, change assignments or call OCI."""

import argparse
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path


# Reject an incomplete, stale or unresolved plan without producing accepted work.
class BlockedBatch(ValueError):
    pass


# Bind a fixture decision to exact target, candidate and chosen block content.
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


# Make illustrative content evidence, not an authentication or authorization token.
def decision(target, candidate, kind, choice):
    return {"choice": choice, "content": digest([target, candidate, kind, choice])}


# Calculate counts and proposed results; every unresolved review blocks the whole batch.
def preview(target, frozen, current, decisions, resolver):
    ids = [item["id"] for item in frozen]
    live_ids = [item["id"] for item in current]
    if not ids or len(set(ids)) != len(ids) or len(set(live_ids)) != len(live_ids):
        raise BlockedBatch("Empty or duplicate candidate set")
    if set(ids) != set(live_ids):
        raise BlockedBatch("Refresh the complete candidate scope")
    frozen_map = {item["id"]: item for item in frozen}
    current_map = {item["id"]: item for item in current}
    if digest(frozen_map) != digest(current_map):
        raise BlockedBatch("Assignment or override changed; refresh plan/reviews")
    if not set(decisions).issubset(ids):
        raise BlockedBatch("Review belongs to another candidate set")
    ready, exceptions, proposed = [], {}, {}
    for candidate in frozen:
        key = candidate["id"]
        ov = deepcopy(candidate["override"])
        conflicts = []
        choices = decisions.get(key, {})
        expected = set()
        if ov is not None:
            for kind in ("policy", "quota"):
                field = kind + "_statements"
                if field not in ov or ov["reviewed_against"].get(kind) == resolver.digest(
                    target[kind]["statements"]
                ):
                    continue
                expected.add(kind)
                selected = choices.get(kind)
                valid_choice = selected is not None and selected["choice"] in {
                    "baseline",
                    "override",
                }
                if not valid_choice or selected != decision(
                    target, candidate, kind, selected["choice"]
                ):
                    conflicts.append(kind)
                    continue
                if selected["choice"] == "baseline":
                    del ov[field], ov["reviewed_against"][kind]
                else:
                    ov["reviewed_against"][kind] = resolver.digest(target[kind]["statements"])
            if not set(choices).issubset(expected):
                raise BlockedBatch("Unexpected or stale block decision")
            ov["baseline_version"] = target["version"]
            ov["revision"] += 1
        elif choices:
            raise BlockedBatch("Unexpected decision without an override")
        if conflicts:
            # Do not mistake a count of ready targets for permission to start that subset.
            exceptions[key] = conflicts
        else:
            result = resolver.resolve(target, ov)
            ready.append(key)
            proposed[key] = {"override": ov, "effective": result["effective"]}
    return {
        "total": len(ids),
        "ready": len(ready),
        "exceptions": exceptions,
        "can_start": not exceptions,
        "proposed": proposed,
    }


# Return design-only accepted intent only after rechecking the complete authoritative scope.
def accept(target, frozen, current, decisions, resolver):
    result = preview(target, frozen, current, decisions, resolver)
    if not result["can_start"]:
        raise BlockedBatch("Resolve all batch conflicts before starting")
    return {
        "kind": "design-reference-intent",
        "target": deepcopy(target),
        "targets": deepcopy(result["proposed"]),
    }


# Verify staged choices, all-conflicts gating and stale-context rejection on saved examples.
def check(directory, resolver_path):
    spec = importlib.util.spec_from_file_location("configuration_reference", resolver_path)
    resolver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolver)
    target = json.loads((directory / "baseline-v2.json").read_text())
    grant = json.loads((directory / "grant-overlay.json").read_text())
    team = json.loads((directory / "team-overlay.json").read_text())
    quota, policy = deepcopy(grant), deepcopy(grant)
    del quota["policy_statements"], quota["reviewed_against"]["policy"]
    del policy["quota_statements"], policy["reviewed_against"]["quota"]
    candidates = [
        {"id": "alex", "assignment_revision": 1, "override": None},
        {"id": "jordan", "assignment_revision": 1, "override": team},
        {"id": "grant", "assignment_revision": 1, "override": quota},
        {"id": "sam", "assignment_revision": 1, "override": policy},
    ]
    pristine = deepcopy((target, candidates))
    results = []
    p = preview(target, candidates, candidates, {}, resolver)
    assert (p["ready"], len(p["exceptions"]), p["can_start"]) == (2, 2, False)
    results.append("initial-ready2-conflicts2")
    try:
        accept(target, candidates, candidates, {}, resolver)
    except BlockedBatch:
        results.append("direct-start-blocked-with-conflicts")
    else:
        raise AssertionError("Unresolved batch accepted")
    choices = {"grant": {"quota": decision(target, candidates[2], "quota", "baseline")}}
    p = preview(target, candidates, candidates, choices, resolver)
    assert (p["ready"], len(p["exceptions"]), p["can_start"]) == (3, 1, False)
    assert p["proposed"]["grant"]["effective"]["quota"] == target["quota"]
    results.append("use-baseline-staged-ready3-conflicts1")
    try:
        accept(target, candidates, candidates, choices, resolver)
    except BlockedBatch:
        results.append("ready-subset-still-cannot-start")
    else:
        raise AssertionError("Ready subset started early")
    choices["sam"] = {"policy": decision(target, candidates[3], "policy", "override")}
    p = preview(target, candidates, candidates, choices, resolver)
    assert (p["ready"], len(p["exceptions"]), p["can_start"]) == (4, 0, True)
    assert p["proposed"]["sam"]["effective"]["policy"]["statements"] == policy["policy_statements"]
    assert p["proposed"]["jordan"]["effective"]["budget"]["monthly_amount"] == 500
    results.append("keep-override-staged-ready4-conflicts0")
    accepted = accept(target, candidates, candidates, choices, resolver)
    assert set(accepted["targets"]) == {c["id"] for c in candidates}
    results.append("complete-reviewed-batch-accepted")
    assert (target, candidates) == pristine
    results.append("review-never-mutates-active-assignment-or-override")
    removed = deepcopy(choices)
    del removed["grant"]
    assert not preview(target, candidates, candidates, removed, resolver)["can_start"]
    results.append("cancelled-or-cleared-decision-restores-gate")
    changed_target = deepcopy(target)
    changed_target["version"] = 3
    assert not preview(changed_target, candidates, candidates, choices, resolver)["can_start"]
    results.append("target-version-change-invalidates-choices")
    current = deepcopy(candidates)
    current[2]["override"]["quota_statements"].append("set compute-core quota to 0 in tenancy")
    for name, live, frozen in [
        ("edited-live-override-blocks", current, candidates),
        ("omitted-conflict-cannot-bypass", candidates, candidates[:2]),
        ("duplicate-candidate-blocks", candidates, candidates + [candidates[0]]),
    ]:
        try:
            accept(target, frozen, live, choices, resolver)
        except BlockedBatch:
            results.append(name)
        else:
            raise AssertionError(name)
    both = deepcopy(candidates[:1])
    both[0]["override"] = deepcopy(grant)
    p = preview(target, both, both, {}, resolver)
    assert len(p["exceptions"]) == 1 and len(p["exceptions"][both[0]["id"]]) == 2
    results.append("one-tenancy-two-blocks-counts-once")
    return {
        "status": "pass",
        "checked_on": "2026-10-21",
        "decision": "D31",
        "checks": results,
        "checks_passed": len(results),
        "oci_calls": 0,
        "production_runner_implemented": False,
        "database_transactions_executed": False,
        "limits": "Pure design gate only; no real authorization, eligibility, queue or OCI work.",
        "input_sha256": {
            n: hashlib.sha256((directory / n).read_bytes()).hexdigest()
            for n in ("baseline-v2.json", "grant-overlay.json", "team-overlay.json")
        },
    }


# Run the bounded batch-gate scenarios and optionally retain their receipt.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--resolver", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = check(args.directory, args.resolver)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
