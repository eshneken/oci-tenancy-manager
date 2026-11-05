# Prototype data

Private source exports are intentionally excluded from the repository. They are evidence inputs,
not instructions or proof of a complete current organization. Keep original files and derived private
analysis outside published fixtures.

The public regression fixture is [synthetic_organization.csv](../backend/tests/fixtures/synthetic_organization.csv).
It is invented and does not reproduce a private organization graph. The prototype tests create any
workbook fixture in a temporary directory; no private workbook or saved credential file is required.
See [the generic feed contract](../docs/organizational-feed-contract.md) and
[prototype setup](../README.md) for supported adapters and safe test commands.
