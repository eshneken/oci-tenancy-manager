# Atlas corporate identity pilot

The implementation checks exact OCI login lookup, immutable domain identity binding, and
environment-specific app eligibility. It uses allowlisted SCIM user requests and native OCI membership operations. The OIDC primitives generate S256 authorization
parameters and verify signed claims from a caller-selected trusted RSA key. A successful check
returns the signed domain user GUID and exact environment group GUID. The sign-in boundary
requires both the group proof and a valid Atlas grant. Local recovery uses its existing grant
checks without contacting OCI.

The opt-in laptop API uses a same-origin sign-in start and exact HTTPS callback, covered by
synthetic tests and exercised on 8445. Its in-process store accepts up to 128 attempts for 300 seconds and
consumes a matching browser attempt before exchange. A server restart invalidates pending
attempts. Shared storage for hosted replicas remains a separate implementation step.

The exchange pins domain discovery, token and signing-key HTTPS endpoints. It uses an injected
server-side confidential-client secret loader only after validating discovery. Migration 0031
adds a closed `corporate_sign_in_succeeded` audit event. Session issuance rechecks the Atlas grant
under the protected recovery-row lock and commits the hashed session and audit event together.

The sign-in page shows **Sign in with Corporate SSO** as its primary action when the backend reports
that corporate sign-in is configured. Password and TOTP remain available under **Recovery
administrator sign-in**. Installations with recovery sign-in alone display the recovery form
directly. Capability discovery never calls OCI and has a two-second client-side timeout.

The OCI pilot verified the signed immutable user ID, Oracle SSO provenance and the exact
development group in `groups[].id`. Atlas requests `openid get_groups` and verifies the group
only at session issuance. Existing sessions recheck the Atlas grant in PostgreSQL. OCI-only group
removal affects the next sign-in. Atlas grant revocation ends existing sessions immediately.
No upstream tokens, group lists or OCI directory reader credentials are stored by this flow.

The 8445 laptop launcher opts in when its ignored installation directory has a private
`corporate-sign-in.json` containing the matching target and OIDC binding. Store the existing
OAuth secret separately as `corporate-client-secret` in the same owner-only directory. A missing
or invalid binding disables corporate sign-in and leaves recovery available. The client secret is
read during exchange. An unavailable secret fails corporate sign-in without affecting recovery.
The existing idle and absolute session settings apply to both methods.

Register the callback `https://127.0.0.1:8445/api/auth/sso/callback` only in the development
confidential client after approval. Qualify trust in the browser used for the pilot. Confirm app
capacity for the domain type, the signed stable user GUID and corporate-provider claims, and
rejection of a pre-existing native OCI session before enabling regular Atlas sign-in. Test the designated provisioning
identity separately, verify that account creation suppresses provider notifications, and verify
that the Atlas app group confers no OCI resource permissions.
Chapter 26 defines the [full acceptance matrix](../engineering-design/26-administrator-sso.md#implementation-and-acceptance).

## OCI Console pilot sequence

1. In the non-production Default domain, prepare an identity-provider policy for
   `otm-application-development` that offers only the existing `Oracle SSO` provider. Prepare a
   sign-on policy scoped to the same app. Put the rule allowing the authenticating `Oracle SSO`
   provider first and require reauthentication. Follow it with a deny rule for every other
   match. Bind and verify the Oracle-only identity-provider policy while the app is inactive.
2. OCI's Console sign-on policy picker lists the active apps. After approval, verify that
   **Login Target** and **Enforce grants as authorization** are on and the app has zero grants.
   Activate the app,
   bind the reviewed sign-on policy to Atlas alone, and read back both policy bindings.
   If the sign-on binding fails verification, return the app to inactive. After both
   bindings pass, assign the empty `otm-development-users` group. Verify that it is the
   sole assignment and that a user outside the group cannot access the app.
3. After approval for one existing federated pilot identity, test Oracle SSO in a fresh browser
   and from a browser with a native OCI session. The verified OIDC GUID must match the domain
   user GUID, and Atlas access must require an active grant in the 8445 database.

See [assigning groups to custom applications](https://docs.oracle.com/en-us/iaas/Content/Identity/applications/assign-groups-custom-applications.htm)
and [creating a sign-on policy](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/add-sign-policy.htm).

## Administrator enrollment and removal

Open **Administrators → Add administrator** when the development writer is enabled. Enter the
exact Oracle SSO work email, then review the address, environment and account action. Atlas
checks the OCI login again on confirmation. It reuses an existing active OCI account by GUID and
preserves the user's native OCI sign-in options. Atlas sign-in still requires Oracle SSO. If the login is absent and creation is enabled, Atlas creates a federated OCI account
using the submitted email as the login and the required first and last names for the new OCI
profile. Each name must contain 1–100 characters after trimming. Atlas requests notification
bypass and supplies no local password, API credentials or roles.
Atlas independently reads back the exact domain, login and GUID before adding the single
group membership and committing the Atlas grant. Authentication uses the existing Oracle SSO
federation. The receiving user only needs to sign in to Atlas.

To remove access, review the identity and environment before confirming. When a grant has no
saved work email, the current directory shows its unique Atlas grant reference. Atlas revokes the
grant, invalidates its sessions and records the audit event in one transaction. Then it removes
that identity's membership in the exact environment group. The OCI user and all other group
memberships stay intact, including for accounts originally created by Atlas. Atlas resolves the
exact existing native membership OCID and calls `RemoveUserFromGroup` with that association
ID. Enrollment calls `AddUserToGroup` with the verified user and group OCIDs.
If cleanup is pending, use
**Retry OCI group cleanup** for the revoked row. Once both OCI membership views confirm removal,
Atlas records completion for that grant revision and hides the row from the administrator list,
including after reload. Existing unverified revocations stay visible for retry. The grant and its
audit history remain, and a regrant restores the same grant identity with a new authorization
revision. A new grant revision invalidates old retry requests. The qualified adapter must also settle any ambiguous OCI write before permitting an
opposite mutation and bound calls made while holding the administration lock.

Pilot existing federated accounts first, including removal and regrant from a recovery
session. Before enabling creation, verify the new account can federate through the exact
corporate username mapping and has no OCI resource access through the Atlas group or
automatic domain membership. Independently confirm suppressed provider email and successful
reconciliation of an uncertain create.

Enrollment on 8445 uses an ignored, owner-only `corporate-enrollment.json`. Specify
`config_file` (absolute private OCI config path) and `profile` (the dedicated development
writer). Set `use_application_profile` only when both fields match the isolated 8445 application's
configured scoped signer. In that mode the startup check reads the exact Atlas group with the
same signer and leaves the operator profile outside the web process. Run the OCI development
database setup before enabling enrollment on an older installation.

Keep an owner-only `corporate-assignment.json` beside the writer configuration. Use a separate
operator read of the active application's immutable ID, OAuth client name and exact callback.
Verify enforcement of app assignments and read the precise group grant. Record the app, client,
callback, group and grant in the `app`, `client_id`, `callback`, `group` and `grant` fields.
Request only nonsecret provider attributes. The restricted writer cannot read apps or grants.
The grant field records the operator-verified group-to-app assignment GUID. Atlas matches the
app, client, callback and group to its configuration before mounting enrollment. It verifies the
named development group
on each mutation. Remove the evidence and restart the laptop API before changing the active
app or assignment. Reverify and restore it after the approved change.

Migration 0033 admits distinct `administrator_granted` and `administrator_regranted` security
events. Regrants keep the original Atlas grant
and OCI user ID, refresh the verified contact and display details, and record both authorization
revisions without copying names into the event evidence.

Plan and qualify the [laptop enrollment policy](../how-to/laptop-oci-development.md#development-laptop-enrollment-policy)
with that profile. Configure the matching `create_users` switch only after approval of its
separate policy statement. The pilot verifies reads independently. Use controlled pilot users
to verify member updates, user creation, notification suppression and denial of unrelated writes.

The private `corporate-enrollment-holds` directory contains `.pending` markers for writes
whose result may be unverified. A marker fences either account creation for the same login or
membership changes for the same OCI GUID. A later retry can clear an acknowledged membership
marker after both the native association state and the SSO group read agree with the recorded
direction. An unacknowledged write requires operator reconciliation using exact OCI readback
and available audit evidence. Retain its marker while the outcome is uncertain. Verify recovery sign-in before testing removal and regrant.

## Terraform follow-through

Use [OKE Workload Identity](../how-to/oke-workload-identity.md) for staging and production
provider calls. The local milestone leaves enrollment IAM absent in both hosted platform roots.
Scope future IAM to each installation's cluster, namespace and Kubernetes service
account. Qualify Identity Domains operations using that workload identity before enabling
hosted enrollment. The local API-key profile is unavailable to hosted runtimes.

After the development pilot passes, manage each installation's OIDC client, app-assignment group,
group-to-app assignment, app-specific identity-provider and sign-on policies, and qualified runtime
authorization through Terraform. Use environment-owned state and separate client, group, callback
and credential bindings for development, staging and production. Development and staging share
the non-production domain's signing-key setting. Production owns its setting separately. See
[Terraform ownership for signing keys](../engineering-design/26-administrator-sso.md#terraform-ownership-for-signing-keys)
for import, verification and shared-domain impact. Reference the approved upstream federation
without taking ownership of shared federation or the existing workload client.

Use the Terraform [application registration metadata module](../../infra/modules/application-registration/main.tf)
for integrated app and app-assignment group display names and descriptions. The module returns
metadata strings and declares no OCI resource. Apply display-name updates to the existing app and
group so the OAuth client ID, group ID, membership and all bindings stay intact. Import the exact qualified development objects into
their Terraform addresses after qualifying secret exclusion and require a reviewed no-change
plan before applying follow-on changes. Review staging and production
plans independently. Keep OIDC client secrets in dedicated environment custody. Qualify the
provider's secret handling before adoption and exclude secret values from source, plans, artifacts
and Terraform state. Atlas owns routine membership and grant changes after onboarding is enabled.

The development operator bootstrap already owns the state bucket and the two development IAM
policies. A refreshed plan using a private copy of the operator state returned no changes.
The protected **Development infrastructure** workflow plans the Vault and software key in its
separate custody state. It has no identity-domain adoption authority.

The pinned OCI provider 9.13.0 was tested against a synthetic App endpoint. Both CLI import and
an import-block plan used default App reads despite the resource's attribute allowlist. The
synthetic client credential fields appeared in the resulting state and saved plan. Keep the
existing development app outside Terraform until a supported import and refresh path excludes
those fields. Also qualify group adoption without importing administrator membership data.
[Oracle App resource and import documentation](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/identity_domains_app.html#import)
