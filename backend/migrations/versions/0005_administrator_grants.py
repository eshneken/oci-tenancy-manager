"""Establish protected application grants and scoped revocation audit."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0005_administrator_grants"
down_revision = "0004_session_idle_policy"
branch_labels = None
depends_on = None
SQL_SHA256 = "e7a4323c3e0ecbf1588749df0aba632393f195059d0861b7a7f1ba4ca85a0584"


# Apply frozen DDL and discard only pre-grant operational sessions.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0005-administrator-grants.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Administrator grant migration is forward-only")
