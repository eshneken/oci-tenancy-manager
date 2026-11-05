"""Add immutable scoped organization snapshots with sealed current/proposed views."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0008_organization_snapshots"
down_revision = "0007_audit_export"
branch_labels = None
depends_on = None
SQL_SHA256 = "9d58d6479bbb1df7dd486bbfc6b6c65b24e11b50777c12215bf33375daf84c70"


# Create empty organization storage; no employees, credentials or memberships are seeded.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0008-organization-snapshots.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Organization snapshot migration is forward-only")
