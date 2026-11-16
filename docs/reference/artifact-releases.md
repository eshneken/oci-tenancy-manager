# Immutable ARM64 application release candidates

16 November 2026 · Implemented publisher and read-only integrity consumer · Genuine hosted publication/signatures qualified; no OCI deployment

[Operator review](../how-to/application-releases.md) · [Promotion design](../engineering-design/24-environments-and-promotion.md)

A candidate binds one protected source commit, successful Checkpoint run, publishing run/attempt,
two immutable image references, their SBOMs, public deployment source and installed schema contract.
It is **not staging acceptance**. The pure models/helper add no HTTP endpoint, database table,
application workflow or deployment authority. Native publication and genuine laptop signature checks
are qualified below; hosted dispatch, remaining custody cases and OCI qualification stay pending.

## Contract and field dictionary

`ReleaseCandidate` and `ReleaseImage` inherit the closed/frozen strict contract: unknown fields and
coercible values do not become trusted metadata. Digests/hashes are SHA256 with lowercase 64-hex
payloads; source commits use exactly 40 lowercase hex characters.

| `ReleaseImage` field | Source / meaning |
| --- | --- |
| `repository` | GHCR image name; the candidate enforces exactly `ghcr.io/{repository}` for application and `ghcr.io/{repository}-caddy` for ingress. The standalone string contract is bounded and GHCR-only. |
| `digest` | Registry manifest digest `sha256:` plus 64 lowercase hex characters, obtained for the published image; never a branch/version tag. |
| `sbom_sha256` | Hash of the exact separately uploaded CycloneDX document attested against this image digest. |

| `ReleaseCandidate` field | Source / meaning |
| --- | --- |
| `format_version` | Fixed integer 1, default 1; descriptor-format compatibility, not an app or DB revision. |
| `repository` | Lowercase GitHub owner/repository; owner 1–39 and repository 1–100 allowed name characters. Determines both exact GHCR image names. |
| `source_sha` | Exact protected-master commit used by Checkpoint, checked-out workflow source and committed Docker build contexts. |
| `checkpoint_run_id` | Positive integer reference to the independently fetched successful Checkpoint run; not a caller-provided pass flag. |
| `build_run_id` | Positive integer publishing workflow run ID, independent of the Checkpoint run. |
| `build_attempt` | Positive integer publishing-run attempt; reruns receive a different candidate identity. |
| `platform` | Fixed `linux/arm64`; native ARM build, no implicit amd64 or multiarch substitution. |
| `application` | `ReleaseImage` for the common installed app image used by API/worker/migration/maintenance. |
| `caddy` | `ReleaseImage` for the independently built ingress image from the same source revision. |
| `deployment_source_sha256` | Hash of the exact deterministic `deployment-source.tar`; it is public source, not a private rendered environment bundle. |
| `schema_revision` | Embedded Alembic head, 1–128 alphanumeric/underscore characters. The installed-image probe must agree with the source contract before publication. |
| `settings_schema_sha256` | Hash of sorted JSON for this revision's `ApplicationSettings` JSON Schema; installed image and source must agree. |
| `accepted_caddy_cves` | Unique tuple containing only the two owner-approved Caddy CVE IDs, or empty when the findings are absent. Captures actual accepted scan findings, not a staging approval. |

There are 16 declared fields across the two models (13 candidate, three image); nested image values
occur twice. The candidate also exposes three **derived, nonserialized** values:

| Derived value | Meaning |
| --- | --- |
| `release_id` | `{source_sha[:12]}-{build_run_id}-{build_attempt}`; locator only, not authorization. |
| `canonical_bytes()` | Sorted compact JSON of the full descriptor, including defaults and accepted findings; standard provenance subject. |
| `fingerprint` | SHA256 of those canonical bytes. Changing source, image/SBOM, public bundle, schema, build identity or accepted findings changes it. |

## Checkpoint evidence and workflow boundary

The publisher runs after completed `Checkpoint` on master only when the trigger is a successful
same-repository push and its head SHA equals the publishing workflow's standard `github.sha`.
Checkout uses that exact SHA. A delayed green Checkpoint for an older master commit may be skipped;
it does not authorize building a newer commit or spoofing standard attestation context.

The helper fetches the run and latest-job evidence from fixed GitHub API endpoints over verified TLS.
It checks repository/head repository, source SHA, master branch, push event, completed/success state,
exact `.github/workflows/checkpoint.yml` path and positive run ID. Trigger/run IDs must agree.
Exactly these five jobs must be present once, completed and successful, with total_count 5:

- Backend unit coverage
- Frontend unit coverage
- PostgreSQL and Playwright
- Security and publication
- Documentation and contracts

Skipped, duplicate, renamed, missing or incomplete job evidence fails. A successful event payload
alone is insufficient. API reads have bounded response/time limits and fail closed.

The source job targets `ubuntu-24.04-arm`, serializes publication by source SHA without cancelling
in-flight work, and requests only contents/actions read plus GHCR package and GitHub attestation
publication permissions. GitHub attestation OIDC is distinct from OCI federation; this workflow has
no OCI credentials, Terraform/apply, Kubernetes target or staging/production Environment authority.
The genuine hosted publisher execution is qualified below; deployment and acceptance remain separate.

## Build, inspect, scan and publish

The helper exports the exact committed source with `git archive`; ignored/untracked files and local
working edits are not build inputs. Docker's application-context deny-default filter remains a
second boundary. The successful Checkpoint's publication scan remains necessary: an archive
allowlist does not prove accidentally committed content is safe.

Each image is built once with explicit ARM64 and source/revision labels. The app's networkless,
read-only installed-package probe loads its actual Alembic head and settings schema, compares them
with the host/source contract and starts no database/server or credential resolver. OS/architecture
inspection must report `linux/arm64`.

The exact local image bytes are saved to a temporary archive and scanned before that image's push.
OS and language scan classes must both be present, malformed findings fail, and CycloneDX SBOMs
must identify their format with a nonempty component inventory. The application has no vulnerability
exceptions; Caddy uses only the [approved exact availability-risk policy](caddy-security-exceptions.md).
SBOMs are generated from those same saved image bytes. Local scan archives/logs/cache/source context
are not publication artifacts.

Pushes use run/attempt tags for transport, then the descriptor records the immutable GHCR manifest
digests. Tags alone never identify a release. If a later stage fails, an earlier image may already
exist in GHCR; this is not a completed or staging-qualified candidate. Do not weaken checks or
silently rebuild a selected release to make partial publication look complete.

## Public artifacts, attestations and custody

The workflow uploads exactly four files, with no wildcard directory upload and 90-day retention:

| Artifact | Evidence role |
| --- | --- |
| `release.json` | Exact canonical candidate descriptor. |
| `deployment-source.tar` | Deterministic public source archive, separately provenance-attested. |
| `application.cdx.json` | CycloneDX inventory whose hash is bound in the application image record. |
| `caddy.cdx.json` | CycloneDX inventory whose hash is bound in the Caddy image record. |

The archive contains seven explicit public files plus generated `application-settings.schema.json`:

- `backend/src/otm/kubernetes_release.py`
- `backend/src/otm/caddy_ingress.py`
- `backend/src/otm/ingress_settings.py`
- `backend/config/staging.application.toml`
- `backend/config/production.application.toml`
- `tools/caddy/Dockerfile`
- `tools/caddy/security-exceptions.json`

Sorted member order, zeroed owner/time metadata and mode 0444 make the tar deterministic for the
same source/schema bytes. This subset is neither a standalone renderer installation nor a deployment
manifest containing reviewed private OCIDs, contacts, settings or bound environment/network input.
It does not replace future staging/deployment provenance for those private renders.

Pinned `actions/attest` v4 supplies standard image provenance, image-bound SBOM attestations and
provenance for descriptor/archive. All five attestation steps set `create-storage-record: false`:
the optional linked-artifact storage metadata feature is unused, and no `artifact-metadata: write`
permission is granted. Standard GitHub attestation publication and image-attestation pushes to GHCR
remain selected; this is not an OCI cloud federation/deployment permission. Attestation does not
establish application acceptance or OCI deployability.
A consumer must verify trusted repository/workflow/ref/source and exact subjects, not simply compare
JSON or accept any attestation signed by an unrelated workflow. The read-only integrity consumer below verifies these bindings; authenticated staging acceptance remains separate work.

Ninety days is artifact retention, not permanent release custody. Registry retention/access,
long-term descriptor/archive/SBOM and verified-attestation preservation remain pending. Missing or
expired required evidence must stop selection/promotion. Never rebuild a nominally identical release
silently and reuse its old acceptance; a rebuild is a new candidate requiring new verification.

## Content matching is not staging authorization

`match_staging_acceptance(candidate, trusted_repository, accepted_fingerprint)` revalidates the
candidate and compares repository/fingerprint only. It has no API/CLI accepting a pass boolean.
The caller must first authenticate acceptance through the future trusted deployment/attestation
verification workflow. This function does not verify signatures, approvals, OCI state, acceptance
run identity or success. No current candidate becomes staging-qualified merely by invoking it.

## Historical publisher source qualification (before the integrity consumer)

The complete backend unit-only gate passed 2,921 cases at 95.4192% line coverage across 198
application modules; the 60 focused cases pass. The owned native application-container pipeline
passed build-context filtering, installed assets/API/native worker/disposable PostgreSQL and Trivy.
The release contract probe then ran against that real qualified ARM64 image, restored from its
private owned archive: actual installed migration head `0028_signing_credentials` and settings-schema
hash match the source contract. Its temporary image was removed; no saved instance was used.
The owned real-Git archive regression also passed. These results do not execute a real registry
publication or the full milestone suite. Static/purpose/privacy and independent security review pass.

GitHub trigger/permissions, the actual hosted native ARM runner, registry digest/SBOM/provenance
publication and genuine-artifact consumer behavior still require hosted qualification. OCI ARM pulls, compatible migrations,
staging acceptance, production approval and unchanged-byte promotion remain [Pending](../how-to/real-oci-test-manifest.md#immutable-arm64-release-artifacts).
No publication, push/merge, cloud resource or saved 8443 change is part of this source checkpoint.


## Read-only authenticated integrity verification

`scripts/verify_application_release.py` invokes `otm.release_verification.main`. Select exactly one input mode: `--directory` (four existing public files) or `--download`
(the selected run’s current successful publishing attempt). Both require `--repository` (trusted
expected GitHub owner/repository) and `--run-id` (trusted expected publishing run ID). It neither downloads
arbitrary archives nor accepts attestation JSON, custom trust roots, unsigned fallbacks or pass flags.
The shared `BUNDLE_FILES` allowlist lives in `otm.artifact_release`; the publisher and verifier use the
same unchanged seven-source-file contract plus generated settings schema. Descriptor format stays 1.

The implementation:

1. Requires GitHub CLI 2.102.0 or newer, including the attestation ref-matching security correction.
2. Requires exactly the four public filenames, reads regular files without following final-component
   symlinks and freezes their bytes. Each file and parsed CLI response is limited to 16 MiB; subprocess
   capture first uses private temporary disk files, with a 120-second timeout for each `gh` call.
3. Rejects duplicate JSON keys and noncanonical descriptors. Independently fetches the exact successful
   publishing attempt from GitHub, checks repository/head repository, SHA, master, workflow_run event,
   exact publishing path/run/attempt, and revalidates the existing Checkpoint/five-job gate.
4. Checks source/SBOM/schema hashes. Reads the plain tar in memory without extracting or executing it;
   members must be the exact allowlist once each, regular, bounded and without PAX headers. Inventories
   must identify CycloneDX and contain components.
5. Invokes standard online `gh attestation verify` six times: provenance for descriptor and source tar,
   provenance for each immutable image, and CycloneDX SBOM for each image. The producer has five
   attestation **steps** because its file-provenance step signs both local files; these counts differ.
6. Pins github.com, the current expected repository, exact publishing workflow, master ref, source and
   signer SHA, and GitHub-hosted runners. Requires the verified certificate's signed `runInvocationURI`
   to identify the exact build run/attempt, the expected subject digest/predicate type and matching SBOM
   predicate contents. It fetches attestations through GitHub rather than accepting local bundles.

Publishing attempts use the exact attempt endpoint so later reruns cannot substitute metadata for
an earlier immutable candidate. The Checkpoint contract intentionally remains conservative: its
current run and latest five jobs must all be successful; a pending/failed rerun blocks verification.

Only successful verification emits these nine report fields:

| Field | Meaning |
| --- | --- |
| `status` | `integrity_verified`; neither acceptance nor deployment. |
| `release_id` | Existing candidate locator. |
| `fingerprint` | Canonical whole-candidate SHA256. |
| `repository` | Independently selected and authenticated expected repository. |
| `source_sha` | Exact signed and successful source commit. |
| `build_run_id` | Independently selected successful publishing run. |
| `build_attempt` | Exact successful, signed publishing attempt. |
| `staging_acceptance` | Always `not_evaluated`. |
| `deployment` | Always `not_performed`. |

Verification failure produces a fixed nonsecret JSON message and exit 1, without raw command output,
credentials or file contents. Invalid command usage (such as missing or unknown selectors) instead
uses argparse usage/errors and exit 2, with no verification report. Missing registry/read permissions are failure, not permission to
substitute unsigned metadata. Tokens remain in approved host/CI credential handling and never become
CLI arguments. Executable lookup requires an existing absolute GitHub CLI path; legitimate
installation symlinks are supported. This assumes a trusted installed CLI and host PATH, rather than
authenticating the CLI binary itself. Standard verification authenticates the signed builder's claims; it does not replace
an independent deployed-image/readiness check, current vulnerability rescan, durable custody,
production approval or authenticated staging acceptance. Reports themselves grant no authority.

References: [GitHub CLI verification](https://cli.github.com/manual/gh_attestation_verify),
[ref-matching advisory](https://github.com/cli/cli/security/advisories/GHSA-4mq3-hpgx-9cx8),
[workflow-run attempt API](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt).

### Historical integrity-consumer source checkpoint (before hosted qualification)

The complete backend unit-only gate passes **2,982 tests**, with **95.4638%** line coverage across
199 application modules; this includes **119 focused candidate/publisher/verifier tests**. The
unchanged frontend gate passes 650 tests at 96.99%. Purpose/link/publication/credential scans and
Bandit pass. Scoped B404/B603 annotations describe independently reviewed fixed-argv subprocess
false positives; executable resolution is absolute and shell execution is explicitly disabled.
No scanner policy, assertion, timeout or coverage threshold was weakened.

This is a targeted source checkpoint after the preceding full platform qualification. The full
PostgreSQL/browser suite is not rerun for this read-only CLI-only addition; required complete
milestone/PR gates remain mandatory before its next PR. Genuine hosted cryptographic verification,
registry authorization, OCI deployment and authenticated staging acceptance remain Pending.

## Repeatable verification workflow and genuine qualification — 16 November 2026

`verify_run` authenticates current publishing metadata before a native `gh run download` into a
fresh private temporary directory. Artifact name is derived from exact source/run/attempt; callers
cannot supply an archive URL, artifact name, output path or verification JSON. GitHub CLI 2.102.0+
includes both the signature-policy and [symlink extraction fixes](https://github.com/cli/cli/security/advisories/GHSA-39wj-f2f4-978v).
The normal verifier rechecks all signed subjects and binds its resulting source/attempt to the initial
selection. Downloaded data is never executed; cleanup runs on success/failure. Native download and
extraction happen before file-read bounds, so those bounds are not an extraction-disk quota.
Directory mode continues to support exact earlier successful attempts; download mode fails if the
currently selected publishing attempt is not successful.

`.github/workflows/verify-application-release.yml` exposes one string input, `build_run_id`, through
manual dispatch from master only. Protected verifier source is checked out by exact workflow SHA.
Job permissions are read-only contents/actions/packages/attestations; it has no environment, OIDC,
cloud, publication or deployment grant. Existing pinned checkout/Python/uv/registry-login actions
are reused. Input enters Python through quoted environment values, never expression interpolation
into shell code. The existing job token supplies ephemeral registry authentication; cleanup logs out.
The workflow uploads no artifact/report and grants no acceptance authority.

[First native ARM release](https://github.com/eshneken/oci-tenancy-manager/actions/runs/43901645180)
completed on protected source after all five Checkpoint jobs passed. Its two ARM64 images and
four-file artifact were published with the five expected attestation steps. The laptop automatic
consumer verified all six genuine provenance/SBOM subjects with exact source/run/attempt identity.
An authenticated temporary registry configuration fixed the expected failure of unauthenticated
image reads; credentials were removed afterward. Genuine cryptographic rejection of a modified
descriptor and metadata rejection of a Checkpoint run also passed. This does not qualify every
negative path, retention/restore, hosted manual dispatch, OCI pulls/deployment or staging acceptance.
Earlier source-only checkpoint statements above are historical and do not supersede this evidence.
