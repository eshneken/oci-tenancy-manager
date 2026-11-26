# Hosting compartment release input

Each hosted environment uses **one OCI hosting compartment**. Staging and production have
separate hosting compartments, state, credentials and deployments. Staging shares the
non-production tenancy with development. Production uses its own tenancy.
The bootstrap root owns the compartment. The protected workflow passes its verified ID to the composed infrastructure root. The
[composed Terraform design](../engineering-design/24-environments-and-promotion.md#terraform-layout-for-each-environment)
requires Terraform ownership of staging-specific resource creation in the reviewed infrastructure
apply.

Configure **`OTM_HOSTING_COMPARTMENT_OCID`** as a private reference in a GitHub Actions **Environment Secret**
in both `staging` and `production`. Use each tenancy's approved existing compartment OCID. There is
no default and no synthetic value is configured for live deployment. The actual tenancy/compartment
values remain pending until access is available. The deployment workflow must use the selected
protected Environment's value, not an unrestricted caller-supplied target or a PR/fork value.

This variable feeds the required flat Terraform input `hosting_compartment_ocid` in the three
composed infrastructure roots. The infrastructure modules receive the same selected value for
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

The held [plan/review/apply infrastructure workflows](infrastructure-plans.md) pass the reference as data,
without shell interpolation or command evaluation. Secret-backed custody prevents GitHub from
printing the private OCID in a step header before the renderer runs:

```yaml
# Trusted environment input; the implemented workflows remain held pending live qualification.
env:
  OTM_HOSTING_COMPARTMENT_OCID: ${{ secrets.OTM_HOSTING_COMPARTMENT_OCID }}
```

Existing short-lived operator authentication remains separate from backend authentication and from
application identities. Independently verify the principal, selected tenancy, compartment ancestry,
namespace and effective IAM before live planning or mutation. The Terraform provider identity and
cloud IAM must constrain the target even if a variable is accidentally changed. A changed hosting
compartment is an infrastructure migration requiring explicit review, not a routine app update.

Use the [state bootstrap](terraform-state-bootstrap.md) to manage the compartment. The
[Vault](vault-foundation.md) and [network](network-foundation.md) modules then share that
compartment inside one infrastructure root and remote state per environment. IAM must restrict access by the
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
