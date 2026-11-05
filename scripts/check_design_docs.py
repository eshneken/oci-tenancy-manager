"""Validate cross-tier design links, explicit authoring fields and proposed ER inventory."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from documentation_links import check_index, check_links

root = Path(__file__).resolve().parents[1]

files, links, errors = check_links(root)
errors.extend(check_index(root))
for file in files:
    if file.suffix == ".md" and len(re.findall(r"^```", file.read_text(), re.MULTILINE)) % 2:
        errors.append(f"{file.name}: unbalanced fences")
config = (root / "docs/engineering-design/10-configuration-data-model.md").read_text()
combined = (root / "docs/engineering-design/11-production-data-model.md").read_text() + config
sources = [
    root / "docs/architecture/diagrams" / f"{slug}.mmd"
    for slug in [
        "configuration-data-model-proposed",
        "production-core-access-proposed",
        "production-finance-proposed",
        "application-administrators-proposed",
    ]
]
config_source = sources[0].read_text()
fields = [
    "policy_statements",
    "quota_statements",
    "monthly_budget_amount",
    "budget_currency",
    "budget_period",
    "tag_namespace",
    "tag_defaults",
    "policy_override_statements",
    "quota_override_statements",
    "monthly_budget_override_amount",
    "required_policy_manifest",
    "required_policy_manifest_hash",
    "policy_render_contract_version",
]
for field in fields:
    if field not in config or field not in config_source:
        errors.append(f"Missing explicit configuration field {field}")
for field in [
    "tenancy_ocid",
    "home_region_key",
    "home_region_identifier",
    "provider_ocid",
    "coverage_subject_kind",
    "coverage_subject_key",
]:
    if field not in combined or field not in config_source:
        errors.append(f"Missing registry/identity/coverage field {field}")
human_access = (
    root / "docs/engineering-design/13-local-support-and-emergency-access.md"
).read_text()
core_source = sources[1].read_text()
human_access_fields = [
    "requester_snapshot",
    "lifetime_policy_version",
    "duration_seconds",
    "deadline_anchor",
    "domain_metadata",
]
for field in human_access_fields:
    if field not in human_access or field not in combined or field not in core_source:
        errors.append(f"Missing explicit human access field {field}")
# D40 removes temporary-account ownership; a historical note must not reintroduce these ER fields.
grant_entity = re.search(r"  otm_human_access_grant \{(.*?)\n  \}", core_source, re.DOTALL)
assignment_entity = re.search(r"  otm_access_assignment \{(.*?)\n  \}", core_source, re.DOTALL)
if not grant_entity or not assignment_entity:
    errors.append("Missing D40 disclosure/assignment entities")
else:
    for field in [
        "kind",
        "desired_access_assignment_id",
        "cleanup_operation_id",
        "verified_revocation_at",
    ]:
        if re.search(r"^\s+\w+ " + field + r"(?:\s|$)", grant_entity[1], re.MULTILINE):
            errors.append(f"D40 disclosure request retains temporary-account field {field}")
    if "human_access_grant_id" in assignment_entity[1]:
        errors.append("D40 access assignment retains temporary-grant ownership")
    for field in [
        "credential_id",
        "disclosed_version_id",
        "window_root_grant_id",
        "exposure_generation",
        "due_at",
    ]:
        if field not in grant_entity[1]:
            errors.append(f"Missing D40 disclosure/window field {field}")

# Match full HTML asset references: access-walkthrough.js is also a suffix of the human script.
for name in [
    "access-walkthrough.html",
    "human-access-walkthrough.html",
    "financial-walkthrough.html",
]:
    html_path = root / "docs/walkthroughs" / name
    for asset, version in re.findall(
        r'(?:src|href)=["\']([^"\'?]+)\?v=([a-f0-9]+)["\']', html_path.read_text()
    ):
        asset_path = html_path.parent / asset
        if not asset_path.exists() or not hashlib.sha256(
            asset_path.read_bytes()
        ).hexdigest().startswith(version):
            errors.append(f"{name}: stale asset fingerprint for {asset}")

# D41's one-response snapshot is explicit in storage, the screen map and the ER source.
finance_source = sources[2].read_text()
finance_journeys = (root / "docs/engineering-design/14-financial-journeys.md").read_text()
financial_fields = [
    "budget_binding_id",
    "budget_binding_generation",
    "budget_ocid",
    "observed_budget_amount",
    "actual_spend",
    "forecasted_spend",
    "time_spend_computed",
]
for field in financial_fields:
    if field not in combined or field not in finance_source or field not in finance_journeys:
        errors.append(f"Missing D41 financial source/snapshot field {field}")
provider_inventory = json.loads(
    (root / "docs/contracts/oci-provider-call-inventory.json").read_text()
)
actual_scopes = Counter(call["design_scope"] for call in provider_inventory["calls"])
if dict(actual_scopes) != provider_inventory["design_scope_counts"]:
    errors.append("Provider call-inventory scope counts are stale")
for call in provider_inventory["calls"]:
    if (
        call["call"].startswith("oci.usage_api.")
        and call["design_scope"] != "reference_only_not_v1"
    ):
        errors.append("D41 Usage API call remains selected for V1")

# A reviewed receipt must describe the exact current artifacts, not an earlier successful run.
c5_guide = (root / "docs/engineering-design/16-c5-contract-review.md").read_text()
c5_receipt = json.loads(
    (root / "docs/contracts/receipts/c5-contract-checks-2026-10-28.json").read_text()
)
c5_schema = json.loads((root / "docs/contracts/c5-collection-delivery.schema.json").read_text())
for artifact, expected_hash in c5_receipt["artifact_sha256"].items():
    path = root / artifact
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        errors.append(f"C5 receipt is stale for {artifact}")
c5_examples = json.loads((root / "docs/contracts/c5-collection-delivery-examples.json").read_text())
for group, count_field in (
    ("positive_examples", "positive_examples"),
    ("negative_examples", "negative_examples"),
):
    if len(c5_examples[group]) != c5_receipt[count_field]:
        errors.append(f"C5 receipt count does not match {group}")
if c5_receipt["status"] != "pass" or not all(row["pass"] for row in c5_receipt["checks"]):
    errors.append("C5 receipt does not record a complete passing review")
for field in (
    "period_evidence",
    "currency_minor_units",
    "authorized_attempt_context",
    "supersedes_notification_id",
):
    if field not in c5_guide:
        errors.append(f"C5 field-map coverage missing {field}")
budget_models = [
    model for model in provider_inventory["models"] if model["model"] == "oci.budget.models.Budget"
]
cycle_fields = c5_schema["$defs"]["BudgetCycleFacts"]["properties"]
if len(budget_models) != 1 or not set(cycle_fields) <= set(budget_models[0]["fields"]):
    errors.append("C5 monthly source fields lack one pinned Budget model inventory")


# D54 keeps current password resolution distinct from immutable audit and in-flight candidates.
restore_design = (root / "docs/engineering-design/17-recovery-and-release.md").read_text()
for field in ("vault_secret_ocid", "current_version_id", "staged_version_id"):
    if field not in restore_design or field not in combined:
        errors.append(f"D54 credential field lacks narrative/model mapping: {field}")
if 'stage="CURRENT"' not in human_access or 'stage="CURRENT"' not in restore_design:
    errors.append("D54 normal password CURRENT selection is missing")
for source in sources[1:]:
    if re.search(
        r"^    (?:bigint recovery_epoch|string recovery_state)$", source.read_text(), re.MULTILINE
    ):
        errors.append(f"Withdrawn recovery mirror remains in {source.name}")

new = set()
for source in sources:
    new.update(re.findall(r"^  (otm_\w+) \{", source.read_text(), re.MULTILINE))
if len(new) != 20:
    errors.append(f"Expected 20 proposed new application tables including D58, found {len(new)}")
# D58 adds two authority/credential tables, retaining the same session and audit entities.
admin_source = root / "docs/architecture/diagrams/application-administrators-proposed.mmd"
admin_model = admin_source.read_text()
admin_design = (root / "docs/engineering-design/19-administrator-provisioning.md").read_text()
admin_fields = (
    "otm_administrator",
    "otm_local_credential",
    "authorization_revision",
    "identity_kind",
    "password_hash",
    "totp_secret_reference",
    "last_totp_step",
    "mfa_enrolled_at",
    "password_changed_at",
    "failed_attempts",
    "failure_window_started_at",
    "retry_after",
    "administrator_id",
    "entitlement_reference",
    "entitlement_revision",
)
for field in admin_fields:
    if field not in admin_model or field not in admin_design or field not in combined:
        errors.append(f"D58 administrator field lacks model/design coverage: {field}")
if f"```mermaid\n{admin_model.rstrip()}\n```" not in admin_design:
    errors.append("D58 inline ER differs from its diagram source")
spec = (root / "docs/product/oci-tenancy-manager-spec.md").read_text()
if not spec.startswith("# OCI Tenancy Manager\n") or "engineering intake" not in spec[:200].lower():
    errors.append("Product spec header was replaced or renamed without updating its contract")
for number in range(1, 15):
    if not re.search(r"^## " + str(number) + r"\. ", spec, re.MULTILINE):
        errors.append(f"Missing product-spec section {number}")
criteria = re.findall(r"^\| AC(\d+)(?: \(V2\))? \|", spec, re.MULTILINE)
if len(criteria) < 77 or len(criteria) != len(set(criteria)):
    errors.append("Product acceptance criteria missing or duplicated; D54 requires AC01–AC77")
if {int(value) for value in criteria} != set(range(1, len(criteria) + 1)):
    errors.append("Product acceptance criteria IDs are not contiguous")
# Accepted recovery objectives must agree across the nondeployable example and model authority.
recovery_example = json.loads(
    (root / "docs/contracts/platform-recovery-policy.example.json").read_text()
)
recovery_policy = recovery_example["workspace_runtime_policy_fragment"]["recovery"]
expected_recovery = {
    "objectives_revision": "d51-d52-v1",
    "rpo_seconds": 900,
    "rto_seconds": 14400,
    "disaster_scope": "in_region",
}
if recovery_policy != expected_recovery:
    errors.append("D51/D52 recovery example diverges from accepted objectives/scope")
if recovery_example["artifact_kind"] != "design_example_not_runtime_configuration":
    errors.append("Recovery example incorrectly claims to be runtime configuration")
for field in expected_recovery:
    if field not in combined:
        errors.append(f"Recovery objective lacks existing runtime-policy model mapping: {field}")
platform = (root / "docs/engineering-design/06-platform-and-delivery.md").read_text()
for field in (
    "incident_started_at",
    "recovered_contiguous_through_at",
    "read_only_ready_at",
    "safe_service_ready_at",
    "measured_rpo_seconds",
    "measured_rto_seconds",
):
    if field not in platform:
        errors.append(f"Recovery measurement field missing from evidence contract: {field}")

print(
    json.dumps(
        {
            "documents": len(files),
            "local_links": links,
            "explicit_configuration_fields": len(fields),
            "explicit_human_access_fields": len(human_access_fields),
            "explicit_financial_snapshot_fields": len(financial_fields),
            "c5_positive_examples": c5_receipt["positive_examples"],
            "c5_negative_controls": c5_receipt["negative_examples"],
            "recovery_objectives": recovery_policy,
            "new_application_tables": len(new),
            "existing_application_tables": 10,
            "errors": errors,
        },
        indent=2,
    )
)
raise SystemExit(bool(errors))
