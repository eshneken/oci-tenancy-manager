# Terraform state bootstrap

**Implemented source; live execution not yet qualified.** This procedure covers only the initial
state bucket. It does not create OKE, PostgreSQL, IAM federation or an application deployment, and
does not authorize live changes. Use staging first when tenancy access and approval are available.
The [infrastructure reference](../../infra/README.md) documents inputs, guards and mock tests.

Use the [hosting compartment renderer](hosting-compartment.md) to create private `hosting.tfvars.json`
from `OTM_HOSTING_COMPARTMENT_OCID` before planning. All roots use that existing compartment; no child
compartments are created. Pass the file alongside the other reviewed inputs.

## Before any live command

1. Confirm the approved environment, tenancy, region, existing hosting compartment and
   Object Storage namespace through OCI. Verify the authenticated principal's actual tenancy,
   effective permissions and compartment ancestry independently. An OCID pattern or environment
   string is not proof. Staging and production must not share principals or state paths.
2. Use an approved short-lived operator SecurityToken profile for this first bootstrap. The root
   also supports explicitly selected ResourcePrincipal or InstancePrincipal for later qualified
   execution; it never selects these automatically. Do not pass tokens, private keys or passwords
   through Terraform inputs or record them in plans, chat or repository files.
3. Install the exact CLI version and run `bash scripts/check_infrastructure.sh` from the repository
   root. This is safe without OCI credentials: all provider effects in those tests are mocked.
4. Create an operator-only directory outside the checkout, set `umask 077` and verify directory
   permissions. Give staging and production separate absolute paths. Copy only the selected
   root's `terraform.tfvars.example` to a private `target.tfvars` there, then replace its synthetic
   coordinates and profile with the approved values. Keep provider metadata, plans, state and state
   backups there too. Exclude all of this from cloud-synced/public folders and CI artifacts.

## Create the bucket — operator-reviewed commands

The following is a template for **staging only**, not a command executed during development.
Replace the private directory before use. Run from the repository root. Do not point the production
root at staging inputs, or reuse either environment's initialized backend directory.

```sh
umask 077
export OTM_BOOTSTRAP_DIR=/absolute/private/path/otm-staging-bootstrap
export TF_DATA_DIR="$OTM_BOOTSTRAP_DIR/provider-data"

terraform -chdir=infra/environments/staging/bootstrap init \
  -input=false -lockfile=readonly \
  -backend-config="path=$OTM_BOOTSTRAP_DIR/bootstrap.tfstate"

terraform -chdir=infra/environments/staging/bootstrap plan \
  -input=false -var-file="$OTM_BOOTSTRAP_DIR/target.tfvars" \
  -var-file="$OTM_BOOTSTRAP_DIR/hosting.tfvars.json" \
  -out="$OTM_BOOTSTRAP_DIR/bootstrap.tfplan"

terraform -chdir=infra/environments/staging/bootstrap show \
  "$OTM_BOOTSTRAP_DIR/bootstrap.tfplan"
```

1. Inspect the plan locally. Expect exactly one new private, versioned Standard bucket in the
   approved compartment/namespace, no IAM/compute/database changes and no destruction. Verify the
   account using an independent OCI session; keep raw plan output private.
2. Once approved, apply that **exact saved plan**, without re-planning under different inputs:

   ```sh
   terraform -chdir=infra/environments/staging/bootstrap apply \
     -input=false "$OTM_BOOTSTRAP_DIR/bootstrap.tfplan"
   ```

3. Verify the actual bucket's scope, private access, versioning and encryption in OCI. Securely
   preserve the local bootstrap state and backup. If creation is interrupted, inspect that state
   and OCI before retrying; do not discard state and try a second independent creation.
4. Record only sanitized revision/result evidence in the manifest. Keep identifiers, plans,
   state and credentials private. Remove expired plan files through the approved private-file
   handling process. Production repeats this procedure with its own root, inputs, paths,
   credentials and approval after staging qualification.

## What this does not finish

The bootstrap state's local backend must remain protected. The output key
`platform/<environment>/terraform.tfstate` is reserved for that environment's separate **platform
root**, not a migration destination for this bucket's bootstrap state. The
[network foundation](network-foundation.md) now declares those partial remote backends; initialization,
locking and recovery still require live qualification. Bootstrap-state migration remains separate
work. Never initialize two different root states onto the same key.

Before using hosted Terraform delivery, qualify remote locking with competing writers, least-privilege
access, version recovery, loss of local bootstrap state, interrupted initialization and state-bucket
deletion protections. Do not use retention locks on mutable state/lock objects. Terraform's
`prevent_destroy` cannot stop privileged direct OCI deletion or resource removal from configuration.

These open cases remain [Pending in the live manifest](real-oci-test-manifest.md#terraform-state-bootstrap).
Do not infer remote-backend or recovery qualification from the mocked tests or bucket creation.
