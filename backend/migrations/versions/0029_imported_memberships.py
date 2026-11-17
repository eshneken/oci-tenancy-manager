"""Preserve exact existing-user adoption metadata without adding a second membership registry."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0029_imported_memberships"
down_revision = "0028_signing_credentials"
branch_labels = None
depends_on = None
SQL_SHA256 = "ed2957a6f5be82bdb869381d7c56ceb32a27ddd700d652b1b93cb2d266159ff2"


# Add nullable provenance for new explicit imports; historical associations remain unadopted.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0029-imported-memberships.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Accepted identity provenance cannot be removed through an ordinary migration rollback.
def downgrade() -> None:
    raise RuntimeError("Imported membership provenance is forward-only")
