"""Append immutable, read-only configuration check evidence."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0018_configuration_drift"
down_revision = "0017_membership_onboarding"
branch_labels = None
depends_on = None
SQL_SHA256 = "6f47d62be29f6dac0b3ec2390f3a5d5bef10314c713f9c4abb9400f1c5b53c5e"


# Add generated acquisition ordering and append-only check evidence without changing saved data.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0018-configuration-drift.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Configuration drift migration is forward-only")
