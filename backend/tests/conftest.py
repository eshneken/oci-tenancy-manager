"""Synthetic, deterministic provider fixtures; no OCI credentials, database or network access."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from database_helpers import migrate, seed_legacy_admission, seed_legacy_session
from database_helpers import test_engine as create_test_engine

from otm.providers.inspection import TenancyInspection
from otm.providers.inspection_contracts import (
    ExecutionContext,
    InspectionTarget,
    InspectTenancy,
    TenancyFacts,
)
from otm.providers.inspection_simulator import (
    ManualClock,
    SimulatedAccess,
    SimulatedInspectionProvider,
    SimulatedTenancy,
)

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


# Keep caller intent, provider state and time separately editable in scenario tests.
@dataclass
class InspectionScenario:
    clock: ManualClock
    provider: SimulatedInspectionProvider
    service: TenancyInspection
    command: InspectTenancy
    access: SimulatedAccess
    tenancy: SimulatedTenancy


# Seed a permitted child, its expected parent and an exact binding generation.
@pytest.fixture
def inspection():
    clock = ManualClock(NOW)
    context = ExecutionContext(
        workspace_id="synthetic-org",
        operation_id=uuid4(),
        step_key="inspect_target",
        attempt_id=uuid4(),
        intent_revision=1,
        execution_generation=1,
        access_binding_id=uuid4(),
        credential_generation=1,
    )
    target = InspectionTarget(
        organization_id="synthetic-organization",
        parent_tenancy_ocid="ocid1.tenancy.oc1..syntheticparent",
        tenancy_ocid="ocid1.tenancy.oc1..syntheticchild",
    )
    command = InspectTenancy(
        contract_version="execution-1-draft",
        kind="inspect_tenancy",
        context=context,
        payload=target,
    )
    access = SimulatedAccess(
        workspace_id=context.workspace_id,
        access_binding_id=context.access_binding_id,
        credential_generation=1,
        permitted=True,
        tenancy_ocids=frozenset({target.tenancy_ocid}),
    )
    tenancy = SimulatedTenancy(
        workspace_id=context.workspace_id,
        visible_at=NOW,
        facts=TenancyFacts(
            **target.model_dump(),
            actual_name="Example sandbox",
            home_region_key="EXAMPLE-HOME",
            home_region_identifier=None,
            role="CHILD",
            observed_at=NOW,
        ),
    )
    provider = SimulatedInspectionProvider(clock.now)
    provider.set_access(access)
    provider.set_tenancy(tenancy)
    return InspectionScenario(
        clock, provider, TenancyInspection(provider, clock.now), command, access, tenancy
    )


# Migrate once and retain append-only history across isolated workspace tests.
@pytest.fixture(scope="session")
def pg_engine():
    engine = create_test_engine()
    try:
        migrate(engine, "0001_operation_admission")
        seed_legacy_admission(engine)
        migrate(engine, "0003_admin_session")
        seed_legacy_session(engine)
        migrate(engine, "0004_session_idle_policy")
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT revoked_at,idle_timeout_seconds FROM public.otm_admin_session "
                "WHERE workspace_id='migration-legacy-session'"
            ).one()
            assert row.revoked_at is not None and row.idle_timeout_seconds == 1800
        # Qualify the narrow capture migration against actual preexisting operation/audit data.
        migrate(engine, "0021_financial_collection")
        capture_orders = {
            "otm_operation": "id",
            "audit_event": "id",
            "otm_operation_step": "workspace_id,operation_id,intent_revision,step_key",
        }
        with engine.connect() as connection:
            before_capture = {
                table: connection.exec_driver_sql(
                    f"SELECT * FROM public.{table} ORDER BY {order}"
                ).all()
                for table, order in capture_orders.items()
            }
        migrate(engine)
        with engine.connect() as connection:
            for table, rows in before_capture.items():
                assert (
                    connection.exec_driver_sql(
                        f"SELECT * FROM public.{table} ORDER BY {capture_orders[table]}"
                    ).all()
                    == rows
                )
            assert (
                connection.exec_driver_sql(
                    "SELECT count(*) FROM public.otm_admin_session "
                    "WHERE workspace_id='migration-legacy-session'"
                ).scalar_one()
                == 0
            )
        yield engine
    finally:
        engine.dispose()
