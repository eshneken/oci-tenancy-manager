# Caddy image exceptions and continuous updates

15 November 2026 · Explicit owner-approved availability risks · Targeted policy/native validation passes

The owner approved continuing with the latest official Caddy build under **two exact DoS
exceptions**, provided the image remains current and is continuously checked for updates. This
supersedes the earlier suggestion to wait for an official patch or choose a custom build. It is
not a general waiver for Caddy, Go modules, future image versions or vulnerability classes.

## Approved scope

| CVE | Exact component/version | Severity | Exact binary | Official Caddy release |
| --- | --- | --- | --- | --- |
| CVE-2026-116587 | `github.com/go-jose/go-jose/v3` `v3.0.5` | HIGH | `usr/bin/caddy` | `2.11.9` |
| CVE-2026-78661 | `golang.org/x/net` `v0.60.0` | HIGH | `usr/bin/caddy` | `2.11.9` |

The policy binds the official release version, exact package/CVE/version/severity and binary path.
The Dockerfile is separately digest-pinned and its changes require normal PR review; the exception
does not bind one immutable digest. A same-release digest update may retain this acceptance if all
reviewed finding tuples still match. Scan reports retain the accepted findings. There is
no blanket ignore-unfixed flag or exception for the Python application image. All other/new
HIGH/CRITICAL findings, scope mismatches and unavailable/malformed/incomplete scans remain blocking.
A new Caddy release requires exception-policy review. A component/version/severity/path change
does not inherit an allowance merely because the CVE identifier is unchanged. Same-release digest
updates still require reviewed image pins and fresh native/scan evidence.

These findings concern availability. The owner accepts the residual denial-of-service risk of this
specific official build; limited ingress, HTTP challenge handling and hardened pods are not proof
that vulnerable code is unreachable or that exploitation is impossible. Live reachability has not
been established either way. Do not describe the findings as fixed, absent or harmless.

The 15-November TLS-verified GitHub API check reported [official v2.11.9](https://github.com/caddyserver/caddy/releases/tag/v2.11.9),
published on 5 November, as the latest official stable release. This dated observation is not a
permanent assertion that the pinned version stays latest.

## Machine-policy fields

| Field | Meaning |
| --- | --- |
| `caddy_version` | Reviewed official release; must equal the version selected by the pinned official Dockerfile. A different release requires exception review. |
| `approved_on` | Date of the explicit owner authorization; decision metadata, not a promise of safety or a scan timestamp. |
| `reason` | Retained risk-acceptance rationale and its limits. |
| `exceptions` | The two reviewed entries; no wildcard package/version/CVE allowance. |
| Entry `id` | Exact CVE identifier matched against the scanner's `VulnerabilityID`. |
| Entry `package` | Exact Go module name matched against `PkgName`. |
| Entry `version` | Exact installed version string, including its `v` prefix, matched against `InstalledVersion`. |
| Entry `severity` | Exact HIGH classification; a severity change requires review. |

The binary target restriction is in the evaluator, not configurable through a wildcard policy field.
Missing fixed findings need no dummy exception result; they remain visible in historical evidence.

## Policy and update paths

The source implementation uses `tools/caddy/security-exceptions.json` and
`scripts/caddy_image_policy.py`; the official version/digest remains pinned in `tools/caddy/Dockerfile`.
The acceptance decision does not authorize replacing official artifacts with an unreviewed custom
binary or removing findings from the retained scan. Re-evaluate exact pins and exception scope on
each update, and complete native/configuration/proxy/certificate tests before promotion.

The new `.github/workflows/caddy-security.yml` source schedules daily checks at 11:20 UTC and manual
dispatch. It performs latest-official stable checks
and the native Caddy/image gate with fresh Trivy vulnerability data. A later official release or
unaccepted finding must fail the check and require a reviewed update. Existing weekly Dependabot
proposes Caddy version/digest updates; it does not merge or deploy them automatically. Retain normal
milestone/PR required gates and human review. This dedicated monitor supplements them.

The daily workflow is **source only until published and enabled in GitHub**. No hosted daily run,
notification delivery, automatic upgrade or completed deployment is inferred from adding YAML.
Record hosted activation and first successful current-image run separately after publication.

## Validation and remaining limits

Before approval, the native gate passed real isolated Pebble issuance/renewal/restart/header/HTTP404
checks but failed the image stage. That historical failure remains a failure; it is not rewritten
because the owner subsequently accepted narrow risks. The subsequent native rerun passed protocol
and image-policy checks with two accepted findings and zero blocked findings. The final stricter
evaluator rechecked that same actual scan successfully. Complete backend unit-only validation passed
2,861 cases at 95.4027% line coverage across 197 application modules; purpose/static/privacy and
independent security review checks pass. Latest official v2.11.9 and the Docker Hub tag/digest match
were verified. These are targeted source results, not a full milestone run or hosted daily execution.

[Held HTTP-01 ingress](../how-to/caddy-ingress.md) still requires real OCI/NLB/NSG/CSI/DNS/Let's Encrypt
qualification and the normal deployment prerequisites. The sole saved Atlas 8443 application,
its data and all live OCI/public-CA resources remain unchanged. No app/UI/database feature or broader
risk acceptance is added by this policy.
