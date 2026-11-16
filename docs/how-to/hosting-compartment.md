# Hosting compartment release input

Each environment installs all Atlas infrastructure in **one existing OCI compartment**. No child
compartments are created. Staging and production remain in separate tenancies and use their own
hosting compartment, state, credentials and deployments.

Configure **`OTM_HOSTING_COMPARTMENT_OCID`** as a nonsecret GitHub Actions **environment variable**
in both `staging` and `production`. Use each tenancy's approved existing compartment OCID. There is
no default and no synthetic value is configured for live deployment. The actual tenancy/compartment
values remain pending until access is available. The deployment workflow must use the selected
protected Environment's value, not an unrestricted caller-supplied target or a PR/fork value.

This variable feeds the required flat Terraform input `hosting_compartment_ocid` in all six
bootstrap/security/platform roots. The infrastructure modules receive the same selected value for
state bucket, Vaults, encryption keys, IAM policy, VCN/network resources, OKE and managed PostgreSQL.
No target is inferred from the organization parent/child tenancy. Resource-specific service behavior
and actual placement still require live verification.

## Render and apply the reference

With the approved environment variable supplied privately, run from the repository root:

```sh
uv run --project backend python -m otm.hosting_release \
  --output /absolute/private/path/hosting.tfvars.json
```

The offline converter validates the OCID string (maximum 255 characters), exclusively creates an
owner-only `0600` file and prints only its SHA-256 digest. It refuses missing/malformed/padded input,
existing files and symlink destinations. It does not authenticate, create compartments, initialize
state or call OCI. Format validation is **not** proof of tenancy ownership or permissions.

Pass `-var-file=/absolute/private/path/hosting.tfvars.json` when planning each root, alongside its
other private inputs, then review/apply that exact saved plan. Keep this input file environment-owned
and private. Remove the former `target.compartment_ocid` field from private target files; tenancy,
namespace, environment and region remain in `target`. A single flat input avoids Terraform's
whole-object tfvars replacement semantics and conflicting handwritten compartment selections.
Do not use another var-file or `-var` to override the selected hosting value.

The protected infrastructure workflow is still pending implementation. Its environment binding will
pass the variable as data, without shell interpolation or command evaluation:

```yaml
# Trusted infrastructure-job fragment, not an implemented deployment workflow.
env:
  OTM_HOSTING_COMPARTMENT_OCID: ${{ vars.OTM_HOSTING_COMPARTMENT_OCID }}
```

Existing short-lived operator authentication remains separate from backend authentication and from
application identities. Independently verify the principal, selected tenancy, compartment ancestry,
namespace and effective IAM before live planning or mutation. The Terraform provider identity and
cloud IAM must constrain the target even if a variable is accidentally changed. A changed hosting
compartment is an infrastructure migration requiring explicit review, not a routine app update.

Use the [state bootstrap](terraform-state-bootstrap.md), [Vault foundation](vault-foundation.md)
and [platform network procedure](network-foundation.md) in order. All use the same compartment input
within the selected environment, but retain independent state keys. IAM must restrict access by the
necessary resource IDs/conditions; sharing a compartment never justifies broad app secret or state
access. Live placement, effective permission/denial and workflow-origin checks remain in the
[manual qualification manifest](real-oci-test-manifest.md#single-hosting-compartment-input).

## Source verification — 13 November 2026

All eleven native infrastructure suites passed (137 cases), plus five resource-replacement guards.
Both environments' six roots test alternate explicit compartment placement and malformed-input
rejection. The Vault suite checks exact Vault-ID-conditioned IAM in the shared compartment, with
no child-compartment resources. All 2,508 backend unit tests passed without skips and 95.18%
complete-source line coverage, including 13 hosting-renderer cases. Documentation/contracts,
publication, credential scan, inline-purpose, Ruff and focused Bandit checks passed. Independent
security review passed; documentation findings about the former compartment layout were corrected.
No live OCI target variable, resource, application snapshot or data was changed. Full application
integration/milestone and live service qualification remain separate gates.


## Laptop development alongside staging — 14 November 2026

The non-production tenancy may host sibling development and staging compartments. The single-compartment rule applies within each environment, not across both: staging retains its own one-compartment platform while [development](laptop-oci-development.md) adds only its own Vault/key. No OKE/managed database is duplicated for the laptop. Each root has its own private state and input; production remains in another tenancy.
