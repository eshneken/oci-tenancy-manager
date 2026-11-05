"""Make latest publication the automatic default while preserving accepted pins."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0014_latest_baseline"
down_revision = "0013_baseline_pinning"
branch_labels = None
depends_on = None
SQL_SHA256 = "cf278fd5495825703d16c398d8fd127fb4bc17c8434e39a83f10122c4c017799"


# Invalidate old previews once; retain selection history and immutable accepted snapshots.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0014-latest-baseline.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Baseline authoring migration is forward-only")
