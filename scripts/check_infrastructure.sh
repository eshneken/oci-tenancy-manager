#!/usr/bin/env bash
# Validate all infrastructure composition using fixed, mock-only Terraform test suites.
set -euo pipefail
umask 077
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

terraform fmt -check -recursive infra
for root in \
  infra/environments/development/bootstrap \
  infra/environments/development/custody \
  infra/modules/state-bootstrap \
  infra/environments/staging/bootstrap \
  infra/environments/production/bootstrap \
  infra/modules/networking \
  infra/modules/oke \
  infra/modules/postgresql \
  infra/modules/secret-foundation \
  infra/modules/workload-vault-access \
  infra/modules/application-registration \
  infra/environments/staging/security \
  infra/environments/production/security \
  infra/environments/staging/platform \
  infra/environments/production/platform; do
  # Do not initialize a real state backend or permit dependency-lock rewrites in a check.
  terraform -chdir="$root" init -backend=false -lockfile=readonly -input=false -no-color
  terraform -chdir="$root" validate -no-color
  terraform -chdir="$root" test -no-color
done

# prevent_destroy errors are not native test assertion failures, so require the exact negative
# journey: mock setup succeeds, the replacement plan fails, and the lifecycle guard is the reason.
guard_log="$(mktemp "${TMPDIR:-/tmp}/otm-state-guard.XXXXXX")"
trap 'rm -f -- "$guard_log"' EXIT
# Require the intended mock setup and exact guard error; an unrelated test failure never passes.
check_replacement_guard() {
  local test_root="$1"
  local seed_run="$2"
  local replacement_run="$3"
  local test_directory="${4:-guard-tests}"
  local expected_address="${5:-}"
  if terraform -chdir="$test_root" test -test-directory="$test_directory" -no-color >"$guard_log" 2>&1; then
    cat "$guard_log"
    echo "ERROR: replacement guard did not block the plan in $test_root." >&2
    exit 1
  fi
  if ! grep -F "run \"$seed_run\"... pass" "$guard_log" >/dev/null ||
     ! grep -F "run \"$replacement_run\"... fail" "$guard_log" >/dev/null ||
     ! grep -F 'Instance cannot be destroyed' "$guard_log" >/dev/null; then
    cat "$guard_log"
    echo 'ERROR: negative test failed for a reason other than the required lifecycle guard.' >&2
    exit 1
  fi
  # A parent replacement can also hit child guards; require the intended resource's own rejection.
  if [[ -n "$expected_address" ]] && ! grep -F "Resource $expected_address has" "$guard_log" >/dev/null; then
    cat "$guard_log"
    echo 'ERROR: lifecycle rejection did not identify the intended protected resource.' >&2
    exit 1
  fi
  echo "Replacement guard passed: $test_root (expected lifecycle rejection, mocked OCI only)."
}
check_replacement_guard infra/modules/state-bootstrap seed_mock_bucket reject_bucket_replacement
check_replacement_guard infra/modules/oke seed_mock_cluster reject_cluster_replacement

check_replacement_guard infra/modules/postgresql seed_mock_database reject_database_replacement

check_replacement_guard infra/modules/secret-foundation seed_mock_vault reject_vault_replacement guard-vault 'oci_kms_vault.domain["database-provisioning"]'
check_replacement_guard infra/modules/secret-foundation seed_mock_key reject_key_replacement guard-key 'oci_kms_key.domain["database-provisioning"]'

# Development custody has the same immutable-vault/key safeguards without a hosted platform.
check_replacement_guard infra/environments/development/custody seed_mock_vault reject_vault_replacement guard-vault 'oci_kms_vault.application'
check_replacement_guard infra/environments/development/custody seed_mock_key reject_key_replacement guard-key 'oci_kms_key.application_software'

check_replacement_guard infra/modules/networking seed_mock_ingress reject_ingress_address_replacement guard-ingress 'oci_core_public_ip.ingress[0]'
