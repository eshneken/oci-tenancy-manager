# Local review: Required users

This runbook reviews stored identities in the simulated local application. It cannot validate real
OCI account presence, privileges, passwords or MFA. Those cases remain Pending in the
[real OCI manifest](real-oci-test-manifest.md). Run only after the new revision is installed;
keep the saved test environment's current version distinct from the main preview.

## 1. Inspect an existing tenancy

1. Sign in to the updated main preview and choose Tenancies → an existing tenancy.
2. Find Required users below Accountability & registration. Expect Automation user and Recovery user.
3. Older setup operations may show Not recorded with no Identity details disclosure. This means
   OTM has no canonical identity record; it does not mean the user is missing in OCI.
4. Confirm Presence and permissions says Not checked. Refresh records should not create an operation
   or start a cloud check. No repair/password controls or new navigation badges are offered.

## 2. Follow a new simulated setup

1. Use a clearly synthetic test employee with the normal Organization actions. Create a tenancy
   (unique lowercase name and subscribed simulated home region), or import a simulated child.
   Keep the current organization intact; no reset is required for this review.
2. Before completing setup, open the pending tenancy from Tenancies. Required users should show
   Not recorded and the setup-in-progress notice. Return to the embedded setup panel to continue.
3. Complete the simulated handoff, review the exact temporary accounts, confirm cleanup and Start
   setup. Wait for Local setup verified; no real OCI account or email is created by simulation.
4. Open the tenancy. Both account identities should now show Recorded, still with Not checked for
   presence/permissions. They are OTM operational identities, not additional employee memberships.
5. Expand Identity details with mouse or keyboard. Verify distinct user OCIDs and SCIM IDs, the same
   domain OCID, UTC recording time and View setup operation. That link should open this setup;
   its Open tenancy link returns to the registered child.
6. Reload the browser on the child URL and refresh records. The same stored IDs should remain.

## 3. Responsive and historical review

- At desktop width, the cards should have equal widths. Expand one without stretching the closed
  card. At narrow mobile width, cards stack and long identifiers remain contained. Refresh and
  disclosure controls must remain reachable by keyboard with visible focus.
- Optional, on a disposable simulated test tenancy only: save its detail URL, then initiate deletion
  through the existing guarded flow. Reopen that URL afterward. Retired record, its retirement UTC
  time and the history notice should appear; no wording should claim actual OCI user deletion.
- A failed refresh must show an error rather than Not recorded. Previously loaded records may stay
  visible with that qualification. Unauthorized/expired access must hide records and require sign-in.
  These failure cases are covered automatically; no new product fault-injection control is added.

See the [14-field API/UI map](../reference/required-users-screen.md) for exact source mappings.
