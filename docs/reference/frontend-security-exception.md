# Temporary frontend development dependency exception

17 November 2026 · Explicit repository-owner approval for the current milestone

The repository owner approved merging with the current picomatch advisory while the existing
scheduled update watch checks for patched releases and compatible dependent-package updates.
This supersedes the earlier **local-development-only** acceptance for this one finding. It does
not waive the security job, protected-master checks or any unrelated vulnerability.

## Accepted scope and remaining risk

The sole accepted root is [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf),
the high-severity repeated-extglob regular-expression denial-of-service advisory in
**picomatch4.0.7**. The reported affected range must remain `<=4.0.7`. Acceptance requires exact
locked development-only installation, high severity and no compatible fix reported available. Every dependent
finding must also be development-only and have only this root cause throughout its complete npm
`via` graph. Peer cycles do not grant acceptance unless they reach the approved advisory, and every
reachable cause is checked. No production dependency, new advisory, changed root version/range,
severity escalation or newly available compatible fix inherits this approval.

npm11 labels forced downgrades of development tooling to older major releases as available fixes
(for example Vite8 to Vite6), while npm12 can report no fix for the same root. These proposals are
not compatible patches. The evaluator permits that reporting difference only when the proposed
target is an exact currently locked development dependency, npm explicitly marks a breaking change,
and the proposed numeric version has a strictly older major. This never authorizes performing the
downgrade. Direct picomatch replacement proposals, newer/equal majors, compatible fixes, unknown
targets and malformed proposals remain blocking. All exact advisory/version/scope checks still apply.

The latest raw npm audit reports ten high entries including dependents. Those findings remain
present in the original report; the exception does not make the audit clean or the vulnerable code
safe. Development/build tooling can still suffer denial of service when processing hostile glob
patterns. No claim is made that the vulnerable behavior is unreachable. Dependencies and lockfile
are unchanged by this acceptance.

## Enforcement and revisit

[`scripts/check_frontend_audit.py`](../../scripts/check_frontend_audit.py) runs the real
`npm audit --json`, retains its complete report under ignored `.local-dev/quality`, checks scanner
exit status and count consistency, then evaluates every finding against the exact scope above.
The required Security and publication job uses this evaluator after `npm ci --ignore-scripts`.
Malformed, missing or unavailable evidence remains blocking. All unrelated findings remain
blocking, including low-severity findings; no global audit threshold or ignore-unfixed switch
was added. The evaluator prints accepted and blocked package names separately.

The **repository maintainer** owns the residual risk and removal of the exception. Revisit it with
the existing weekly Monday update watch and whenever npm reports a compatible fix, the root pin
changes or the advisory scope changes. The existing watch is an operator automation, not a new
GitHub schedule introduced by this patch. Patched compatible dependencies must go through normal
tests, independent review and required PR checks. Do not auto-merge or deploy an update based only
on an advisory disappearing. Remove the exception when the reviewed dependency update resolves it.

The earlier failed audits and local-only receipts remain historical failures. This later explicit
acceptance permits only the named finding and its sole-cause development dependency reports to
pass the normal gate. Image checks, application tests, privacy controls and real OCI qualification
requirements remain unchanged.

## Validation

Synthetic policy tests cover clean scans, the exact root with a peer cycle, additional/mixed
advisories, rootless and unknown graphs, changed versions/ranges/severity, runtime dependencies,
compatible fixes, rejected new/equal/root/malformed downgrade proposals, missing nodes,
malformed/count-inconsistent reports and process/network failures.
Actual npm evaluation and independent security review are recorded with the milestone check results.
