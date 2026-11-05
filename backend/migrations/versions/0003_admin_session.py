"""Add server-side session metadata without a token issuance or login endpoint."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0003_admin_session"
down_revision = "0002_inspection_worker"
branch_labels = None
depends_on = None
SQL_SHA256 = "c26bd67ada1d6dbd2b7180b79b2b1caed92255ce77825ac3713f9b74a31cdbf8"


# Apply frozen session metadata DDL using the caller-owned migration transaction.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0003-admin-session.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Use reviewed forward changes or restore rather than accidentally reactivating sessions.
def downgrade() -> None:
    raise RuntimeError("Session metadata migration is forward-only")
