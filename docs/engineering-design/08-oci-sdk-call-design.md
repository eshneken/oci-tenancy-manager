# 08: OCI SDK call design and qualification

20 October 2026 | C2 call map, first review draft | No OCI runtime qualification

[Design hub](README.md) · [Execution/facade](02-operations-and-provider.md) ·
[Identity and credentials](04-identity-and-access.md) · [Onboarding](07-onboarding-journeys.md)

## Read this first

The workflows now have concrete Python SDK candidates. Create/import and bootstrap are traced in
execution order; deletion and association flows reuse those primitives. Configuration, financial and
credential calls are mapped, but their complete payload/normalization rules still belong to C3–C5.
This is not approval of a migration, production facade implementation or new product behavior.

Static inspection found **91 selected methods on 10 clients and 23 model definitions** in Oracle's
Python SDK **2.188.0**, tag `v2.188.0`, commit `df5a803743d2560ec37ef5d1e437d5978ef7d33a`.
[The machine-readable inventory](../contracts/oci-provider-call-inventory.json) records inputs,
response descriptions, HTTP paths, per-method retry-token/ETag/request-ID support and source links.
The check receipt (private historical evidence; not distributed) states what
was inspected. SDK files were parsed as text/AST, never imported; no SDK was installed into the app,
no credentials were loaded and no OCI endpoint was called. This reviewed version is not yet the
application's dependency pin. Live `latest` documentation pages showed differing patch versions;
the pinned source is the authority for the static method inventory.

Evidence levels: **source checked** means a call/model exists at that commit; **candidate** means
our proposed use needs permission/behavior qualification; **manual** means an accepted human step;
**blocked** means a required capability/decision remains unresolved. None means pilot-proven.

Important findings:

- Create returns no tenancy object in its response body. Persist safe response headers and resolve
  the actual target through supported work-request/discovery/handoff evidence.
- `CreateChildTenancyDetails.compartment_id` is the **parent tenancy OCID**, not the application's
  hosting compartment. An administrator display name is recorded by OTM; the model accepts email,
  not a separate administrator-name field.
- D27: the user confirmed all existing tenancies use identity domains. V1 uses domain identity
  management, with no standalone legacy-IAM adapter. Keep OCI user OCID and SCIM user ID distinct;
  an email is not a safe substitute. IAM service calls for metadata/compartments/policies still apply.
- A legacy one-time console reset is not deterministic rotation of a stored emergency password.
- Tenancy administration and directly assigned identity-domain administration are separate checks.
- D26 completes deletion at confirmed initiation; do not add a final-deletion waiter or 30-day poll.

## Access contexts and endpoint rules

| Context | Credential and purpose | Boundary |
|---|---|---|
| Hosting | Qualified workload identity for OKE, or configured credential; accesses OTM's Vault compartment and supporting services | Hosting tenancy may be different from parent. It gains no implicit child/parent administration |
| Parent | Configured parent API identity or qualified same-tenancy workload identity | Organization reads/create/termination; parent region subscriptions and qualified billing queries |
| Bootstrap child | Temporary API identity; private key only in Vault, public key handed to admin | Inspect and establish replacement access, then permanently retire exactly this temporary user/key |
| Permanent child | Bound automation identity and exact Vault key version | Subsequent user/group/configuration checks and changes in that child |
| Independent recovery | Custodied human account and out-of-band runbook | Not a background-job signer or a dependency on the availability of OTM |

A provider request identifies the intended tenancy, domain, region, item binding and credential
reference; the resolver validates their relationship before signing. Do not share a mutable SDK
client between concurrent tenancy contexts. Changing an SDK config's tenancy string does not grant
cross-tenancy rights. Cross-tenancy policies, where needed, require separate qualification.

Discover domain URL/home-region URL using `IdentityClient.list_domains` / `get_domain` in the correct
child scope. Validate the HTTPS endpoint against verified provider metadata and configured realm;
never accept an arbitrary browser-supplied service URL. Domain SDK resource paths already contain
`/admin/v1`; construct the service endpoint accordingly, without duplicating that path. Discovery
failure is Unverified, not a reason to switch silently to a legacy adapter or another domain.
Read policies/users/compartments in the qualified region/domain; use `list_regions` to translate
home-region keys and `list_region_subscriptions(parent_ocid)` for creation choices.

References: [domain API authorization](https://docs.oracle.com/en-us/iaas/Content/Identity/api-getstarted/api-get-started.htm),
[Identity client](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/client/oci.identity.IdentityClient.html),
[domain client](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity_domains/client/oci.identity_domains.IdentityDomainsClient.html).

## Facade contracts: candidate shapes

Keep a small set of typed application capabilities rather than exposing 91 methods as public API
endpoints. Names below are design labels, not implemented Python methods or approved HTTP schemas.

| Capability | Application input | Safe result and boundary |
|---|---|---|
| Inspect organization/tenancy | Context reference, configured organization/parent, exact target OCID | Actual parent/role, name, home region, origin evidence, observation time and coverage |
| Request child | Frozen requested name/home region, parent/subscription options, initiating verified email, request identity | Accepted/Rejected/Unknown; provider request/work-request identifiers when present; no invented child OCID |
| Inspect onboarding identity | Target/context, supplied bootstrap user OCID, configured domain selection | Verified identity binding, domain URL/OCID, SCIM ID if applicable, key fingerprint and capability evidence |
| Apply one identity/grant/item | Frozen typed desired item, explicit binding/scope/dependencies, expected revision | Known binding plus observed effect, Pending, Rejected or Unknown; no unbounded onboarding script |
| Retire one identity/grant | Bound identity/grant IDs, remaining-use checks and current retirement intent | Verified removal or honest partial/unsupported/unverified outcome |
| Request termination | Exact registered eligible child, guards, expected provider version when available, request identity | Confirmed initiation, Rejected or Unknown; D26 result, not permanent deletion |
| Observe item/access | Bound target/item and desired version | Present/matching, confirmed missing/different, or unable to observe; timestamp and coverage |
| Read/write credential reference | Hosting context, exact Vault secret/version, intended consumer and operation | Secret material confined to resolver/disclosure boundary; other callers see nonsecret receipt |
| Collect financial observations | Qualified child automation, exact bound budget OCID/generation, current monthly cycle and rate-card currency/profile | Same-read budget amount/current-cycle actual/total forecast/computation timestamp; unavailable is not zero |

An outcome envelope retains target, operation/step/attempt, expected intent revision, observation time,
provider correlation, safe error code and evidence source. Not every method accepts `opc_request_id`:
record provider-returned IDs when available and retain OTM attempt IDs regardless. Do not leak
passwords, PEMs, OAuth tokens or vendor objects into the envelope. Distinguish command acceptance,
item verification and human login evidence. No single `success: true` can represent all three.

## Create and import: ordered call map

Abbreviations in the following tables: `Org` = `oci.tenant_manager_control_plane.OrganizationClient`;
`WR` = that service's `WorkRequestClient`; `IAM` = `oci.identity.IdentityClient`;
`Domain` = `oci.identity_domains.IdentityDomainsClient`. Methods/payload fields are source checked;
permission sufficiency and exact response evidence remain qualification obligations.

| Step | Context and exact SDK candidate | Inputs / output to persist | Completion or recovery |
|---|---|---|---|
| C01 Check parent | Parent: `Org.get_organization(organization_id)`, `get_organization_tenancy(organization_id, parent_ocid)`; `IAM.list_region_subscriptions(parent_ocid)` | Bind returned organization compartment/parent and role; subscribed region choices | Wrong/protected scope blocks; denied or incomplete reads remain unverified |
| C02 Prepare bootstrap | Hosting: `VaultsClient.create_secret(CreateSecretDetails(...))`, later `get_secret`; local keypair generation | Vault/key/hosting compartment, unique name, private PEM secret; public PEM/fingerprint separately | Stage private material before any API upload; unknown Vault create reconciles by recorded intent/binding |
| C03 Request child | Parent: `Org.create_child_tenancy(CreateChildTenancyDetails(...), opc_retry_token=..., opc_request_id=...)` | Required `compartment_id=parent_ocid`, `tenancy_name`, `home_region`, `admin_email`; optional subscription/governance/policy/features only if configured/qualified | Response data is None. Record status and correlation; capture `opc-work-request-id` if returned. Lost response is Unknown, not a new child request |
| C04 Track request | Parent: `WR.get_work_request(id)`, paginated `list_work_request_errors/logs(id)`; when justified `list_work_requests(parent_ocid)` | Work-request status and resource identifiers; safe, redacted diagnostics | Persist next check and release worker. Do not run composite waiters through a human wait; missing/ambiguous resource identity needs inspection |
| C05 Human activation | No SDK replacement selected | Initiating admin activates tenancy, sets password/MFA, creates temporary API user with required grants, uploads public key, supplies child, bootstrap user and activation administrator user OCIDs (the last field is create-only) | Durable human wait. No activation URL or personal credentials collected by OTM |
| C06 Inspect handoff | Bootstrap: `IAM.get_tenancy(child_ocid)`, `list_domains(child_ocid)` / `get_domain(domain_ocid)`; Domain `list_users` to resolve verified supplied OCI OCID, then `get_user(scim_id)`; Parent: `Org.get_organization_tenancy(organization_id, child_ocid)` | Actual name/home-region key, actual child role, identity/domain facts; independently resolve the bootstrap and create-only activation administrator OCIDs to verified same-child domain/SCIM bindings before domain writes | Prove actual parent against configured organization, identity binding and same target; do not trust supplied names or an email match |
| C07 Prove parentage | Parent: `Org.get_organization(organization_id)` plus target membership; optional `LinkClient.list_links` / `get_link(link_id)` | Organization parent identity and, where used, active CORE parent/child link | A scoped membership result is not generic proof of every child capability. Missing/incomplete proof blocks writes |
| C08 Permanent automation | Bootstrap: identity/key/group/role calls in next section; Hosting: new permanent private-key secret | Bound permanent identity/key/grants and Vault reference | Verify a separate request signed using the permanent key, including required domain access, before relying on it |
| C09 Owner/recovery/baseline | Permanent child: same identity/grant handlers and managed-item calls below | Intended owner full administration, required recovery and exact frozen baseline results | D20 does not wait for first owner sign-in. D39/D40 select the recovery-only MFA exemption and persistent recovery flow; exact policy/login/restoration behavior still requires qualification |
| C10 Retire temporary access | Permanent child: applicable membership/grant/key/user retirement calls | Recorded temporary API identity/key and, for net-new create only, bound initial local human identity | Never self-delete or remove last required administrator. Verify cleanup; partial cleanup stays visible and prevents Setup verified |
| C11 Publish setup | OTM database only | Verified operation/item evidence, registry and active associations | Atomically publish local verified state/history; no SDK call creates an organizational ownership relationship |

The create model's home region must be subscribed by the parent. Requested name is provisional;
actual name is discovered from verified OCID. Definitive name rejection may amend the same operation;
uncertain creation reconciles before another create. The model does not provide global name
reservation. Optional `subscription_id` adds permission requirements. Sources:
[create model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/tenant_manager_control_plane/models/oci.tenant_manager_control_plane.models.CreateChildTenancyDetails.html),
[child creation](https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm),
[work-request client](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/tenant_manager_control_plane/client/oci.tenant_manager_control_plane.WorkRequestClient.html).

Import starts at C02/C06 after external parent transfer, performs read-only inspection and an
explicit preview/start, then reuses C08–C11. It does not invoke sender/recipient invitations,
subscription remapping, link deletion or another `create_child_tenancy`. Keep OCI origin distinct
from imported-via-OTM provenance. Preserve unrelated existing identities; import cleanup removes
only the explicitly bound temporary access. A live parent's administrative scope does not prove
its child IAM credential works. A copied source user name is insufficient to establish that access.

## Identity, key and grant primitives

### Store both identifiers

For domains, persist the verified tuple `(child tenancy OCID, domain OCID, domain endpoint,
SCIM user id, OCI user OCID)`, with provenance and observed-at. Keep `Group.id` versus `Group.ocid`
and key resource ID versus fingerprint distinct too. Signing uses OCI identity/fingerprint; SCIM
resource URLs use SCIM IDs. The bootstrap UI still asks only for the accepted user OCID: the adapter
resolves its corresponding domain resource and verifies returned `ocid`/domain/tenancy. If it cannot
resolve uniquely, request qualified missing context rather than treating an OCID as a SCIM ID.
Email/name search yields collision candidates only. Do not retarget a known binding by email.

D27 makes the domain path below the V1 design. The SDK's IAM client remains necessary for
OCI tenancy metadata, domain discovery, compartments and root policies; using that service does
not imply supporting a legacy user-management model. An optional OCI `get_user` lookup may be
qualified as a domain/OCID bridge, not as a fallback adapter. The primary lookup resolves the
supplied OCID to a domain user and validates its returned OCI OCID, SCIM ID and domain/tenancy.

| Primitive | Identity-domain path | Verification / special rule |
|---|---|---|
| Personal or automation user | `create_user(user=User(...))`; `get_user(scim_id)` / `list_users(filter=...)`; explicit SCIM schemas/profile | Verify binding and owned/adopted intent. Request body is keyword `user`; an email match alone cannot authorize adoption |
| API key | `create_api_key(api_key=ApiKey(...user reference..., key=public_pem))`; `get_api_key` / `list_api_keys` | Verify expected user and public fingerprint; fresh signer proves usability. Private PEM never uploaded to OCI IAM |
| Group | `create_group(group=Group(...))`; `get_group` / `list_groups` | Bind exact SCIM ID/OCI OCID; no auto-adoption by display name; preserve unrelated groups |
| Membership add/remove | `patch_group(group_id, patch_op=PatchOp(...))` with target member add/remove, then inspect bound group/member | Preserve all other members. Use current ETag where supported; do not PUT a stale complete member list |
| Full OCI administration | Qualified domain-qualified group membership plus root IAM policy as needed | Domain administration alone is not full tenancy administration; verify OCI and domain privileges independently |
| Direct domain role | `list_app_roles`, `get_app_role`, `list_grants`; explicit `create_grant(grant=Grant(...))` / `get_grant` | Discover system app/role and exact grantee refs; required direct-role assignment survives cleanup |
| Credential capabilities | `put_user_capabilities_changer(scim_id, user_capabilities_changer=UserCapabilitiesChanger(...))` | Enable required API-key use; disable unused capabilities only for tool-owned operational identities |
| Key removal | `delete_api_key(api_key_id)` | Bind intended user's exact key; inspect under adequate permission; never prematurely remove the only working key |
| User removal | `delete_user(scim_id)` | Retire desired assignment first; check safe identity ownership/use and replacement admin. Never delete corporate IdP identity or force-delete protected users |
| Grant removal | `delete_grant(grant_id)` and/or scoped membership patch | Inspect intended retired grant; preserve direct-admin/recovery constraints and other people's access |

SCIM collection pagination can use index/count and service tokens; IAM infrastructure collections
have their own page mechanism. Follow the actual service continuation/total semantics. Group member
attributes may be partial or require explicit attributes/pagination; a truncated list cannot prove
absence. Discovery filters must be correctly escaped, bounded and validated against returned
identity/tenancy. Qualify support for lookup by OCI OCID; never substitute a guessed SCIM ID.

The [default domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm)
and [administrator roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm)
require separate attention to OCI Administrators membership and directly assigned domain
administration. Before C10, qualify both invariants with the replacement identities. Existence of a
user, API key or policy alone is not a proof of usable administrative access. Do not try destructive
probe operations merely to test privileges. Supported safe probes plus observed grants and a
qualified entitlement matrix establish readiness; insufficient evidence remains Unverified.

The inventory preserves the original 91-call source receipt, but now classifies each call:
74 planned SDK candidates, one conditional OCI-to-domain identity bridge and16 reference-only calls
(14 legacy identity methods plus the two post-V1 Usage API calls under D41), outside V1 implementation/test scope. This is not 91 facade methods.
All tenancies using domains does not establish that they share one domain, all use Default, or have
identical federation/policy configuration. Import discovers and validates the actual target domain;
an unsupported identity model fails visibly without a legacy fallback. Exact role payloads,
permissions, endpoint/identifier lookup and supported domain configurations remain qualification gates.

## Transfer, membership and offboarding reuse

| Workflow | Concrete provider work | Local publication and boundary |
|---|---|---|
| Transfer shared owner | Establish/adopt replacement identity, grant full administration, inspect grants; apply D22 previous-owner Remove/Remain profile using primitives above | Publish one new owner only after replacement privileges verified. Old-access cleanup may remain pending; no resource or compartment move |
| Add scoped shared member | `IAM.list_compartments(child_ocid, compartment_id_in_subtree=True, ...)`, `get_compartment(parent_ocid)`; `create_compartment(CreateCompartmentDetails(compartment_id=selected_parent, name, description))` if selected; identity/group/policy handlers | Explicit D24 existing parent; verify target child/scope and grants before active membership. Full-admin profile uses no artificial compartment restriction |
| Remove shared member | Inspect bound local user/groups/grants; retire scoped memberships and personal user with applicable identity adapter | D23: no resource inventory/purge, `delete_compartment`, bulk delete or cleanup verifier. Show owner/manual compartment guidance; verify identity removal |
| Delete owned child | Parent: current organization/target/link checks; `Org.delete_organization_tenancy(child_ocid, if_match=... when available, opc_retry_token=..., opc_request_id=...)` | D26: persist a qualified successful initiation receipt and retire only that association. No wait for permanent deletion, no automatic Restore |
| Offboard person | One D25-confirmed plan dispatches independent scoped transfer/removal/termination operations | No separate OCI offboard-person API. Keep partial results; remove from active directory only when required effects are complete and no links are kept |
| Organization metadata update / identity merge | No OCI mutation implied | Stable internal identity/tenancy links preserved; email/name update is not an automatic OCI user rename or access migration |

For compartment discovery, a response limited to accessible objects is not proof that the hierarchy
is complete. D24 rechecks selected parent tenancy/lifecycle/path/permissions immediately before
creation. The parent scope grants no implicit access to siblings. If creation succeeds but profile
application fails, preserve the compartment binding and resume; never delete as compensation.

Deletion success must use the exact operation's qualified response contract. An SDK None body is
not a failure: inspect successful response/correlation. A timeout/404/access failure is not a
confirmation. If accepted-request headers provide a work request, record it, but D26 does not wait
for its permanent-deletion lifecycle. Reconciliation of an unknown request may use qualified work
request/target evidence; if still ambiguous, remain Needs attention without blind retermination.
SDK retry tokens have a bounded validity and can be invalidated; keep OTM's durable request identity
beyond that interval. A different token after uncertainty is a new risky request, not recovery.
Imported standalone-origin deletion remains blocked where OCI requires detachment: this map does
not relax the registered-current-child guard. [OCI deletion paths](https://docs.oracle.com/en-us/iaas/Content/General/organization/organization-tenancy-delete.htm).

## Managed configuration, drift and repair

| Item family | Source-checked client and methods | Payload / verify / scope obligations |
|---|---|---|
| Root IAM policy | `IAM.create_policy`, `get_policy`, `list_policies`, `update_policy`, conditional `delete_policy` | `CreatePolicyDetails(compartment_id=child_root, name, description, statements)`; compare bound statements using reviewed normalization. Domain-qualified group syntax is not a SCIM policy |
| Quota policy | `oci.limits.QuotasClient.create_quota`, `get_quota`, `list_quotas`, `update_quota`, conditional `delete_quota` | `CreateQuotaDetails(compartment_id, name, description, statements)`; validate service/region/quota grammar and parent-governance locks; no invented hard spend cap |
| Budget | `oci.budget.BudgetClient.create_budget`, `get_budget`, `list_budgets`, `update_budget`, conditional `delete_budget` | `CreateBudgetDetails(compartment_id, amount, reset_period, target_type, targets, ...)`; record owner billing context separately from target scope; not a root IAM object |
| Budget alert rule (reference-only provisioning after D30; not V1) | Budget client `create_alert_rule`, `get_alert_rule`, `list_alert_rules`, `update_alert_rule`, conditional `delete_alert_rule` | Explicit budget ID, amount/percent, actual/forecast condition and recipients; separate managed binding and comparison |
| User, group and membership | Identity primitives above | Verify exact managed properties/grants/key fingerprint/capability, not all owner-created users. Audit-user provisioning remains V2 |
| Domain sign-on/MFA policy | Candidate observation: Domain `list_policies/get_policy`, `list_rules/get_rule`, `list_authentication_factor_settings/get_authentication_factor_setting` | These SCIM policies are not OCI root IAM policies. Existence is not enrollment/enforcement proof; D39 selects recovery-only exemption; its exact write handlers, scope/precedence and verification remain C4 qualification |

D30 (21 October) changes the application shape without claiming new live SDK qualification:
exactly one bound root policy and one quota object receive complete `statements` replacements;
the single child-root monthly budget has no alert-rule provisioning. `list_alert_rules` can still
observe the no-alert requirement. Prior alert create/update/delete entries remain source references,
not V1 workflow work. The original91-call inventory is a dated source checkpoint, not the complete
D30 tagging extension below.

Tagging adds a doc-checked IdentityClient path to qualify in the pinned SDK/facade inventory:
`create_tag_namespace`, `get_tag_namespace`, `list_tag_namespaces`, `update_tag_namespace`;
`create_tag`, `get_tag`, `list_tags`, `update_tag`; and
`create_tag_default`, `get_tag_default`, `list_tag_defaults`, `update_tag_default`, `delete_tag_default`.
[IdentityClient reference](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/client/oci.identity.IdentityClient.html). A namespace create uses child root/name OTM/description;
a key create uses the verified namespace ID and key/description; a default create uses child root,
verified tag-definition ID, static value and `is_required=false`. Observe namespace/key activity,
root/default references and value. Key lookup/update uses namespace ID plus tag name. No cascading
namespace/key deletion is a V1 repair.
[Tag namespace model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/models/oci.identity.models.CreateTagNamespaceDetails.html) ·
[Tag model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/models/oci.identity.models.CreateTagDetails.html) ·
[Tag-default model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity/models/oci.identity.models.CreateTagDefaultDetails.html).
Full method signatures, response/error fixtures, permissions and runtime qualification still need
adding to the source inventory; this paragraph does not inflate its checked-call count.

Type-specific create/update/delete bodies are not interchangeable. Handler retirement is allowed
only for explicitly managed, dependency-safe objects and approved intent; inventory inclusion of a
delete method is not approval to delete users' objects. No default delete/recreate repair. Governed
or locked quotas require a qualified parent-managed path or Unsupported, never removal of locks by
stealth. Baseline publication still performs no SDK write; explicit rollout freezes item schemas,
versions, overlays and resolved targets. Every item binds its actual owning service/region/domain,
not just a tenancy OCID. Reference: [quota API](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/limits/client/oci.limits.QuotasClient.html),
[budget model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/budget/models/oci.budget.models.CreateBudgetDetails.html).

A budget supports COMPARTMENT/TAG targets, not a guessed TENANCY target enum. Qualify use of a
child root as a compartment target and any parent billing ownership separately. Do not send both
deprecated `target_compartment_id` and `targets`. Model existence alone does not prove cross-tenancy
budget placement. C3/C5 must select one authoritative per-tenancy budget meaning before cost UI totals.

## Credentials, break glass and rotation

| Action | Calls / data boundary | Required evidence and limits |
|---|---|---|
| Save/read secret material | Hosting `oci.vault.VaultsClient.create_secret/get_secret/update_secret/get_secret_version/list_secret_versions`; `oci.secrets.SecretsClient.get_secret_bundle(secret_id, stage="CURRENT")` for normal recovery-password reads; exact `version_number` for candidate reconciliation/API-key cases | Metadata and content are separate APIs. Stable secret OCID is the password locator; CURRENT is resolved live, with returned/exact candidate versions retained as evidence. Decoded content stays in the credential resolver. Base64 is transport, not encryption |
| Rotate automation key | Stage new private key in Vault; upload public key through identity adapter; verify a request with new signer; publish new version/reference; retire old public key | Inspect key-slot capacity and current generations. Unknown upload/removal reconciles by bound fingerprint/user. No automatic delete of an unrelated key to make space |
| Disclose emergency password | Audited/authorized disclosure boundary reads exact current Vault version | Commit disclosure/notification/deadline intent before release; four-hour per-tenancy rotation remains due. Secret is never an ordinary operation-result payload |
| Set known domain password | `Domain.put_user_password_changer(scim_id, user_password_changer=UserPasswordChanger(schemas=..., password=...))` | Candidate for known per-tenancy password; qualify role, policy, notification and forced-change semantics. No GET reveals or verifies the existing password |
| Reset domain password | `Domain.put_user_password_resetter(scim_id, user_password_resetter=UserPasswordResetter(...))` | Different random/reset flow; not a synonym for setting OTM's pre-staged value |
| Excluded reset shortcut | `IAM.create_or_reset_ui_password(user_ocid)` is reference-only, outside the selected password flow | One-time/reset-link behavior is not known-password rotation. Use and qualify the domain password-change path above |
| Administrator recovery-password access (D40) | Exact bound recovery user, usable Vault version, qualified password-change and reconciliation primitives; no temporary support user | Recovery-only MFA exemption behavior and password verification require qualification; password rotation is not universal session/token revocation. Named support grant/retirement is deferred |

The password flow must preserve a recoverable candidate secret version before changing IAM, then
publish the correct current reference only under qualified outcome evidence. A Vault version update
and a child password change are separate remote effects, not one transaction. Unknown password
change, failed publication, policy rejection and missed deadline remain visible; do not claim
rotation verified by simply writing Vault. Do not use a harmless-looking GET as proof a password
works. Exact stages/promotion/overlap/recovery and grant expiry are C4 decisions still to close.
`VaultsClient.rotate_secret` is not selected as a magic cross-service password-rotation call; it
requires a supported target-system configuration, which has not been established for these IAM users.

References: [secret management](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/vault/client/oci.vault.VaultsClient.html),
[retrieval](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/secrets/client/oci.secrets.SecretsClient.html),
[password-change model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/identity_domains/models/oci.identity_domains.models.UserPasswordChanger.html),
[credential behavior](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm).

## Actual cost and native forecast

D41 accepts `oci.budget.BudgetClient.get_budget(budget_id)` through the child automation context as
V1 current-cycle financial source. The stored exact managed `budget/main` binding/OCID is used for
both budget configuration observation and budget/spend snapshot acquisition. One response provides
`amount`, `actual_spend`, `forecasted_spend`, `time_spend_computed`, processing-period/target metadata
and version. Capture exact context/binding generation, cycle and source-profile revision. Reusing a
read does not imply a whole-configuration successful check or permission to clear unrelated issues.

`forecasted_spend` is the provider's full cycle-end estimate: never add actual spend. Normalize optional
values and timestamps without making null0; distinguish computation time from retrieval. Currency is
not an explicit Budget property: pin qualified customer rate-card currency/provenance. Qualify exact
monthly cycle, target scope, endpoint/permissions, no-alert-budget spend population, rollover and SDK
float/decimal/rounding behavior before calling real results comparable. D7 still forbids application
forecasting. [Budget model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/budget/models/oci.budget.models.Budget.html).

Historical reporting, parent-side Usage API collection and backfill are post-V1. The candidate
`request_summarized_usages` and `request_summarized_configurations` methods remain in the pinned source
inventory as reference-only, not production V1 source/fallback requirements. Their grouping/period,
subscription attribution and interval-composition research remains historical/post-V1 evidence.
There is no dependency bump, new live endpoint call or permission proof in this design change.

## Permission qualification matrix

This matrix states required capability, not a deployable least-privilege policy. Full child
administration for automation/owners remains the accepted intent; parent/hosting scopes remain
separate. Terraform policy bodies and domain role grants need tested positive and negative examples.

| Scope | Required permissions/capability | Evidence / outstanding qualification |
|---|---|---|
| Parent organization | ORGANIZATIONS_ENTITY_INSPECT/READ, ORGANIZATIONS_TENANCY_INSPECT/READ/CREATE/DELETE as applicable; link reads where used | Oracle operation matrix gives Create/Delete tenancy permissions. An explicit subscription adds ORGANIZATIONS_SUBSCRIPTION_MAPPING_CREATE. Scope policy to configured parent; no Restore privilege needed for this workflow |
| Parent work requests | Inspect/read organization work requests and safe diagnostics | Qualify parent compartment/region and request ownership, actual headers and status semantics; not a generic unrelated WorkRequestClient |
| Child IAM root | Read tenancy/domain/compartment facts; required root policy/compartment mutations | IAM infrastructure access remains needed with domains. Domain user/group/credential management uses the domain context; neither proves root policy-write access |
| Domain administration | Users, groups, public keys, capabilities, password and exact app-role grants | Qualify signer authorization plus direct domain roles separately; no blanket assumption from OCI all-resources alone |
| Quota/budget | Service-specific quota/budget and alert-rule enumeration/read only (no V1 alert writes) in owning scope | Qualify governance locks, budget owner/target scope, notification semantics and region |
| Hosting Vault | Secret create/update/metadata and explicitly permitted secret-bundle retrieval; necessary Vault/key service permissions | Separate secret metadata from content permission; verify compartment/vault/key boundaries and workload-identity subject |
| Billing | Qualified get_budget access to each child’s exact managed root Budget through existing automation | Prove root-wide target, current cycle/rate-card currency, optional spend/forecast, no-alert computation and rollover; parent Usage API reporting is post-V1 |

Sources: [organization operation permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/organizationsreference.htm),
[IAM permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/iampolicyreference.htm),
[Vault/secret permissions](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/keypolicyreference.htm).

## Retry, verification and simulator rules

- Set an explicit SDK retry strategy per call. Writes must not inherit an indiscriminate client
  retry policy. Use supported provider tokens/ETags only where the inventory shows the parameter;
  persist original tokens and expected version. Tokens do not make every workflow idempotent.
- Read retry can be bounded for throttling/transient failures, with durable rescheduling outside
  worker/transaction holds. A write transport timeout or ambiguous server response may have taken
  effect. Classify using the documented operation contract, not status-code folklore alone.
- A 409 may be an unrelated collision; a 404 may hide denied access; a 412 needs fresh inspection,
  not overwrite. Key/grant/user absence requires adequate observation and coverage. For D26,
  only qualified initiation evidence completes the effect; no finality polling is introduced.
- Refresh policy/role/key propagation through bounded persisted checks. Preserve Unknown during
  observation lag; do not create a duplicate user/group or publish readiness merely because a read
  briefly shows old state. Mutation coordination and association-revision fences remain mandatory.
- Implement a deterministic stateful simulator for these effect boundaries, with injectable clock,
  source revisions, page boundaries and faults. Give domain SCIM resources and OCI infrastructure
  distinct identifiers/endpoints. Test rejection of unsupported legacy identity models rather than
  maintaining a second legacy identity-management simulator or adapter.

| Scenario group | Simulator / contract assertion | Real qualification that mocks cannot prove |
|---|---|---|
| Create request | None response body, header present/absent, delayed resource ID, success then response lost, definitive name collision | Real headers/correlation, name/region/subscription restrictions and activation |
| Handoff | Wrong parent/target, OCI OCID != SCIM ID, ambiguous user search, denied domain discovery, tampered endpoint | Actual domain authorization/endpoint discovery and parent role semantics |
| Permanent access | New key exists but cannot sign; domain role missing; propagation lag; last-admin cleanup blocked | Positive safe probes and role/policy combinations; actual last-admin constraints |
| Import | Different origin, nonstandard domain, existing same-name unrelated objects; no attach/detach/create calls | Supported origin/delete route under current-child guard |
| Members/transfer | Select actual parent, partial create, replacement grant succeeds/cleanup fails, stale repair after retirement | Service-specific scoped grants and safe personal identity deletion |
| Termination | Confirmed initiation completes once; timeout never completes; duplicate delivery; mixed person-plan outcomes; no finality task | Successful initiation response and non-destructive evidence for unknown-effect reconciliation |
| Drift/configuration | Missing vs modified vs unverified, pagination gaps, governed quota, stale binding, unrelated object collision | Exact comparison/permission/lock semantics for each handler |
| Secret/rotation | Upload/change succeeds then Vault publish fails; secret read denied; stale version; old worker/duplicate deadline | Password policy, forced-change behavior, MFA and sessions; workload/Vault permissions |
| Financial | Budget/access missing, actual/forecast unavailable/stale, source timestamp unknown, mixed currency/cycle and month rollover | Real child-budget no-alert spend/forecast/currency/period and precision qualification; historical/Usage API reporting post-V1 |

The existing 134 prototype tests remain reusable organization/association evidence, not a pass
receipt for any new OCI capability. The new source check is static and does not add runtime tests.
The adapter and simulator will share contract scenarios, with live runs restricted to explicitly
provisioned pilot resources and approved destructive-test scopes.

## Gates before calling a journey implementation-ready

1. Qualify create/delete response receipts, work-request resource resolution and unknown-effect
   reconciliation; prove selected parent policy and region/subscription/origin combinations.
2. Qualify a bootstrap-to-permanent signer handoff for each supported identity-domain configuration, including
   dual-ID lookup, system role references and safe removal of temporary identities.
3. Qualify the selected D39/D40 recovery-only MFA policy and D54 CURRENT/known-candidate password flow. API existence does not prove policy scope, usable recovery or hard session logout.
4. Implement and qualify the selected C3 handler/diff/override/retirement contracts and C5 child-budget source/attribution. Current chapters03/10–16 define their design; this earlier call map does not reopen those choices.
5. Freeze reviewed facade request/result schemas and failure fixtures; implement stateful fake first,
   then qualify the real adapter against the same cases. Do not mark C1/C2 complete from this call map.

## Runtime contract alignment — 31 October2026

The local creation form/admission now require the name/home region already specified in C03. Creation-region choices belong to the parent facade; the real adapter must qualify IdentityClient.list_region_subscriptions for the configured parent before mapping returned identifiers into CreationRegion. Local choices are explicit simulated fixtures. C06 continues to read actual name/home-region key using the supplied OCID/bootstrap credentials; it does not replace C03 inputs.

### Create-name rejection qualification — 2 November 2026

C03/C04 must distinguish a definitive rejected name with no accepted child request from an accepted
or uncertain request. Only the former permits a replacement name within the same operation: retain
owner/type/region, append an audited intent revision, validate current authority/parent and use a
new retry token for the changed parameters. Original-name evidence is immutable. A generic HTTP409
or timeout alone is not a sufficient no-effect proof; resolve the original work request before any
changed create attempt. Present the rejection promptly when observed, without cancelling the whole
workflow. Qualify actual OCI codes and work-request timing; do not invent a global name-check API.
Today's simulator implements local registry uniqueness and guided setup, not C03/C04 submissions or
late provider rejection/correction. Import handoff independently enforces the frozen target already
selected in the modal, now read-only in the UI. No new storage/contract fields in this slice.


## Local identity-removal and onboarding simulator refinement — 3 November 2026

Qualified locally; no OCI SDK/credential adapter is qualified. SimulatedLifecycleFacade now returns
MemberRemoval receipts scoped to the frozen association, child and personal user, with verified
group-removal/user-deletion flags. The worker rejects missing/extra/duplicate/wrong-target receipts
before registry retirement. Its immutable lifecycle outcome and two operation steps commit with
that retirement. This is the local D23 identity boundary only: no resource inventory/purge,
compartment deletion or cleanup verifier. Actual domain/user/group lookup and readback remain
required live-adapter qualification.

New onboarding version 2 calls the shared ConfigurationFacade for the four frozen-baseline managed
categories, then reruns verify_automation/verify_required before retire_temporary. Initial probes
cannot prove access survived later root-policy changes. The shared simulator is still synchronous
local state within the database phase; do not plug network SDK writes into that transaction.
Live dispatch, partial-effect reconciliation, required/access composition and provider-specific
managed bindings still need qualification. Existing-compartment assignment uses exact discovered
child/non-root scope, without claiming a new compartment was created.
