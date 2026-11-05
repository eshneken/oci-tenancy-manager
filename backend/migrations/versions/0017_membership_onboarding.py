"""Extend membership cleanup and baseline onboarding evidence."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0017_membership_onboarding"
down_revision = "0016_tenancy_overrides"
branch_labels = None
depends_on = None
SQL_SHA256 = "3e90069c0221f8e8e519843918e30ebe59ea9dc651cc7cfa2e9daabca0fd2721"


# Extend closed step keys without rewriting accepted workflows or application data.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0017-membership-onboarding.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Membership onboarding migration is forward-only")
