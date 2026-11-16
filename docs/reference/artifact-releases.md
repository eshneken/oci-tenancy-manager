# Immutable ARM64 application release candidates

16 November 2026 · Implemented build source; targeted source validation passes · No hosted publication or deployment

[Operator review](../how-to/application-releases.md) · [Promotion design](../engineering-design/24-environments-and-promotion.md)

A candidate binds one protected source commit, successful Checkpoint run, publishing run/attempt,
two immutable image references, their SBOMs, public deployment source and installed schema contract.
It is **not staging acceptance**. The pure models/helper add no HTTP endpoint, database table,
application workflow or deployment authority. Hosted registry/attestation and OCI qualification remain pending.

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
No hosted execution is claimed before the source workflow is published and qualified.

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
JSON or accept any attestation signed by an unrelated workflow. That trusted consumer is future work.

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

## Qualification status

The complete backend unit-only gate passed 2,921 cases at 95.4192% line coverage across 198
application modules; the 60 focused cases pass. The owned native application-container pipeline
passed build-context filtering, installed assets/API/native worker/disposable PostgreSQL and Trivy.
The release contract probe then ran against that real qualified ARM64 image, restored from its
private owned archive: actual installed migration head `0028_signing_credentials` and settings-schema
hash match the source contract. Its temporary image was removed; no saved instance was used.
The owned real-Git archive regression also passed. These results do not execute a real registry
publication or the full milestone suite. Static/purpose/privacy and independent security review pass.

GitHub trigger/permissions, the actual hosted native ARM runner, registry digest/SBOM/provenance
publication and trusted consumer behavior still require hosted qualification. OCI ARM pulls, compatible migrations,
staging acceptance, production approval and unchanged-byte promotion remain [Pending](../how-to/real-oci-test-manifest.md#immutable-arm64-release-artifacts).
No publication, push/merge, cloud resource or saved 8443 change is part of this source checkpoint.
