"""Explicit disposable production-test connections and programmatic migration ownership."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]


# Reject missing/unsafe URLs before construction; never read the saved prototype connection.
def test_engine():
    raw = os.environ.get("OTM_BACKEND_TEST_DATABASE_URL")
    if not raw:
        raise ValueError("Run scripts/run_backend_postgres_tests.py for required database tests")
    url = make_url(raw)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.username != "otm_test"
        or url.database != "otm_backend_test"
        or not url.port
        or not url.password
        or url.query
    ):
        raise ValueError("Only the disposable production-test database is allowed")
    return create_engine(
        url,
        hide_parameters=True,
        pool_size=4,
        max_overflow=4,
        connect_args={
            "hostaddr": "127.0.0.1",
            "connect_timeout": 5,
            "options": "-c statement_timeout=10000 -c lock_timeout=5000 -c timezone=UTC",
        },
    )


# Run Alembic on a provided connection without storing credentials in config.
def migrate(engine, revision="head", *, downgrade=False):
    configuration = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        configuration.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(configuration, revision)


# Write a real accepted intent/job under migration0001 before upgrading its audit schema.
def seed_legacy_admission(engine):
    from datetime import UTC, datetime
    from uuid import uuid4

    from otm.operations.contracts import ActorIdentity, InspectImportRequest, InspectionIntent
    from otm.providers.inspection_contracts import InspectionTarget
    from otm.storage.admission import SqlAdmissionStore
    from otm.storage.enqueue import InspectionEnqueuer

    request = InspectImportRequest(
        workspace_id="migration-compatibility",
        client_request_key=uuid4(),
        tenancy_ocid="ocid1.tenancy.oc1..legacychild",
    )
    actor = ActorIdentity(issuer="https://sso.example.test", subject="legacy-test-admin")
    intent = InspectionIntent(
        contract_version="inspect-import-1",
        kind="inspect_import",
        workspace_id=request.workspace_id,
        policy_revision=uuid4(),
        access_binding_id=uuid4(),
        target=InspectionTarget(
            organization_id="example-organization",
            parent_tenancy_ocid="ocid1.tenancy.oc1..exampleparent",
            tenancy_ocid=request.tenancy_ocid,
        ),
    )
    SqlAdmissionStore(engine, InspectionEnqueuer()).insert(
        request, actor, intent, datetime.now(UTC)
    )


# Seed the actual pre-idle schema so the shared upgrade fixture can verify fail-closed migration.
def seed_legacy_session(engine):
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from otm.storage.tables import admin_session

    at = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            admin_session.insert().values(
                id=uuid4(),
                workspace_id="migration-legacy-session",
                session_token_hash=uuid4().hex + uuid4().hex,
                issuer="https://sso.example.test",
                subject="legacy-fixture",
                display_snapshot={"display_name": "Migration fixture"},
                entitlement_reference="fixture-group",
                entitlement_revision=uuid4(),
                entitlement_checked_at=at,
                auth_time=at,
                created_at=at,
                expires_at=at + timedelta(hours=8),
                last_seen_at=at,
                revoked_at=None,
                provider_session_reference_hash=None,
            )
        )


# Explicitly seed the new grant FK for legacy session-only integration cases, without issuing
# tokens.
def seed_session_grant(connection, values):
    from uuid import uuid4

    from sqlalchemy.dialects.postgresql import insert

    from otm.storage.tables import administrator

    connection.execute(
        insert(administrator)
        .values(
            id=uuid4(),
            workspace_id=values["workspace_id"],
            identity_kind="corporate_sso",
            issuer=values["issuer"],
            subject=values["subject"],
            display_name="Synthetic administrator",
            email=None,
            status="active",
            authorization_revision=values["entitlement_revision"],
            created_at=values["created_at"],
            updated_at=values["created_at"],
            revoked_at=None,
        )
        .on_conflict_do_nothing(constraint="uq_administrator_identity")
    )
