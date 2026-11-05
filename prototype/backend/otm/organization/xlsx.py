"""Values-only workbook adapter; workbook content never supplies trusted source policy."""

from pathlib import Path

from openpyxl import load_workbook
from pydantic import ValidationError

from otm.organization.contracts import Record

HEADERS = (
    "ID",
    "ECA_NAME",
    "ECA_EMAIL",
    "ECA_MANAGER",
    "ECA_MANAGER_EMAIL",
    "ECA_TOP_MGR_DIR_MINUS_3",
    "ENG_TERRITORY",
)


# Workbook data cannot safely be mapped to the canonical employee-row contract.
class FeedFormatError(ValueError):
    pass


# Read values only, including hidden rows; never evaluate workbook formulas.
def read_xlsx(path: Path, sheet: str = "Sheet1") -> tuple[Record, ...]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        if sheet not in workbook.sheetnames:
            raise FeedFormatError("configured worksheet missing")
        rows = iter(workbook[sheet].iter_rows())
        first = next(rows, None)
        if first is None:
            raise FeedFormatError("header row missing")
        headers = [str(cell.value).strip() if cell.value is not None else "" for cell in first]
        for name in HEADERS:
            if headers.count(name) != 1:
                raise FeedFormatError(f"required header missing/duplicated: {name}")
        positions = {name: headers.index(name) for name in HEADERS}
        result: list[Record] = []
        for row_number, row in enumerate(rows, 2):
            cells = {name: row[index] for name, index in positions.items()}
            if all(cell.value is None for cell in row):
                continue
            if any(cell.data_type == "f" for cell in cells.values()):
                raise FeedFormatError(f"formula is not source data: row {row_number}")

            # Normalize one scalar source cell; preserve integral IDs and reject
            # booleans/unsupported types.
            def text(name: str, cells=cells, row_number=row_number) -> str | None:
                value = cells[name].value
                if value is None:
                    return None
                if isinstance(value, bool):
                    raise FeedFormatError(f"unexpected boolean: row {row_number}, {name}")
                if name == "ID" and isinstance(value, (int, float)):
                    if int(value) != value:
                        raise FeedFormatError(f"non-integral source ID: row {row_number}")
                    return str(int(value))
                if not isinstance(value, str):
                    raise FeedFormatError(f"unexpected cell type: row {row_number}, {name}")
                return value.strip() or None

            try:
                result.append(
                    Record(
                        source_record_id=text("ID"),
                        full_name=text("ECA_NAME"),
                        email=text("ECA_EMAIL"),
                        manager_name=text("ECA_MANAGER"),
                        manager_email=text("ECA_MANAGER_EMAIL"),
                        reported_top_manager_email=text("ECA_TOP_MGR_DIR_MINUS_3"),
                        territory=text("ENG_TERRITORY"),
                    )
                )
            except ValidationError as error:
                raise FeedFormatError(f"invalid source record: row {row_number}") from error
        return tuple(result)
    finally:
        workbook.close()
