"""Add immutable authored configurations and staged override reviews."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0016_tenancy_overrides"
down_revision = "0015_configuration_updates"
branch_labels = None
depends_on = None
SQL_SHA256 = "fc245112049bc0656eecebe6343fc2fe614afff489384fbb59abc1a39c348357"


# Add immutable override revisions, staged reviews and nullable configuration heads.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0016-tenancy-overrides.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Tenancy override migration is forward-only")
