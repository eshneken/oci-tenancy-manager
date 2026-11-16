# Verify an immutable ARM64 application release

16 November 2026 · Native ARM publication and genuine signatures verified · OCI qualification separate

The [release contract](../reference/artifact-releases.md) binds two immutable image digests, their
SBOMs, public deployment source, installed schema contract and exact source/build identity. The
verifier authenticates those artifacts through GitHub's standard attestation verifier. It never
deploys, modifies application data or declares a candidate accepted by staging.

## How the publishing workflow selects a build

`.github/workflows/build-application.yml` follows a successful same-repository master-push
Checkpoint. There is no manual dispatch input for an arbitrary SHA or pass flag. The triggering
head SHA must equal the publishing workflow SHA, and the helper independently checks the exact
Checkpoint run and all five required successful jobs. A delayed Checkpoint for older master may
be skipped; do not remove that source check to force publication.

The native ARM runner builds app and Caddy images once each from a committed Git archive. It checks
ARM64 and the app's installed migration/settings contract, scans exact saved image bytes, generates
CycloneDX inventories and publishes immutable GHCR digests. The app has no vulnerability exceptions;
Caddy has only its [two exact accepted availability findings](../reference/caddy-security-exceptions.md).
The job publishes provenance and SBOM attestations and four public files. It has no OCI/Kubernetes
or staging/production deployment authority. Do not run the publisher from a laptop using copied
Actions tokens.

## Download the four public files

Choose the successful build run from trusted GitHub records; require its protected source and
successful Checkpoint. Use an empty directory under ignored `.local-dev/`. Replace the uppercase
placeholders below with the selected repository, numeric build run ID and exact artifact name
`application-release-{source-prefix}-{build-run}-{attempt}`:

```sh
umask 077
gh run download BUILD_RUN_ID --repo OWNER/REPOSITORY \
  --name APPLICATION_RELEASE_ARTIFACT --dir .local-dev/release-review
```

The directory must contain exactly `release.json`, `deployment-source.tar`, `application.cdx.json`
and `caddy.cdx.json`. Keep signatures/receipts or other notes elsewhere; extra files are rejected.
This manual acquisition path is separate from verification; the optional automatic path below
performs both steps in a disposable directory. Never execute source inside the
downloaded tar or substitute a workspace dump. The source archive is seven public files plus the
generated settings schema, not a ready-to-apply environment render or standalone installer.

## Verify without deploying

Use GitHub CLI **2.102.0 or newer**, authenticated for the expected repository and registry reads.
The minimum includes the [attestation ref-matching fix](https://github.com/cli/cli/security/advisories/GHSA-4mq3-hpgx-9cx8).
Registry authentication, if required, must already exist through approved host/CI credential handling;
never put tokens in CLI arguments, tracked files or output. The verifier does not sign in or fall
back to unsigned evidence.

```sh
uv run --project backend python scripts/verify_application_release.py \
  --directory .local-dev/release-review --repository OWNER/REPOSITORY --run-id BUILD_RUN_ID
```

The command performs read-only GitHub API, attestation and GHCR access. It freezes bounded regular-file
bytes, checks their hashes and archive members without extraction, then verifies descriptor/archive
provenance, both image provenance records and both image-bound SBOMs. Standard `gh attestation verify`
pins the current repository, publishing workflow, master ref, exact source/signer commit and
GitHub-hosted runner; signed run/attempt identity must also match. It does not accept caller-supplied
verification JSON or a pass flag.

A successful JSON report says `status: integrity_verified`, with the release ID/fingerprint and
source/build identity, **`staging_acceptance: not_evaluated`** and **`deployment: not_performed`**.
It is a human-readable integrity result, not a signed acceptance record or deploy authorization.
Save it privately if needed. Failure returns nonzero with a generic message: check selected files,
identity, CLI version, GitHub/registry access and evidence availability. Raw provider/CLI diagnostics
are not printed. Missing/unknown CLI selectors instead show usage and exit 2 without a verification
report. GitHub CLI must resolve to an existing absolute executable in the trusted host PATH.
Each CLI call has a 120-second timeout; six attestation checks may take several minutes.

Publishing run metadata is read for its exact attempt, so a later publishing rerun does not silently
substitute its metadata. Checkpoint deliberately keeps the publisher's conservative **current successful
run and latest five successful jobs** rule: a pending/failed Checkpoint rerun blocks verification until
it succeeds. No failed or incomplete evidence is treated as a previous pass.

## Download and verify a successful run automatically

Instead of selecting filenames yourself, use the current successful publishing attempt:

```sh
uv run --project backend python scripts/verify_application_release.py \
  --download --repository OWNER/REPOSITORY --run-id BUILD_RUN_ID
```

Choose exactly one of `--download` or `--directory`. Automatic mode first requires a successful
same-repository master `Build application release` run. It derives the exact artifact name from that
run's source SHA, ID and attempt, then asks patched GitHub CLI to download it into a fresh private
temporary directory. The usual four-file/hash/signature checks follow. Verified source and attempt
must still match the selection made before download; no later rerun is substituted. The directory
is removed after success or failure, and no downloaded source is executed. Native extraction is
provided by GitHub CLI; the 16 MiB read/parse bounds are not a hard extraction-disk quota.

Automatic mode refuses a currently failed or pending publishing attempt. To verify an earlier
successful publishing attempt, obtain its exact four-file artifact and use `--directory`; all signed
attempt and current Checkpoint checks still apply.

## Run the read-only GitHub Actions workflow

Open **Actions → Verify application release → Run workflow**, select
`master`, and enter the successful **build run ID**, not the Checkpoint run ID. Alternatively:

```sh
gh workflow run verify-application-release.yml --ref master -f build_run_id=BUILD_RUN_ID
```

The workflow checks out protected `master`, not candidate source. It calls automatic mode with the
repository fixed by GitHub, and accepts only the run ID as an environment-quoted input. Permissions
are limited to reading contents, Actions, packages and attestations. Its ephemeral registry login
uses the job's read-only GitHub token and logs out during cleanup; no long-lived registry secret is
introduced. It has no publishing, OIDC, OCI, Kubernetes or deployment authority and uploads no files.
A successful log contains the same integrity-only JSON report. Do not treat its green check as a
staging acceptance or production approval. Hosted success and one intentional rejection are recorded below.

## Genuine hosted qualification — 16 November 2026

The [first native ARM build](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43901645180)
completed after all five protected-master Checkpoint jobs passed. It published both image digests,
SBOMs, descriptor and deployment source with all five attestation steps and the exact four-file
artifact. Automatic verification then passed all six genuine signed subjects using the existing
GitHub session and an isolated temporary registry login; those temporary credentials were removed.
The first unauthenticated image check failed closed while both file signatures passed, confirming
that GitHub API authentication alone was insufficient for that registry client.

A modified descriptor was rejected by a real signature verification call. A Checkpoint run supplied
where a publishing run was expected was also rejected. These read-only checks changed no OCI resource,
application data or saved Atlas instance. They qualify that build and the laptop consumer path;
subsequent hosted evidence is recorded separately below.

After the verifier merged in PR #11 at `a3883ed`, the [first hosted verification](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43922343367)
succeeded. The [intentional wrong-Checkpoint rejection](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43922642231) failed as expected;
registry logout succeeded on that rejection path. After the dependency updates, protected source
`d0aa007fddd23d39338491053a6d0bc69c66a2d0` passed [all five Checkpoint jobs](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43927027728).
Its [native ARM publisher](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43928708074) completed every step, including the upgraded
artifact upload action and all five attestation steps. The [matching hosted verification](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43929086428)
then succeeded with the nine-field integrity-only report, bound to that exact source and build run;
registry logout succeeded. The report retains `staging_acceptance: not_evaluated` and
`deployment: not_performed`. These checks do not qualify every negative path, durable custody,
OCI pulls/deployment or authenticated staging acceptance; those remain Pending.

## Before staging or production

Integrity verification is one prerequisite. Staging target/credentials, private settings/render
provenance, OCI ARM pulls/readiness/migrations and authenticated acceptance still need implementation
or qualification. Production must select exactly the staging-accepted bytes and recheck current
security policy; this command does not re-scan images or grant production approval.

A failed publication may leave an earlier image in GHCR. Partial publication grants no release or
staging acceptance. Missing signatures, unavailable artifacts or failed checks require stopping,
without rebuilding under an old release ID.

The four-file Actions upload retains artifacts for **90 days**. This is not permanent custody.
Before durable promotion/rollback, qualify retention/access/recovery for descriptor, source, SBOMs,
verified provenance and acceptance. A retained digest alone is insufficient.

## Local verification and remaining qualification

```sh
uv run --project backend pytest -q backend/tests/test_artifact_release.py \
  backend/tests/test_build_application_release.py backend/tests/test_release_verification.py
uv run --project backend python scripts/check_design_docs.py
uv run --project backend python scripts/check_inline_docs.py
```

Synthetic unit cases cover trust substitution, malformed/changed/missing public files, bounded file
reads, archive traversal/links/duplicates, schema and SBOM changes, wrong signed subjects/attempts,
CLI/version failures and fixed nonsecret output. They do not replace actual cryptographic checks
against GitHub/GHCR. Keep [hosted artifact and OCI cases](real-oci-test-manifest.md#immutable-arm64-release-artifacts)
Pending where not exercised. The genuine checks above are recorded separately from synthetic coverage.
No new screen, application table, HTTP endpoint or saved 8443 update is
introduced. Required milestone/PR checks and coverage gates remain unchanged.
