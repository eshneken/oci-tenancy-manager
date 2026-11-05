"""Mapping Apply uses installed API privileges rather than relying on table-owner test access."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_organization_fixtures import example_config, example_records
from test_sandbox_runtime_postgres import runtime

from otm.organization.contracts import Envelope, Intake
from otm.organization.mapping import MappingService, editable
from otm.organization.mapping_contracts import MappingApply, MappingRequest
from otm.storage.organization import SqlOrganizationStore
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]


# Exercise the same restricted login, configuration and mutation path as the HTTPS application.
def test_mapping_apply_with_installed_api_role(runtime):
    c = runtime
    store = SqlOrganizationStore(c.api, c.sessions, lambda: datetime.now(UTC))
    config = example_config()
    store.configure_initial(c.principal, config)
    first_capture = datetime.now(UTC) - timedelta(minutes=30)
    store.ingest(
        c.principal,
        Intake(
            envelope=Envelope(
                source_id=config.policy.source_id,
                population_id=config.policy.population_id,
                external_snapshot_id=str(uuid4()),
                captured_at=first_capture,
                declared_completeness="complete",
            ),
            records=example_records(),
        ),
    )
    store.ingest(
        c.principal,
        Intake(
            envelope=Envelope(
                source_id=config.policy.source_id,
                population_id=config.policy.population_id,
                external_snapshot_id=str(uuid4()),
                captured_at=first_capture + timedelta(minutes=10),
                declared_completeness="complete",
            ),
            records=example_records()[:-1],
        ),
    )
    service = MappingService(store, config, OrganizationWorkflows(store))
    state = service.read(c.principal)
    body = editable(config).model_dump()
    body["segments"][0]["designee_emails"] = ("one@example.test", "delegate@example.test")
    body["segments"][1]["designee_emails"] = ("delegate@example.test",)
    request = MappingRequest(
        context=state.context, candidate=type(state.candidate).model_validate(body)
    )
    view = service.preview(c.principal, request)
    service.apply(
        c.principal, MappingApply(**request.model_dump(), preview_token=view.preview_token)
    )
    # A repeated projection updates an existing role case, still under the restricted role.
    updated = service.read(c.principal)
    request = MappingRequest(context=updated.context, candidate=updated.candidate)
    view = service.preview(c.principal, request)
    service.apply(
        c.principal, MappingApply(**request.model_dump(), preview_token=view.preview_token)
    )
