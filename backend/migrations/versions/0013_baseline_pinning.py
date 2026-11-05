"""Pin explicit baseline selection without retroactively assigning existing tenancies."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0013_baseline_pinning"
down_revision = "0012_baseline_publication"
branch_labels = None
depends_on = None
SQL_SHA256 = "09d0e906cecd7865ce4eb1bd19ebbb1f8d7c4c9899ffa3094afab7c6d2fe580c"


# Add nullable scoped selection pointers; existing operations retain their accepted snapshots.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0013-baseline-pinning.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Baseline authoring migration is forward-only")
