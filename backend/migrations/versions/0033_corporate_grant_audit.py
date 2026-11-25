"""Distinguish corporate grants and regrants in the audit event allowlist."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0033_corporate_grant_audit"
down_revision = "0032_administrator_cleanup"
branch_labels = None
depends_on = None
SQL_SHA256 = "513384473e4de8424a443bb8d232ba9cc5167527185c4c0b20fd0a979bdb7620"


# Permit distinct new corporate grant and regrant events while preserving prior records.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0033-corporate-grant-audit.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve distinct corporate grant and regrant evidence during rollback.
def downgrade() -> None:
    raise RuntimeError("Corporate grant audit is forward-only")
