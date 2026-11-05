"""Real factor/custody primitives and unit transaction orchestration; SQL proofs are separate."""

import hashlib
import os
import secrets
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pyotp
import pytest
from pydantic import SecretStr
from test_administrators import grant
from test_admission_service import NOW

from otm.auth.local import LocalAuthFailure, LocalLogin, LocalSignIn, password_verifier, totp_step
from otm.operations.contracts import ActorIdentity
from otm.secrets.directory import DirectorySecrets
from otm.settings import load_settings
from otm.storage.local_auth import SqlLocalAuth


# Keep synthetic factor fixtures out of assertion/context representations and retained reports.
@dataclass
class SyntheticFactors:
    password: str = field(repr=False)
    verifier: str = field(repr=False)
    seed: str = field(repr=False)


# Use a single real random verifier across cases; never reduce production hash parameters for tests.
@pytest.fixture(scope="module")
def factors():
    password = secrets.token_urlsafe(24)
    seed = pyotp.random_base32()
    return SyntheticFactors(password=password, verifier=password_verifier(password), seed=seed)


# Model scoped SQL results while exercising real factor verification and service branching.
@pytest.fixture
def local_case(factors):
    settings = load_settings(Path(__file__).resolve().parents[1] / "config/application.toml")
    row = grant(
        local=True, workspace_id=settings.local_auth.workspace_id, issuer=settings.local_auth.issuer
    )
    credential = dict(
        workspace_id=row.workspace_id,
        administrator_id=row.id,
        password_hash=factors.verifier,
        totp_secret_reference="synthetic:version-1",
        last_totp_step=int(NOW.timestamp()) // 30 - 1,
        mfa_enrolled_at=NOW - timedelta(minutes=1),
        password_changed_at=NOW - timedelta(minutes=1),
        failed_attempts=0,
        failure_window_started_at=None,
        retry_after=None,
    )
    connection = MagicMock()
    engine = Mock(
        connect=Mock(return_value=nullcontext(connection)),
        begin=Mock(return_value=nullcontext(connection)),
    )
    clock = Mock(return_value=NOW)
    repository = SqlLocalAuth(engine, settings, clock)
    writes = []

    # Return data by queried table, keeping captured writes independent of the service's result.
    def execute(statement):
        result = MagicMock()
        if statement.is_select:
            name = statement.get_final_froms()[0].name
            result.mappings.return_value.one_or_none.return_value = (
                row.model_dump() if name == "otm_administrator" else credential.copy()
            )
        else:
            writes.append(statement)
            result.rowcount = 1
        return result

    connection.execute.side_effect = execute
    connection.exec_driver_sql.return_value.one.return_value = (True, "test_operator")
    custody = Mock(get=Mock(return_value=factors.seed))
    service = LocalLogin(settings, repository, custody)
    command = LocalSignIn(
        username="recovery-admin",
        password=factors.password,
        totp_code=pyotp.TOTP(factors.seed).at(NOW),
    )
    return SimpleNamespace(
        settings=settings,
        row=row,
        credential=credential,
        connection=connection,
        engine=engine,
        clock=clock,
        repository=repository,
        service=service,
        command=command,
        custody=custody,
        writes=writes,
        factors=factors,
    )


# Both operator and login composition fail closed without explicit local identity configuration.
def test_local_auth_requires_explicit_configuration(local_case):
    c = local_case
    settings = c.settings.model_copy(update={"local_auth": None})
    with pytest.raises(ValueError):
        SqlLocalAuth(c.engine, settings, c.clock)
    with pytest.raises(ValueError):
        LocalLogin(settings, c.repository, c.custody)


# Reject invalid bootstrap passphrases without truncation or silently changing Unicode.
@pytest.mark.parametrize("password", [None, "short", "x" * 129])
def test_operator_password_bounds(password):
    with pytest.raises(LocalAuthFailure) as error:
        password_verifier(password)
    assert error.value.code == "INVALID_LOCAL_CREDENTIALS"


# Handle adjacent-counter collisions using library verification without custom OTP cryptography.
def test_totp_consumes_greatest_colliding_counter():
    generator = Mock(timecode=Mock(return_value=100), verify=Mock(return_value=True))
    with patch("otm.auth.local.pyotp.TOTP", return_value=generator):
        assert totp_step("A" * 32, "123456", NOW, 99) == 101
        assert totp_step("A" * 32, "123456", NOW, 101) is None


# Bad factors and already consumed codes cannot become a valid proof.
def test_real_totp_rejects_invalid_and_replayed_factors(factors):
    generator = pyotp.TOTP(factors.seed)
    code = generator.at(NOW)
    step = totp_step(factors.seed, code, NOW, -1)
    assert step is not None and totp_step(factors.seed, code, NOW, step) is None
    assert totp_step("bad", code, NOW, -1) is None
    assert totp_step(factors.seed, "x" * 6, NOW, -1) is None


# A real verified proof creates only hashed session metadata and a nonsecret success event.
def test_login_success_stores_digest_only_and_pins_settings(local_case):
    c = local_case
    with patch("otm.storage.local_auth.require_transaction"):
        result = c.service.sign_in(c.command, "a" * 43)
    assert result.session.entitlement_revision == c.row.authorization_revision
    assert result.session.expires_at == NOW + timedelta(hours=8)
    assert (
        result.session.session_token_hash
        == hashlib.sha256(result.handle.get_secret_value().encode()).hexdigest()
    )
    assert result.handle.get_secret_value() not in repr(result)
    assert any(statement.table.name == "audit_event" for statement in c.writes)


# All bad credentials get the same outcome, while unavailable custody remains a fixed outage.
@pytest.mark.parametrize(
    "damage", ["password", "username", "code", "custody", "missing", "capacity", "invalid_hash"]
)
def test_login_failures_do_not_issue_or_expose_credentials(local_case, damage):
    c = local_case
    changes = {}
    if damage == "password":
        changes["password"] = SecretStr("wrong synthetic password")
    if damage == "username":
        changes["username"] = "unknown"
    if damage == "code":
        changes["totp_code"] = SecretStr("x" * 6)
    if damage == "custody":
        c.custody.get.side_effect = RuntimeError("private custody error")
    if damage == "missing":
        c.repository.material = Mock(return_value=None)
    if damage == "capacity":
        c.service.capacity = Mock(acquire=Mock(return_value=False))
    if damage == "invalid_hash":
        c.credential["password_hash"] = "invalid"
    with (
        patch("otm.storage.local_auth.require_transaction"),
        pytest.raises(LocalAuthFailure) as error,
    ):
        c.service.sign_in(c.command.model_copy(update=changes))
    assert error.value.status == (503 if damage in {"custody", "capacity", "invalid_hash"} else 401)
    assert c.factors.password not in str(error.value)
    assert not any(statement.table.name == "otm_admin_session" for statement in c.writes)


# Shared cooldown attempts cannot prolong the deadline or emit an event per rejected request.
def test_cooldown_and_failure_windows_are_bounded(local_case):
    c = local_case
    c.credential.update(
        failed_attempts=5, failure_window_started_at=NOW, retry_after=NOW + timedelta(seconds=60)
    )
    with patch("otm.storage.local_auth.require_transaction"), pytest.raises(LocalAuthFailure):
        c.service.sign_in(c.command)
    assert not c.writes
    c.credential.update(retry_after=NOW - timedelta(seconds=1))
    with patch("otm.storage.local_auth.require_transaction"), pytest.raises(LocalAuthFailure):
        c.service.sign_in(c.command.model_copy(update={"password": SecretStr("wrong password")}))
    assert len(c.writes) == 2


# Final factor checks must use the currently locked credential revision and immutable reference.
@pytest.mark.parametrize("change", ["revision", "reference", "missing_grant", "missing_credential"])
def test_changed_proof_dependencies_are_rejected(local_case, change):
    c = local_case
    material = c.repository.material()
    if change == "revision":
        material = (material[0].model_copy(update={"authorization_revision": uuid4()}), material[1])
    if change == "reference":
        material[1]["totp_secret_reference"] = "different-version"
    if change.startswith("missing"):
        previous = c.connection.execute.side_effect

        # Make absence visible only at the selected final locked row.
        def execute(statement):
            result = previous(statement)
            if statement.is_select and statement.get_final_froms()[0].name == (
                "otm_administrator" if change == "missing_grant" else "otm_local_credential"
            ):
                result.mappings.return_value.one_or_none.return_value = None
            return result

        c.connection.execute.side_effect = execute
    with patch("otm.storage.local_auth.require_transaction"), pytest.raises(LocalAuthFailure):
        c.repository.finish(
            material, True, c.factors.seed, c.command.totp_code.get_secret_value(), None
        )
    assert not c.writes


# A missing credential row is unavailable rather than a password-only local login path.
def test_material_requires_complete_enrollment(local_case):
    c = local_case
    previous = c.connection.execute.side_effect

    # Return a protected grant but no credential from the read query.
    def execute(statement):
        result = previous(statement)
        if statement.is_select and statement.get_final_froms()[0].name == "otm_local_credential":
            result.mappings.return_value.one_or_none.return_value = None
        return result

    c.connection.execute.side_effect = execute
    with pytest.raises(ValueError, match="LOCAL_CREDENTIAL_UNAVAILABLE"):
        c.repository.material()


# Operator role verification is tied to the actual database connection, not arbitrary attribution.
def test_operator_role_and_one_time_status(local_case):
    c = local_case
    with pytest.raises(LocalAuthFailure) as error:
        c.repository.operator_status()
    assert error.value.code == "LOCAL_ADMINISTRATOR_ALREADY_INITIALIZED"
    existing, actor = c.repository.operator_status(reset=True)
    assert existing.id == c.row.id and actor.subject == "test_operator"
    c.connection.exec_driver_sql.return_value.one.return_value = (False, "not_operator")
    with pytest.raises(LocalAuthFailure) as error:
        c.repository.operator_status()
    assert error.value.code == "OPERATOR_PRIVILEGES_REQUIRED"
    c.connection.exec_driver_sql.return_value.one.return_value = (True, "test_operator")
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    c.connection.execute.side_effect = None
    assert c.repository.operator_status()[0] is None
    with pytest.raises(LocalAuthFailure):
        c.repository.operator_status(reset=True)


# Reset requires the exact original grant revision and a real changed credential row.
@pytest.mark.parametrize(
    "damage", ["none", "revision", "missing_row", "operator", "bootstrap_again"]
)
def test_operator_enroll_and_reset_guards(local_case, damage):
    c = local_case
    actor = ActorIdentity(issuer="urn:otm:database-operator", subject="test_operator")
    expected = c.row
    if damage == "revision":
        expected = expected.model_copy(update={"authorization_revision": uuid4()})
    if damage == "operator":
        actor = actor.model_copy(update={"subject": "forged"})
    if damage == "bootstrap_again":
        expected = None
    if damage == "missing_row":
        previous = c.connection.execute.side_effect

        # Simulate zero affected rows without pretending this proves database concurrency.
        def execute(statement):
            result = previous(statement)
            result.rowcount = 0
            return result

        c.connection.execute.side_effect = execute
    with patch("otm.storage.local_auth.require_transaction"):
        if damage == "none":
            assert (
                c.repository.enroll(c.factors.verifier, "synthetic:next", 100, actor, expected)
                == c.row.id
            )
        else:
            with pytest.raises(LocalAuthFailure):
                c.repository.enroll(c.factors.verifier, "synthetic:next", 100, actor, expected)


# First enrollment inserts grant and credential atomically, after the operator/enrollment proof.
def test_initial_enrollment_has_no_preexisting_identity(local_case):
    c = local_case
    c.connection.execute.side_effect = None
    c.connection.execute.return_value.mappings.return_value.one_or_none.return_value = None
    actor = ActorIdentity(issuer="urn:otm:database-operator", subject="test_operator")
    with patch("otm.storage.local_auth.require_transaction"):
        assert c.repository.enroll(c.factors.verifier, "synthetic:version", 100, actor) is not None


# Never allow arbitrary exception text to become a public authentication diagnostic.
def test_local_failure_allowlist():
    with pytest.raises(ValueError):
        LocalAuthFailure(500, "private-value")


# Immutable custody remains exactly owner-readable under even a maximally restrictive umask.
def test_local_secret_permissions_immutability_and_retrieval(tmp_path):
    root = tmp_path / "custody"
    root.mkdir(mode=0o700)
    custody = DirectorySecrets(root)
    previous = os.umask(0o777)
    try:
        reference = custody.put(pyotp.random_base32())
    finally:
        os.umask(previous)
    seed = custody.get(reference)
    assert len(seed) == 32 and len(custody.put(seed)) > 0 and len(list(root.iterdir())) == 2
    path = root / reference.split(":")[1]
    path.chmod(0o644)
    with pytest.raises(ValueError):
        custody.get(reference)
    path.chmod(0o600)
    os.link(path, root / "hardlink")
    with pytest.raises(ValueError):
        custody.get(reference)


# Path traversal, symlinks, loose directories and malformed material cannot redirect custody.
def test_local_secret_rejects_unsafe_files_and_paths(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    custody = DirectorySecrets(root)
    with pytest.raises(ValueError):
        DirectorySecrets(Path("relative"))
    root.chmod(0o755)
    with pytest.raises(ValueError):
        DirectorySecrets(root)
    root.chmod(0o700)
    link = tmp_path / "linked"
    link.symlink_to(root)
    with pytest.raises(OSError):
        DirectorySecrets(link)
    for value in ("bad", "../escape", "local-secret:../../escape"):
        with pytest.raises(ValueError):
            custody.get(value)
    with pytest.raises(ValueError):
        custody.put("bad")
    reference = custody.put(pyotp.random_base32())
    path = root / reference.split(":")[1]
    path.write_text(pyotp.random_base32())
    with pytest.raises(ValueError, match="MFA_SECRET_CONTENT_CHANGED"):
        custody.get(reference)
    path.write_text("invalid")
    with pytest.raises(ValueError):
        custody.get(reference)
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(OSError):
        custody.get(reference)
