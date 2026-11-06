"""Permit permanent-user capture without rewriting earlier onboarding operations."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0022_onboarding_users"
down_revision = "0021_financial_collection"
branch_labels = None
depends_on = None
SQL_SHA256 = "0365d01790d92e662b3477db55ce384d3e7647a75bb59490876609309e297173"


# Widen only the step allowlist; preserve stored rows, privileges and frozen earlier artifacts.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0022-onboarding-users.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Capture evidence must survive a forward repair or approved restore.
def downgrade() -> None:
    raise RuntimeError("Onboarding identity migration is forward-only")
