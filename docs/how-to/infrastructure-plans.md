# Review and apply an infrastructure plan

16 November 2026 · Held source-only procedure · Requires OCI qualification before first use

[Documentation home](../README.md) · [Input/security contract](../reference/infrastructure-plans.md) ·
[Infrastructure updates](hosted-administration.md#infrastructure-update)

Plan mode generates a plan for review without applying it. The separately enabled apply mode
changes infrastructure using exactly one reviewed saved plan; it never rebuilds that plan.
Do not enable it merely to try the workflow before tenancy access is available. Local source tests
need no OCI credentials; a real dispatch needs its own approved environment, trust, IAM and bucket.

Development uses the same private plan and reviewed-apply tooling with its own fixed infrastructure root,
state, and one protected GitHub Environment for planning and applying. Follow the
[development-specific setup](laptop-oci-development.md#development-infrastructure-through-github-actions).
The setup below covers hosted staging and production.

## One-time setup in each hosted environment

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
   bundles are not ordinary plan inputs. Separately review the least resource-mutation authority
   needed for apply, plan reads and conditional attempt-marker/recovery-object writes; enabling
   plan access must not silently broaden that authority.
5. Configure the [documented variables and private JSON secrets](../reference/infrastructure-plans.md#inputs).
   Match the existing root schema. Supply the explicit target region and expected namespace, existing
   compartment, private service references, versions, CIDRs and cloud-init where required. Verify
   staging/production topology and sizing match; retain separate state, identities and private values.
6. Keep `OTM_INFRASTRUCTURE_ENABLED` and `OTM_INFRASTRUCTURE_APPLY_ENABLED` absent or false
   until their relevant trust, negative-access, credential-lifetime, state/storage and apply cases
   are qualified. Plan enablement alone does not enable apply. Use GitHub CLI 2.104.0 or newer.
   An administrator must explicitly authorize first OCI-backed qualification; source implementation
   is not that authorization. Production requires its own effective Environment approval policy.

## Generate and review

After setup and authorized live qualification:

1. Open **Actions → Staging infrastructure** or **Production infrastructure**. Select
   protected master, `operation=plan`, then `security` or `platform`. Security is normally planned before platform
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
6. Preserve the exact private plan and review evidence. A successful plan or private object key
   alone does not authorize apply. Continue only through the separately enabled reviewed-plan
   consumer below after the required approval; do not improvise a direct Terraform apply.

CLI dispatch is equivalent to the Actions form after the same setup/approval:

```sh
gh workflow run infra-staging.yml --ref master -f operation=plan -f component=security
gh workflow run infra-production.yml --ref master -f operation=plan -f component=platform
```

These commands are not local smoke tests: an enabled configured workflow contacts OCI. Do not run
them against an unqualified environment or infer readiness from an empty/automatically created
GitHub Environment.

## Apply staging, test explicitly, then review production

This is a held source procedure, not permission to create OCI resources now. After separately
approved setup/qualification, enable apply deliberately in the selected Environment in addition to
plan enablement. Plan jobs have 30-minute limits, 60-minute tokens and a shared 20-minute Terraform
budget; apply jobs use 90-minute limits, 120-minute tokens and a shared 75-minute Terraform budget.
Approval occurs before federation; do not wait for manual review inside a live credential window.

1. For staging, select `operation=apply`, the same component, its successful `plan_run_id` and
   the exact privately reviewed `reviewed_plan_sha256`. Ensure protected master still identifies
   the plan's exact source. Changed source or inputs requires a fresh reviewed plan. The consumer
   authenticates native GitHub run/attempt/job-log evidence, private receipt and binary hash before
   using the own-environment backend; bucket contents alone are not trusted provenance.
2. Obtain staging Environment approval. The consumer checks current rendered inputs, native plan
   counts and locking, then conditionally claims the plan once before applying its exact binary.
   Record the successful apply run and safe result hashes. Do not rerun the consuming job against
   that plan, even if a timeout or lost response hides whether it started.
3. Perform the required staging tests on the actual applied component: relevant topology/sizing,
   versions, node image/IMDSv1 refusal, permissions, connectivity, backup/recovery and application
   compatibility. Retain restricted test evidence. A successful Terraform apply is not a test pass.
4. Generate production's **own** plan from the identical source and shared versions/sizing, with
   production identities/state/private inputs. For platform, supply the complete qualified staging
   ARM image selection. Review all production changes and the explicit
   [automatic parity whitelist and its limits](../reference/infrastructure-plans.md#production-staging-gate-and-exact-parity-whitelist).
   Same source does not justify copying staging secrets, state or its binary plan into production.
5. Select production `operation=apply`, production `plan_run_id`, its reviewed hash, the successful
   same-source/component `staging_apply_run_id` and `staging_tests_confirmed=true` only after those
   tests passed. This is an explicit human confirmation, not automated test-proof verification.
   Obtain protected production Environment approval before credentials or mutation. If the source,
   inputs or tested outcome changed, stop and repeat the appropriate staging/plan/review steps.
6. Confirm the applied production topology, node-image identity and safe live health independently.
   Preserve the plan/apply/approval/test references privately. Infrastructure apply does not deploy
   the application, qualify staging acceptance for an app release or change the saved Atlas instance.

The Actions forms are preferred for reviewing all inputs. Equivalent fixed commands after approval:

```sh
gh workflow run infra-staging.yml --ref master -f operation=apply -f component=platform \
  -f plan_run_id=STAGING_PLAN_RUN -f reviewed_plan_sha256=REVIEWED_STAGING_HASH
gh workflow run infra-production.yml --ref master -f operation=apply -f component=platform \
  -f plan_run_id=PRODUCTION_PLAN_RUN -f reviewed_plan_sha256=REVIEWED_PRODUCTION_HASH \
  -f staging_apply_run_id=SUCCESSFUL_STAGING_APPLY_RUN -f staging_tests_confirmed=true
```

## Failed or interrupted apply: investigate, never replay

The conditional `apply-attempt.json` beside the producer's plan is permanent. Never delete it to
retry, change the consuming run ID to evade it or assume a failed job rolled infrastructure back.
Inspect actual OCI effects, remote state/locks and the selected run with authorized private tools;
reconcile uncertainty, then generate and review a **fresh plan** before another apply attempt.
Native Terraform stale-plan and locking failures remain stops, not permission to force execution.

If backend state saving fails, Terraform may leave `errored.tfstate`. The consumer best-effort
retains that native recovery file privately beside the selected plan; the public failure reports
only whether retention succeeded. If retained, inspect/reconcile it through the separately
approved manual state-repair procedure. If not retained, investigate actual state/provider effects
without assuming recovery bytes exist. No automatic state push, edit, restore, marker clearing or
second apply occurs. Exclude attempt markers and unresolved recovery state from obsolete-plan cleanup.

## Failure and retained custody

Plan failure output includes a fixed stage and may include a numeric HTTP status from 400
through 599. It omits raw Terraform and provider output, request URLs, credentials, and private configuration.
Check the selected root/input format, environment protection, current client secret, exact trust
claims, intended IAM grants and private state bucket with separately authorized operator tools.
Do not print secrets, weaken TLS, add an API-key fallback, disable state locking or make the bucket
public. A wrong source, expired/mismatched token, unknown action kind or insufficient access must stop.

If upload may have succeeded before the response was lost, inspect the exact run/attempt object
before retrying. New attempts use separate object keys; do not overwrite a reviewed plan. A retry
creates a new plan and review context. Neither plan is applied automatically. If an apply marker
exists or an apply might have started, investigate before generating another plan; do not reuse
the consumed plan or remove its marker.
Normal temporary-file cleanup is tested, while hard-cancellation/runner-loss behavior remains live
qualification. After a change is retired, an authorized operator may clean its obsolete objects
only under `infrastructure-plans/`, retaining required change evidence privately. Keep all apply
attempt markers and unresolved recovery-state objects. Never delete state, state versions or lock
objects as plan cleanup. No automated plan-retention service is introduced.

## Local checks without OCI

```sh
uv run --project backend pytest -q backend/tests/test_infrastructure_plan.py \
  backend/tests/test_infrastructure_apply.py backend/tests/test_caddy_image_policy.py
uv run --project backend python scripts/check_inline_docs.py
uv run --project backend python scripts/check_design_docs.py
bash scripts/check_infrastructure.sh
```

Tests use synthetic environment values, temporary private files, real local key generation and
mocked external exchange/SDK/Terraform orchestration. Native Terraform mocks independently validate
the existing roots. They do not exercise a hosted OAuth secret, OCI IAM, remote state or actual plan
upload or actual reviewed-plan apply. Keep those cases Pending in
[the live qualification manifest](real-oci-test-manifest.md). Apply regression/qualification scope
is recorded in [the test policy](../engineering-test-plan.md#reviewed-infrastructure-apply-source--16-november-2026);
the earlier plan-only checkpoint counts do not qualify this new consumer.
