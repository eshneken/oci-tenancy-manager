"""Generate editable local CSV demonstrations without loading or resetting any workspace."""

import csv
from pathlib import Path


# Copy the baseline, add a fictional employee, then omit them for an absence review.
def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "data/root-leader_org_261015_clean.csv"
    destination = root / ".local-dev/csv-scenarios"
    destination.mkdir(parents=True, exist_ok=True)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    additions = rows + [
        {
            "EMPLOYEE_FULL_NAME": "Demo Engineer (fictional)",
            "EMAIL": "demo.engineer@example.test",
            "MGR": "example-94504a07@example.test",
            "TOP_MGR": "example-94504a07@example.test",
        }
    ]
    changed = [dict(row) for row in rows]
    changed[0]["EMPLOYEE_FULL_NAME"] += " (name change demo)"
    scenarios = (
        ("01-baseline.csv", rows),
        ("02-new-employee.csv", additions),
        ("03-absence.csv", changed),
    )
    for filename, records in scenarios:
        with (destination / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        print(destination / filename)


if __name__ == "__main__":
    main()
