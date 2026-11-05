"""Current-cycle financial collection and immutable observations."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0021_financial_collection"
down_revision = "0020_email_delivery"
branch_labels = None
depends_on = None
SQL_SHA256 = "8d8df5395cb09921e37358bf858b384e73526a0c6041aac9492075246c050fd5"


# Keep historical migrations frozen and install guarded financial collection/observation tables.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0021-financial-collection.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Financial acquisition history must survive reviewed forward repair or restoration.
def downgrade() -> None:
    raise RuntimeError("Financial collection migration is forward-only")
