"""Add explicit local publication metadata and immutable publication audit evidence."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0012_baseline_publication"
down_revision = "0011_baseline_drafts"
branch_labels = None
depends_on = None
SQL_SHA256 = "77f89b6bbc86cfb552d60a69292132c8751a34759ef726a137bd6c2d2bb71cb2"


# Add local publication without changing existing drafts, organizations or tenancy assignments.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0012-baseline-publication.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Baseline authoring migration is forward-only")
