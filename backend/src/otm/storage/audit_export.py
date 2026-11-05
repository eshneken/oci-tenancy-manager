"""Bounded, redacted CSV preparation with immutable evidence committed before disclosure."""

import csv
import json
from collections.abc import Callable
from datetime import UTC, datetime
from io import StringIO
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.engine import Engine

from otm.audit.contracts import AuditExportEvidence, AuditExportQuery
from otm.auth.service import AdminPrincipal, SessionFailure
from otm.contracts import UtcInstant
from otm.operations.contracts import canonical_hash
from otm.storage.admin_authority import authorize_administrator as authorize_export
from otm.storage.audit_directory import entry, selection
from otm.storage.tables import administrator, audit_event

MAX_EXPORT_ROWS = 10_000
CSV_FIELDS = (
    "id",
    "at",
    "kind",
    "category",
    "actor_name",
    "operation_id",
    "administrator_id",
    "administrator_name",
    "safe_code",
    "organization_subject_name",
    "summary",
    "changes",
)


# Carry a fixed public limit diagnostic without attaching data or SQL to the error.
class AuditExportTooLarge(ValueError):
    pass


# Quoting alone does not prevent spreadsheet formulas; neutralize executable/control-led cells.
def csv_cell(value):
    if value is None:
        return ""
    text = (
        value.isoformat()
        if isinstance(value, datetime)
        else json.dumps(value, ensure_ascii=False)
        if isinstance(value, (tuple, list))
        else str(value)
    )
    significant = text.lstrip(" \t\r\n\v\f\ufeff")
    if significant.startswith(("=", "+", "-", "@")) or any(ord(c) < 32 for c in text):
        return "'" + text
    return text


# Emit only the public projection, with stable columns and lossless CSV quoting for ordinary text.
def csv_document(rows):
    stream = StringIO(newline="")
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    writer.writerow(CSV_FIELDS)
    for row in rows:
        values = entry(row).model_dump()
        writer.writerow([csv_cell(values[name]) for name in CSV_FIELDS])
    return stream.getvalue().encode("utf-8-sig")


# Read a complete bounded snapshot and commit a preparation record before returning any CSV bytes.
class SqlAuditExport:
    # The injected clock is server-owned; callers cannot select time, workspace or output paths.
    def __init__(self, engine: Engine, clock: Callable[[], datetime] | None = None):
        self.engine = engine
        self.clock = clock or (lambda: datetime.now(UTC))

    # No partial file escapes on a limit, malformed evidence, authorization loss or failed commit.
    def export(self, principal: object, query: AuditExportQuery) -> bytes:
        if not isinstance(principal, AdminPrincipal):
            raise SessionFailure(403, "ADMINISTRATOR_REQUIRED")
        query = AuditExportQuery.model_validate(query)
        workspace = principal.session.workspace_id
        source, where, order = selection(workspace, query)
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                target = authorize_export(connection, principal, self.clock)
                rows = (
                    connection.execute(
                        select(
                            audit_event, administrator.c.display_name.label("administrator_name")
                        )
                        .select_from(source)
                        .where(*where)
                        .order_by(order, audit_event.c.id)
                        .limit(MAX_EXPORT_ROWS + 1)
                    )
                    .mappings()
                    .all()
                )
                if len(rows) > MAX_EXPORT_ROWS:
                    raise AuditExportTooLarge("AUDIT_EXPORT_TOO_LARGE")
                content = csv_document(rows)
                evidence = AuditExportEvidence(
                    contract_version="audit-export-1",
                    row_count=len(rows),
                    query_digest=canonical_hash(query.model_dump(mode="json")),
                ).model_dump(mode="json")
                at = TypeAdapter(UtcInstant).validate_python(self.clock())
                actor = principal.actor
                connection.execute(
                    audit_event.insert().values(
                        id=uuid4(),
                        workspace_id=workspace,
                        operation_id=None,
                        administrator_id=target,
                        intent_revision=None,
                        actor=actor.key,
                        actor_subject=actor.key,
                        actor_snapshot=actor.model_dump(mode="json"),
                        kind="audit_export",
                        at=at,
                        contract_version="audit-export-1",
                        data=evidence,
                        data_hash=canonical_hash(evidence),
                    )
                )
        return content
