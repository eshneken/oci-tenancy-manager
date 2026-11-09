"""Synthetic authored repair examples shared by unit, SQL and native browser qualification."""

from decimal import Decimal

from test_baseline_authoring import PAYLOAD

from otm.configuration.override_contracts import OverrideValues

POLICY_OVERRIDE = (
    "Allow group ExampleOverride to inspect instances in tenancy",
    "Allow group ExampleOverride to read buckets in tenancy\nwhere request.region='example'",
)
QUOTA_OVERRIDE = (
    "set example quota example-count to 3 in tenancy",
    "set example quota other-count to 5 in tenancy",
)
OVERRIDES = OverrideValues(
    policy_override_statements=POLICY_OVERRIDE,
    quota_override_statements=QUOTA_OVERRIDE,
    monthly_budget_override_amount=Decimal("650"),
)
# These literal expected payloads independently express authored values and inherited tag behavior.
BASELINE_PAYLOADS = {
    "policy": {"statements": PAYLOAD["policy_statements"]},
    "quota": {"statements": PAYLOAD["quota_statements"]},
    "budget": {"monthly_amount": "200.0000", "currency": "USD", "period": "MONTHLY"},
    "tags": {"namespace": "OTM", "defaults": [{"key": "Environment", "value": "Test"}]},
}
OVERRIDE_PAYLOADS = {
    "policy": {"statements": list(POLICY_OVERRIDE)},
    "quota": {"statements": list(QUOTA_OVERRIDE)},
    "budget": {"monthly_amount": "650.0000", "currency": "USD", "period": "MONTHLY"},
    "tags": BASELINE_PAYLOADS["tags"],
}
CHANGED_PAYLOADS = {
    "policy": {"statements": ["Allow group ExampleChanged to read buckets in tenancy"]},
    "quota": {"statements": ["set example quota example-count to 1 in tenancy"]},
    "budget": {"monthly_amount": "25.0000", "currency": "USD", "period": "MONTHLY"},
    "tags": {"namespace": "OTM", "defaults": [{"key": "Environment", "value": "Changed"}]},
}
