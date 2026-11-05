"""Add baseline-only asynchronous configuration state without changing existing assignments."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0015_configuration_updates"
down_revision = "0014_latest_baseline"
branch_labels = None
depends_on = None
SQL_SHA256 = "8a38620ca0cc4d5ba2c69f78c2ac61003c6151dfde25775436c7a3685c88edc6"


# Extend closed operation/step evidence and add nullable configuration verification facts.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0015-configuration-updates.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Baseline authoring migration is forward-only")
