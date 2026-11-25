"""Allow a closed audit event for a committed Atlas corporate session."""

import hashlib
from pathlib import Path

from alembic import op

revision = "0031_corporate_sign_in"
down_revision = "0030_tenancy_ocid_search"
branch_labels = None
depends_on = None
SQL_SHA256 = "49cc71b64df9e210a7b56c13dee22fa1d3b8878c6501904f4abdc183c736ffc2"


# Extend the security event allowlist without rewriting existing audit history.
def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0031-corporate-sign-in.sql"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SQL_SHA256:
        raise RuntimeError("Frozen migration artifact changed")
    op.get_bind().exec_driver_sql(content.decode(), execution_options={"no_parameters": True})


# Preserve immutable corporate audit rows and require a forward-compatible recovery.
def downgrade() -> None:
    raise RuntimeError("Corporate session audit is forward-only")
