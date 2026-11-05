# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.25.1"]
# ///
"""Validate C5 design examples and reference predicates without OCI, mail, jobs or database access.

This is a design-review utility. Its pure predicates make semantic counterexamples reproducible;
they are not production normalization, authorization, transaction or provider implementations.
Run with ``uv run --no-project scripts/check_c5_contracts.py`` to isolate the schema dependency.
"""

import argparse
import hashlib
import importlib.metadata
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
GUARDS = (
    "workspace_id",
    "tenancy_id",
    "operation_id",
    "intent_revision",
    "execution_generation",
    "source_access_context_id",
    "source_context_generation",
    "budget_binding_id",
    "budget_binding_generation",
    "configuration_id",
    "configuration_generation",
    "source_policy_revision",
    "scope_hash",
    "source_tenancy_ocid",
    "budget_ocid",
    "expected_period_start",
    "expected_period_end",
    "billing_timezone",
)


# Reject a semantic mismatch with a stable diagnostic usable by negative-control fixtures.
def require(condition, code):
    if not condition:
        raise ValueError(code)


# Parse a schema-validated UTC instant without substituting a local or retrieval timestamp.
def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Check nullability and provenance prerequisites, without trusting the evidence itself.
def validate_snapshot(snapshot):
    source = snapshot["source"]
    start, end = snapshot["spend_period_start"], snapshot["spend_period_end"]
    computed = snapshot["time_spend_computed"]
    if snapshot["period_state"] == "unknown":
        require(start is None and end is None, "unknown_period_has_bounds")
    else:
        require(start is not None and end is not None, "period_missing_bounds")
        require(instant(start) < instant(end), "period_interval_invalid")
        require(snapshot["period_evidence_event_id"] is not None, "period_evidence_missing")
        if snapshot["period_state"] == "current":
            require(
                (start, end) == (source["expected_period_start"], source["expected_period_end"]),
                "current_period_mismatch",
            )
        else:
            require(
                instant(end) <= instant(source["expected_period_start"]), "prior_period_mismatch"
            )
        require(
            computed is not None and instant(start) <= instant(computed) < instant(end),
            "computation_not_in_proven_period",
        )
    if computed is not None:
        require(instant(computed) <= instant(snapshot["captured_at"]), "future_computation")
    currency_fields = [
        snapshot[key]
        for key in (
            "currency",
            "currency_minor_units",
            "currency_policy_revision",
            "currency_evidence_event_id",
        )
    ]
    require(
        all(value is None for value in currency_fields)
        or all(value is not None for value in currency_fields),
        "currency_provenance_incomplete",
    )
    for field, availability in (
        ("observed_budget_amount", "budget_availability"),
        ("actual_spend", "actual_availability"),
        ("forecasted_spend", "forecast_availability"),
    ):
        require(
            (snapshot[field] is None) == (snapshot[availability] == "unavailable"),
            "availability_null_mismatch",
        )
        if snapshot[availability] in {"available", "stale"}:
            require(
                snapshot["period_state"] == "current"
                and snapshot["currency"] is not None
                and computed is not None
                and snapshot["fresh_until"] is not None,
                "availability_lacks_qualification",
            )


# Verify one-response copying and derive independent display states.
def financial_case(case):
    request, result, snapshot, profile = (
        case["request"],
        case["result"],
        case["snapshot"],
        case["profile"],
    )
    source = request["source"]
    require(request["payload"]["budget_id"] == source["budget_ocid"], "request_budget_mismatch")
    for key in ("operation_id", "attempt_id", "intent_revision", "execution_generation"):
        require(request["context"][key] == source[key], "request_context_mismatch")
    require(
        request["context"]["workspace_id"] == source["workspace_id"]
        and request["context"]["access_binding_id"] == source["source_access_context_id"],
        "request_context_mismatch",
    )
    require(
        instant(source["expected_period_start"]) < instant(source["expected_period_end"]),
        "expected_period_invalid",
    )
    ZoneInfo(source["billing_timezone"])
    require(
        result["source"] == source and result["context"] == request["context"],
        "response_receipt_mismatch",
    )
    require(profile["revision"] == source["source_policy_revision"], "profile_revision_mismatch")
    require(instant(result["captured_at"]) <= instant(case["as_of"]), "future_capture")
    if result["kind"] == "budget_read_unobservable":
        require(snapshot is None, "failed_read_fabricated_snapshot")
        expected_family = (
            "data_unqualified"
            if result["diagnostic_code"] == "normalization_unsupported"
            else "read_failure"
        )
        require(result["failure_category"] == expected_family, "failure_category_mismatch")
        return {
            "read_state": result["failure_category"],
            "actual": "unknown",
            "forecast": "unknown",
        }
    require(snapshot is not None and snapshot["source"] == source, "snapshot_receipt_mismatch")
    response = result["response"]
    require(
        response["budget_ocid"] == source["budget_ocid"]
        and response["owning_compartment_ocid"] == source["source_tenancy_ocid"]
        and response["target_ocids"] == [source["source_tenancy_ocid"]],
        "response_scope_mismatch",
    )
    for output, raw in (
        ("observed_budget_amount", "amount"),
        ("actual_spend", "actual_spend"),
        ("forecasted_spend", "forecasted_spend"),
        ("time_spend_computed", "time_spend_computed"),
    ):
        require(snapshot[output] == response[raw], "mixed_response_values")
    require(snapshot["captured_at"] == result["captured_at"], "mixed_capture_time")
    require(snapshot["observed_cycle_facts"] == response["cycle_facts"], "mixed_cycle_facts")
    if snapshot["period_state"] != "unknown":
        facts = response["cycle_facts"]
        require(
            facts == profile["qualified_cycle_facts"]
            and profile["cycle_qualification_event_id"] is not None
            and facts["reset_period"] == "MONTHLY"
            and facts["processing_period_type"] == "MONTH"
            and facts["budget_processing_period_start_offset"] == 1
            and facts["start_date"] is None
            and facts["end_date"] is None
            and source["billing_timezone"] == "UTC",
            "monthly_scope_unqualified",
        )
        computed = snapshot["time_spend_computed"]
        require(computed is not None, "period_missing_computation")
        stamp = instant(computed)
        start = stamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        require(
            snapshot["spend_period_start"] is not None
            and snapshot["spend_period_end"] is not None
            and instant(snapshot["spend_period_start"]) == start
            and instant(snapshot["spend_period_end"]) == end,
            "cycle_evidence_mismatch",
        )
    for field in ("currency", "currency_minor_units", "currency_evidence_event_id"):
        require(snapshot[field] == profile[field], "currency_profile_mismatch")
    expected_currency_revision = profile["revision"] if profile["currency"] else None
    require(
        snapshot["currency_policy_revision"] == expected_currency_revision,
        "currency_profile_mismatch",
    )
    computed = snapshot["time_spend_computed"]
    ages = (profile["source_max_age_seconds"], profile["retrieval_max_age_seconds"])
    if computed is None or any(value is None for value in ages):
        require(snapshot["fresh_until"] is None, "invented_freshness")
    else:
        expected_until = min(
            instant(computed) + timedelta(seconds=ages[0]),
            instant(snapshot["captured_at"]) + timedelta(seconds=ages[1]),
        )
        require(
            snapshot["fresh_until"] is not None
            and instant(snapshot["fresh_until"]) == expected_until,
            "freshness_policy_mismatch",
        )
    validate_snapshot(snapshot)
    qualified = (
        snapshot["period_state"] == "current"
        and snapshot["currency"] is not None
        and snapshot["fresh_until"] is not None
    )
    fresh = qualified and instant(case["as_of"]) <= instant(snapshot["fresh_until"])
    for field, availability in (
        ("observed_budget_amount", "budget_availability"),
        ("actual_spend", "actual_availability"),
        ("forecasted_spend", "forecast_availability"),
    ):
        expected = (
            "unavailable"
            if snapshot[field] is None
            else "unverified"
            if not qualified
            else "available"
            if fresh
            else "stale"
        )
        require(snapshot[availability] == expected, "availability_policy_mismatch")
    value = {
        key: Decimal(snapshot[key]) if snapshot[key] is not None else None
        for key in ("observed_budget_amount", "actual_spend", "forecasted_spend")
    }
    statuses = {}
    for field, label in (("actual_spend", "actual"), ("forecasted_spend", "forecast")):
        amount, budget = value[field], value["observed_budget_amount"]
        statuses[label] = (
            "unknown"
            if not fresh or amount is None or budget is None
            else "over"
            if amount > budget
            else "at"
            if amount == budget
            else "within"
        )
    scale = snapshot["currency_minor_units"]
    # Preserve exact comparisons. Expand display precision if ordinary currency rounding hides a
    # difference, instead of changing the accepted threshold or rendering equal-looking overruns.
    if scale is not None and fresh and value["observed_budget_amount"] is not None:
        unit = Decimal(1).scaleb(-scale)
        rounded_budget = value["observed_budget_amount"].quantize(unit, rounding=ROUND_HALF_UP)
        for field in ("actual_spend", "forecasted_spend"):
            amount = value[field]
            if amount is not None:
                rounded = amount.quantize(unit, rounding=ROUND_HALF_UP)
                exact_sign = (amount > value["observed_budget_amount"]) - (
                    amount < value["observed_budget_amount"]
                )
                rounded_sign = (rounded > rounded_budget) - (rounded < rounded_budget)
                if exact_sign != rounded_sign:
                    scale = 4
    return {
        "read_state": "observed",
        **statuses,
        "display_scale": scale,
        "projection_complete": fresh and all(amount is not None for amount in value.values()),
    }


# Model guarded selection only, without simulating a transaction or a database lock.
def publication_case(case):
    financial_case(case["financial"])
    source = case["financial"]["request"]["source"]
    candidate, previous = case["financial"]["snapshot"], case["previous"]
    compatible = False
    if previous:
        # Scope validation must precede every retained-value path, including failed reads.
        require(
            previous["source"]["workspace_id"] == source["workspace_id"]
            and previous["source"]["tenancy_id"] == source["tenancy_id"],
            "previous_scope_mismatch",
        )
        validate_snapshot(previous)
        compatible = all(
            previous["source"][key] == source[key]
            for key in (
                "workspace_id",
                "tenancy_id",
                "source_access_context_id",
                "source_context_generation",
                "budget_binding_id",
                "budget_binding_generation",
                "source_policy_revision",
                "source_tenancy_ocid",
                "budget_ocid",
                "expected_period_start",
                "expected_period_end",
                "scope_hash",
                "billing_timezone",
            )
        )
        if previous["source"]["collection_id"] == source["collection_id"]:
            require(previous == candidate, "collection_snapshot_conflict")
    if any(source[key] != case["live_source"][key] for key in GUARDS):
        return "obsolete_evidence"
    if candidate is None:
        return "retain_prior" if previous and compatible else "unavailable"
    if previous:
        if previous["source"]["collection_id"] == source["collection_id"]:
            return "duplicate_noop"
        # Monotonicity applies within one qualified source domain. A newer old-context value
        # cannot block the first valid read from a replacement context, binding or cycle.
        if compatible and previous["time_spend_computed"] is not None:
            old_time = instant(previous["time_spend_computed"])
            new_time = (
                instant(candidate["time_spend_computed"])
                if candidate["time_spend_computed"]
                else None
            )
            if new_time is None or new_time < old_time:
                return "retain_prior"
            if new_time == old_time and instant(candidate["captured_at"]) < instant(
                previous["captured_at"]
            ):
                return "retain_prior"
    return "select_candidate"


# Protect D50 audience and safe operation-link shape; do not infer sender authorization.
def email_intent(intent):
    addresses = [row["email"].strip().casefold() for row in intent["recipients"]]
    require(len(addresses) == len(set(addresses)), "duplicate_recipient")
    if intent["safe_payload"]["operation_detail_path"] is not None:
        require(
            intent["operation_id"] is not None
            and intent["safe_payload"]["operation_detail_path"]
            == "/operations/" + intent["operation_id"],
            "operation_link_mismatch",
        )
    if intent["notice_family"] == "lifecycle":
        require(
            intent["notice_kind"] in {"action_required", "terminal_failure"},
            "lifecycle_trigger_invalid",
        )
        responsibility = intent["responsibility"]
        require(
            responsibility is not None and len(intent["recipients"]) == 1,
            "lifecycle_recipient_count",
        )
        recipient = intent["recipients"][0]
        require(
            recipient["actor_subject"] == responsibility["responsible_actor_subject"]
            and recipient["roles"] == ["responsible_admin"]
            and intent["operation_id"] == responsibility["operation_id"],
            "lifecycle_wrong_responsible_actor",
        )
    if intent["notice_family"] == "cost_read_failure":
        require(
            intent["notice_kind"] == "cost_read_exhausted"
            and all(row["roles"] == ["admin"] for row in intent["recipients"]),
            "cost_read_recipient_scope",
        )


# Check exact recipient partition and captured service context without sending any email.
def delivery_case(case):
    intent, result = case["intent"], case["result"]
    email_intent(intent)
    require(result["notification_id"] == intent["notification_id"], "notification_mismatch")
    authorized = case["authorized_attempt_context"]
    require(result["delivery_context"] == authorized, "delivery_context_mismatch")
    require(
        all(
            authorized[key] == intent["delivery_context"][key]
            for key in intent["delivery_context"]
            if key != "credential_version_id"
        ),
        "delivery_namespace_mismatch",
    )
    expected = {row["email"].strip().casefold() for row in intent["recipients"]}
    actual = [row["email"].strip().casefold() for row in result["recipient_outcomes"]]
    require(
        len(actual) == len(set(actual)) and set(actual) == expected, "recipient_partition_mismatch"
    )
    statuses = {row["status"] for row in result["recipient_outcomes"]}
    if len(statuses) == 1:
        expected_outcome = {
            "accepted": "accepted",
            "delivered": "delivered",
            "rejected": "rejected",
            "unknown": "uncertain",
        }[next(iter(statuses))]
    else:
        expected_outcome = "partial"
    require(result["outcome"] == expected_outcome, "delivery_outcome_mismatch")
    require(
        (result["delivered_at"] is not None) == (statuses == {"delivered"}),
        "acceptance_not_delivery",
    )
    for row in result["recipient_outcomes"]:
        if row["status"] in {"accepted", "delivered"}:
            require(row["provider_reference"] is not None, "provider_reference_missing")
    return result["outcome"]


# Guard corrections against uncertain or already accepted submissions.
def routing_case(case):
    intent, live = case["intent"], case["live_responsibility"]
    email_intent(intent)
    require(intent["notice_family"] == "lifecycle", "routing_not_lifecycle")
    require(live["operation_id"] == intent["operation_id"], "routing_operation_mismatch")
    corrected = case["corrected_intent"]
    authorized = live["responsible_actor_subject"] in case["authorized_subjects"]
    changed = live != intent["responsibility"]
    if corrected:
        require(case["submission_state"] == "known_unsent", "uncertain_reroute_forbidden")
        email_intent(corrected)
        require(
            corrected["delivery_context"]["submission_key"]
            != intent["delivery_context"]["submission_key"],
            "correction_submission_key_reused",
        )
        require(
            authorized
            and corrected["responsibility"] == live
            and corrected["notification_id"] != intent["notification_id"]
            and corrected["source_event_id"] != intent["source_event_id"]
            and corrected["supersedes_notification_id"] == intent["notification_id"],
            "correction_identity_invalid",
        )
        for key in (
            "workspace_id",
            "notice_family",
            "notice_kind",
            "operation_id",
            "attention_episode_key",
        ):
            require(corrected[key] == intent[key], "correction_changes_notice")
        return "supersede_known_unsent"
    if case["submission_state"] == "uncertain":
        return "reconcile_original"
    if case["submission_state"] == "accepted":
        return "preserve_accepted"
    if not authorized or changed:
        return "blocked_no_fallback"
    return "dispatch_current_responsible"


# Dispatch the bounded design predicates while leaving schema shape to jsonschema.
def inspect_value(value):
    kind = value["kind"]
    if kind == "financial_case":
        return financial_case(value)
    if kind == "publication_case":
        return publication_case(value)
    if kind == "delivery_case":
        return delivery_case(value)
    if kind == "routing_case":
        return routing_case(value)
    if kind == "email_intent":
        email_intent(value)
    if kind == "financial_snapshot":
        validate_snapshot(value)
    return None


# Check valid examples and targeted counterexamples with artifact hashes.
def check_contracts(directory):
    paths = [
        directory / name
        for name in (
            "c5-collection-delivery.schema.json",
            "c5-collection-delivery-examples.json",
            "oci-execution.schema.json",
        )
    ]
    schema, examples, existing = [json.loads(path.read_text()) for path in paths]
    for document in (schema, existing):
        Draft202012Validator.check_schema(document)
    registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in (schema, existing)
    )
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    checks = []
    ids = [
        item["id"]
        for group in ("positive_examples", "negative_examples")
        for item in examples[group]
    ]
    require(len(ids) == len(set(ids)), "duplicate_fixture_id")
    for example in examples["positive_examples"]:
        validator.validate(example["value"])
        actual = inspect_value(example["value"])
        require(actual == example["expected"], "positive_expectation_mismatch:" + example["id"])
        checks.append({"id": example["id"], "kind": "positive", "pass": True})
    for example in examples["negative_examples"]:
        shape_errors = list(validator.iter_errors(example["value"]))
        if example["layer"] == "shape":
            require(bool(shape_errors), "negative_shape_accepted:" + example["id"])
        else:
            require(not shape_errors, "semantic_fixture_has_shape_error:" + example["id"])
            try:
                inspect_value(example["value"])
            except ValueError as error:
                require(
                    str(error) == example["expected_code"],
                    "wrong_negative_diagnostic:" + example["id"],
                )
            else:
                raise ValueError("negative_semantic_accepted:" + example["id"])
        checks.append({"id": example["id"], "kind": example["layer"], "pass": True})
    return {
        "checked_on": datetime.now(UTC).date().isoformat(),
        "status": "pass",
        "validation_kind": "design-shape-and-reference-predicates-only",
        "schema_validator": "jsonschema " + importlib.metadata.version("jsonschema"),
        "positive_examples": len(examples["positive_examples"]),
        "negative_examples": len(examples["negative_examples"]),
        "checks": checks,
        "runtime_workflows_tested": False,
        "database_transactions_tested": False,
        "provider_qualification_tested": False,
        "oci_calls": 0,
        "emails_sent": 0,
        "application_dependencies_changed": False,
        "artifact_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [*paths, directory / "oci-provider-call-inventory.json", Path(__file__)]
        },
    }


# Write a reproducible design receipt without external side effects.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "docs/contracts")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = check_contracts(args.directory)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, indent=2))


if __name__ == "__main__":
    main()
