# Atlas application screenshots

[Main README](../../README.md) · [Documentation home](../README.md)

These PNGs capture the actual application at source checkpoint `786f83b` using an owned temporary
HTTPS application and freshly migrated disposable PostgreSQL database. The saved demonstration
instance was neither read nor changed. Temporary API/worker processes and their label-verified
database container were removed after capture.

- `atlas-organization.png`: synthetic CSV intake and the nine fictional identities in the public
  [stakeholder baseline](../how-to/stakeholder-demo-01-baseline.csv), with Engineering/Research mappings.
- `atlas-configuration.png`: one baseline published through normal UI interactions, explicitly
  marked as simulated validation. No tenancy configuration or real OCI resource was changed.

Captured at a 1440px desktop viewport. Names are invented; all employee addresses use reserved
`example.test`. No private HR export, real account/contact, password, MFA value, key or connection
string appears. The Atlas artwork is separately user-authorized branding. Screenshots are product
illustrations, not evidence of live OCI qualification. Source policy/quota example text is illustrative;
publication in simulation does not validate OCI syntax or deployment permission.

To refresh images, use an owned disposable environment with the checked-in synthetic data and the
normal authenticated UI. Never capture the saved/private directory and redact it afterward. Inspect
every image, obtain independent privacy/UX review and update the publication-asset hashes alongside
the README. Keep raw browser traces, temporary credentials and capture diagnostics private.
