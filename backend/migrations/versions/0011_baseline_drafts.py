"""Add the scoped baseline draft recipe and immutable authoring audit evidence."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0011_baseline_drafts"
down_revision = "0010_guided_onboarding"
branch_labels = None
depends_on = None
SQL_SHA256 = "5fc226142ed58adb93f9f27c92cbd5f587793076a6db7cf545c0c0029fa9a6a7"


# Add a draft recipe without changing organizations, tenancies or published configuration.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0011-baseline-drafts.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Baseline authoring migration is forward-only")
