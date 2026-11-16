# Read-only Vault retrieval and explicit platform identity

This implemented source boundary reads secrets; it does not create, rotate or delete secrets,
change IAM, mount pod credentials or activate hosted workloads. Existing simulator/local custody
remains explicitly separate. No application tables or ER relationships change.

## Layout and inputs

| File | Responsibility |
| --- | --- |
| `backend/src/otm/secrets/contracts.py` | SDK-independent scope, redacted result and normalized failure type |
| `backend/src/otm/secrets/vault_oci.py` | Concrete OCI SDK reader and explicit platform-identity client factories |
| `backend/tests/test_vault_oci.py` | Synthetic response models, guards and real SDK dispatch with HTTP intercepted |

`VaultReadScope` requires a full region name, exact application-Vault OCID and exact existing hosting
compartment OCID. Fields are strict and bounded; endpoints, credential files, SDK kwargs and descendant
compartment scope are not configurable through this contract. Trusted server composition supplies
these values; there is no new browser/API endpoint. Platform authentication is selected through the [OCI settings](../how-to/laptop-oci-development.md#explicit-application-settings).

The application Vault remains distinct from the database-provisioning Vault. These guards add a
check in the application; they do not substitute for least-privilege IAM on each workload identity.
Only previously authorized credential bindings may reach this internal reader. Knowing an OCID is
not authorization to disclose its secret.

## Read behavior

`OciVaultReader.current(secret_ocid)` resolves CURRENT on every request. It never caches a secret
version pointer. `version(secret_ocid, version_number)` requires a positive integer and returns only
that exact immutable version; it does not silently substitute CURRENT. Existing MFA/reference
and recovery/key services are not yet wired to this adapter.

Before requesting secret bytes, the reader calls `VaultsClient.get_secret` and verifies exact secret,
Vault and compartment identities and ACTIVE state. It then calls `SecretsClient.get_secret_bundle`
with either CURRENT or the exact numeric version and verifies returned identity/version/stage.
Unexpected response types, invalid base64/UTF-8, empty/NUL content and content above 25,000 decoded
bytes fail closed. Policy-specific validation of a password, PEM or MFA seed remains the consumer's
responsibility.

`VaultSecretValue` carries the public secret OCID/version and a `SecretStr` value omitted from its
representation. Consumers must explicitly retrieve the text for legitimate use. Do not serialize,
log or place the revealed value in audit events, API errors or command arguments. Read failures are
only `VAULT_SECRET_UNAVAILABLE`; provider exception details are suppressed.

## Workload identity

`oke_vault_reader(scope)` is an explicit hosted composition call. Importing the module does not
contact OCI. Construction requires a known SDK region and an identical
`OCI_RESOURCE_PRINCIPAL_REGION` environment value. It obtains one OKE workload signer and reuses it
for both regional clients. No OCI config-file, laptop API-key, instance-principal, recovery-user or
simulator fallback exists. Startup errors return only `OKE_VAULT_STARTUP_FAILED`.

The official OCI Python SDK is pinned in the backend lockfile. Service clients retain verified TLS,
use 5-second connection/10-second read timeouts and explicitly disable SDK retries/circuit breaking
so higher-level workflows own retry policy. Requests do not enable debug logging. The SDK workload
signer's token exchange has its own timeout behavior; the service-client timeouts are not a total
startup deadline. Keep signer instances long-lived rather than constructing one per secret read.

The factory selects `/var/run/secrets/kubernetes.io/serviceaccount/token`. The SDK also requires the
service-account CA and Kubernetes service host, and contacts the OKE proxymux token service. These
are platform-provided inputs, not credentials accepted from browser requests. The current held
manifests disable automatic token mounting and use the approved [NSG-only V1 network boundary](../how-to/nsg-only-networking.md). [Token/CA projection and scoped read IAM](../how-to/oke-workload-identity.md) now exist in source. Before activation,
qualify them and add specific network permissions; do not enable workloads by relying on node instance authority.

## Tests and pending qualification

Automated synthetic tests cover CURRENT rotation, immutable version selection, wrong scope/state,
wrong returned identity/version, malformed/oversized content, redaction/error suppression, strict
factory region selection and no alternate identity fallback. A real SDK client dispatch test
intercepts the HTTP boundary and verifies GET selectors; no OCI calls occur.

Live Enhanced OKE identity/token refresh, IAM deny cases, Vault metadata/retrieval privileges,
network timeouts, rotation races and service-role integration remain Pending in the
[real OCI qualification manifest](../how-to/real-oci-test-manifest.md#vault-retrieval-and-oke-identity).
No new interactive test is exposed in Atlas by this slice.

Official references: [Python SDK signing](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/signing.html),
[secret retrieval API](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/secrets/client/oci.secrets.SecretsClient.html)
and [workload identity setup and IAM](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm).

## Source validation — 14 November 2026

The backend unit gate passed 2,756 cases with no failures/errors/skips and 95.35% complete-source
line coverage across 193 modules. All 54 focused Vault cases passed. The owned container
build/runtime smoke/image-scan pipeline passed without using saved application data. The runtime
dependency audit found an existing OpenTelemetry API vulnerability; the lockfile now uses the fixed
1.45.2 release and the fresh audit reports no known vulnerabilities. No audit bypass was added.

Ruff, inline-purpose, Bandit, documentation/link, publication, credential and whitespace checks passed;
independent documentation/security reviews passed. Scanner false positives for a file-path constant
and synthetic identifier were resolved with clearer names, without scanner exceptions. The full
integration/Playwright suite remains a milestone/PR gate. No Vault/OCI calls or deployment occurred;
the saved demo continues to use its previous matched source/assets snapshot.

## Named development profile follow-up — 14 November 2026

`configured_vault_reader(settings, scope)` now supports the explicit local API-key profile or hosted
OKE selection through `platform_identity`. The original `oke_vault_reader` remains OKE-only; its
no-local-fallback contract is unchanged. Both paths use the same metadata/content/version guards.
Full live application service composition and actual IAM qualification remain pending.
