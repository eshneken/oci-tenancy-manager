"""Add approved recovery credential custody and immutable disclosure-window records."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0027_recovery_passwords"
down_revision = "0026_recovery_network_repair"
branch_labels = None
depends_on = None
SQL_SHA256 = "331aec3da0c8544d74c73349afc1eea528c22e4bee35ca899ad361c8fcff7c01"


# Install exact scoped records and deadline guards without modifying historical rows.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0027-recovery-passwords.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Secret exposure obligations cannot be discarded by an ordinary schema rollback.
def downgrade() -> None:
    raise RuntimeError("Recovery password history is forward-only")
