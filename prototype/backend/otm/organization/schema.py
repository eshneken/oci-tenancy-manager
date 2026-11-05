"""Local organization evidence, simulated tenancy associations and readable inspection views."""

import re

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB


# Define organization, tenancy association and immutable audit/outbox tables.
def schema_tables(schema: str) -> tuple[MetaData, dict[str, Table]]:
    metadata = MetaData(schema=schema)
    tables = {}

    # Register a physical table under its concise repository binding.
    def add(key: str, name: str, *columns: object) -> Table:
        table = Table(name, metadata, *columns)
        tables[key] = table
        return table

    # Return a schema-qualified organization primary key reference.
    def fk(name: str) -> str:
        return f"{schema}.org_{name}.id"

    add(
        "person",
        "org_person",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("email", String(320), nullable=False, unique=True),
    )
    workspace = add(
        "workspace",
        "org_workspace",
        Column("id", String, primary_key=True),
        Column("configuration_id", Uuid(as_uuid=False), nullable=False),
        Column("configuration", JSONB, nullable=False),
        Column("applied_version_id", Uuid(as_uuid=False)),
        Column("proposed_version_id", Uuid(as_uuid=False)),
        Column("applied_kind", String, nullable=False, server_default="applied"),
        Column("proposed_kind", String, nullable=False, server_default="proposed"),
        CheckConstraint("applied_kind = 'applied' AND proposed_kind = 'proposed'"),
    )
    add(
        "feed",
        "org_feed",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("workspace_id", String, ForeignKey(fk("workspace")), nullable=False),
        Column("source_id", String, nullable=False),
        Column("external_id", String, nullable=False),
        Column("captured_at", DateTime(timezone=True)),
        Column("digest", String(64), nullable=False),
        Column("data", JSONB, nullable=False),
        Column("state", String, nullable=False),
        Column("diagnostics", JSONB, nullable=False),
        Column("proposed_version_id", Uuid(as_uuid=False)),
        Column("applied_version_id", Uuid(as_uuid=False)),
        UniqueConstraint("workspace_id", "source_id", "external_id"),
        UniqueConstraint("workspace_id", "id"),
    )
    version = add(
        "version",
        "org_version",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("workspace_id", String, ForeignKey(fk("workspace")), nullable=False),
        Column("kind", String, nullable=False),
        Column("base_version_id", Uuid(as_uuid=False)),
        Column("feed_id", Uuid(as_uuid=False), nullable=False),
        Column("configuration_id", Uuid(as_uuid=False), nullable=False),
        Column("configuration", JSONB, nullable=False),
        Column("sealed", Boolean, nullable=False, server_default="false"),
        Column("data", JSONB, nullable=False),
        CheckConstraint("kind IN ('proposed', 'applied')"),
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "id", "kind"),
        ForeignKeyConstraint(
            ["workspace_id", "feed_id"],
            [f"{schema}.org_feed.workspace_id", f"{schema}.org_feed.id"],
        ),
    )
    version.append_constraint(
        ForeignKeyConstraint(
            ["workspace_id", "base_version_id"],
            [f"{schema}.org_version.workspace_id", f"{schema}.org_version.id"],
        )
    )
    for pointer, kind in (
        ("applied_version_id", "applied_kind"),
        ("proposed_version_id", "proposed_kind"),
    ):
        workspace.append_constraint(
            ForeignKeyConstraint(
                ["id", pointer, kind],
                [
                    f"{schema}.org_version.workspace_id",
                    f"{schema}.org_version.id",
                    f"{schema}.org_version.kind",
                ],
                use_alter=True,
            )
        )
    # Deferred same-version manager FKs allow bulk insertion in any order, but reject
    # cross-version reporting edges at transaction commit.
    member = add(
        "member",
        "org_member",
        Column("version_id", Uuid(as_uuid=False), ForeignKey(fk("version")), primary_key=True),
        Column("person_id", Uuid(as_uuid=False), ForeignKey(fk("person")), primary_key=True),
        Column("email", String(320), nullable=False),
        Column("full_name", String),
        Column("manager_person_id", Uuid(as_uuid=False)),
        Column("manager_email", String(320)),
        Column("profile", String, nullable=False),
        Column("evidence", String, nullable=False),
        Column("lob_id", String),
        Column("accountable_leader_email", String(320)),
        Column("designee_emails", JSONB, nullable=False),
        Column("ancestry", String, nullable=False),
        Column("absence_review", Boolean, nullable=False),
        Column("data", JSONB, nullable=False),
        UniqueConstraint("version_id", "email"),
        CheckConstraint("person_id <> manager_person_id", name="not_self_managed"),
        ForeignKeyConstraint(
            ["version_id", "manager_person_id"],
            [f"{schema}.org_member.version_id", f"{schema}.org_member.person_id"],
            deferrable=True,
            initially="DEFERRED",
            name="manager_same_revision",
        ),
    )
    Index("manager_children", member.c.version_id, member.c.manager_person_id)
    recommendation = add(
        "recommendation",
        "org_recommendation",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("workspace_id", String, ForeignKey(fk("workspace")), nullable=False),
        Column("feed_id", Uuid(as_uuid=False), ForeignKey(fk("feed")), nullable=False),
        Column(
            "proposed_version_id", Uuid(as_uuid=False), ForeignKey(fk("version")), nullable=False
        ),
        Column("applied_version_id", Uuid(as_uuid=False), ForeignKey(fk("version"))),
        Column("person_id", Uuid(as_uuid=False), ForeignKey(fk("person"))),
        Column("category", String, nullable=False),
        Column("kind", String, nullable=False),
        Column("target", String, nullable=False),
        Column("field", String),
        Column("before_value", JSONB),
        Column("after_value", JSONB),
        Column("status", String, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("resolved_at", DateTime(timezone=True)),
        Column("reason", String),
        Column("actor", String),
    )
    Index(
        "one_open_exception",
        recommendation.c.workspace_id,
        recommendation.c.kind,
        recommendation.c.target,
        unique=True,
        postgresql_where=(recommendation.c.category == "exception")
        & recommendation.c.status.in_(["open", "acknowledged"]),
    )
    add(
        "event",
        "audit_event",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("workspace_id", String, ForeignKey(fk("workspace")), nullable=False),
        Column("feed_id", Uuid(as_uuid=False), ForeignKey(fk("feed"))),
        Column("version_id", Uuid(as_uuid=False), ForeignKey(fk("version"))),
        Column("actor", String, nullable=False),
        Column("kind", String, nullable=False),
        Column("at", DateTime(timezone=True), nullable=False),
        Column("data", JSONB, nullable=False),
    )
    add(
        "notification",
        "notification_outbox",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column(
            "recommendation_id",
            Uuid(as_uuid=False),
            ForeignKey(fk("recommendation")),
            nullable=False,
            unique=True,
        ),
        Column("version_id", Uuid(as_uuid=False), ForeignKey(fk("version")), nullable=False),
        Column("recipients", JSONB, nullable=False),
        Column("state", String, nullable=False),
    )
    tenancy = add(
        "tenancy",
        "org_tenancy",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("workspace_id", String, ForeignKey(fk("workspace")), nullable=False),
        Column("name", String(200), nullable=False),
        Column("kind", String, nullable=False),
        Column("status", String, nullable=False),
        Column("legacy", Boolean, nullable=False, server_default="false"),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("kind IN ('individual', 'shared')"),
        CheckConstraint("status IN ('active', 'deleted')"),
    )
    association = add(
        "association",
        "org_tenancy_association",
        Column("id", Uuid(as_uuid=False), primary_key=True),
        Column("workspace_id", String, ForeignKey(fk("workspace")), nullable=False),
        Column("tenancy_id", Uuid(as_uuid=False), nullable=False),
        Column("person_id", Uuid(as_uuid=False), ForeignKey(fk("person")), nullable=False),
        Column("role", String, nullable=False),
        Column("status", String, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        ForeignKeyConstraint(
            ["workspace_id", "tenancy_id"], [tenancy.c.workspace_id, tenancy.c.id]
        ),
        CheckConstraint("role IN ('owner', 'member')"),
        CheckConstraint("status IN ('active', 'removed')"),
    )
    Index(
        "uq_active_tenancy_person",
        association.c.workspace_id,
        association.c.tenancy_id,
        association.c.person_id,
        unique=True,
        postgresql_where=text("status = 'active'"),
    )
    Index(
        "uq_active_tenancy_owner",
        association.c.workspace_id,
        association.c.tenancy_id,
        unique=True,
        postgresql_where=text("status = 'active' AND role = 'owner'"),
    )
    return metadata, tables


# Protect immutable evidence and expose plain SQL views; this is not a production
# migration.
def install_guards(connection, schema: str) -> None:
    # Identifiers cannot be bound as SQL values; validate before every direct DDL entry point.
    if not re.fullmatch(r"otm_[a-z0-9_]+", schema):
        raise ValueError("invalid local schema")
    # These triggers protect ordinary writes, not privileged DBA changes. The outbox
    # is immutable intent-only evidence; future delivery attempts are a separate concern.
    # Column-level feed protection permits processing updates without rewriting source evidence.
    connection.execute(
        text(f'''
      CREATE OR REPLACE FUNCTION "{schema}".protect_content() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        IF TG_TABLE_NAME = 'org_feed' AND TG_OP = 'UPDATE' AND
          (to_jsonb(OLD) - ARRAY['state','diagnostics',
                       'proposed_version_id','applied_version_id']) =
          (to_jsonb(NEW) - ARRAY['state','diagnostics',
                       'proposed_version_id','applied_version_id'])
          THEN RETURN NEW; END IF;
        IF TG_TABLE_NAME = 'org_recommendation' AND TG_OP = 'UPDATE' AND
          (to_jsonb(OLD) - ARRAY['applied_version_id','status','updated_at',
                       'resolved_at','reason','actor']) =
          (to_jsonb(NEW) - ARRAY['applied_version_id','status','updated_at',
                       'resolved_at','reason','actor'])
          THEN RETURN NEW; END IF;
        IF TG_TABLE_NAME = 'org_version' AND TG_OP = 'UPDATE' AND NOT OLD.sealed AND NEW.sealed
          AND (to_jsonb(OLD) - 'sealed') = (to_jsonb(NEW) - 'sealed') THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'immutable organization content';
      END; $$;
      CREATE OR REPLACE FUNCTION "{schema}".unsealed_member_insert() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        IF (SELECT sealed FROM "{schema}".org_version WHERE id = NEW.version_id)
          THEN RAISE EXCEPTION 'published revision is sealed'; END IF;
        RETURN NEW;
      END; $$;
    ''')  # nosec B608
    )
    for name in (
        "org_person",
        "org_feed",
        "org_version",
        "org_member",
        "audit_event",
        "notification_outbox",
        "org_recommendation",
    ):
        connection.execute(
            text(f'''CREATE OR REPLACE TRIGGER immutable_content
          BEFORE UPDATE OR DELETE ON "{schema}"."{name}" FOR EACH ROW
          EXECUTE FUNCTION "{schema}".protect_content();''')
        )
    connection.execute(
        text(f'''CREATE OR REPLACE TRIGGER unsealed_member_insert
      BEFORE INSERT ON "{schema}".org_member FOR EACH ROW
      EXECUTE FUNCTION "{schema}".unsealed_member_insert();''')
    )
    # Names and LOB labels use the selected version's frozen evidence, not today's config.
    # Setup review is a provisional read-model signal until a tenancy registry can resolve it.
    # Initial census employees are not assumed to require new tenancies; later employee profiles
    # remain visible across repeated feeds, including promotion from reference-only evidence.
    for view, pointer in (
        ("current_organization", "applied_version_id"),
        ("proposed_organization", "proposed_version_id"),
    ):
        connection.execute(
            text(f'''CREATE OR REPLACE VIEW "{schema}".{view} AS
          SELECT w.id AS workspace_id, m.version_id, m.person_id, m.full_name, m.email,
                 m.manager_email, manager.full_name AS manager_name, m.profile, m.evidence,
                 m.lob_id, m.accountable_leader_email, m.designee_emails, m.ancestry,
                 m.absence_review,
                 leader.full_name AS accountable_leader_name,
                 lob.value->>'label' AS lob_name,
                 COALESCE((m.data->>'known_manager')::boolean, false) AS known_manager,
                 COALESCE(designees.names, '[]'::jsonb) AS designee_names,
                 CASE WHEN m.lob_id IS NULL THEN 'no_lob'
                      WHEN jsonb_array_length(COALESCE(lob.value->'designee_emails',
                                                      '[]'::jsonb))=0 THEN 'not_configured'
                      WHEN jsonb_array_length(m.designee_emails)=0 THEN 'needs_review'
                      WHEN NOT (m.designee_emails @> (lob.value->'designee_emails')
                                    AND m.designee_emails <@ (lob.value->'designee_emails'))
                           THEN 'needs_review'
                      ELSE 'assigned' END AS designee_status,
                 onboarding.needs_review AS tenancy_setup_review,
                 'not_tracked'::text AS tenancy_association_status,
                 COALESCE(actions.kinds, '[]'::jsonb) ||
                   CASE WHEN onboarding.needs_review THEN
                     '["TENANCY_SETUP_REVIEW"]'::jsonb ELSE '[]'::jsonb END AS required_actions
          FROM "{schema}".org_workspace w JOIN "{schema}".org_member m ON m.version_id=w.{pointer}
          JOIN "{schema}".org_version selected ON selected.id=m.version_id
          LEFT JOIN "{schema}".org_member manager ON manager.version_id=m.version_id
            AND manager.person_id=m.manager_person_id
          LEFT JOIN "{schema}".org_member leader ON leader.version_id=m.version_id
            AND leader.email=m.accountable_leader_email
          LEFT JOIN LATERAL (
            SELECT value FROM jsonb_array_elements(selected.configuration->'lobs')
            WHERE value->>'id'=m.lob_id
          ) lob ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(COALESCE(d.full_name, address.value) ORDER BY address.ordinality)
                   AS names
            FROM jsonb_array_elements_text(m.designee_emails)
                 WITH ORDINALITY AS address(value, ordinality)
            LEFT JOIN "{schema}".org_member d ON d.version_id=m.version_id
              AND d.email=address.value
          ) designees ON true
          CROSS JOIN LATERAL (
            SELECT m.profile='employee' AND NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements(COALESCE(
                  selected.configuration->'review_decisions', '[]'::jsonb)) decision
              WHERE decision->>'kind'='TENANCY_SETUP_REVIEW'
                AND decision->>'target'=m.email
            ) AND EXISTS (
              SELECT 1 FROM "{schema}".org_version baseline
              WHERE baseline.workspace_id=w.id AND baseline.kind='applied'
                AND baseline.base_version_id IS NULL
                AND NOT EXISTS (
                  SELECT 1 FROM "{schema}".org_member original
                  WHERE original.version_id=baseline.id AND original.person_id=m.person_id
                    AND original.profile='employee'
                )
            ) AS needs_review
          ) onboarding
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(DISTINCT r.kind ORDER BY r.kind) AS kinds
            FROM "{schema}".org_recommendation r
            WHERE r.workspace_id=w.id AND r.person_id=m.person_id AND r.category='exception'
              AND r.status IN ('open', 'acknowledged')
          ) actions ON true;''')  # nosec B608
        )
    connection.execute(
        text(f'''CREATE OR REPLACE VIEW "{schema}".organization_reconciliation AS
      SELECT r.*, p.email AS person_email FROM "{schema}".org_recommendation r
      LEFT JOIN "{schema}".org_person p ON p.id=r.person_id;
      CREATE OR REPLACE VIEW "{schema}".pending_organization_reviews AS
      SELECT * FROM "{schema}".organization_reconciliation
      WHERE category='exception' AND status IN ('open','acknowledged');
    ''')  # nosec B608
    )
