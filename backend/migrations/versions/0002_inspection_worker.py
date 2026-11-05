"""Add one logical read step and typed worker audit events without rewriting existing intent."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0002_inspection_worker"
down_revision = "0001_operation_admission"
branch_labels = None
depends_on = None
SQL_SHA256 = "2923b36138d1d675dd44c4cf7430c958939b777a835817be36dcb41af1a89278"


# Apply the frozen forward migration using the caller's migration-owner transaction.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0002-inspection-worker.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve dispatch and read evidence rather than truncating history on downgrade.
def downgrade() -> None:
    raise RuntimeError("Inspection evidence migration is forward-only")
