# Review an immutable ARM64 application release

16 November 2026 · Build source implemented; targeted checks pass · No hosted publication/deployment

The [release contract](../reference/artifact-releases.md) binds two image digests, SBOM hashes,
public deployment-source hash, installed schema contract and source/build identity. Build source
exists; trusted staging acceptance, promotion and long-term release custody remain separate work.
This is a review procedure, not a command to publish or activate the current source.

## How the source workflow selects a build

After publication/enabling, `.github/workflows/build-application.yml` follows a successful
same-repository master-push Checkpoint automatically. It has no manual dispatch input for an
arbitrary SHA, artifact or caller-supplied pass flag. Trigger head SHA must equal the standard
publishing workflow SHA; the helper independently fetches exact run/path and all five successful
required jobs. A stale Checkpoint may not produce a candidate after master advances. Do not remove
the SHA equality rule to force publication; use the matching protected source and required CI.

The job uses native `ubuntu-24.04-arm`; it builds the app and Caddy once each from a committed Git
archive and inspects ARM64 plus the app's actual installed migration/settings contract. It scans
saved image bytes and generates CycloneDX SBOMs before pushing each image. App vulnerabilities have
no exceptions; Caddy has only its [two exact accepted DoS findings](../reference/caddy-security-exceptions.md).
Publication permissions are confined to GHCR/GitHub attestations, with no OCI/Kubernetes authority.
The helper's `--output` is a new private work directory; it is not a staging/production selector.
Do not copy Actions tokens or run the publishing helper on a developer laptop for a local preview.

## Review a future successful candidate

Once the workflow is hosted and qualified:

1. Confirm the protected source, triggering Checkpoint and publishing run/attempt through trusted
   GitHub records. Require all five existing gates; a green unrelated run is not evidence.
2. Select `application-release-{release_id}`, where release_id is source-prefix/build-run/attempt.
   Require the completed trusted publishing workflow and exactly four files: `release.json`,
   `deployment-source.tar`, `application.cdx.json`, `caddy.cdx.json`. Never download/consume a general
   workspace dump or private config from an arbitrary run.
3. Verify standard provenance and SBOM attestations against the expected repository/workflow/ref,
   exact source and image/descriptor/archive subjects. Compare full canonical descriptor fingerprint,
   both SBOM hashes and archive hash. This trusted verification/acceptance workflow is not implemented
   by the small content-matching helper; do not replace it with a local JSON pass flag.
4. Use both `repository@sha256:...` image references, never mutable build tags or `latest`. Confirm
   platform `linux/arm64`, source/build IDs, accepted Caddy findings and embedded migration/settings
   contract. Presence of artifacts alone does not establish that scans or attestations passed.
5. Stop before deployment until staging target/credentials, private settings/render provenance,
   OCI ARM pull/readiness/migration behavior and acceptance are implemented and qualified. Future
   production selects that exact accepted candidate, not a rebuild of the same branch.

The archive is seven public source files plus the generated settings schema. It is not a ready-to-apply
environment bundle or standalone renderer. Private environment/network bindings remain outside it.
A failed later stage may leave an earlier image in GHCR; partial publication grants no release
or deployment authority and must not be called a staging-qualified candidate.

## Retain evidence before the 90-day boundary

The source upload policy retains the four files for 90 days. GHCR digest availability alone is
insufficient: future promotion/rollback also needs the descriptor, public source, inventories and
verified provenance/acceptance. Long-term release and attestation custody is not implemented in
this slice. Before approving durable use, qualify retention/access/recovery and immutable evidence
storage. If required artifacts expire or cannot be verified, stop; do not silently rebuild and
reuse an old release ID or staging result.

## Local checks and current limits

Source tests use synthetic GitHub/scanner/Docker evidence plus an owned temporary Git repository
for archive isolation. They do not push to a real registry or bootstrap OCI trust. Appropriate
focused checks from the repository root are:

```sh
uv run --project backend pytest -q backend/tests/test_artifact_release.py backend/tests/test_build_application_release.py
python3 scripts/check_design_docs.py
python3 scripts/check_inline_docs.py
```

Targeted checks pass: the complete backend unit gate passed 2,921 cases at 95.4192% coverage
across 198 modules, including the 60 focused cases. The existing owned native container qualification
passed app/context/assets/API/worker/PostgreSQL/Trivy checks. The new networkless installed-contract
probe passed against the actual qualified ARM64 image, with matching embedded migration head and
settings-schema hash; the owned temporary image was removed. Real-Git archive isolation also passes.
The orchestration tests use synthetic API/scanner/Docker publication results; no hosted publish or
attestation run is inferred from them.

This checkpoint runs no publishing workflow, requests no actual OIDC credential, changes no
OCI/Kubernetes resource and leaves saved Atlas 8443 unchanged. Required
full milestone/PR gates remain in force. Follow the [live qualification cases](real-oci-test-manifest.md#immutable-arm64-release-artifacts)
for hosted GitHub/GHCR/attestations and later OCI ARM staging pulls/deployment/acceptance. No new
application table, screen, HTTP route or administrator action is introduced here.
