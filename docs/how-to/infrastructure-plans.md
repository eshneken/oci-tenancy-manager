# Prepare an infrastructure plan

16 November 2026 · Held source-only procedure · Requires OCI qualification before first use

[Documentation home](../README.md) · [Input/security contract](../reference/infrastructure-plans.md) ·
[Infrastructure updates](hosted-administration.md#infrastructure-update)

This procedure generates a plan for review. It does not install, upgrade or delete infrastructure.
Do not enable it merely to try the workflow before tenancy access is available. Local source tests
need no OCI credentials; a real dispatch needs its own approved environment, trust, IAM and bucket.

## One-time setup in each environment

1. Complete the separately reviewed [state bootstrap](terraform-state-bootstrap.md). Preserve its
   private operator state. The expected versioned, private state bucket must already exist in the
   selected environment's existing hosting compartment. Bootstrap is not a workflow component.
2. Configure GitHub Environments `staging` and `production` separately. Restrict deployment refs to
   protected master and require an available human reviewer. Confirm the protections actually apply
   on this repository/account. Do not assume that declaring an environment in YAML protects it.
3. Use separate privileged setup authority to configure the identity domain's GitHub issuer/JWKS,
   audience and exact immutable repository/owner/environment/master/workflow claims described in
   the [reference](../reference/infrastructure-plans.md#federation-contract). Register a restricted
   token-exchange OAuth client without identity-domain administrator roles, and put its own client
   secret in that environment. Never use a child-tenancy or application credential as the CI identity.
4. Qualify effective IAM for that external principal: intended discovery/resource reads, state
   read/locking and conditional plan-object writes only within its environment. Deny the other
   environment, unrelated state, application secrets and trust administration. Runtime secret
   bundles are not ordinary plan inputs. Add apply authority only as a separately reviewed future step.
5. Configure the [documented variables and private JSON secrets](../reference/infrastructure-plans.md#inputs).
   Match the existing root schema. Supply the explicit target region and expected namespace, existing
   compartment, private service references, versions, CIDRs and cloud-init where required. Verify
   staging/production topology and sizing match; retain separate state, identities and private values.
6. Keep `OTM_INFRASTRUCTURE_ENABLED` absent or false until the manifest's trust, negative-access,
   credential-lifetime, state and private-storage cases are qualified. An administrator must explicitly
   authorize any first OCI-backed run; source implementation is not that authorization.

## Generate and review

After setup and authorized live qualification:

1. Open **Actions → Plan staging infrastructure** or **Plan production infrastructure**. Select
   protected master, then `security` or `platform`. Security is normally planned before platform
   because platform inputs reference separately established custody. Select the correct fixed
   workflow; there is no arbitrary environment, source-ref or state-path input.
2. Obtain the configured environment approval. The job then requests temporary GitHub/OCI identity;
   no credential is minted while waiting for approval. Keep the job running normally. Do not cancel
   it merely to resolve a Terraform lock or start a competing change.
3. On success, record the source/run/attempt, counts, private-input digest, binary-plan digest and
   relative private object key from its JSON result. This is a **plan**, not a staging acceptance or
   apply result. Unexpected replacements/deletions are a stop, even if Terraform exited successfully.
4. With authorized operator credentials, retrieve only that exact object from the selected tenancy's
   private state bucket into an owner-only directory outside the checkout. Never paste it into
   GitHub comments, upload it as an artifact or attach raw output to a public issue. Confirm the
   two expected regular archive members and plan hash before inspecting it; do not extract arbitrary
   archive paths or execute downloaded content. Use the pinned Terraform version and reviewed source
   to inspect `terraform show` privately. Public action counts alone are insufficient review.
5. Review complete resource changes, data references, backend/state target and maintenance impact.
   For production, retain independent evidence that this source/version/image/topology was qualified
   in staging. Generate production's own plan; never reuse staging's binary plan or state.
6. Stop here. **The controlled apply consumer is not implemented in this checkpoint.** Preserve the
   exact private plan and review evidence for that next step. Neither a successful workflow nor the
   private object key authorizes an improvised apply, direct state edit or automatic production update.

CLI dispatch is equivalent to the Actions form after the same setup/approval:

```sh
gh workflow run infra-staging.yml --ref master -f component=security
gh workflow run infra-production.yml --ref master -f component=platform
```

These commands are not local smoke tests: an enabled configured workflow contacts OCI. Do not run
them against an unqualified environment or infer readiness from an empty/automatically created
GitHub Environment.

## Failure and retained custody

The public fixed error intentionally omits raw Terraform/provider output and private configuration.
Check the selected root/input format, environment protection, current client secret, exact trust
claims, intended IAM grants and private state bucket with separately authorized operator tools.
Do not print secrets, weaken TLS, add an API-key fallback, disable state locking or make the bucket
public. A wrong source, expired/mismatched token, unknown action kind or insufficient access must stop.

If upload may have succeeded before the response was lost, inspect the exact run/attempt object
before retrying. New attempts use separate object keys; do not overwrite a reviewed plan. A retry
creates a new plan and review context. The source does not automatically apply either object.
Normal temporary-file cleanup is tested, while hard-cancellation/runner-loss behavior remains live
qualification. After a change is retired, an authorized operator may clean its obsolete objects
only under `infrastructure-plans/`, retaining required change evidence privately. Never delete state,
state versions or lock objects as plan cleanup. No automated plan-retention service is introduced.

## Local checks without OCI

```sh
uv run --project backend pytest -q backend/tests/test_infrastructure_plan.py \
  backend/tests/test_caddy_image_policy.py
uv run --project backend python scripts/check_inline_docs.py
uv run --project backend python scripts/check_design_docs.py
bash scripts/check_infrastructure.sh
```

Tests use synthetic environment values, temporary private files, real local key generation and
mocked external exchange/SDK/Terraform orchestration. Native Terraform mocks independently validate
the existing roots. They do not exercise a hosted OAuth secret, OCI IAM, remote state or actual plan
upload. Keep those cases Pending in [the live qualification manifest](real-oci-test-manifest.md).
