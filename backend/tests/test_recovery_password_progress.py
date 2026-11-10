"""Original-window safe operation projections without secret retrieval or mutable-head reads."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_recovery_password_custody import custody
from test_recovery_password_units import NOW, password_case

from otm.operations.views import RecoveryPasswordProgress
from otm.storage.operation_directory import password_progress

__all__ = ["custody", "password_case"]


# Only explicitly scoped immutable grants can provide original-window progress.
def test_original_progress_projection(password_case):
    c = password_case
    connection = Mock()
    first = c.intent.due_at - timedelta(hours=4)
    connection.execute.return_value.one.return_value = (
        2,
        first,
        first,
        c.intent.due_at,
        c.intent.due_at,
    )
    result = password_progress(connection, c.row, c.intent)
    assert result.request_count == 2 and result.first_request_at == first
    assert result.rotation_due_at == c.intent.due_at
    assert result.tenancy_id == c.intent.location.target.tenancy_id
    statement = connection.execute.call_args.args[0]
    assert set(statement.compile().params.values()) >= {
        c.row["workspace_id"],
        c.row["id"],
        c.intent.credential_id,
        c.intent.location.target.tenancy_id,
        c.intent.exposure_generation,
    }
    for name in (
        "workspace_id",
        "accepted_operation_id",
        "credential_id",
        "tenancy_id",
        "exposure_generation",
    ):
        assert name in str(statement)
    assert "reference" not in result.model_dump_json() and "version" not in result.model_dump_json()


# Setup is distinct from exposure and needs neither a grant query nor an invented clock.
def test_preparation_progress_has_no_window(password_case):
    c = password_case
    intent = c.intent.model_copy(update={"phase": "setup", "due_at": None})
    connection = Mock()
    result = password_progress(connection, c.row, intent)
    assert result.phase == "setup" and result.request_count == 0
    assert result.first_request_at is None and result.rotation_due_at is None
    connection.execute.assert_not_called()
    with pytest.raises(ValueError, match="INVALID_RECOVERY_PROGRESS"):
        password_progress(connection, c.row, SimpleNamespace(kind="inspect_import"))


# Missing, divergent or extended original records fail closed rather than borrowing current state.
@pytest.mark.parametrize("damage", ["missing", "first", "due", "duration"])
def test_inconsistent_progress_is_unavailable(password_case, damage):
    c = password_case
    first = NOW - timedelta(hours=4)
    values = (1, first, first, NOW, NOW)
    values = {
        "missing": (0, None, None, None, None),
        "first": (1, first, first + timedelta(seconds=1), NOW, NOW),
        "due": (1, first, first, NOW, NOW + timedelta(seconds=1)),
        "duration": (1, first + timedelta(seconds=1), first + timedelta(seconds=1), NOW, NOW),
    }[damage]
    connection = Mock()
    connection.execute.return_value.one.return_value = values
    with pytest.raises(ValueError, match="INVALID_RECOVERY_PROGRESS"):
        password_progress(connection, c.row, c.intent)


# Public metadata rejects setup exposures and rotations without an original window.
@pytest.mark.parametrize(
    "phase,first,due,count",
    [
        ("setup", NOW, None, 0),
        ("setup", None, NOW, 0),
        ("setup", None, None, 1),
        ("rotation", None, NOW, 1),
        ("rotation", NOW, None, 1),
        ("rotation", NOW, NOW, 0),
    ],
)
def test_progress_contract_rejects_invented_windows(password_case, phase, first, due, count):
    c = password_case
    with pytest.raises(ValueError, match="INVALID_RECOVERY_PROGRESS"):
        RecoveryPasswordProgress(
            phase=phase,
            tenancy_id=c.child["id"],
            user_name="otm-recovery",
            first_request_at=first,
            rotation_due_at=due,
            request_count=count,
        )
