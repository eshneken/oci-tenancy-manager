"""Extend existing durable records for conditional recovery-perimeter repair."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0026_recovery_network_repair"
down_revision = "0025_user_presence_checks"
branch_labels = None
depends_on = None
SQL_SHA256 = "b4864a4762d376d8457de52dd84a1e74cf9edfd0630d2a3ce375f6d984ab6148"


# Extend closed operation/event/step constraints without rewriting historical evidence or rows.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0026-recovery-network-repair.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Security-change evidence survives forward fixes; rollback uses the owned restore procedure.
def downgrade() -> None:
    raise RuntimeError("Recovery network repair is forward-only")
