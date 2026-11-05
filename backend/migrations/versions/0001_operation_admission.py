"""Initial scoped operation/intent storage plus the qualified native runner schema."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0001_operation_admission"
down_revision = None
branch_labels = None
depends_on = None

FILES = {
    "procrastinate-3.10.0.sql": "c70ec4b400a60ad9592787653aae5ae77ae41bf801d56b5bd2712751a07f2009",
    "0001-application.sql": "699f3fc3d4ed03c878a6f461bd67a65b093264b71f6d41d3fa092f7ca9f97996",
}


# Apply frozen reviewed SQL on the migration owner's caller-managed transaction.
def upgrade() -> None:
    folder = Path(__file__).resolve().parents[1] / "sql"
    statements = []
    for name, expected in FILES.items():
        content = (folder / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError("Frozen migration artifact changed")
        statements.append(content.decode("utf-8"))
    connection = op.get_bind()
    connection.exec_driver_sql("SET LOCAL search_path = public, pg_catalog")
    for statement in statements:
        connection.exec_driver_sql(statement, execution_options={"no_parameters": True})


# Preserve administrative history; use reviewed forward migrations or the restore runbook.
def downgrade() -> None:
    raise RuntimeError("Initial administrative-history baseline is forward-only")
