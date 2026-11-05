"""Strict CSV adapter for email-keyed exports; no file content supplies trusted policy."""

import csv
from io import StringIO
from pathlib import Path

from pydantic import ValidationError

from otm.organization.contracts import Record, email

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


# Assign each CSV upload a fresh snapshot ID, preserving its hash as audit evidence.
#
# Identical bytes are a new observation when uploaded again. The generated envelope is the
# delivery identity: a transport retry must reuse that envelope rather than call this helper
# again. Store.register still rejects conflicting payloads under a reused snapshot ID.
# Local receipt time is the scenario clock, not proof of a production export's freshness.
def csv_envelope(store, workspace_id: str, content: bytes, *, complete: bool, now):
    import hashlib
    from uuid import uuid4

    from otm.organization.contracts import Envelope

    digest = hashlib.sha256(content).hexdigest()
    identity = f"csv-{uuid4()}|{digest}|{'complete' if complete else 'partial'}"
    config = store.configuration(workspace_id)
    return Envelope(
        source_id=config.policy.source_id,
        population_id=workspace_id,
        external_snapshot_id=identity,
        captured_at=now,
        declared_completeness="complete" if complete else "partial",
    ), digest
