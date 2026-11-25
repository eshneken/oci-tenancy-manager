"""Prove corporate session and audit writes share the same reauthorized transaction."""

import hashlib
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_administrators import grant
from test_admission_service import NOW

from otm.auth.contracts import AdminEntitlement
from otm.auth.corporate_enrollment import EnrollmentTarget
from otm.auth.corporate_oidc import VerifiedDomainLogin
from otm.settings import load_settings
from otm.storage.corporate_sessions import SqlCorporateSessions


# Recheck the committed grant under the recovery lock before writing a session and audit.
@pytest.mark.parametrize(
    "fault", [None, "wrong_group", "missing_anchor", "changed_grant", "expiry", "audit"]
)
def test_session_issuance_shares_the_locked_grant_and_closed_audit(fault):
    workspace = "development"
    row = grant(workspace_id=workspace, subject="a" * 32)
    target = EnrollmentTarget(
        environment="development",
        workspace=workspace,
        issuer=row.issuer,
        domain="domain",
        app="b" * 32,
        group="c" * 32,
    )
    verified = VerifiedDomainLogin(
        guid=row.subject, group="d" * 32 if fault == "wrong_group" else target.group
    )
    entitlement = AdminEntitlement(
        workspace_id=workspace,
        issuer=row.issuer,
        subject=verified.guid,
        reference=str(row.id),
        revision=row.authorization_revision,
        checked_at=NOW,
        valid_until=NOW + timedelta(seconds=1),
    )
    connection = Mock()
    connection.execute.return_value.scalar_one_or_none.return_value = (
        None if fault == "missing_anchor" else "protected"
    )
    store = Mock()
    store.engine.begin.return_value = nullcontext(connection)
    store._grant.return_value = row
    authority = Mock(target=target, grants=store, require_admin=Mock(return_value=entitlement))
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    issuer = SqlCorporateSessions(
        authority, settings.sessions, lambda: NOW + timedelta(seconds=(fault == "expiry"))
    )
    if fault == "changed_grant":
        authority.require_admin.return_value = entitlement.model_copy(update={"reference": "other"})
    if fault == "audit":
        connection.execute.side_effect = [
            Mock(scalar_one_or_none=Mock(return_value="protected")),
            Mock(),
            RuntimeError(),
        ]
    if fault == "audit":
        with pytest.raises(RuntimeError):
            issuer.issue(verified)
    elif fault:
        with pytest.raises(PermissionError):
            issuer.issue(verified)
        assert connection.execute.call_count == (0 if fault == "wrong_group" else 1)
    else:
        issued = issuer.issue(verified)
        assert (
            issued.session.session_token_hash
            == hashlib.sha256(issued.handle.get_secret_value().encode()).hexdigest()
        )
        assert connection.execute.call_count == 3
        statements = str(connection.execute.call_args.args[0])
        assert "audit_event" in statements
        assert issued.handle.get_secret_value() not in statements
