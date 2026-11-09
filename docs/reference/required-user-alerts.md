# Confirmed missing required-user email

Locally qualified; the main preview is updated with existing data preserved. See the
[final checkpoint](../history/required-user-alerts-checkpoint-2026-11-07.md), including runtime headroom
and the unchanged parallel preview. Live OCI qualification remains pending.
This extends [manual presence checks](user-presence-checks.md), not security findings, permission
checks, identity repair, credential recovery or daily scheduling. All OCI reads remain simulated.

## Trigger and incident behavior

A new alert-enabled manual check may confirm one exact automation/recovery subject Missing. A
qualified Missing for one user still matters when the other user is Unknown. Denied, incomplete,
late or superseded reads cannot manufacture Missing. Original per-user results and dates remain
visible; email acceptance does not repair an account or establish usable permissions.

Each subject has an independent incident UUID. Repeated Missing and Unknown retain the same open
incident; only a verified Present closes it. A later Missing opens a new incident. Exact subject,
domain, binding generation, connection or provider-policy changes start a separate scope. Registry
name/revision changes do not. Late callbacks store historical results but cannot copy/reset the
current incident or stage email. The highest admitted terminal acquisition sequence owns state.

Incident state lives in the existing sealed check evidence, including when email transport is
disabled. Re-enabling delivery does not resend an existing initial notice or backfill observations
made while disabled. New intent/evidence fields are optional and omitted when absent; historical
intent hashes, replays and non-alerting accepted checks retain their original behavior.

## Recipients and delivery

On a newly opened incident, resolve one current applied organization/mapping snapshot. Capture owner,
direct manager, designees and active administrators. Deduplicate normalized original addresses while
retaining every applicable role reason, then apply the existing environment email policy. Different
original contacts remain separate intent records even when staging redirects them to one capture
mailbox. Do not rewrite employee identities or administrator profiles.

Absent/reference/merged/offboarded people and invalid contacts are not invented as recipients.
Unavailable owner/manager/designee contacts remain explicit routing issues with administrator
routing. An administrator without an email also has an explicit unavailable-contact warning. An
existing email-less local recovery administrator may still use the already approved explicit testing
capture route; without that route delivery is Blocked. No available authorized contact never counts
as successful empty delivery.

Before first SMTP submission and each retry, validate the original sealed Missing, the same current
incident, active child/exact subject/connection/policy and at least one surviving frozen recipient
role/address. A person remaining in the feed after losing their owner/manager/designee role is
insufficient. Administrator reasons require the same active grant, authorization revision and
original address. Changed recipients are superseded, never silently replaced. Route, origin and
transport fingerprints retain their existing guards. A resolved incident or retired/replaced target
cannot send an obsolete initial alert. No recovery/parent credential fallback is introduced.

The body is fixed plain text describing the required-user purpose and tenancy review link, without
credentials, provider diagnostics or a free-form employee message. The existing outbox provides
bounded known-rejection retries. Uncertain/sending outcomes never become automatic blind resends.

## Fields and persistence

No physical tables/columns/migrations or new scheduler are added. Existing operations, steps,
`audit_event`, `otm_user_presence_check` and the 15-column `otm_notification_outbox` are reused.
Both-or-neither publication covers check results, incident metadata, outbox intents, email audit
and native queue deferral in the same existing child/workspace transaction.

| Contract | Fields and source |
| --- | --- |
| `PresenceCheckIntent` (9) | Existing `contract_version`, `kind`, `workspace_id`, `administrator_id`, `authorization_revision`, `snapshot`, `context_hash`, `target`; new optional `notice_policy_version=1` is server-set for new admissions, never a browser option. Stored in immutable operation-intent audit JSON. |
| `PresenceCheckEvidence` (10) | Existing `contract_version`, `tenancy_id`, `operation_id`, `context_hash`, `state`, `safe_code`, `started_at`, `checked_at`, `results`; optional `notice_episodes` contains two ordered automation/recovery states only for current alert-enabled head publication. Stored in sealed outcome audit JSON and verified step `last_outcome`; check result columns remain unchanged. |
| `PresenceNoticeEpisode` (3) | `purpose`: automation/recovery; `scope_hash`: canonical exact one-subject/connection/policy identity excluding tenancy name/revision; nullable `episode_id`: open incident UUID or closed. Original evidence/scope hashes are validated before carry-forward. Ordered purposes and Present/Missing coherence are validated. |
| `RecipientReason` (4) | `role`: owner/manager/designee/administrator; `person_id` for organization roles; `administrator_id` plus `authorization_revision` for an admin grant. Explicit unavailable-admin placeholders have no authority and cannot authorize SMTP. Frozen in the notice. |
| `RequiredUserMissingNotice` (18) | `contract_version=required-user-missing-email-1`; `operation_id`, `tenancy_id`, `purpose`, `scope_hash`, `episode_id`, `check_context_hash` tie to original sealed Missing; `organization_version_id`, `configuration_id` freeze routing provenance; `reasons`, `routing_issues` freeze role/fallback evidence; `original_recipient`, `delivery_recipient`, `route`, `application_origin`, `delivery_profile_hash` freeze existing egress policy; `event=required_user_missing`, `created_at` identify trigger/time. Stored in immutable outbox `intent` with canonical `intent_hash`. |
| `NotificationSummary` (14) | Existing `id`, `state`, `event`, `recipient`, `original_recipient`, `created_at`, `updated_at`, `redirected`, `last_attempt_at`, `attempts`, `safe_code`; new optional `required_user_purpose`, `recipient_roles`, `routing_issues` are derived from the frozen notice for Operations. Empty/absent additions preserve older response shapes. |

`transition_key` binds exact subject scope, incident UUID and normalized original recipient. Existing
workspace/child serialization plus the duplicate lookup prevent extra initial emails. Neither
notification retry nor current routing changes allocate another incident. There is no separate
incident coordinator or generic workflow framework.

## Screens and qualification

Required users and the Tenancies summary retain their existing per-user Missing/Unknown/freshness
semantics. The check's Operations page shows each email's purpose, notified roles, original/effective
contact, routing issues and delivery state. Email delivery remains a separate audit category;
mail-server acceptance never claims inbox receipt. The panel is read-only, not a resend/repair UI.

Synthetic unit, disposable PostgreSQL, loopback Mailpit/native-worker and Playwright tests cover
repeated Missing, Unknown, per-subject recovery/relapse, disabled delivery, role/authority changes,
late callbacks, exact-target guards, atomic rollback and contact redirection. Production code has
no simulator fault switches. Actual OCI absence/read authorization and approved hosted SMTP remain
Pending in the [manual manifest](../how-to/real-oci-test-manifest.md).
