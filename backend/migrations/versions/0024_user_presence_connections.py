"""Persist explicit simulated read connections from opted-in fresh captures."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0024_user_presence_connections"
down_revision = "0023_managed_identity_bindings"
branch_labels = None
depends_on = None
SQL_SHA256 = "fdca14b8e766d8da61944565cb23d7312402680d39a738a897ba2751b0381d07"


# Install scoped simulated connections without inferring or backfilling historical identities.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0024-user-presence-connections.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Capture evidence must survive a forward repair or approved restore.
def downgrade() -> None:
    raise RuntimeError("Simulated presence connections are forward-only")
