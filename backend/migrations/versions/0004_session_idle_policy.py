"""Pin session idle policy without granting old rows a new authentication lifetime."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0004_session_idle_policy"
down_revision = "0003_admin_session"
branch_labels = None
depends_on = None
SQL_SHA256 = "25cc54723f46ded40426bb440ec9ac0a4a53b6c1253b85de271cba6be560c8a7"


# Apply frozen transactional DDL; existing unqualified sessions remain explicitly revoked.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0004-session-idle-policy.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve policy and revocation history through reviewed forward migration or restore procedures.
def downgrade() -> None:
    raise RuntimeError("Session idle policy migration is forward-only")
