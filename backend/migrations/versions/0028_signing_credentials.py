"""Add independent exact-version automation signing-credential heads and existing job evidence."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0028_signing_credentials"
down_revision = "0027_recovery_passwords"
branch_labels = None
depends_on = None
SQL_SHA256 = "d5895716c62ba4d0a3892598ff4a6ceed954cba79f0c363cc0b78271fa228f3e"


# Install source-bound heads without adopting existing inventory or changing historical connections.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0028-signing-credentials.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Rotation history and retirement obligations cannot be discarded through an ordinary rollback.
def downgrade() -> None:
    raise RuntimeError("Signing credentials are forward-only")
