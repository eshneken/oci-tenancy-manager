"""Extend existing operation steps and evidence for guided local onboarding."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0010_guided_onboarding"
down_revision = "0009_organization_workflows"
branch_labels = None
depends_on = None
SQL_SHA256 = "5d6ab1f13c8fec4fc984ca40c288f5b0530f77320bef19f1b54f00aadf78fd5c"


# Add only new allowed step/evidence kinds; preserve existing work and identity history.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0010-guided-onboarding.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Organization snapshot migration is forward-only")
