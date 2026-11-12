# Installed application container

This checkpoint packages the existing application; it does not deploy it or replace the saved
local review instance. Continue using the running application on port8443 for demonstrations.

## Build and inspect

From the repository root, with Docker/BuildKit and uv available:

```sh
docker build --pull --no-cache --tag otm:local .
uv run --project backend python scripts/run_container_smoke.py
```

The smoke command owns a uniquely labelled image and temporary containers. It creates a disposable
PostgreSQL database, applies migrations only there and removes its labelled containers and image.
It never reads the saved application's state or connection files. Private diagnostic evidence stays
under ignored `.local-dev/quality/container-*`; do not upload these directories or image archives.
Build/run/scan Docker commands share a 600-second deadline; disposable setup and ownership-checked
cleanup are separate. Any failed qualification or cleanup step fails the run. This is not an
end-to-end process timeout. Initial network pulls may exceed the command budget; rerun after
resolving registry access rather than weakening TLS verification or skipping tests.

The multi-stage [Dockerfile](../../Dockerfile) pins Node, Python and uv by image digest, checks the
frontend contracts and installs frozen Python dependencies without editable imports. Both Python
stages use the same official Python3.12 Alpine3.24 digest; the backend environment is built on
Alpine rather than copied across C-library families. Distribution updates are installed through
the supported package manager. No custom system-library builds or scanner exceptions are used. The final
image includes the built UI and the wheel's migration/settings assets. It excludes development
packages, source checkout, Node and uv. UID/GID10001 runs the application. The deny-by-default
[build context](../../.dockerignore) excludes local feeds, private settings, keys and credentials;
the smoke test exercises Docker's actual filtering with synthetic canaries, including nested files.
Only public source/configuration belongs in admitted source paths. The allowlist does not replace
publication/secret checks or authorize putting private material under application source.

## Commands and configuration boundary

The image's default command invokes the **explicit local/simulator** API factory on port8080.
Without operator-provided `OTM_APPLICATION_CONFIG` and credentials it must fail closed. It does not
select saved laptop settings, bootstrap an administrator, migrate a database or fall back to a
simulator when a hosted provider fails. The bundled `otm_settings/application.toml` is a public
example, not automatically selected deployment configuration.

The same installed image contains `otm-simulation-worker`, `otm-maintenance`, `otm-admin` and
`otm-validate-release`. Listing/installing those commands is not qualification of a hosted worker.
Do not mount laptop secrets into a new persistent container or weaken the existing local-loopback
and hosted-release guards to make Docker networking convenient. The maintenance test shares only
its disposable database's network namespace so the existing loopback restrictions remain intact.
It uses a dedicated session-sweeper login with column-scoped privileges, never the database owner
or the application API account.

The probes check nonroot execution, installed asset hashes, frontend artifacts, command-module
imports and real HTTP liveness under a read-only filesystem with capabilities dropped. They require
the exact expected missing-configuration refusal, then run installed session cleanup with a dedicated
restricted login against the disposable migrated database.

Native compatibility checks execute actual Argon2 hash/verify and wrong-password rejection; RSA
bootstrap-key generation, custody and retry; the explicitly configured local API with its installed
frontend over HTTPS; trusted certificate acceptance, untrusted certificate/incorrect hostname rejection;
and unauthenticated protected-API rejection. They compose/drain the actual OTM worker using its
restricted role and separately enqueue/execute a real Procrastinate job in a short, isolated queue.
The probe's sample task and synthetic settings exist only in that disposable container; they are not
packaged application code. No persistent extra review instance is created.

This is **not** an authenticated browser journey, actual OTM lifecycle-job execution, remote database
TLS qualification or proof of OKE readiness. Existing application tests remain required. In particular,
a successful empty OTM queue drain proves worker composition, not create/import/rotation behavior.

An exact-image vulnerability scan uses a pinned Trivy image, a local image archive and current
vulnerability metadata. No image or Docker socket is sent to a scanner service. HIGH/CRITICAL
findings block the check; there is no blanket unfixed-vulnerability exclusion. Digest updates and
any scoped vulnerability disposition require review. Registry/metadata failures are failures,
not clean scan results.

## Remaining deployment work

Hosted composition, verified remote PostgreSQL TLS, Secret/Vault mounts, authenticated readiness,
graceful worker shutdown, ingress, OKE/Terraform and scheduled workloads remain separate work.
Track their real-environment qualification in the [live test manifest](real-oci-test-manifest.md).
No new persistent local instance or cloud tenancy is needed for the packaging smoke test.

## Runtime selection and maintenance

The Debian candidate remained at47 HIGH matches across11 CVEs after applying available fixes.
Several matches concern source-package components not used by OTM, but the candidate still contains
some affected tools/libraries. We selected a maintained official Python3.12 Alpine3.24 base rather
than maintaining a collection of advisory exceptions or manually deleting shared libraries.
[Alpine release support](https://alpinelinux.org/releases/) and the
[official Python image](https://hub.docker.com/_/python) are the upstream references.

Alpine uses musl rather than glibc, so locked native wheel availability alone is insufficient:
the installed native-compatibility probes above are required. New OCI SDK dependencies must be
qualified on this base when introduced; the current image does not claim SDK or real OCI coverage.

Keep all base/tool image digests explicit. [Dependabot configuration](../../.github/dependabot.yml)
proposes one grouped weekly container-image/scanner update PR and one grouped CI-action update PR,
with at most one open PR per group. These activate after the configuration merges to the default
branch; no hosted update result is claimed before then. The scanner pin has one authority:
[tools/trivy/Dockerfile](../../tools/trivy/Dockerfile). The smoke runner reads that exact upstream
version/digest and rejects unpinned images or extra instructions; it does not build a wrapper image.
Python3.12 and the Node major remain deliberate compatibility choices rather than automatic release-line
upgrades. Digest changes for existing tags and scanner releases still require normal CI and human
review; no automerge or deployment is enabled. Review security notices promptly between scheduled PRs.

Trivy's advisory database is fetched into each run's new cache, independently of the engine pin;
new CVEs can therefore be detected without changing the engine. Engine updates also deliver parser,
platform and detection changes and fixes to the scanner. [Trivy database documentation](https://trivy.dev/docs/latest/configuration/db/)
explains that distinction. Registry/metadata failures still fail qualification. Rebuild
without cache so supported OS updates are fetched, scan the resulting exact image with current
metadata and rerun compatibility checks. A clean scan is dated evidence, not a guarantee that no
unknown vulnerabilities exist. Move off the distribution before its supported lifetime ends.
The existing Security and publication CI lane runs this smoke/scan on every checkpoint build,
without adding a sixth required check or changing existing suite/coverage timeouts. No scheduled
cloud deployment or image publishing is enabled here.

## Validation scope

The fresh uncached ARM64 build passes installed-image, native-runtime and strict HIGH/CRITICAL
scanning, with both OS and Python-package inventories detected and zero findings at those severities.
No exclusions were added. The scanned runtime is Alpine3.24.4, image
`sha256:91d3bfdd657c4a1b73357349ec30ea0e583534692d7ff8a997cffc6bdb0ef1d3`.
Independent source/security and documentation reviews found no remaining material candidate issues.
Backend and frontend complete-source unit-only gates independently require at least95% line
coverage. The checkpoint PR records final suite counts and coverage; targeted image checks do not
replace those gates. Purpose, style, documentation, publication, secret and dependency checks remain
required. Negative runner regressions exercise scanner failures, absent/malformed scan reports,
missing inventories, failed probes, expired budgets and cleanup/ownership failures using synthetic
external-tool boundaries; they do not substitute for actual installed-image or advisory scanning.

The full application integration suite remains independently required before a milestone PR;
targeted image compatibility is not application milestone/PR
qualification. Supported architecture claims must match actual results: local ARM64 execution does
not qualify AMD64, which requires its own CI execution. The updated CI gate is source configuration,
not an already observed hosted CI pass.
No container PR, registry publication, hosted qualification or saved-demo update is implied.
