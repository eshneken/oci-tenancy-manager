"""Real loopback SMTP capture, restricted native worker and HTTPS delivery/contact projections."""

import json
import subprocess
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import tomli_w
from sqlalchemy import select
from test_baseline_authoring import content
from test_organization_fixtures import envelope, example_config, example_records
from test_organization_workflows_postgres import action
from test_sandbox_runtime_postgres import drain, run_browser_runtime, runtime

from otm.configuration.contracts import PublishBaseline, SaveBaselineDraft
from otm.configuration.service import BaselineAuthoring
from otm.notifications.runtime import compose_notifications
from otm.operations.sandbox import load_sandbox
from otm.organization.contracts import Intake
from otm.providers.baseline_simulator import SimulatedBaselineQualifier
from otm.providers.lifecycle_simulator import SimulatedLifecycleFacade
from otm.settings import load_settings
from otm.storage.enqueue import ORGANIZATION_TASK, InspectionEnqueuer, workspace_queue
from otm.storage.organization import SqlOrganizationStore
from otm.storage.tables import notification_outbox
from otm.tenancies.worker import OrganizationLifecycleWorker
from otm.tenancies.workflows import OrganizationWorkflows

pytestmark = pytest.mark.postgres
__all__ = ["runtime"]
IMAGE = (
    "axllent/mailpit:v1.32.0@sha256:"
    "0790692be935ea4420d085694f7985b1f692ca6a8771ab0e0bd8ba75ac180498"
)


# A dedicated capture network has no configured relay; host ports bind loopback only.
@pytest.fixture
def mail_capture():
    marker = uuid4().hex
    name, network = "otm-mail-test-" + marker[:12], "otm-mail-net-" + marker[:12]
    created = False
    subprocess.run(
        [
            "docker",
            "network",
            "create",
            "--label",
            "otm.test.mail=" + marker,
            network,
        ],
        check=True,
        capture_output=True,
    )
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--label",
                "otm.test.mail=" + marker,
                "--network",
                network,
                "--user",
                "1000:1000",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--tmpfs",
                "/tmp:size=32m,mode=1777",
                "--memory",
                "128m",
                "--env",
                "MP_DATABASE=/tmp/mailpit.db",
                "--env",
                "MP_MAX_MESSAGES=10",
                "--env",
                "MP_DISABLE_VERSION_CHECK=true",
                "--env",
                "MP_SMTP_DISABLE_RDNS=true",
                "--publish",
                "127.0.0.1::1025",
                "--publish",
                "127.0.0.1::8025",
                IMAGE,
            ],
            check=True,
            capture_output=True,
        )
        created = True
        info = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
        assert info["Config"]["Labels"]["otm.test.mail"] == marker
        ports = info["NetworkSettings"]["Ports"]
        assert all(bindings[0]["HostIp"] == "127.0.0.1" for bindings in ports.values() if bindings)
        smtp_port, ui_port = (
            int(ports["1025/tcp"][0]["HostPort"]),
            int(ports["8025/tcp"][0]["HostPort"]),
        )
        url = f"http://127.0.0.1:{ui_port}"
        with httpx.Client(trust_env=False, timeout=3) as client:
            for _ in range(50):
                try:
                    if client.get(url + "/api/v1/messages").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("OWNED_MAIL_CAPTURE_NOT_READY")
        yield SimpleNamespace(smtp_port=smtp_port, url=url)
    finally:
        if created:
            inspected = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
            assert inspected["Config"]["Labels"]["otm.test.mail"] == marker
            subprocess.run(["docker", "rm", "--force", name], check=True, capture_output=True)
        subprocess.run(["docker", "network", "rm", network], check=True, capture_output=True)


# Runtime configuration changes only this fixture's private installation and test mailbox profile.
def captured_runtime(c, capture):
    settings = c.settings.model_dump(mode="json", exclude_none=True)
    settings["testing"] = {"email_override": "capture@otm.test"}
    settings["notifications"].update(enabled=True, smtp_port=capture.smtp_port, tls_mode="local")
    path = c.root / "application.toml"
    path.write_text(tomli_w.dumps(settings))
    path.chmod(0o600)
    c.settings = load_settings(path)
    notifier, _, _ = compose_notifications(
        c.settings, workspace_queue(c.settings.local_auth.workspace_id)
    )
    return notifier


# Both accepted SMTP and browser views use production code with actual installed API/worker roles.
def test_native_mailpit_delivery_and_https(runtime, mail_capture, monkeypatch):
    c = runtime
    notifier = captured_runtime(c, mail_capture)

    # Real server UTC avoids synthetic factor/time drift during browser enrollment/login.
    def clock():
        return datetime.now(UTC)

    store = SqlOrganizationStore(c.owner, c.sessions, clock)
    store.configure_initial(c.principal, example_config())
    store.ingest(
        c.principal, Intake(envelope=envelope("mail-browser", clock()), records=example_records())
    )
    author = BaselineAuthoring(store, SimulatedBaselineQualifier())
    draft = author.save(c.principal, SaveBaselineDraft(content=content()))
    author.publish(c.principal, PublishBaseline(baseline_id=draft.id, expected_revision=1))
    sandbox = load_sandbox(c.root / "simulation.json", c.settings.local_auth.workspace_id)
    loader = Mock(return_value=sandbox)
    facade = SimulatedLifecycleFacade(sandbox.policy)
    workflow = OrganizationWorkflows(
        store,
        policy=sandbox.policy,
        policy_loader=loader,
        facade=facade,
        enqueuer=InspectionEnqueuer(
            queue=workspace_queue(sandbox.policy.workspace_id), task=ORGANIZATION_TASK
        ),
        mail_policy=c.settings.mail_policy(),
        notifications=notifier,
    )
    worker = OrganizationLifecycleWorker(
        c.owner,
        sandbox.policy.workspace_id,
        clock,
        loader,
        facade,
        mail_policy_loader=c.settings.mail_policy,
        notifications=notifier,
    )
    prepared = SimpleNamespace(
        store=store,
        principal=c.principal,
        workflow=workflow,
        worker=worker,
        engine=c.owner,
        policy=c.settings.local_auth,
        clock=clock,
        provider=facade,
        loader=loader,
    )
    person = next(
        person
        for person in store.head(c.principal).people
        if person.email == "engineer@example.test"
    )
    _, receipt = action(prepared, person.id, "create_tenancy")
    worker.run(receipt.operation_id)
    drain(c, monkeypatch)
    with c.owner.connect() as connection:
        rows = (
            connection.execute(
                select(notification_outbox).where(
                    notification_outbox.c.workspace_id == c.settings.local_auth.workspace_id,
                    notification_outbox.c.operation_id == receipt.operation_id,
                )
            )
            .mappings()
            .all()
        )
        assert len(rows) == 1 and rows[0]["state"] == "sent" and rows[0]["attempts"] == 1
    with httpx.Client(trust_env=False, timeout=3) as client:
        capture = client.get(mail_capture.url + "/api/v1/messages").json()
        assert capture["total"] == 1
        message = capture["messages"][0]
        assert message["To"] == [{"Name": "", "Address": "capture@otm.test"}]
        body = client.get(mail_capture.url + "/api/v1/message/" + message["ID"]).json()
        assert str(receipt.operation_id) in body["Text"]
    run_browser_runtime(
        c,
        "e2e/email-delivery.spec.ts",
        {
            "OTM_E2E_EMAIL_OPERATION_ID": str(receipt.operation_id),
            "OTM_E2E_EMAIL_TEST_ADDRESS": "capture@otm.test",
            "OTM_E2E_EMAIL_EMPLOYEE_NAME": "Delegate",
        },
    )
