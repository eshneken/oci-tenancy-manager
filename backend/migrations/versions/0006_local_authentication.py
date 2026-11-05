"""Add closed local authentication audit kinds without changing existing event ownership."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0006_local_authentication"
down_revision = "0005_administrator_grants"
branch_labels = None
depends_on = None
SQL_SHA256 = "0c6e885be08820ac2443c44b83817ed5dce7b7bf9169ec1cb0921444f02635bd"


# Expand the closed auth event family; no credentials or sessions are seeded.
def upgrade() -> None:
    content = (
        Path(__file__).resolve().parents[1] / "sql/0006-local-authentication.sql"
    ).read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve administrator authority/history through reviewed forward migration or restore.
def downgrade() -> None:
    raise RuntimeError("Local authentication migration is forward-only")
