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

## One infrastructure plan and apply per environment

One local [operator bootstrap](terraform-state-bootstrap.md) establishes the delivery foundation
for each environment. Hosted staging and production compose custody, networking, OKE, PostgreSQL,
IAM and SSO inside their own `infrastructure` roots and remote states. Development uses its
smaller infrastructure root and retains its existing state. Staging can use the previously
established shared non-production foundation and external Oracle SSO. Production uses independent
delivery and OCI state. Hosted source is implemented and remains held pending live qualification.
Staging dispatch stays disabled until the shared domain has a qualified
[client-bound exchange](terraform-state-bootstrap.md#github-exchange-client-rollout).

### Staging composed plan and apply

First staging acceptance requires one protected plan for the complete staging root and one
approved apply of that exact saved plan. The root provisions the database bootstrap secret
through Vault service-side generation and connects its immutable reference/version to PostgreSQL.
The approved delivery foundation exists before dispatch. Staging resource dependencies are resolved
during the same infrastructure apply. Record the run IDs, exact plan hash, state scope and
readback/acceptance evidence. Use the
[acceptance design](../engineering-design/24-environments-and-promotion.md#staging-infrastructure-acceptance).

## One-time setup in each hosted environment

1. Review the [operator bootstrap](terraform-state-bootstrap.md) and preserve its private state.
   Verify the target tenancy, namespace, compartment and versioned private bucket. Qualify the
   Terraform-owned GitHub environment protection and exact OCI token-exchange client/trust.
   Verify the [sealed input handoff](terraform-state-bootstrap.md#github-environment-and-protected-inputs), issuer, audience, exact
   repository/workflow/environment claims, effective isolation and denied unrelated access.
2. Prepare the private settings file for the bootstrap's [protected workflow inputs](../reference/infrastructure-plans.md#inputs).
   Verify tenancy, target, shared version/topology and environment-specific private inputs.
   The workflow reads a fresh version of the inputs before applying the exact reviewed binary.
3. Check for earlier `security/<environment>/terraform.tfstate` and
   `platform/<environment>/terraform.tfstate` objects. The hosted preflight stops if either
   object exists, even if its state contains no resources. Review and reconcile an empty
   object separately. If the state owns resources, use an independently reviewed migration or
   import plan and private backups to reconcile addresses, dependencies and ownership.
   Verify the retained resources in a composed follow-up plan. Preserve old history and keep
   each resource under one writable state. Never point the composed root at either old key.
4. Keep `OTM_INFRASTRUCTURE_ENABLED` and `OTM_INFRASTRUCTURE_APPLY_ENABLED` false until separately
   authorized. Qualify backend and state locks, credential lifetime, denied access, OCI service
   permissions and generated-secret/DB reference behavior before a live hosted apply. CI source
   tests do not establish effective IAM. Production requires its own approvals.

## Generate and review

1. After live plan approval, open **Actions → Staging infrastructure** or
   **Production infrastructure**, choose protected `master` and select `operation=plan`.
   Each workflow fixes its root, environment and backend. There is no component selector.
2. The environment reviewer approves before the runner exchanges identity. On success, record
   source/run/attempt, counts, private-input digest, binary-plan digest and private object key.
3. Retrieve only that exact plan bundle into an owner-only operator directory. Confirm its two
   expected files and reviewed hash before inspecting it. Use the pinned Terraform version and
   reviewed source to inspect the full plan privately. Keep private inputs, raw plan and state
   out of GitHub comments and artifacts.
4. Review the complete effects, including IAM, secret generation and state scope. Stop for any
   unexpected changes, replacements or deletions. Retain restricted review evidence.

## Apply staging, test explicitly, then review production

Live execution requires separate approval. Planning jobs use a 30-minute job limit and 20-minute
Terraform budget. Apply jobs use a 90-minute job limit and 75-minute Terraform budget. Approval
occurs before federation.

1. Select `operation=apply`, the exact successful `plan_run_id` and privately reviewed
   `reviewed_plan_sha256`. Use the same protected source and private inputs. Changed context
   requires a fresh plan and review.
2. Approve the environment dispatch. The consumer verifies source/run/attempt, inputs, receipt
   and plan hash, claims the producer plan once, and applies the exact saved binary. Record the
   run and restricted resource evidence. An uncertain apply requires reconciliation and a
   fresh reviewed plan.
3. Test staging's actual resources, including topology, versions, IAM grants and denials,
   networking, IMDSv1 refusal, generated Vault secret reference, PostgreSQL and backup/recovery.
   Qualify app deployment and compatibility separately.
4. Generate production's own plan from the same reviewed source and qualified staging versions,
   sizing and image. Preserve independent state, inputs and approval. Review the
   [parity whitelist](../reference/infrastructure-plans.md#production-staging-gate-and-exact-parity-whitelist).
5. Production apply also requires the successful `staging_apply_run_id` and
   `staging_tests_confirmed=true` after those tests pass. This is a human confirmation.

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
