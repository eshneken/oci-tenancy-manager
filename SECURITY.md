# Security

Report suspected vulnerabilities privately to the repository owner through GitHub's private
vulnerability reporting when enabled, or another agreed private channel. Do not place credentials,
organization exports, customer data or exploit details in public issues or pull requests.

Follow the [security review policy](docs/security-review-policy.md),
[publication/checkpoint procedure](docs/how-to/github-checkpoints.md) and
[required test gates](docs/engineering-test-plan.md). Every development slice requires independent
security review. Automated scanning supplements that review; it cannot establish that all examples
are synthetic or that live OCI access has been qualified.

No private runtime configuration, passwords, MFA seeds, API keys, database dumps, HR feeds or raw
application screenshots belong in the repository or CI artifacts, even while the repository is private.
Keep dependency locks and immutable tool/action/image pins reviewed. Required checks must pass before
merging into protected master. A workflow file alone does not establish hosted protection.
