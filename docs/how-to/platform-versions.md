# Platform versions and automatic OKE image selection

**Implemented source/input contract; live qualification Pending.** Version selection is an
infrastructure change. Editing a variable does not upgrade a cluster or database and must not
silently change an approved application promotion.

## Protected environment variables

| GitHub Actions variable | Terraform input | Meaning |
| --- | --- | --- |
| `OTM_OKE_KUBERNETES_VERSION` | `oke_kubernetes_version` | Required exact canonical `vMAJOR.MINOR.PATCH`, at most 32 characters; no floating latest/minor-only value |
| `OTM_POSTGRESQL_VERSION` | `postgresql_version` | Required two-digit PostgreSQL major string, such as `16`; no minor/patch suffix or floating value |

Both variables are configured separately in the existing staging and production GitHub Environments.
The owner selected initial targets `v1.37.0` and `16` on13November2026. Oracle currently labels
OKE1.37.0 a **preview**; this source target is not live Ashburn or production qualification. Record
its support status in the normal deployment approval and verify regional catalog/image/add-on
availability before apply. PostgreSQL16 matches the disposable test baseline. Both environments
must use the same exact qualified versions and topology. Future upgrades target the latest suitable
production-supported release through explicit staged qualification, never a floating latest selector.
See [Oracle's release table](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengaboutk8sversions.htm).

The OKE root injects the flat version into the module; remove the old nested version and manual
`node_image_ocid` from private target files. Version inputs belong in the separate rendered candidate,
not duplicate handwritten settings. The existing `[oke]`-equivalent Terraform object retains
placements, capacity and the explicit OS-major setting.

With both variables supplied through the trusted selected environment, run:

```sh
uv run --project backend python -m otm.platform_version_release \
  --output /absolute/private/path/versions.tfvars.json
```

The offline renderer validates syntax and exclusively creates an owner-only `0600` file containing
the two string inputs. It does not authenticate, look up versions, create resources or upgrade
services. Existing files/symlinks are refused and diagnostics are fixed/non-disclosing. Its receipt
contains a digest. The actual protected infrastructure workflow is still a subsequent slice; its
binding will pass these values as data, not interpolate them into shell code:

```yaml
# Protected-environment infrastructure-job fragment; not a deployed workflow.
env:
  OTM_OKE_KUBERNETES_VERSION: ${{ vars.OTM_OKE_KUBERNETES_VERSION }}
  OTM_POSTGRESQL_VERSION: ${{ vars.OTM_POSTGRESQL_VERSION }}
```

## How Terraform selects the node image

1. Query OKE options for the exact Kubernetes version and `AARCH64`, matching the selected
   `VM.Standard.A1.Flex` chipset. Unsupported version/CNI/shape or absence of image sources fails.
2. Query available Compute images for A1, Oracle Linux and `oke.node_os_major` (default `8`, supported
   choices `8`/`9`). This separate explicit setting prevents a silent OS-family jump during a patch
   refresh. Changing it also requires sensor/image staging qualification.
3. Intersect the image IDs returned by those two APIs. Exclude non-IMAGE sources and wrong OS/state;
   deduplicate identical IDs. No name-based guess, alternate architecture or arbitrary image fallback.
4. Compare actual parsed `time_created` timestamps, including timezones. Select the unique newest
   compatible image regardless of API order. Missing/conflicting timestamps, zero eligible images or
   multiple distinct images tied for newest block the plan before control-plane/node creation.
5. The reviewed saved plan pins the resolved image OCID. Apply **that exact saved plan**. A replan
   can select a newly published image, even for the same Kubernetes version; it needs renewed review
   and staging qualification. Application-only releases do not invoke Terraform/image discovery.

Catalog support does not prove GA status, correct image hardening, sensor health, available A1
capacity or runtime behavior. These are [live qualification requirements](real-oci-test-manifest.md#platform-version-and-image-promotion).

## Production uses the staging selection

The cluster output includes `image_selection`, a record with:

| Field | Meaning |
| --- | --- |
| `image_ocid` | Exact resolved region-local image ID |
| `kubernetes_version` | Exact selected patch |
| `architecture` | `AARCH64` for the A1 pool |
| `os_major` | Explicit Oracle Linux major |

After staging acceptance, the deployment pipeline must retain this selection with the trusted
source/plan/acceptance evidence and verify artifact provenance before production credentials are
available. Standard protected GitHub release artifacts/attestations will be used; no separate
qualification service or custom signing system is introduced.

Pass that record as `qualified_node_image` to production in a private qualification tfvars file.
Production refuses a missing record or a version/architecture/OS mismatch. The selected ID must
still be eligible in production's region/catalog; if it was withdrawn, fail and requalify a new
candidate. A newer catalog image does not replace the older still-eligible staging-qualified one.
The same optional record can pin a deliberate staging replay.

### Executable operator handoff

The offline `otm.image_handoff` command now connects the staging output to the production input.
It does not establish deployment credentials or verify staging acceptance. After testing the applied
staging deployment, the authorized operator must verify its approved source revision, selected image,
saved plan and acceptance result before exporting the record. Export from the matching staging state;
never export a speculative plan as evidence of a successful deployment.

Use an owner-only directory outside the checkout. With the correct staging backend already initialized
and the production `OTM_OKE_KUBERNETES_VERSION` supplied through the approved private environment:

```sh
umask 077
# OTM_HANDOFF_DIR must already identify a private operator-owned directory outside the checkout.
terraform -chdir=infra/environments/staging/platform output -json cluster \
  > "$OTM_HANDOFF_DIR/staging-cluster.json"
uv run --project backend python -m otm.image_handoff \
  --staging-cluster-output "$OTM_HANDOFF_DIR/staging-cluster.json" \
  --os-major 8 --region us-ashburn-1 \
  --output "$OTM_HANDOFF_DIR/qualified-image.tfvars.json"
```

Use `--os-major 9` only when both the accepted staging deployment and reviewed production target
explicitly select that family. The command accepts the **single cluster output**, not full Terraform
state or the all-outputs wrapper. It validates the staging label, matching cluster/selection version,
A1 architecture, OS and Ashburn image OCID. Input is bounded to 64 KiB; duplicate JSON fields,
unexpected selection fields, malformed/mismatched records and existing destination files are rejected.
The new file is owner-only `0600`, contains only `qualified_node_image`, and the command prints only
its SHA-256 digest. Private endpoints and other cluster metadata are not copied. The source output
remains private; never publish it, Terraform state, cloud-init or secret-bearing plans as GitHub artifacts.

Add `-var-file="$OTM_HANDOFF_DIR/qualified-image.tfvars.json"` to the separately reviewed production
`terraform plan`, alongside its own target/network/version/bootstrap inputs. Production's Terraform
validation and live discovery independently check the binding and current eligibility. Review and
apply that production saved plan; a successful conversion alone authorizes no deployment. Keep the
handoff file and recorded digest with the private staging acceptance evidence.

The future protected Actions workflow will invoke this same converter after verifying the trusted
staging run. Automated transfer, artifact provenance verification and production approval enforcement
are **not implemented** by this command. This initial operator procedure intentionally adds no custom
release registry, signing system or qualification service.

**A matching input record is a binding, not proof of qualification.** Terraform cannot prove that an
arbitrary supplied JSON object came from a trusted successful staging run. The future workflow must
verify source revision, environment, selected version/image/OS/architecture and acceptance evidence;
that verification is not implemented by this module. Operators performing initial manual deployment
must make and record the same checks privately.

## PostgreSQL boundary

OCI's managed database resource takes a PostgreSQL **major** version in `db_version`. Its supported
upgrade behavior depends on the provider/service and an explicit upgrade setting; a bare version
change can otherwise plan database replacement. See [OCI provider's database version contract](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/psql_db_system.html).

The [managed database module](managed-postgresql.md) now consumes this input in both platform roots,
with service configuration/shape checks, private networking, Vault-referenced provisioning credentials,
backup/PITR policy and replacement protection. Its `database.requested_version` output labels the
configured major, not an observed deployed minor/build. No live service was created/upgraded during
source validation. Major changes require an explicit reviewed upgrade opt-in and backup/maintenance
procedure; managed minor/security patch maintenance remains separate.

Before increasing the major, qualify application drivers, migrations, native Procrastinate schema,
extensions and recovery on that major. The current local/CI PostgreSQL16 image is unchanged by this
variable; update/test the supported CI baseline deliberately alongside a future managed upgrade.
Production receives the staged, approved version change through its reviewed infrastructure plan,
not an automatic cascade from a staging variable edit.

## Prior version/image source verification — 13 November 2026

All seven native Terraform suites passed: 19 bootstrap, 23 network, 30 OKE and 19 platform-root
cases (91 total), plus the state-bucket and cluster replacement guards. Image cases cover parsed
timezone comparison, response-order independence, identical/conflicting duplicates, invalid times,
missing/tied images, incompatible qualification records and an older still-eligible staging image.
After the operator handoff addition, backend unit-only validation passed 2,495 tests without skips
and 95.17% complete-source line coverage. The version renderer has 19 focused cases, and the handoff
has 30 focused cases covering target mismatches, malformed/duplicate/oversized JSON, private-field
exclusion, exclusive file creation, OS-family selection and non-disclosing CLI behavior.
Inline documentation, link/contracts, publication, credential scanning, Ruff and focused Bandit checks
passed. Independent documentation and security reviews found no material issues; the independent
design review's complete-selection, saved-plan and qualification-boundary requirements are captured above.

These are offline source checks, not OCI qualification. Full PostgreSQL/browser/frontend integration
and the other required milestone gates still precede the combined milestone PR. The running Atlas
snapshot and all live resources remain unchanged.
