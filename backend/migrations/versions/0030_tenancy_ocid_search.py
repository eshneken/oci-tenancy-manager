"""Index the tenancy inventory OCID search."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0030_tenancy_ocid_search"
down_revision = "0029_imported_memberships"
branch_labels = None
depends_on = None
SQL_SHA256 = "dada0b2e52c6af1ab1b99cad5a65c53b0bc8b4853755ed3c9f1dc4b5581013b4"


# Add an index for OCID substring queries without rewriting tenancy records.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0030-tenancy-ocid-search.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Remove only the application index. Other database objects may use the extension.
def downgrade() -> None:
    op.drop_index("ix_tenancy_ocid_search", table_name="otm_tenancy", schema="public")
