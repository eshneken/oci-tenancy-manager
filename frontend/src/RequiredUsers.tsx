import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { followLink } from "./navigation";

const purposes = { automation: "Automation user", recovery: "Recovery user" };
const states = { recorded: "Recorded", not_recorded: "Not recorded", retired: "Retired record" };

// Show registered identities without suggesting OCI presence, usable credentials or admin access.
export function RequiredUsers({ tenancyId, expired, navigate }: {
  tenancyId: string; expired: () => void; navigate: (path: string) => void;
}) {
  const result = useQuery({
    queryKey: ["tenancies", "required-users", tenancyId],
    queryFn: ({ signal }) => api.requiredUsers(tenancyId, signal),
    retry: false,
  });
  const authorizationLost = result.error instanceof ApiError && [401, 403].includes(result.error.status);
  useEffect(() => {
    if (authorizationLost) expired();
  }, [authorizationLost, expired]);
  const data = authorizationLost ? undefined : result.data;
  return <section className="operation-panel required-users" aria-labelledby="required-users-title" aria-busy={result.isFetching}>
    <div className="required-users-heading">
      <h2 id="required-users-title">Required users</h2>
      <button className="button secondary" disabled={result.isFetching} onClick={() => void result.refetch()}>
        {result.isPending ? "Loading records…" : result.isFetching ? "Refreshing records…" : result.isError ? "Try again" : "Refresh records"}
      </button>
    </div>
    <p className="muted">Stored identity records only. Presence and permissions in OCI have not been checked.</p>
    {result.isPending && <p role="status">Loading required user records…</p>}
    {result.isError && <p className="alert" role="alert">{data ? "Unable to refresh records. Previously loaded records are shown." : "Unable to load required user records. Try again."}</p>}
    {data && <>
      {data.tenancy_status === "pending" && <p className="notice">Setup is still in progress. Recorded identities do not mean the tenancy is ready.</p>}
      {!["active", "pending"].includes(data.tenancy_status) && <p className="notice">These identity records are retained for tenancy history.</p>}
      <ul className="required-users-grid">
        {data.users.map(user => <li key={user.purpose} className="required-user-card">
          <h3>{purposes[user.purpose]}</h3>
          <dl className="required-user-facts">
            <div><dt>Username</dt><dd>{user.identity?.user_name ?? "Not recorded"}</dd></div>
            <div><dt>Identity record</dt><dd><span className="badge required-user-state">{states[user.identity_state]}</span></dd></div>
            <div><dt>Presence and permissions</dt><dd>Not checked</dd></div>
          </dl>
          {user.identity && <details className="required-user-details">
            <summary>Identity details</summary>
            <dl className="required-user-facts">
              <div><dt>Domain OCID</dt><dd className="technical-id">{user.identity.domain_ocid}</dd></div>
              <div><dt>User OCID</dt><dd className="technical-id">{user.identity.user_ocid}</dd></div>
              <div><dt>SCIM resource ID</dt><dd className="technical-id">{user.identity.scim_resource_id}</dd></div>
              <div><dt>Recorded (UTC)</dt><dd>{new Date(user.identity.recorded_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}</dd></div>
              {user.identity.retired_at && <div><dt>Record retired (UTC)</dt><dd>{new Date(user.identity.retired_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}</dd></div>}
              <div><dt>Source</dt><dd><a href={"/operations/" + user.identity.source_operation_id} onClick={event => followLink(event, "/operations/" + user.identity!.source_operation_id, navigate)}>View setup operation</a></dd></div>
            </dl>
          </details>}
        </li>)}
      </ul>
    </>}
  </section>;
}
