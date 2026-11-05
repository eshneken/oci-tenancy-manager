"""Permit immutable audited responsibility changes for existing guided operations."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0019_operation_responsibility"
down_revision = "0018_configuration_drift"
branch_labels = None
depends_on = None
SQL_SHA256 = "6ff2c1bb07b5da28422b14fd0855dce0f47710af2688cfcf2ce9a59f276196b5"


# Extend only the closed audit kind constraint; existing provider intent and rows remain untouched.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0019-operation-responsibility.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Operation responsibility migration is forward-only")
