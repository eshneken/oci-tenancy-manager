"""Candidates bind every promoted byte to one exact successful protected build."""

import copy
import json

import pytest
from pydantic import ValidationError

from otm.artifact_release import ReleaseCandidate, match_staging_acceptance, validate_checkpoint

REPOSITORY = "example/atlas"
SHA = "a" * 40


# Synthetic artifact references cannot identify a real application, person or cloud resource.
def candidate():
    image = {
        "repository": "ghcr.io/" + REPOSITORY,
        "digest": "sha256:" + "b" * 64,
        "sbom_sha256": "c" * 64,
    }
    return ReleaseCandidate.model_validate(
        {
            "repository": REPOSITORY,
            "source_sha": SHA,
            "checkpoint_run_id": 1,
            "build_run_id": 2,
            "build_attempt": 1,
            "application": image,
            "caddy": {**image, "repository": image["repository"] + "-caddy"},
            "deployment_source_sha256": "d" * 64,
            "schema_revision": "0001_example",
            "settings_schema_sha256": "e" * 64,
        }
    )


# Event success alone is insufficient: path, source and every required job must agree.
def checkpoint():
    run = {
        "id": 1,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
        "head_sha": SHA,
        "head_branch": "master",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/checkpoint.yml",
    }
    names = [
        "Backend unit coverage",
        "Frontend unit coverage",
        "PostgreSQL and Playwright",
        "Security and publication",
        "Documentation and contracts",
    ]
    jobs = {
        "total_count": 5,
        "jobs": [{"name": name, "status": "completed", "conclusion": "success"} for name in names],
    }
    return run, jobs


# Stable canonical bytes survive JSON roundtrips and never embed a fabricated acceptance flag.
def test_candidate_identity_and_roundtrip():
    item = candidate()
    assert item.release_id == "aaaaaaaaaaaa-2-1"
    assert ReleaseCandidate.model_validate_json(item.canonical_bytes()) == item
    assert len(item.fingerprint) == 64
    assert "qualified" not in json.loads(item.canonical_bytes())
    assert (
        match_staging_acceptance(
            item, trusted_repository=REPOSITORY, accepted_fingerprint=item.fingerprint
        )
        == item
    )


# Any promoted image, bundle, SBOM, settings/schema or source change invalidates prior acceptance.
@pytest.mark.parametrize(
    "field",
    [
        "source_sha",
        "build_run_id",
        "deployment_source_sha256",
        "settings_schema_sha256",
        "schema_revision",
        "application",
        "caddy",
    ],
)
def test_changed_candidate_cannot_reuse_staging_acceptance(field):
    original = candidate()
    raw = original.model_dump()
    if field in {"application", "caddy"}:
        raw[field]["digest"] = "sha256:" + "f" * 64
    elif field == "build_run_id":
        raw[field] = 3
    elif field == "schema_revision":
        raw[field] = "0002_example"
    elif field == "source_sha":
        raw[field] = "f" * 40
    else:
        raw[field] = "f" * 64
    changed = ReleaseCandidate.model_validate(raw)
    with pytest.raises(ValueError, match="STAGING_CANDIDATE_MISMATCH"):
        match_staging_acceptance(
            changed, trusted_repository=REPOSITORY, accepted_fingerprint=original.fingerprint
        )
    with pytest.raises(ValueError, match="STAGING_CANDIDATE_MISMATCH"):
        match_staging_acceptance(
            original, trusted_repository="another/atlas", accepted_fingerprint=original.fingerprint
        )


# Scope mistakes, mutable tags, coercion and duplicated exception records never parse as releases.
@pytest.mark.parametrize(
    "fault", ["repository", "platform", "tag", "image", "extra", "boolean", "duplicate"]
)
def test_candidate_contract_rejections(fault):
    raw = candidate().model_dump()
    if fault == "repository":
        raw["repository"] = "other/atlas"
    elif fault == "platform":
        raw["platform"] = "linux/amd64"
    elif fault == "tag":
        raw["application"]["digest"] = "latest"
    elif fault == "image":
        raw["caddy"]["repository"] = "ghcr.io/other/caddy"
    elif fault == "extra":
        raw["staging_approved"] = True
    elif fault == "boolean":
        raw["build_run_id"] = True
    else:
        raw["accepted_caddy_cves"] = ("CVE-2026-116587",) * 2
    with pytest.raises(ValidationError):
        ReleaseCandidate.model_validate(raw)


# A complete trusted run supplies only its integer evidence reference.
def test_complete_checkpoint():
    run, jobs = checkpoint()
    assert validate_checkpoint(run, jobs, repository=REPOSITORY, source_sha=SHA) == 1


# PR/fork/manual/spoofed-workflow and mismatched-SHA runs cannot activate publication authority.
@pytest.mark.parametrize(
    "field,value",
    [
        ("repository", {"full_name": "fork/atlas"}),
        ("head_repository", {"full_name": "fork/atlas"}),
        ("head_sha", "b" * 40),
        ("head_branch", "feature"),
        ("event", "pull_request"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("path", ".github/workflows/spoofed.yml"),
        ("id", True),
        ("id", 0),
    ],
)
def test_untrusted_checkpoint_rejected(field, value):
    run, jobs = checkpoint()
    run[field] = value
    with pytest.raises(ValueError, match="RELEASE_CHECKPOINT_UNTRUSTED"):
        validate_checkpoint(run, jobs, repository=REPOSITORY, source_sha=SHA)


# Skips, duplicates, partial pagination and unknown checks never mean all passed.
@pytest.mark.parametrize("fault", ["skip", "missing", "duplicate", "count", "name", "running"])
def test_required_jobs_are_exhaustive(fault):
    run, jobs = checkpoint()
    jobs = copy.deepcopy(jobs)
    if fault == "skip":
        jobs["jobs"][0]["conclusion"] = "skipped"
    elif fault == "missing":
        jobs["jobs"].pop()
    elif fault == "duplicate":
        jobs["jobs"][0] = jobs["jobs"][1]
    elif fault == "count":
        jobs["total_count"] = 100
    elif fault == "name":
        jobs["jobs"][0]["name"] = "Unknown required check"
    else:
        jobs["jobs"][0]["status"] = "running"
    with pytest.raises(ValueError, match="RELEASE_REQUIRED_CHECKS_INCOMPLETE"):
        validate_checkpoint(run, jobs, repository=REPOSITORY, source_sha=SHA)
