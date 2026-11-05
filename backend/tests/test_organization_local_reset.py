"""Operator reset safeguards and transaction ownership, independent of a live database."""

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from test_local_development import local_state

from otm.organization.local_reset import TABLES, clear_organization, reset_test_organization
from otm.settings import load_settings

__all__ = ["local_state"]


# Use explicit local settings and synthetic labeled-container metadata, never saved credentials.
def reset_case(local_state):
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    settings = settings.model_copy(
        update={
            "local_server": settings.local_server.model_copy(
                update={"organization_reset_enabled": True}
            )
        }
    )
    info = {
        "Config": {"Labels": {"otm.local.instance": str(local_state.instance_id)}},
        "State": {"Running": True},
        "NetworkSettings": {
            "Ports": {
                "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(local_state.database_port)}]
            }
        },
    }
    return settings, info


# Missing opt-in, confirmation or loopback identity must fail before inspection or owner access.
@pytest.mark.parametrize("damage", ["confirm", "disabled", "server", "auth", "remote"])
def test_reset_requires_explicit_local_authority(local_state, damage):
    settings, info = reset_case(local_state)
    if damage == "disabled":
        settings = settings.model_copy(
            update={
                "local_server": settings.local_server.model_copy(
                    update={"organization_reset_enabled": False}
                )
            }
        )
    elif damage in {"server", "auth"}:
        settings = settings.model_copy(
            update={"local_server" if damage == "server" else "local_auth": None}
        )
    elif damage == "remote":
        settings = settings.model_copy(
            update={
                "local_server": settings.local_server.model_copy(
                    update={"public_origin": "https://remote.example.test"}
                )
            }
        )
    inspect = Mock(return_value=json.dumps([info]))
    with (
        patch("otm.organization.local_reset.maintenance_engine") as engine,
        pytest.raises(ValueError),
    ):
        reset_test_organization(
            local_state,
            settings,
            confirmed=damage != "confirm",
            inspect=inspect,
            database_url=Mock(),
        )
    inspect.assert_not_called()
    engine.assert_not_called()


# Do not connect to a different installation, stopped database, exposed port or stale saved port.
@pytest.mark.parametrize("damage", ["label", "stopped", "public", "port", "multiple"])
def test_reset_verifies_container_before_connect(local_state, damage):
    settings, info = reset_case(local_state)
    port = info["NetworkSettings"]["Ports"]["5432/tcp"][0]
    if damage == "label":
        info["Config"]["Labels"]["otm.local.instance"] = str(uuid4())
    elif damage == "stopped":
        info["State"]["Running"] = False
    elif damage == "public":
        port["HostIp"] = "0.0.0.0"
    elif damage == "port":
        port["HostPort"] = "1"
    else:
        info["NetworkSettings"]["Ports"]["5432/tcp"].append(dict(port))
    with (
        patch("otm.organization.local_reset.maintenance_engine") as engine,
        pytest.raises(ValueError),
    ):
        reset_test_organization(
            local_state,
            settings,
            confirmed=True,
            inspect=Mock(return_value=json.dumps([info])),
            database_url=Mock(),
        )
    engine.assert_not_called()


# Guard changes stay in one transaction; dispose after either success or failure.
@pytest.mark.parametrize("failure", [False, True])
def test_reset_owns_transaction_and_disposes(local_state, failure):
    settings, info = reset_case(local_state)
    connection, engine = Mock(), Mock()
    engine.begin.return_value = nullcontext(connection)
    with (
        patch("otm.organization.local_reset.maintenance_engine", return_value=engine),
        patch(
            "otm.organization.local_reset.clear_organization",
            side_effect=RuntimeError("synthetic") if failure else None,
            return_value={"org_feed": 2},
        ),
    ):
        if failure:
            with pytest.raises(RuntimeError):
                reset_test_organization(
                    local_state,
                    settings,
                    confirmed=True,
                    inspect=Mock(return_value=json.dumps([info])),
                    database_url=Mock(),
                )
        else:
            assert reset_test_organization(
                local_state,
                settings,
                confirmed=True,
                inspect=Mock(return_value=json.dumps([info])),
                database_url=Mock(),
            ) == {"org_feed": 2}
    engine.dispose.assert_called_once()


# Future schema, wrong database and foreign scopes are refused before any trigger changes.
@pytest.mark.parametrize(
    "damage", ["database", "tables", "foreign", "issuer", "pending", "real", "email", "none"]
)
def test_clear_requires_exact_owned_scope_and_preserves_other_tables(damage):
    import psycopg

    connection = Mock()
    connection.in_transaction.return_value = True
    connection.get_isolation_level.return_value = "READ COMMITTED"
    connection.connection.driver_connection = Mock(spec=psycopg.Connection, autocommit=False)
    connection.scalar.side_effect = [
        damage != "database",
        damage == "foreign",
        damage != "issuer",
        damage == "pending",
        damage == "real",
        damage == "email",
        *([2] * len(TABLES)),
    ]
    connection.scalars.return_value = (
        (*TABLES, "otm_tenancy_unreviewed") if damage == "tables" else TABLES
    )
    if damage == "none":
        assert clear_organization(connection, "example-org", "urn:synthetic") == dict.fromkeys(
            TABLES, 2
        )
        statements = [call.args[0] for call in connection.exec_driver_sql.call_args_list]
        assert len([s for s in statements if "DISABLE TRIGGER" in s]) == len(TABLES)
        assert len([s for s in statements if "ENABLE TRIGGER" in s]) == len(TABLES)
        assert not any(
            "CASCADE" in s or "audit_event" in s or "DISABLE TRIGGER ALL" in s for s in statements
        )
    else:
        with pytest.raises(ValueError):
            clear_organization(connection, "example-org", "urn:synthetic")
        assert not any(
            "DISABLE" in call.args[0] for call in connection.exec_driver_sql.call_args_list
        )


# The explicit CLI flag is mandatory and the owner command never falls through to HTTPS startup.
def test_reset_cli_dispatch_and_safe_failure(tmp_path, local_state):
    from otm import local_development as local

    settings, info = reset_case(local_state)
    with (
        patch.object(Path, "cwd", return_value=Path(__file__).resolve().parents[2]),
        patch.object(local, "DirectorySecrets"),
        patch.object(local, "read_state", return_value=local_state),
        patch.object(local, "load_settings", return_value=settings),
        patch.object(local, "run", return_value=SimpleNamespace(stdout=json.dumps([info]))),
        patch.object(local, "docker", return_value="docker"),
        patch("otm.organization.local_reset.reset_test_organization", return_value={}) as reset,
    ):
        assert (
            local.main(
                ["reset-organization", "--directory", str(tmp_path), "--confirm-reset-organization"]
            )
            == 0
        )
        assert reset.call_args.kwargs["confirmed"]
        assert reset.call_args.kwargs["inspect"]("synthetic-name") == json.dumps([info])
        reset.side_effect = ValueError("not enabled")
        assert local.main(["reset-organization", "--directory", str(tmp_path)]) == 1


# A direct unsafe helper call fails before locks, trigger changes or truncation.
def test_reset_refuses_nontransactional_connection():
    connection = Mock()
    connection.in_transaction.return_value = False
    with pytest.raises(RuntimeError, match="ACTIVE_READ_COMMITTED"):
        clear_organization(connection, "example-org", "urn:synthetic")
    connection.exec_driver_sql.assert_not_called()
