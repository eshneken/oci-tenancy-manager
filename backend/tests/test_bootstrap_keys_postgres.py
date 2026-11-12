"""Real scoped create/import handoffs expose only stable public bootstrap material."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from test_organization_storage_postgres import factors, login_case, organization_case
from test_organization_workflows_postgres import action, workflow_case

from otm.providers.bootstrap_keys_local import LocalBootstrapKeys
from otm.storage.organization import OrganizationConflict
from otm.storage.tables import audit_event, operation_step
from otm.tenancies.onboarding_contracts import OnboardingCommand

pytestmark = pytest.mark.postgres
__all__ = ["factors", "login_case", "organization_case", "workflow_case"]


# Only current real operation scope reaches the chosen private local adapter.
@pytest.mark.parametrize("origin", ["create_tenancy", "import_tenancy"])
def test_new_create_import_prepare_public_key(workflow_case, tmp_path, origin):
    c = workflow_case
    directory = tmp_path / "bootstrap"
    directory.mkdir(mode=0o700)
    keys = LocalBootstrapKeys(directory)
    c.workflow.bootstrap_keys = c.worker.bootstrap_keys = keys
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    fields = (
        {"import_ocid": "ocid1.tenancy.oc1..otmsimimport" + uuid4().hex}
        if origin == "import_tenancy"
        else {}
    )
    _, receipt = action(c, person.id, origin, **fields)
    c.worker.run(receipt.operation_id)
    view = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert view.phase == "handoff"
    assert view.public_key.startswith("-----BEGIN PUBLIC KEY-----")
    assert c.workflow.onboarding(c.principal, receipt.operation_id).public_key == view.public_key
    assert "prepare_bootstrap_key" in view.available_actions
    with c.engine.connect() as connection:
        data = connection.scalars(
            select(audit_event.c.data).where(audit_event.c.operation_id == receipt.operation_id)
        ).all()
        safe = all(
            "PRIVATE KEY" not in str(value) and "private_pem" not in str(value) for value in data
        )
        assert safe


# Waiting operations prepare explicitly without replaying setup or resetting the form.
def test_existing_wait_public_generation_is_guarded_and_idempotent(workflow_case, tmp_path):
    c = workflow_case
    person = next(p for p in c.store.head(c.principal).people if p.email == "engineer@example.test")
    _, receipt = action(c, person.id, "create_tenancy")
    c.worker.run(receipt.operation_id)
    before = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert before.public_key is None
    directory = tmp_path / "bootstrap"
    directory.mkdir(mode=0o700)
    c.workflow.bootstrap_keys = LocalBootstrapKeys(directory)
    command = OnboardingCommand(
        client_request_key=uuid4(), revision=before.revision, action="prepare_bootstrap_key"
    )
    with pytest.raises(OrganizationConflict, match="ONBOARDING_PREVIEW_CHANGED"):
        c.workflow.onboarding_action(
            c.principal,
            receipt.operation_id,
            command.model_copy(update={"revision": before.revision + 1}),
        )
    assert c.workflow.onboarding(c.principal, receipt.operation_id).public_key is None
    # Custody may survive an interrupted audit transaction; retry must still complete.
    c.workflow.bootstrap_keys.prepare(c.policy.workspace_id, receipt.operation_id)
    retained_public = c.workflow.onboarding(c.principal, receipt.operation_id).public_key
    first = c.workflow.onboarding_action(c.principal, receipt.operation_id, command)
    assert (
        c.workflow.onboarding_action(c.principal, receipt.operation_id, command).operation_id
        == first.operation_id
    )
    after = c.workflow.onboarding(c.principal, receipt.operation_id)
    assert (
        after.phase == "handoff"
        and after.revision == before.revision
        and after.public_key == retained_public
    )
    with c.engine.connect() as connection:
        events = connection.scalars(
            select(audit_event.c.data).where(
                audit_event.c.operation_id == receipt.operation_id,
                audit_event.c.kind == "onboarding_action",
            )
        ).all()
        assert len(events) == 1 and events[0]["step"] == "prepare_bootstrap_key"
        assert not connection.scalars(
            select(operation_step.c.operation_id).where(
                operation_step.c.operation_id == receipt.operation_id
            )
        ).all()
