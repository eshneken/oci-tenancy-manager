"""Add durable organization reviews and scoped registered tenancy associations."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0009_organization_workflows"
down_revision = "0008_organization_snapshots"
branch_labels = None
depends_on = None
SQL_SHA256 = "d90923556f05c9995230b046dd9cbf2df8b3aadda9869c28f790d207c1d7d770"


# Add empty reviews/registry; do not fabricate tenancy relationships for existing employees.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0009-organization-workflows.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Organization snapshot migration is forward-only")
