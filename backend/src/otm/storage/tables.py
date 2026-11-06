"""Staged production operation, evidence, read-step and session metadata tables.

Future organization/tenancy/session fields remain in the approved data dictionary until their
own migrations. These are actual application tables, distinct from runner qualification fixtures.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(schema="public")
operation = Table(
    "otm_operation",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("kind", String(64), nullable=False),
    Column("initiating_actor_subject", String(256), nullable=False),
    Column("initiating_actor_snapshot", JSONB, nullable=False),
    Column("responsible_actor_subject", String(256), nullable=False),
    Column("client_request_key", Uuid(as_uuid=True), nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("current_intent_revision", Integer, nullable=False),
    Column("current_intent_event_id", Uuid(as_uuid=True), nullable=False),
    Column("state", String(32), nullable=False),
    Column("stage", String(256), nullable=False),
    Column("wait_reason", String(32), nullable=True),
    Column("effect_knowledge", String(16), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("workspace_id", "id", name="uq_operation_workspace_id"),
    UniqueConstraint(
        "workspace_id",
        "initiating_actor_subject",
        "client_request_key",
        name="uq_operation_request",
    ),
    CheckConstraint(
        "kind IN ('inspect_import','organization_action"
        "','configuration_update','configuration_check','cost_collection')",
        name="ck_operation_kind",
    ),
    CheckConstraint(
        "state IN ('queued','running','waiting','needs_attention',"
        "'succeeded','cancelled','failed')",
        name="ck_operation_state",
    ),
    CheckConstraint("effect_knowledge IN ('none','known','unknown')", name="ck_operation_effect"),
    CheckConstraint("current_intent_revision>=1 AND revision>=1", name="ck_operation_revisions"),
    CheckConstraint("request_digest ~ '^[0-9a-f]{64}$'", name="ck_operation_digest"),
    ForeignKeyConstraint(
        ["workspace_id", "id", "current_intent_revision", "current_intent_event_id"],
        [
            "public.audit_event.workspace_id",
            "public.audit_event.operation_id",
            "public.audit_event.intent_revision",
            "public.audit_event.id",
        ],
        name="fk_operation_exact_intent",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    ),
)
audit_event = Table(
    "audit_event",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("operation_id", Uuid(as_uuid=True), nullable=True),
    Column("administrator_id", Uuid(as_uuid=True), nullable=True),
    Column("intent_revision", Integer, nullable=True),
    Column("actor", String(256), nullable=False),
    Column("actor_subject", String(256), nullable=False),
    Column("actor_snapshot", JSONB, nullable=False),
    Column("kind", String(64), nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("contract_version", String(64), nullable=False),
    Column("data", JSONB, nullable=False),
    Column("data_hash", String(64), nullable=False),
    UniqueConstraint(
        "workspace_id", "operation_id", "intent_revision", name="uq_audit_intent_revision"
    ),
    UniqueConstraint(
        "workspace_id", "operation_id", "intent_revision", "id", name="uq_audit_exact_intent"
    ),
    UniqueConstraint("workspace_id", "operation_id", "id", name="uq_audit_operation_event"),
    CheckConstraint(
        "(operation_id IS NOT NULL AND administrator_id IS NULL AND "
        "((kind='operation_intent' AND intent_revision IS NOT NULL AND intent_revision>=1) "
        "OR (kind IN ('inspection_dispatch','inspection_outcome','organization_action_out"
        "come','onboarding_action','onboarding_outcome','configuration_outcome',"
        "'configuration_retry','configuration_check_outcome','cost_collection_outcome','operation_responsibility_changed',"
        "'email_delivery') "
        "AND intent_revision IS NULL))) "
        "OR (kind IN ('administrator_revoked','administrator_bootstrapped',"
        "'local_credentials_reset',"
        "'local_sign_in_succeeded','local_sign_in_failed','session_logged_out','audit_export') "
        "AND operation_id IS NULL "
        "AND intent_revision IS NULL AND administrator_id IS NOT NULL) "
        "OR (kind IN ('organization_configured','organization_feed_received',"
        "'organization_feed_rejected','organization_published','organization_review_decid"
        "ed','cost_refresh_requested') AND operation_id IS NULL "
        "AND administrator_id IS NULL AND intent_revision IS NULL) "
        "OR (kind IN "
        "('configuration_review_staged','baseline_draft_saved','baseline_published',"
        "'baseline_default_changed') "
        "AND operation_id IS NULL "
        "AND administrator_id IS NULL AND intent_revision IS NULL)",
        name="ck_audit_event_revision",
    ),
    CheckConstraint("data_hash ~ '^[0-9a-f]{64}$'", name="ck_audit_digest"),
    ForeignKeyConstraint(
        ["workspace_id", "administrator_id"],
        ["public.otm_administrator.workspace_id", "public.otm_administrator.id"],
        name="fk_audit_administrator",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_audit_operation",
        deferrable=True,
        initially="DEFERRED",
    ),
)

# Bound timestamp paging/range exports to the current workspace as immutable history grows.
Index("ix_audit_workspace_at_id", audit_event.c.workspace_id, audit_event.c.at, audit_event.c.id)
Index(
    "uq_org_decision_request",
    audit_event.c.workspace_id,
    audit_event.c.actor_subject,
    audit_event.c.data["request_key"].astext,
    unique=True,
    postgresql_where=audit_event.c.kind == "organization_review_decided",
)

# One logical inspection step is reused across read attempts; attempts remain immutable audit
# events rather than a new attempt table. Exact intent ownership cannot point at outcome rows.
operation_step = Table(
    "otm_operation_step",
    metadata,
    Column("workspace_id", String(256), primary_key=True),
    Column("operation_id", Uuid(as_uuid=True), primary_key=True),
    Column("intent_revision", Integer, primary_key=True),
    Column("step_key", String(256), primary_key=True),
    Column("intent_event_id", Uuid(as_uuid=True), nullable=False),
    Column("command_kind", String(64), nullable=False),
    Column("contract_version", String(64), nullable=False),
    Column("inputs", JSONB, nullable=False),
    Column("state", String(32), nullable=False),
    Column("execution_generation", Integer, nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("current_attempt_id", Uuid(as_uuid=True), nullable=False),
    Column("effect_knowledge", String(16), nullable=False),
    Column("last_outcome", JSONB),
    Column("verified_at", DateTime(timezone=True)),
    Column("evidence_event_id", Uuid(as_uuid=True)),
    CheckConstraint(
        "(step_key='inspect_target' AND command_kind='inspect_tenancy') "
        "OR (command_kind='organization_action' AND (step_key='apply_lifecycle' "
        "OR step_key ~ '^(remove_member_groups|delete_member_user):[0-9a-f-]{36}$')) "
        "OR (command_kind='onboarding' AND step_key IN ('handoff','inspect_bootstrap',"
        "'establish_automation','verify_automation','configure_required','verify_required',"
        "'retire_temporary','configure_baseline','verify_configured_access',"
        "'capture_required_users')) "
        "OR (command_kind='configuration_update' AND step_key ~ '^configuration:[0-9a-f-]{36}$') "
        "OR (command_kind='configuration_check' AND ste"
        "p_key ~ '^configuration_check:[0-9a-f-]{36}$') "
        "OR (command_kind='cost_collection' AND step_key ~ '^cost:[0-9a-f-]{36}$')",
        name="ck_inspection_step_kind",
    ),
    CheckConstraint(
        "state IN ('running','verified','needs_attention')", name="ck_inspection_step_state"
    ),
    CheckConstraint(
        "intent_revision>=1 AND execution_generation>=1 AND attempt_number>=1",
        name="ck_inspection_step_generations",
    ),
    CheckConstraint(
        "(command_kind IN ('inspect_tenancy','configur"
        "ation_check','cost_collection') AND effect_knowledge='none') OR "
        "(command_kind IN ('organization_action','onboarding','configuration_update') "
        "AND effect_knowledge IN ('none','known'))",
        name="ck_inspection_read_only",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id", "intent_revision", "intent_event_id"],
        [
            "public.audit_event.workspace_id",
            "public.audit_event.operation_id",
            "public.audit_event.intent_revision",
            "public.audit_event.id",
        ],
        name="fk_step_exact_intent",
        deferrable=True,
        initially="DEFERRED",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_step_operation",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id", "evidence_event_id"],
        [
            "public.audit_event.workspace_id",
            "public.audit_event.operation_id",
            "public.audit_event.id",
        ],
        name="fk_step_evidence",
    ),
)

# SSO handshake/issuance is deliberately separate. Store only a digest of an opaque browser
# handle; a session row never substitutes for a fresh administrator entitlement decision.
admin_session = Table(
    "otm_admin_session",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("session_token_hash", String(64), nullable=False),
    Column("issuer", String(256), nullable=False),
    Column("subject", String(256), nullable=False),
    Column("display_snapshot", JSONB, nullable=False),
    Column("entitlement_reference", String(256), nullable=False),
    Column("entitlement_revision", Uuid(as_uuid=True), nullable=False),
    Column("entitlement_checked_at", DateTime(timezone=True), nullable=False),
    Column("auth_time", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("idle_timeout_seconds", Integer, nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("provider_session_reference_hash", String(64)),
    CheckConstraint("idle_timeout_seconds>=1", name="ck_admin_session_idle"),
    UniqueConstraint("session_token_hash", name="uq_admin_session_token_hash"),
    CheckConstraint("session_token_hash ~ '^[0-9a-f]{64}$'", name="ck_admin_session_hash"),
    CheckConstraint(
        "provider_session_reference_hash IS NULL "
        "OR provider_session_reference_hash ~ '^[0-9a-f]{64}$'",
        name="ck_admin_session_provider_hash",
    ),
    CheckConstraint(
        "auth_time<=created_at AND created_at<expires_at "
        "AND last_seen_at>=created_at AND entitlement_checked_at<=created_at",
        name="ck_admin_session_times",
    ),
)


# Persist explicit application grants independently of employees and temporary sessions.
administrator = Table(
    "otm_administrator",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("identity_kind", String(32), nullable=False),
    Column("issuer", String(256), nullable=False),
    Column("subject", String(256), nullable=False),
    Column("display_name", String(256), nullable=False),
    Column("email", String(256)),
    Column("status", String(16), nullable=False),
    Column("authorization_revision", Uuid(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    UniqueConstraint("workspace_id", "id", name="uq_administrator_workspace_id"),
    UniqueConstraint("workspace_id", "issuer", "subject", name="uq_administrator_identity"),
    CheckConstraint(
        "identity_kind IN ('local_recovery','corporate_sso')", name="ck_administrator_kind"
    ),
    CheckConstraint("status IN ('active','revoked')", name="ck_administrator_status"),
    CheckConstraint(
        "(status='active' AND revoked_at IS NULL) OR (status='revoked' AND revoked_at IS NOT NULL)",
        name="ck_administrator_revocation",
    ),
    CheckConstraint(
        "updated_at>=created_at AND (revoked_at IS NULL OR revoked_at>=created_at)",
        name="ck_administrator_times",
    ),
    CheckConstraint(
        "identity_kind!='local_recovery' OR (subject=id::text AND status='active')",
        name="ck_administrator_local",
    ),
    CheckConstraint(
        "length(btrim(workspace_id))>0 AND length(btrim(issuer))>0 "
        "AND length(btrim(subject))>0 AND length(btrim(display_name))>0",
        name="ck_administrator_text",
    ),
)
Index(
    "uq_administrator_recovery",
    administrator.c.workspace_id,
    unique=True,
    postgresql_where=administrator.c.identity_kind == "local_recovery",
)

# Store verifier/version references; the local-auth service owns enrollment and proof verification.
local_credential = Table(
    "otm_local_credential",
    metadata,
    Column("workspace_id", String(256), primary_key=True),
    Column("administrator_id", Uuid(as_uuid=True), primary_key=True),
    Column("password_hash", String(2048), nullable=False),
    Column("totp_secret_reference", String(1024), nullable=False),
    Column("last_totp_step", BigInteger, nullable=False),
    Column("mfa_enrolled_at", DateTime(timezone=True), nullable=False),
    Column("password_changed_at", DateTime(timezone=True), nullable=False),
    Column("failed_attempts", Integer, nullable=False),
    Column("failure_window_started_at", DateTime(timezone=True)),
    Column("retry_after", DateTime(timezone=True)),
    ForeignKeyConstraint(
        ["workspace_id", "administrator_id"],
        ["public.otm_administrator.workspace_id", "public.otm_administrator.id"],
        name="fk_local_credential_administrator",
    ),
    CheckConstraint("last_totp_step>=0 AND failed_attempts>=0", name="ck_local_credential_counts"),
    CheckConstraint(
        "password_hash LIKE '$argon2id$%' AND length(btrim(totp_secret_reference))>0",
        name="ck_local_credential_material",
    ),
    CheckConstraint(
        "(failed_attempts=0 AND failure_window_started_at IS NULL AND retry_after IS NULL) "
        "OR (failed_attempts>0 AND failure_window_started_at IS NOT NULL "
        "AND (retry_after IS NULL OR retry_after>=failure_window_started_at))",
        name="ck_local_credential_throttle",
    ),
)
admin_session.append_constraint(
    ForeignKeyConstraint(
        ["workspace_id", "issuer", "subject"],
        [
            "public.otm_administrator.workspace_id",
            "public.otm_administrator.issuer",
            "public.otm_administrator.subject",
        ],
        name="fk_session_administrator_identity",
    )
)


# Keep source scope inside its configuration; the workspace key is application authorization scope.
org_workspace = Table(
    "org_workspace",
    metadata,
    Column("registry_revision", Integer, nullable=False, server_default="1"),
    CheckConstraint("registry_revision>=1", name="ck_org_registry_revision"),
    Column("id", String(256), primary_key=True),
    Column("configuration_id", Uuid(as_uuid=True), nullable=False),
    Column("configuration", JSONB, nullable=False),
    Column("applied_version_id", Uuid(as_uuid=True)),
    Column("proposed_version_id", Uuid(as_uuid=True)),
    Column("current_baseline_id", Uuid(as_uuid=True)),
    Column("applied_kind", String(16), nullable=False, server_default="applied"),
    Column("proposed_kind", String(16), nullable=False, server_default="proposed"),
    CheckConstraint(
        "applied_kind='applied' AND proposed_kind='proposed'", name="ck_org_head_kinds"
    ),
    CheckConstraint(
        "(configuration->>'id') IS NOT DISTINCT FROM configuration_id::text",
        name="ck_org_configuration_id",
    ),
)

# Original email anchors are scoped to an installation; current names/emails belong to revisions.
org_person = Table(
    "org_person",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("email", String(320), nullable=False),
    Column("directory_status", String(16), nullable=False, server_default="included"),
    Column("setup_required", Boolean, nullable=False, server_default="false"),
    Column("setup_episode_id", Uuid(as_uuid=True)),
    Column("removed_capture_at", DateTime(timezone=True)),
    Column("pending_operation_id", Uuid(as_uuid=True)),
    ForeignKeyConstraint(
        ["workspace_id", "pending_operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
    ),
    CheckConstraint(
        "directory_status IN ('included','exempt','offboarded','outside','merged')",
        name="ck_org_person_directory",
    ),
    UniqueConstraint("workspace_id", "id", name="uq_org_person_scope"),
    UniqueConstraint("workspace_id", "email", name="uq_org_person_email"),
    ForeignKeyConstraint(
        ["workspace_id"], ["public.org_workspace.id"], name="fk_org_person_workspace"
    ),
)

# Mutable processing status never replaces immutable canonical delivery data or source-byte digest.
org_feed = Table(
    "org_feed",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("source_id", String(256), nullable=False),
    Column("population_id", String(256), nullable=False),
    Column("external_id", String(512), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("captured_at", DateTime(timezone=True)),
    Column("digest", String(64), nullable=False),
    Column("raw_digest", String(64)),
    Column("data", JSONB, nullable=False),
    Column("state", String(16), nullable=False),
    Column("diagnostics", JSONB, nullable=False),
    Column("proposed_version_id", Uuid(as_uuid=True)),
    Column("applied_version_id", Uuid(as_uuid=True)),
    UniqueConstraint("workspace_id", "id", name="uq_org_feed_scope"),
    UniqueConstraint("workspace_id", "source_id", "external_id", name="uq_org_delivery"),
    ForeignKeyConstraint(
        ["workspace_id"], ["public.org_workspace.id"], name="fk_org_feed_workspace"
    ),
    CheckConstraint(
        "state IN ('received','staged','published','rejected','superseded')",
        name="ck_org_feed_state",
    ),
    CheckConstraint(
        "digest ~ '^[0-9a-f]{64}$' AND (raw_digest IS NULL OR raw_digest ~ '^[0-9a-f]{64}$')",
        name="ck_org_feed_digest",
    ),
)
Index("ix_org_feed_received", org_feed.c.workspace_id, org_feed.c.received_at, org_feed.c.id)

# A sealed header and its immutable members form one complete proposed or applied organization.
org_version = Table(
    "org_version",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("base_version_id", Uuid(as_uuid=True)),
    Column("feed_id", Uuid(as_uuid=True), nullable=False),
    Column("configuration_id", Uuid(as_uuid=True), nullable=False),
    Column("configuration", JSONB, nullable=False),
    Column("member_count", Integer, nullable=False),
    Column("sealed", Boolean, nullable=False, server_default="false"),
    Column("data", JSONB, nullable=False),
    UniqueConstraint("workspace_id", "id", name="uq_org_version_scope"),
    UniqueConstraint("workspace_id", "id", "kind", name="uq_org_version_kind"),
    CheckConstraint("kind IN ('proposed','applied')", name="ck_org_version_kind"),
    CheckConstraint(
        "(configuration->>'id') IS NOT DISTINCT FROM configuration_id::text",
        name="ck_org_version_configuration",
    ),
    ForeignKeyConstraint(
        ["workspace_id"], ["public.org_workspace.id"], name="fk_org_version_workspace"
    ),
    ForeignKeyConstraint(
        ["workspace_id", "feed_id"],
        ["public.org_feed.workspace_id", "public.org_feed.id"],
        name="fk_org_version_feed",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "base_version_id"],
        ["public.org_version.workspace_id", "public.org_version.id"],
        name="fk_org_version_base",
    ),
)
for pointer, kind in (
    ("applied_version_id", "applied_kind"),
    ("proposed_version_id", "proposed_kind"),
):
    org_workspace.append_constraint(
        ForeignKeyConstraint(
            ["id", pointer, kind],
            ["public.org_version.workspace_id", "public.org_version.id", "public.org_version.kind"],
            name="fk_org_workspace_" + kind,
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        )
    )
for pointer in ("proposed_version_id", "applied_version_id"):
    org_feed.append_constraint(
        ForeignKeyConstraint(
            ["workspace_id", pointer],
            ["public.org_version.workspace_id", "public.org_version.id"],
            name="fk_org_feed_" + pointer,
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        )
    )

# Readable projection columns agree with the full PersonState evidence pinned to one version.
org_member = Table(
    "org_member",
    metadata,
    Column("workspace_id", String(256), primary_key=True),
    Column("version_id", Uuid(as_uuid=True), primary_key=True),
    Column("person_id", Uuid(as_uuid=True), primary_key=True),
    Column("email", String(320), nullable=False),
    Column("full_name", String),
    Column("manager_person_id", Uuid(as_uuid=True)),
    Column("manager_email", String(320)),
    Column("profile", String(16), nullable=False),
    Column("evidence", String(16), nullable=False),
    Column("lob_id", String),
    Column("accountable_leader_email", String(320)),
    Column("designee_emails", JSONB, nullable=False),
    Column("ancestry", String(16), nullable=False),
    Column("absence_review", Boolean, nullable=False),
    Column("data", JSONB, nullable=False),
    UniqueConstraint("workspace_id", "version_id", "email", name="uq_org_member_email"),
    ForeignKeyConstraint(
        ["workspace_id", "version_id"],
        ["public.org_version.workspace_id", "public.org_version.id"],
        name="fk_org_member_version",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "person_id"],
        ["public.org_person.workspace_id", "public.org_person.id"],
        name="fk_org_member_person",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "version_id", "manager_person_id"],
        [
            "public.org_member.workspace_id",
            "public.org_member.version_id",
            "public.org_member.person_id",
        ],
        name="fk_org_member_manager",
        deferrable=True,
        initially="DEFERRED",
    ),
    CheckConstraint(
        "profile IN ('employee','reference','configured')", name="ck_org_member_profile"
    ),
    CheckConstraint(
        "evidence IN ('feed_row','retained','reference','configured')",
        name="ck_org_member_evidence",
    ),
    CheckConstraint("ancestry IN ('root','resolved','incomplete')", name="ck_org_member_ancestry"),
    CheckConstraint("person_id<>manager_person_id", name="ck_org_member_not_self"),
)
Index(
    "ix_org_manager_children",
    org_member.c.workspace_id,
    org_member.c.version_id,
    org_member.c.manager_person_id,
)


# Persist review episodes and their decisions independently of immutable source observations.
org_recommendation = Table(
    "org_recommendation",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("person_id", Uuid(as_uuid=True)),
    Column("kind", String(64), nullable=False),
    Column("category", String(24), nullable=False),
    Column("target", String(512), nullable=False),
    Column("basis", String(256), nullable=False),
    Column("status", String(16), nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column("version_id", Uuid(as_uuid=True), nullable=False),
    Column("resolution", String(64)),
    Column("operation_id", Uuid(as_uuid=True)),
    Column("data", JSONB, nullable=False),
    UniqueConstraint("workspace_id", "id", name="uq_org_recommendation_scope"),
    ForeignKeyConstraint(["workspace_id"], ["public.org_workspace.id"]),
    ForeignKeyConstraint(
        ["workspace_id", "person_id"], ["public.org_person.workspace_id", "public.org_person.id"]
    ),
    ForeignKeyConstraint(
        ["workspace_id", "version_id"], ["public.org_version.workspace_id", "public.org_version.id"]
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
    ),
    CheckConstraint(
        "category IN ('actionable','informational','change')", name="ck_org_review_category"
    ),
    CheckConstraint("status IN ('open','resolved','ignored')", name="ck_org_review_status"),
    CheckConstraint(
        "last_seen_at>=first_seen_at AND (resolved_at IS NULL OR resolved_at>=first_seen_at)",
        name="ck_org_review_times",
    ),
)
Index(
    "uq_org_review_open",
    org_recommendation.c.workspace_id,
    org_recommendation.c.kind,
    org_recommendation.c.target,
    unique=True,
    postgresql_where=org_recommendation.c.status == "open",
)
Index(
    "ix_org_review_inbox",
    org_recommendation.c.workspace_id,
    org_recommendation.c.category,
    org_recommendation.c.status,
    org_recommendation.c.last_seen_at,
)


# Track only registered children, keeping simulated facts visibly distinct from real OCI
# qualification.
tenancy = Table(
    "otm_tenancy",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("baseline_version_id", Uuid(as_uuid=True)),
    Column("verified_baseline_version_id", Uuid(as_uuid=True)),
    Column("configuration_verified_at", DateTime(timezone=True)),
    Column("configuration_observation", JSONB),
    Column("workspace_id", String(256), nullable=False),
    Column("name", String(200), nullable=False),
    Column("tenancy_ocid", String(256), nullable=False),
    Column("parent_tenancy_ocid", String(256), nullable=False),
    Column("organization_id", String(256), nullable=False),
    Column("home_region", String(64), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("status", String(24), nullable=False),
    Column("provider_mode", String(16), nullable=False),
    Column("origin", String(16), nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("operation_id", Uuid(as_uuid=True)),
    Column("last_operation_id", Uuid(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("verified_at", DateTime(timezone=True)),
    UniqueConstraint("workspace_id", "id", name="uq_tenancy_scope"),
    UniqueConstraint("workspace_id", "tenancy_ocid", name="uq_tenancy_ocid"),
    ForeignKeyConstraint(["workspace_id"], ["public.org_workspace.id"]),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
    ),
    ForeignKeyConstraint(
        ["workspace_id", "last_operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
    ),
    CheckConstraint(
        "kind IN ('individual','shared') AND origin IN ('create','import')",
        name="ck_tenancy_kind_origin",
    ),
    CheckConstraint(
        "status IN ('pending','active','terminating','terminated','failed','cancelled')",
        name="ck_tenancy_status",
    ),
    CheckConstraint(
        "provider_mode='simulated' AND tenancy_ocid<>parent_tenancy_ocid AND revision>=1",
        name="ck_tenancy_qualification",
    ),
)
Index("ix_tenancy_inventory", tenancy.c.workspace_id, tenancy.c.status, tenancy.c.name)


# Keep ownership and shared membership history; removal leaves compartments/resources untouched.
tenancy_membership = Table(
    "otm_tenancy_membership",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("tenancy_id", Uuid(as_uuid=True), nullable=False),
    Column("person_id", Uuid(as_uuid=True), nullable=False),
    Column("role", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("user_ocid", String(256)),
    Column("compartment_ocid", String(256)),
    Column("compartment_name", String(100)),
    Column("parent_compartment_ocid", String(256)),
    Column("cleanup_required", Boolean, nullable=False, server_default="false"),
    Column("operation_id", Uuid(as_uuid=True)),
    Column("revision", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "id", name="uq_tenancy_membership_scope"),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"], ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"]
    ),
    ForeignKeyConstraint(
        ["workspace_id", "person_id"], ["public.org_person.workspace_id", "public.org_person.id"]
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
    ),
    CheckConstraint(
        "role IN ('owner','member') AND status IN ('pending','active','removing','removed"
        "','failed')",
        name="ck_membership_role_status",
    ),
    CheckConstraint("revision>=1", name="ck_membership_revision"),
)
Index(
    "uq_membership_current",
    tenancy_membership.c.workspace_id,
    tenancy_membership.c.tenancy_id,
    tenancy_membership.c.person_id,
    unique=True,
    postgresql_where=tenancy_membership.c.status.in_(("pending", "active", "removing")),
)
Index(
    "uq_membership_owner",
    tenancy_membership.c.workspace_id,
    tenancy_membership.c.tenancy_id,
    unique=True,
    postgresql_where=(tenancy_membership.c.role == "owner")
    & tenancy_membership.c.status.in_(("pending", "active", "removing")),
)
Index(
    "ix_membership_person",
    tenancy_membership.c.workspace_id,
    tenancy_membership.c.person_id,
    tenancy_membership.c.status,
)


# One editable recipe per workspace plus immutable locally qualified publication snapshots.
baseline_version = Table(
    "otm_baseline_version",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("version_number", Integer, nullable=False),
    Column("based_on_id", Uuid(as_uuid=True)),
    Column("schema_version", String(32), nullable=False),
    Column("policy_statements", JSONB, nullable=False),
    Column("quota_statements", JSONB, nullable=False),
    Column("monthly_budget_amount", Numeric(20, 4), nullable=False),
    Column("budget_currency", String(3), nullable=False),
    Column("budget_period", String(16), nullable=False),
    Column("tag_namespace", String(16), nullable=False),
    Column("tag_defaults", JSONB, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("edit_revision", Integer, nullable=False),
    Column("created_by", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_by", String(256)),
    Column("published_at", DateTime(timezone=True)),
    Column("published_by_name", String(256)),
    Column("publication_mode", String(16)),
    UniqueConstraint("workspace_id", "id", name="uq_baseline_scope"),
    UniqueConstraint("workspace_id", "version_number", name="uq_baseline_version"),
    ForeignKeyConstraint(
        ["workspace_id"], ["public.org_workspace.id"], name="fk_baseline_workspace"
    ),
    ForeignKeyConstraint(
        ["workspace_id", "based_on_id"],
        ["public.otm_baseline_version.workspace_id", "public.otm_baseline_version.id"],
        name="fk_baseline_parent",
    ),
    CheckConstraint("version_number>=1 AND edit_revision>=1", name="ck_baseline_revision"),
    CheckConstraint(
        "schema_version='baseline-1' AND budget_period='MONTHLY' AND tag_namespace='OTM'",
        name="ck_baseline_scope_values",
    ),
    CheckConstraint(
        "monthly_budget_amount>0 AND budget_currency ~ '^[A-Z]{3}$'", name="ck_baseline_budget"
    ),
    CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_baseline_hash"),
    CheckConstraint(
        "(published_by IS NULL)=(published_at IS NULL)", name="ck_baseline_publication"
    ),
    CheckConstraint(
        "jsonb_typeof(policy_statements)='array' AND jsonb_array_length(policy_statements)>0 "
        "AND jsonb_typeof(quota_statements)='array' AND jsonb_array_length(quota_statements)>0 "
        "AND jsonb_typeof(tag_defaults)='array'",
        name="ck_baseline_lists",
    ),
    CheckConstraint(
        "(published_at IS NULL AND publication_mode IS NULL AND published_by_name IS NULL) OR "
        "(published_at IS NOT NULL AND publication_mode IS NOT NULL "
        "AND publication_mode='simulated' "
        "AND published_by_name IS NOT NULL)",
        name="ck_baseline_qualification",
    ),
)
Index(
    "uq_baseline_editable",
    baseline_version.c.workspace_id,
    unique=True,
    postgresql_where=baseline_version.c.published_at.is_(None),
)

# Retained historical selection metadata; runtime defaults never consult this deprecated pointer.
org_workspace.append_constraint(
    ForeignKeyConstraint(
        ["id", "current_baseline_id"],
        ["public.otm_baseline_version.workspace_id", "public.otm_baseline_version.id"],
        name="fk_workspace_baseline",
        use_alter=True,
    )
)

# New admissions pin a recipe; legacy tenancies keep NULL until an explicit future assignment.
tenancy.append_constraint(
    ForeignKeyConstraint(
        ["workspace_id", "baseline_version_id"],
        ["public.otm_baseline_version.workspace_id", "public.otm_baseline_version.id"],
        name="fk_tenancy_baseline",
    )
)

# Verification records a distinct full-readback milestone; failed updates retain the prior version.
tenancy.append_constraint(
    ForeignKeyConstraint(
        ["workspace_id", "verified_baseline_version_id"],
        ["public.otm_baseline_version.workspace_id", "public.otm_baseline_version.id"],
        name="fk_tenancy_verified_baseline",
    )
)
tenancy.append_constraint(
    CheckConstraint(
        "(verified_baseline_version_id IS NULL)=(configuration_verified_at IS NULL)",
        name="ck_tenancy_configuration_verified",
    )
)
tenancy.append_constraint(
    CheckConstraint(
        "configuration_observation IS NULL OR jsonb_typeof(configuration_observation)='object'",
        name="ck_tenancy_configuration_observation",
    )
)


# Immutable accepted authored values keep each tenancy's baseline and override revision together.
tenancy_configuration = Table(
    "otm_tenancy_configuration",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("tenancy_id", Uuid(as_uuid=True), nullable=False),
    Column("revision_number", Integer, nullable=False),
    Column("previous_id", Uuid(as_uuid=True)),
    Column("baseline_version_id", Uuid(as_uuid=True), nullable=False),
    Column("policy_override_statements", JSONB(none_as_null=True)),
    Column("quota_override_statements", JSONB(none_as_null=True)),
    Column("monthly_budget_override_amount", Numeric(20, 4)),
    Column("resolution_contract_version", String(32), nullable=False),
    Column("effective_hash", String(64), nullable=False),
    Column("operation_id", Uuid(as_uuid=True), nullable=False),
    Column("created_by", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "tenancy_id", "id", name="uq_configuration_scope"),
    UniqueConstraint(
        "workspace_id", "tenancy_id", "revision_number", name="uq_configuration_revision"
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_configuration_tenancy",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id", "previous_id"],
        [
            "public.otm_tenancy_configuration.workspace_id",
            "public.otm_tenancy_configuration.tenancy_id",
            "public.otm_tenancy_configuration.id",
        ],
        name="fk_configuration_previous",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "baseline_version_id"],
        ["public.otm_baseline_version.workspace_id", "public.otm_baseline_version.id"],
        name="fk_configuration_baseline",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_configuration_operation",
        deferrable=True,
        initially="DEFERRED",
    ),
    CheckConstraint(
        "revision_number>=1 AND resolution_contract_version='simulated-config-1' "
        "AND effective_hash ~ '^[0-9a-f]{64}$'",
        name="ck_configuration_version",
    ),
    CheckConstraint(
        "monthly_budget_override_amount IS NULL OR "
        "(monthly_budget_override_amount>0 AND "
        "monthly_budget_override_amount<10000000000000000 AND "
        "trunc(monthly_budget_override_amount)=monthly_budget_override_amount)",
        name="ck_configuration_budget",
    ),
    CheckConstraint(
        "public.otm_valid_override_statements(policy_override_statements) AND "
        "public.otm_valid_override_statements(quota_override_statements)",
        name="ck_configuration_statements",
    ),
)
tenancy.append_column(Column("desired_configuration_id", Uuid(as_uuid=True)))
tenancy.append_column(Column("last_verified_configuration_id", Uuid(as_uuid=True)))
for pointer in ("desired_configuration_id", "last_verified_configuration_id"):
    tenancy.append_constraint(
        ForeignKeyConstraint(
            ["workspace_id", "id", pointer],
            [
                "public.otm_tenancy_configuration.workspace_id",
                "public.otm_tenancy_configuration.tenancy_id",
                "public.otm_tenancy_configuration.id",
            ],
            name="fk_tenancy_" + pointer,
            use_alter=True,
        )
    )


# Draft plans own review context only; accepting work still uses the existing operation/native
# queue.
configuration_plan = Table(
    "otm_configuration_plan",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("scope_tenancy_id", Uuid(as_uuid=True)),
    Column("target_baseline_version_id", Uuid(as_uuid=True)),
    Column("candidate_set_hash", String(64), nullable=False),
    Column("client_request_key", Uuid(as_uuid=True), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("created_by", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("operation_id", Uuid(as_uuid=True)),
    UniqueConstraint("workspace_id", "id", name="uq_configuration_plan_scope"),
    UniqueConstraint(
        "workspace_id", "created_by", "client_request_key", name="uq_configuration_plan_request"
    ),
    ForeignKeyConstraint(["workspace_id"], ["public.org_workspace.id"], name="fk_plan_workspace"),
    ForeignKeyConstraint(
        ["workspace_id", "scope_tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_plan_scope_tenancy",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "target_baseline_version_id"],
        ["public.otm_baseline_version.workspace_id", "public.otm_baseline_version.id"],
        name="fk_plan_baseline",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_plan_operation",
    ),
    CheckConstraint(
        "revision>=1 AND candidate_set_hash ~ '^[0-9a-f]{64}$'", name="ck_plan_revision"
    ),
)


# A target captures source context and two independent staged whole-list review choices.
configuration_plan_target = Table(
    "otm_configuration_plan_target",
    metadata,
    Column("workspace_id", String(256), primary_key=True),
    Column("plan_id", Uuid(as_uuid=True), primary_key=True),
    Column("tenancy_id", Uuid(as_uuid=True), primary_key=True),
    Column("proposal", JSONB, nullable=False),
    Column("proposal_hash", String(64), nullable=False),
    Column("policy_choice", String(32)),
    Column("quota_choice", String(32)),
    Column("reviewed_by", String(256)),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("accepted_configuration_id", Uuid(as_uuid=True)),
    ForeignKeyConstraint(
        ["workspace_id", "plan_id"],
        ["public.otm_configuration_plan.workspace_id", "public.otm_configuration_plan.id"],
        name="fk_plan_target_plan",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_plan_target_tenancy",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id", "accepted_configuration_id"],
        [
            "public.otm_tenancy_configuration.workspace_id",
            "public.otm_tenancy_configuration.tenancy_id",
            "public.otm_tenancy_configuration.id",
        ],
        name="fk_plan_target_configuration",
    ),
    CheckConstraint(
        "jsonb_typeof(proposal)='object' AND proposal_hash ~ '^[0-9a-f]{64}$'",
        name="ck_plan_target_proposal",
    ),
    CheckConstraint(
        "(policy_choice IS NULL OR policy_choice IN "
        "('use_new_baseline','keep_override')) AND (quota_choice IS NULL OR "
        "quota_choice IN ('use_new_baseline','keep_override')) AND (reviewed_by IS "
        "NULL)=(reviewed_at IS NULL)",
        name="ck_plan_target_review",
    ),
)


# One immutable per-child read attempt retains exact context and database acquisition ordering.
configuration_check = Table(
    "otm_configuration_check",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("tenancy_id", Uuid(as_uuid=True), nullable=False),
    Column("operation_id", Uuid(as_uuid=True), nullable=False),
    Column("acquisition_sequence", BigInteger, Identity(always=True), nullable=False, unique=True),
    Column("contract_version", String(32), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("checked_at", DateTime(timezone=True), nullable=False),
    Column("context", JSONB, nullable=False),
    Column("context_hash", String(64), nullable=False),
    Column("state", String(32), nullable=False),
    Column("results", JSONB, nullable=False),
    Column("evidence_event_id", Uuid(as_uuid=True), nullable=False),
    UniqueConstraint(
        "workspace_id", "operation_id", "tenancy_id", name="uq_configuration_check_target"
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_check_child",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id", "evidence_event_id"],
        [
            "public.audit_event.workspace_id",
            "public.audit_event.operation_id",
            "public.audit_event.id",
        ],
        name="fk_check_evidence",
    ),
    CheckConstraint(
        "acquisition_sequence>0 AND checked_at>=started_"
        "at AND contract_version='configuration-check-1'",
        name="ck_check_version",
    ),
    CheckConstraint(
        "state IN ('matching','drifted','unavailable','superseded')", name="ck_check_state"
    ),
    CheckConstraint(
        "context_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(context)='object'",
        name="ck_check_context",
    ),
    CheckConstraint(
        "jsonb_typeof(results)='array' AND jsonb_array_length(results)=4", name="ck_check_results"
    ),
)
Index(
    "ix_configuration_check_current",
    configuration_check.c.workspace_id,
    configuration_check.c.tenancy_id,
    configuration_check.c.acquisition_sequence.desc(),
)


notification_outbox = Table(
    "otm_notification_outbox",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("operation_id", Uuid(as_uuid=True), nullable=False),
    Column("transition_key", String(64), nullable=False),
    Column("intent", JSONB, nullable=False),
    Column("intent_hash", String(64), nullable=False),
    Column("state", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("attempt_id", Uuid(as_uuid=True), nullable=True),
    Column("last_attempt_at", DateTime(timezone=True), nullable=True),
    Column("next_attempt_at", DateTime(timezone=True), nullable=True),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    Column("safe_code", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "id", name="uq_notification_workspace_id"),
    UniqueConstraint(
        "workspace_id", "operation_id", "transition_key", name="uq_notification_transition"
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_notification_operation",
    ),
    CheckConstraint(
        "state IN ('pending','blocked','sending','sent','failed','unknown','superseded')",
        name="ck_notification_state",
    ),
    CheckConstraint("attempts>=0 AND attempts<=3", name="ck_notification_attempts"),
    CheckConstraint(
        "intent_hash ~ '^[0-9a-f]{64}$' AND transition_key ~ '^[0-9a-f]{64}$'",
        name="ck_notification_hashes",
    ),
    CheckConstraint(
        "updated_at>=created_at AND "
        "(last_attempt_at IS NULL OR last_attempt_at>=created_at) AND "
        "((attempts=0 AND attempt_id IS NULL AND last_attempt_at IS NULL) OR "
        "(attempts>0 AND attempt_id IS NOT NULL AND last_attempt_at IS NOT NULL))",
        name="ck_notification_times",
    ),
    CheckConstraint(
        "(state='sent' AND sent_at IS NOT NULL) OR (state<>'sent' AND sent_at IS NULL)",
        name="ck_notification_sent",
    ),
)
Index(
    "ix_notification_operation",
    notification_outbox.c.workspace_id,
    notification_outbox.c.operation_id,
    notification_outbox.c.created_at.desc(),
)
Index(
    "ix_notification_pending",
    notification_outbox.c.workspace_id,
    notification_outbox.c.state,
    notification_outbox.c.next_attempt_at,
)


# One bounded child acquisition head reuses the operation/audit/native queue authorities.
financial_collection = Table(
    "otm_financial_collection",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("tenancy_id", Uuid(as_uuid=True), nullable=False),
    Column("operation_id", Uuid(as_uuid=True), nullable=False),
    Column("context", JSONB, nullable=False),
    Column("context_hash", String(64), nullable=False),
    Column("source_hash", String(64), nullable=False),
    Column("failure_scope_hash", String(64), nullable=False),
    Column("state", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("attempt_id", Uuid(as_uuid=True)),
    Column("next_attempt_at", DateTime(timezone=True)),
    Column("safe_code", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "id", name="uq_financial_collection_scope"),
    UniqueConstraint(
        "workspace_id",
        "id",
        "tenancy_id",
        "context_hash",
        "source_hash",
        name="uq_financial_collection_exact",
    ),
    UniqueConstraint("workspace_id", "operation_id", "tenancy_id", name="uq_financial_child"),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_financial_collection_child",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_financial_collection_operation",
    ),
    CheckConstraint(
        "state IN ('queued','reading','retry','succeeded','failed','superseded')",
        name="ck_financial_collection_state",
    ),
    CheckConstraint(
        "attempts>=0 AND attempts<=3 AND updated_at>=created_at "
        "AND ((attempts=0 AND attempt_id IS NULL) OR "
        "(attempts>0 AND attempt_id IS NOT NULL))",
        name="ck_financial_collection_attempt",
    ),
    CheckConstraint(
        "context_hash ~ '^[0-9a-f]{64}$' AND source_hash ~ '^[0-9a-f]{64}$' "
        "AND failure_scope_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(context)='object'",
        name="ck_financial_collection_context",
    ),
)
Index(
    "uq_financial_active_context",
    financial_collection.c.workspace_id,
    financial_collection.c.tenancy_id,
    financial_collection.c.context_hash,
    unique=True,
    postgresql_where=financial_collection.c.state.in_(("queued", "reading", "retry")),
)
Index(
    "ix_financial_collection_child",
    financial_collection.c.workspace_id,
    financial_collection.c.tenancy_id,
    financial_collection.c.created_at.desc(),
)


# Immutable same-response snapshots expose queryable numeric values without a cost-history API.
financial_observation = Table(
    "otm_financial_observation",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("tenancy_id", Uuid(as_uuid=True), nullable=False),
    Column("collection_id", Uuid(as_uuid=True), nullable=False),
    Column("context_hash", String(64), nullable=False),
    Column("source_hash", String(64), nullable=False),
    Column("budget_ocid", String(256), nullable=False),
    Column("observed_budget_amount", Numeric(20, 4)),
    Column("actual_spend", Numeric(20, 4)),
    Column("forecasted_spend", Numeric(20, 4)),
    Column("currency", String(3)),
    Column("time_spend_computed", DateTime(timezone=True)),
    Column("captured_at", DateTime(timezone=True), nullable=False),
    Column("period_start", DateTime(timezone=True)),
    Column("period_end", DateTime(timezone=True)),
    Column("snapshot", JSONB, nullable=False),
    Column("snapshot_hash", String(64), nullable=False),
    UniqueConstraint("workspace_id", "collection_id", name="uq_financial_observation_collection"),
    ForeignKeyConstraint(
        ["workspace_id", "collection_id", "tenancy_id", "context_hash", "source_hash"],
        [
            "public.otm_financial_collection.workspace_id",
            "public.otm_financial_collection.id",
            "public.otm_financial_collection.tenancy_id",
            "public.otm_financial_collection.context_hash",
            "public.otm_financial_collection.source_hash",
        ],
        name="fk_financial_observation_collection",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_financial_observation_child",
    ),
    CheckConstraint(
        "context_hash ~ '^[0-9a-f]{64}$' AND snapshot_hash ~ '^[0-9a-f]{64}$' "
        "AND jsonb_typeof(snapshot)='object'",
        name="ck_financial_observation_hash",
    ),
    CheckConstraint(
        "observed_budget_amount IS NULL OR observed_budget_amount>=0",
        name="ck_financial_budget_nonnegative",
    ),
    CheckConstraint(
        "(period_start IS NULL AND period_end IS NULL) OR "
        "(period_start IS NOT NULL AND period_end IS NOT NULL AND period_end>period_start)",
        name="ck_financial_observation_period",
    ),
)
Index(
    "ix_financial_observation_current",
    financial_observation.c.workspace_id,
    financial_observation.c.tenancy_id,
    financial_observation.c.source_hash,
    financial_observation.c.time_spend_computed.desc(),
    financial_observation.c.captured_at.desc(),
)

Index(
    "ix_financial_collection_failure_scope",
    financial_collection.c.workspace_id,
    financial_collection.c.failure_scope_hash,
    financial_collection.c.updated_at.desc(),
)


managed_object_binding = Table(
    "otm_managed_object_binding",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workspace_id", String(256), nullable=False),
    Column("tenancy_id", Uuid(as_uuid=True), nullable=False),
    Column("logical_key", String(64), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("handler_contract_version", String(64), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("identity_domain_binding_id", Uuid(as_uuid=True)),
    Column("provider_ocid", String(256), nullable=False),
    Column("scim_resource_id", String(256)),
    Column("user_name", String(256)),
    Column("ownership_mode", String(32), nullable=False),
    Column("state", String(16), nullable=False),
    Column("created_operation_id", Uuid(as_uuid=True), nullable=False),
    Column("source_evidence_event_id", Uuid(as_uuid=True), nullable=False),
    Column("retired_operation_id", Uuid(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("workspace_id", "tenancy_id", "id", name="uq_managed_binding_scope"),
    UniqueConstraint(
        "workspace_id",
        "tenancy_id",
        "logical_key",
        "generation",
        name="uq_managed_binding_generation",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id"],
        ["public.otm_tenancy.workspace_id", "public.otm_tenancy.id"],
        name="fk_managed_binding_tenancy",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "tenancy_id", "identity_domain_binding_id"],
        [
            "public.otm_managed_object_binding.workspace_id",
            "public.otm_managed_object_binding.tenancy_id",
            "public.otm_managed_object_binding.id",
        ],
        name="fk_managed_binding_domain",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "created_operation_id", "source_evidence_event_id"],
        [
            "public.audit_event.workspace_id",
            "public.audit_event.operation_id",
            "public.audit_event.id",
        ],
        name="fk_managed_binding_capture",
    ),
    ForeignKeyConstraint(
        ["workspace_id", "retired_operation_id"],
        ["public.otm_operation.workspace_id", "public.otm_operation.id"],
        name="fk_managed_binding_retirement",
    ),
    CheckConstraint(
        "generation>=1 AND handler_contract_version='required-user-binding-1'",
        name="ck_managed_binding_version",
    ),
    CheckConstraint(
        "(state='active' AND retired_operation_id IS NULL) OR "
        "(state='retired' AND retired_operation_id IS NOT NULL)",
        name="ck_managed_binding_state",
    ),
    CheckConstraint("updated_at>=created_at", name="ck_managed_binding_time"),
    CheckConstraint(
        "(kind='identity_domain' AND logical_key='identity/domain' "
        "AND ownership_mode='observed_reference' AND identity_domain_binding_id IS NULL "
        "AND scim_resource_id IS NULL AND user_name IS NULL "
        "AND provider_ocid ~ '^ocid1[.]domain[.][A-Za-z0-9.]+$') OR "
        "(kind='managed_user' AND logical_key IN "
        "('identity/user/automation','identity/user/recovery') "
        "AND ownership_mode='managed' AND identity_domain_binding_id IS NOT NULL "
        "AND scim_resource_id IS NOT NULL AND length(btrim(scim_resource_id))>0 "
        "AND user_name IS NOT NULL AND length(btrim(user_name))>0 "
        "AND provider_ocid ~ '^ocid1[.]user[.][A-Za-z0-9.]+$')",
        name="ck_managed_binding_shape",
    ),
)
Index(
    "uq_managed_binding_live_key",
    managed_object_binding.c.workspace_id,
    managed_object_binding.c.tenancy_id,
    managed_object_binding.c.logical_key,
    unique=True,
    postgresql_where=managed_object_binding.c.state == "active",
)
Index(
    "uq_managed_binding_live_ocid",
    managed_object_binding.c.workspace_id,
    managed_object_binding.c.tenancy_id,
    managed_object_binding.c.provider_ocid,
    unique=True,
    postgresql_where=managed_object_binding.c.state == "active",
)
Index(
    "uq_managed_binding_live_scim",
    managed_object_binding.c.workspace_id,
    managed_object_binding.c.tenancy_id,
    managed_object_binding.c.identity_domain_binding_id,
    managed_object_binding.c.scim_resource_id,
    unique=True,
    postgresql_where=(managed_object_binding.c.state == "active")
    & managed_object_binding.c.scim_resource_id.is_not(None),
)
