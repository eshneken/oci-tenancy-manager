"""Record completed OCI group cleanup on revoked administrator grants."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0032_administrator_cleanup"
down_revision = "0031_corporate_sign_in"
branch_labels = None
depends_on = None
SQL_SHA256 = "e9285db0e9af6ec71a026021b14325a01b6ff3d3788d1396a6309fa7c54970be"


# Add a conservative cleanup receipt without modifying existing grants or audit records.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0032-administrator-cleanup.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve cleanup receipts during rollback and require forward recovery.
def downgrade() -> None:
    raise RuntimeError("Administrator cleanup receipts are forward-only")
