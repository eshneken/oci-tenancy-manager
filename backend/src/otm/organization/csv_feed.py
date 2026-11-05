"""Strict CSV adapter for email-keyed exports; no file content supplies trusted policy."""

import csv
from datetime import datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from otm.organization.contracts import Envelope, Intake, Record, SourcePolicy, email

HEADERS = ("EMPLOYEE_FULL_NAME", "EMAIL", "MGR", "TOP_MGR")
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000


# Reject malformed CSV before any organization publication can occur.
class CsvFeedError(ValueError):
    pass


# Convert UTF-8 CSV into canonical records, using normalized email as a local source key.
#
# This synthetic key is explicitly not a stable employee ID. A changed email is a new
# identity until an administrator remap exists. Strict row/header checks prevent silently
# dropping columns or duplicate employees and accidentally interpreting corruption as absence.
def parse_csv(content: bytes) -> tuple[Record, ...]:
    if len(content) > MAX_BYTES:
        raise CsvFeedError("CSV exceeds the 2 MiB upload limit.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvFeedError("Save the CSV using UTF-8 encoding.") from error
    if "\x00" in decoded:
        raise CsvFeedError("CSV contains a null character.")
    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    result = []
    seen = set()
    try:
        headers = next(reader, [])
        headers = [h.strip().upper() for h in headers]
        if len(headers) != len(HEADERS) or set(headers) != set(HEADERS):
            raise CsvFeedError("Expected exactly these headers: " + ", ".join(HEADERS))
        for values in reader:
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(headers):
                raise CsvFeedError(
                    f"Row ending at line {reader.line_num} has the wrong column count."
                )
            row = dict(zip(headers, values, strict=True))
            try:
                address = email(row["EMAIL"])
                record = Record(
                    source_record_id="email:" + address,
                    full_name=row["EMPLOYEE_FULL_NAME"],
                    email=address,
                    manager_email=row["MGR"].strip() or None,
                    reported_top_manager_email=row["TOP_MGR"].strip() or None,
                )
            except (ValidationError, ValueError) as error:
                raise CsvFeedError(f"Invalid name or email at line {reader.line_num}.") from error
            if record.email in seen:
                raise CsvFeedError(f"Duplicate employee email at line {reader.line_num}.")
            seen.add(record.email)
            result.append(record)
            if len(result) > MAX_ROWS:
                raise CsvFeedError("CSV exceeds the 5,000 employee limit.")
    except csv.Error as error:
        raise CsvFeedError(f"Malformed CSV near line {reader.line_num}.") from error
    if not result:
        raise CsvFeedError(
            "CSV must contain at least one employee; an empty file cannot clear an org."
        )
    return tuple(result)


# Read a bounded local CSV without modifying the original export.
def read_csv(path: Path) -> tuple[Record, ...]:
    with path.open("rb") as source:
        return parse_csv(source.read(MAX_BYTES + 1))


# Give each accepted delivery a fresh identity while keeping byte equality as evidence only.
# Source identity and census authority are server-owned policy, never additional CSV columns.
# The caller must preserve this envelope for transport retries; a new call is a new observation.
# captured_at is an independently qualified source time, not automatically the upload receipt.
def csv_intake(
    content: bytes, policy: SourcePolicy, *, captured_at: datetime | None, complete: bool
) -> tuple[Intake, str]:
    records = parse_csv(content)
    digest = sha256(content).hexdigest()
    envelope = Envelope(
        source_id=policy.source_id,
        population_id=policy.population_id,
        external_snapshot_id=f"csv-{uuid4()}|{digest}|{'complete' if complete else 'partial'}",
        captured_at=captured_at,
        declared_completeness="complete" if complete else "partial",
    )
    return Intake(envelope=envelope, records=records), digest
