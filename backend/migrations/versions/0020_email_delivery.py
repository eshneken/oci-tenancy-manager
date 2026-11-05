"""Durable frozen lifecycle-email intent and bounded delivery knowledge."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0020_email_delivery"
down_revision = "0019_operation_responsibility"
branch_labels = None
depends_on = None
SQL_SHA256 = "4a5508f04922c2c4250b87c6aba52ac9a6b0a567ee46d8a511620ea56b8a04bf"


# Keep historical migrations frozen and install one guarded, scoped notification outbox.
def upgrade() -> None:
    artifact = Path(__file__).resolve().parents[1] / "sql/0020-email-delivery.sql"
    content = artifact.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Email acceptance history must survive reviewed forward repair or restoration.
def downgrade() -> None:
    raise RuntimeError("Email delivery migration is forward-only")
