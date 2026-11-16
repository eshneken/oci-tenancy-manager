"""Immutable ARM64 release identities; matching evidence never authenticates its source."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from otm.contracts import Contract

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SourceSha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
Repository = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,38}/[a-z0-9][a-z0-9._-]{0,99}$")]


# The digest identifies published bytes; the SBOM hash identifies the separately attested inventory.
class ReleaseImage(Contract):
    # Only the expected release's GHCR repository is allowed by the containing candidate.
    repository: Annotated[str, Field(pattern=r"^ghcr\.io/[a-z0-9/._-]{3,180}$")]
    # Registry manifest digest, not a mutable version or branch tag.
    digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    # SHA256 of the exact CycloneDX document attached to this image's attestation.
    sbom_sha256: Sha256


# Closed nonsecret metadata connects one successful protected build to its immutable artifacts.
class ReleaseCandidate(Contract):
    # Initial descriptor contract; incompatible future formats require explicit parsing changes.
    format_version: Literal[1] = 1
    # Lowercase GitHub owner/repository, also determining both permitted GHCR image names.
    repository: Repository
    # Exact protected-master commit used by Checkpoint, build context and provenance.
    source_sha: SourceSha
    # Successful Checkpoint run; its repository/path/source/job results are independently checked.
    checkpoint_run_id: Annotated[int, Field(ge=1)]
    # Publishing workflow run and attempt distinguish retry artifacts without mutable release IDs.
    build_run_id: Annotated[int, Field(ge=1)]
    # Retry number within this publishing run; retry artifacts always receive a distinct ID.
    build_attempt: Annotated[int, Field(ge=1)]
    # One native architecture in V1; no unqualified multiarch index or amd64 substitution.
    platform: Literal["linux/arm64"] = "linux/arm64"
    # Application installed once and used for API, workers, migration and maintenance commands.
    application: ReleaseImage
    # Independently built TLS ingress with the same release's reviewed source and policy.
    caddy: ReleaseImage
    # Exact deterministic public deployment-source archive; private environment renders differ.
    deployment_source_sha256: Sha256
    # Embedded Alembic head; schema-changing releases retain the approved maintenance procedure.
    schema_revision: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_]{1,128}$")]
    # Canonical application-settings JSON schema from this exact installed source revision.
    settings_schema_sha256: Sha256
    # Explicit accepted Caddy availability findings; absent fixed findings need not be fabricated.
    accepted_caddy_cves: tuple[Literal["CVE-2026-116587", "CVE-2026-78661"], ...] = ()

    # Prevent image repository substitution and duplicate exception records at artifact boundaries.
    @model_validator(mode="after")
    def exact_images(self):
        if (
            self.application.repository != "ghcr.io/" + self.repository
            or self.caddy.repository != "ghcr.io/" + self.repository + "-caddy"
            or len(set(self.accepted_caddy_cves)) != len(self.accepted_caddy_cves)
        ):
            raise ValueError("RELEASE_ARTIFACT_SCOPE_MISMATCH")
        return self

    # An ID locates a candidate; it grants no staging acceptance or deployment authority.
    @property
    def release_id(self):
        return f"{self.source_sha[:12]}-{self.build_run_id}-{self.build_attempt}"

    # Deterministic bytes are the subject of the release descriptor's provenance attestation.
    def canonical_bytes(self):
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()

    # Whole-candidate identity includes image digests, bundle, schema, source and accepted findings.
    @property
    def fingerprint(self):
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


# This is content matching only: callers must first verify GitHub deployment/attestation provenance.
# No API, CLI or deployment workflow accepts a caller-supplied pass flag through this helper.
def match_staging_acceptance(candidate, *, trusted_repository, accepted_fingerprint):
    candidate = ReleaseCandidate.model_validate(candidate)
    if candidate.repository != trusted_repository or candidate.fingerprint != accepted_fingerprint:
        raise ValueError("STAGING_CANDIDATE_MISMATCH")
    return candidate


# GitHub API evidence must identify the exact workflow and successful required jobs on master.
def validate_checkpoint(run, jobs, *, repository, source_sha):
    if (
        run.get("repository", {}).get("full_name") != repository
        or run.get("head_repository", {}).get("full_name") != repository
        or run.get("head_sha") != source_sha
        or run.get("head_branch") != "master"
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("path") != ".github/workflows/checkpoint.yml"
        or type(run.get("id")) is not int
        or run["id"] < 1
    ):
        raise ValueError("RELEASE_CHECKPOINT_UNTRUSTED")
    required = {
        "Backend unit coverage",
        "Frontend unit coverage",
        "PostgreSQL and Playwright",
        "Security and publication",
        "Documentation and contracts",
    }
    entries = jobs.get("jobs", [])
    if (
        jobs.get("total_count") != len(required)
        or len(entries) != len(required)
        or {entry.get("name") for entry in entries} != required
        or any(
            entry.get("status") != "completed" or entry.get("conclusion") != "success"
            for entry in entries
        )
    ):
        raise ValueError("RELEASE_REQUIRED_CHECKS_INCOMPLETE")
    return run["id"]
