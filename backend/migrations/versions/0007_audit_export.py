"""Add closed audit export preparation kind without changing existing event ownership."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0007_audit_export"
down_revision = "0006_local_authentication"
branch_labels = None
depends_on = None
SQL_SHA256 = "ba93ef5849ada6cfc4abb63dc04e08fd7e0c1cc36ead275a59d53b1229ae3edc"


# Expand the closed export event family; no activity or credentials are seeded.
def upgrade() -> None:
    content = (Path(__file__).resolve().parents[1] / "sql/0007-audit-export.sql").read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Audit export migration is forward-only")
