"""Check D30 full-statement-block design examples without OCI or application writes."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path


# Reject malformed illustrative intent before any application could be planned.
class InvalidConfiguration(ValueError):
    pass


# Keep a target blocked when changed baseline statements need explicit override review.
class ReviewRequired(InvalidConfiguration):
    pass


# Hash exact JSON values; never rewrite policy syntax or merge statement arrays.
def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# Check statement-array structure only, not OCI grammar or granted privileges.
def statements(value):
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(s, str) or not s.strip() for s in value)
    ):
        raise InvalidConfiguration("Supply a nonempty list of complete statement strings")


# Require positive whole example units; booleans are not monetary amounts.
def amount(value):
    if type(value) is not int or value <= 0:
        raise InvalidConfiguration("Invalid monthly example budget amount")


# Validate the bounded root-object shape without claiming full provider validation.
def validate(baseline):
    if not isinstance(baseline, dict) or set(baseline) != {
        "baseline_id",
        "version",
        "policy",
        "quota",
        "budget",
        "tags",
    }:
        raise InvalidConfiguration("Unknown baseline fields")
    if type(baseline["version"]) is not int or baseline["version"] <= 0:
        raise InvalidConfiguration("Invalid version")
    for kind in ("policy", "quota"):
        if not isinstance(baseline[kind], dict) or set(baseline[kind]) != {"statements"}:
            raise InvalidConfiguration("Only one complete statement block per object")
        statements(baseline[kind]["statements"])
    budget = baseline["budget"]
    if not isinstance(budget, dict) or set(budget) != {
        "monthly_amount",
        "currency",
        "period",
        "alerts",
    }:
        raise InvalidConfiguration("Invalid budget fields")
    amount(budget["monthly_amount"])
    if budget["period"] != "MONTHLY" or budget["currency"] != "USD" or budget["alerts"] != []:
        raise InvalidConfiguration("Example budget requires monthly USD and no alerts")
    tags = baseline["tags"]
    if (
        not isinstance(tags, dict)
        or set(tags) != {"namespace", "defaults"}
        or tags["namespace"] != "OTM"
    ):
        raise InvalidConfiguration("One fixed OTM namespace is required")
    if not isinstance(tags["defaults"], list):
        raise InvalidConfiguration("Invalid defined-tag list")
    seen = set()
    for tag in tags["defaults"]:
        if not isinstance(tag, dict) or set(tag) != {"key", "value"}:
            raise InvalidConfiguration("Only defined-tag key and static value supported")
        key, value = tag["key"], tag["value"]
        if (
            not isinstance(key, str)
            or not key
            or any(ord(c) < 33 or ord(c) > 126 or c == "." for c in key)
        ):
            raise InvalidConfiguration("Invalid tag key")
        if key.casefold() in seen:
            raise InvalidConfiguration("Case-insensitive duplicate tag key")
        seen.add(key.casefold())
        if not isinstance(value, str) or not value or "${" in value:
            raise InvalidConfiguration("Static nonempty tag value required")


# Replace a whole policy/quota list or budget amount; reject unresolved review contexts.
def resolve(baseline, override):
    validate(baseline)
    result = deepcopy(baseline)
    source = {k: "baseline" for k in ("policy", "quota", "budget", "tags")}
    if override is not None:
        allowed = {
            "override_id",
            "revision",
            "baseline_id",
            "baseline_version",
            "reviewed_against",
            "policy_statements",
            "quota_statements",
            "budget_amount",
            "budget_context",
        }
        required = {
            "override_id",
            "revision",
            "baseline_id",
            "baseline_version",
            "reviewed_against",
        }
        if not required.issubset(override) or not set(override).issubset(allowed):
            raise InvalidConfiguration("Unsupported override field/object")
        if (override["baseline_id"], override["baseline_version"]) != (
            baseline["baseline_id"],
            baseline["version"],
        ):
            raise InvalidConfiguration("Pin mismatch; preview update first")
        expected_reviews = {k for k in ("policy", "quota") if k + "_statements" in override}
        if set(override["reviewed_against"]) != expected_reviews:
            raise InvalidConfiguration("Missing or unexpected review context")
        for kind in expected_reviews:
            value = override[kind + "_statements"]
            statements(value)
            if override["reviewed_against"][kind] != digest(baseline[kind]["statements"]):
                raise ReviewRequired(kind)
            # A replacement must not append baseline entries or resurrect an old rule implicitly.
            result[kind]["statements"] = deepcopy(value)
            source[kind] = "full-list override"
        if "budget_amount" in override:
            amount(override["budget_amount"])
            context = {k: baseline["budget"][k] for k in ("currency", "period")}
            if override.get("budget_context") != context:
                raise InvalidConfiguration("Budget meaning changed")
            result["budget"]["monthly_amount"] = override["budget_amount"]
            source["budget"] = "amount override"
        elif "budget_context" in override:
            raise InvalidConfiguration("Unexpected budget context")
    return {"effective": result, "provenance": source, "effective_hash": digest(result)}


# Describe the exact proposed review; a token is not authorization or an audit event.
def review_token(baseline, override, kind):
    return digest(
        {
            "target_baseline": digest(baseline),
            "override_revision": override["revision"],
            "override": digest(override),
            "kind": kind,
        }
    )


# Carry overrides only after reviews bound to this exact baseline and override content.
def update_preview(baseline, override, approvals):
    validate(baseline)
    if override is None:
        return resolve(baseline, None)
    if override["baseline_id"] != baseline["baseline_id"]:
        raise InvalidConfiguration("Different baseline lineage")
    candidate = deepcopy(override)
    for kind in ("policy", "quota"):
        if kind + "_statements" in override:
            baseline_hash = digest(baseline[kind]["statements"])
            if override["reviewed_against"].get(kind) != baseline_hash:
                if approvals.get(kind) != review_token(baseline, override, kind):
                    raise ReviewRequired(kind)
                candidate["reviewed_against"][kind] = baseline_hash
    candidate["baseline_version"] = baseline["version"]
    candidate["revision"] += 1
    return resolve(baseline, candidate)


# Apply fixture edits on a copy, preserving saved baseline and override examples.
def changed(value, changes):
    result = deepcopy(value)
    for change in changes:
        parent = result
        for part in change["path"][:-1]:
            parent = parent[part]
        key = change["path"][-1]
        if change.get("remove"):
            del parent[key]
        else:
            parent[key] = deepcopy(change["value"])
    return result


# Run bounded structural/review examples, never apply OCI or execute a production workflow.
def check_examples(directory):
    files = {p.name: json.loads(p.read_text()) for p in directory.glob("*.json")}
    examples = files["configuration-resolution-examples.json"]
    for valid, category in ((True, "positive"), (False, "negative")):
        for case in examples[category]:
            base = changed(files[case["baseline"]], case.get("baseline_changes", []))
            override = files[case["override"]] if case.get("override") else None
            override = changed(override, case.get("override_changes", []))
            approvals = {
                kind: review_token(base, override, kind) for kind in case.get("review", [])
            }
            if case.get("stale_review"):
                approvals["policy"] = "old-review-token"
            try:
                result = (
                    update_preview(base, override, approvals)
                    if case.get("update")
                    else resolve(base, override)
                )
            except InvalidConfiguration:
                if valid:
                    raise AssertionError(f"Valid case rejected: {case['id']}") from None
                continue
            if not valid:
                raise AssertionError(f"Invalid case accepted: {case['id']}")
            for key, expected in case["expected"].items():
                assert result["effective"][key] == expected, case["id"]
    base, nxt, ov = (
        files[n] for n in ("baseline-v1.json", "baseline-v2.json", "grant-overlay.json")
    )
    original = deepcopy((base, nxt, ov))
    result = resolve(base, ov)
    assert result["effective"]["policy"]["statements"] == ov["policy_statements"]
    assert result["effective"]["quota"]["statements"] == ov["quota_statements"]
    assert len(result["effective"]["quota"]["statements"]) == len(ov["quota_statements"])
    assert result["effective"]["tags"] == base["tags"]
    assert result["provenance"]["policy"] == "full-list override"
    assert (base, nxt, ov) == original
    stale = review_token(nxt, ov, "policy")
    edited = deepcopy(ov)
    edited["policy_statements"].append("Allow group OTMOperators to read buckets in tenancy")
    try:
        update_preview(nxt, edited, {"policy": stale, "quota": review_token(nxt, edited, "quota")})
    except ReviewRequired:
        pass
    else:
        raise AssertionError("Review survived editing of the full override")
    return {
        "status": "pass",
        "checked_on": "2026-10-21",
        "decision": "D30-full-statement-blocks",
        "positive_cases": len(examples["positive"]),
        "negative_cases": len(examples["negative"]),
        "additional_invariants": 7,
        "oci_calls": 0,
        "production_resolver_implemented": False,
        "runtime_rollout_or_drift_tests_executed": False,
        "notes": [
            "Structural and review examples only; OCI grammar/authorization not validated.",
            "Required-access integration, drift normalization and budget scope remain unqualified.",
        ],
        "input_sha256": {
            n: hashlib.sha256((directory / n).read_bytes()).hexdigest() for n in sorted(files)
        },
    }


# Check the saved examples and optionally persist a bounded validation receipt.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = check_examples(args.directory)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
