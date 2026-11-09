"""Persist canonical identity mappings from fresh permanent-user capture."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0023_managed_identity_bindings"
down_revision = "0022_onboarding_users"
branch_labels = None
depends_on = None
SQL_SHA256 = "911ef84b844f867bc85b2c381fd8cd23354aec7f785e24a869de513d338522c0"


# Install guarded domain/user mappings without inferring or backfilling historical identities.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0023-managed-identity-bindings.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Capture evidence must survive a forward repair or approved restore.
def downgrade() -> None:
    raise RuntimeError("Managed identity bindings are forward-only")
