"""Persist explicit presence check attempts/results from opted-in fresh captures."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0025_user_presence_checks"
down_revision = "0024_user_presence_connections"
branch_labels = None
depends_on = None
SQL_SHA256 = "253c7dfc794e1c5722b984666803427f21c80bb44d9bb399f49ed1ea2738060b"


# Install scoped check attempts/results without backfilling historical identity evidence.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0025-user-presence-checks.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Capture evidence must survive a forward repair or approved restore.
def downgrade() -> None:
    raise RuntimeError("Simulated presence connections are forward-only")
