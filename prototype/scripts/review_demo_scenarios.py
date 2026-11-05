"""Generate fictional review-lifecycle scenarios around the unchanged real organization export."""

import csv
from pathlib import Path


# Write five feed snapshots for ignore, onboarding, identity merge, correction and removal.
def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / ".local-dev/review-scenarios"
    destination.mkdir(parents=True, exist_ok=True)
    with (root / "data/root-leader_org_261015_clean.csv").open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        original = list(reader)
    old = {
        "EMPLOYEE_FULL_NAME": "Karen Smith (demo)",
        "EMAIL": "karen.smith@example.test",
        "MGR": "example-94504a07@example.test",
        "TOP_MGR": "example-94504a07@example.test",
    }
    new = {**old, "EMPLOYEE_FULL_NAME": "Karen Jones (demo)", "EMAIL": "karen.jones@example.test"}
    engineer = {
        **old,
        "EMPLOYEE_FULL_NAME": "New Engineer (demo)",
        "EMAIL": "new.engineer@example.test",
    }
    snapshots = [("01-baseline.csv", original + [old])]
    for number, name, extra in (
        (2, "new-and-renamed", [new, engineer]),
        (3, "top-manager-fixed", [new, engineer]),
        (4, "departure", [new]),
        (5, "removed-person-repeated", [new, engineer]),
    ):
        rows = [dict(row) for row in original] + extra
        rows[0]["EMPLOYEE_FULL_NAME"] += f" (scenario {number})"
        if number == 2:
            rows[0]["TOP_MGR"] = "example-265e8ea9@example.test"
        snapshots.append((f"{number:02}-{name}.csv", rows))
    for filename, rows in snapshots:
        with (destination / filename).open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(destination / filename)


if __name__ == "__main__":
    main()
