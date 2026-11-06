import { useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { followLink } from "./navigation";

const purposes = { automation: "Automation user", recovery: "Recovery user" };
const presenceNames = {not_checked:"Not checked", present:"Present", missing:"Missing", unknown:"Unable to verify"};
const blocked = {not_configured:"No qualified automation connection is recorded for this tenancy.", tenancy_inactive:"Presence checks are available for active tenancies.", tenancy_busy:"A tenancy operation is in progress. Check again when it finishes.", provider_unavailable:"The selected provider is currently unavailable."};
const states = { recorded: "Recorded", not_recorded: "Not recorded", retired: "Retired record" };

// Show registered identities without suggesting OCI presence, usable credentials or admin access.
export function RequiredUsers({ tenancyId, expired, navigate }: {
  tenancyId: string; expired: () => void; navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const keys = useRef(new Map<string,string>());
  // Keep private observations isolated by the originating child during navigation.
  const queryKey = (id:string) => ["tenancies", "required-users", id];
  const mutation = useMutation({
    mutationFn: async (variables:{tenancyId:string; key:string}) => {
      const receipt = await api.checkRequiredUsers(variables.tenancyId, {client_request_key:variables.key});
      if (!receipt.operation_id) throw new Error("Check receipt unavailable");
      return receipt;
    },
    onMutate: variables => client.cancelQueries({queryKey:queryKey(variables.tenancyId)}),
    onSuccess: (receipt,variables) => {
      keys.current.delete(variables.tenancyId);
      client.setQueryData<Awaited<ReturnType<typeof api.requiredUsers>>>(queryKey(variables.tenancyId),
        data => data ? {...data,pending_operation_id:receipt.operation_id} : data);
      void client.invalidateQueries({queryKey:queryKey(variables.tenancyId)});
      void client.invalidateQueries({queryKey:["operations"]});
      void client.invalidateQueries({queryKey:["audit-history"]});
    },
    onError: (_error,variables) => {void client.invalidateQueries({queryKey:queryKey(variables.tenancyId)});},
    retry:false,
  });
  const result = useQuery({
    queryKey: ["tenancies", "required-users", tenancyId],
    queryFn: ({ signal }) => api.requiredUsers(tenancyId, signal),
    retry: false,
    refetchInterval: query => query.state.data?.pending_operation_id ? 1000 : false,
  });
  const authorizationLost = [result.error,mutation.error].some(error => error instanceof ApiError && [401,403].includes(error.status));
  useEffect(() => {
    if (authorizationLost) expired();
  }, [authorizationLost, expired]);
  const data = authorizationLost ? undefined : result.data;
  const ownMutation = mutation.variables?.tenancyId === tenancyId;
  const checking = Boolean(data?.pending_operation_id) || ownMutation && mutation.isPending;
  // Keep a command UUID after an uncertain response; retry must not enqueue a second operation.
  function checkNow() {
    const key = keys.current.get(tenancyId) ?? crypto.randomUUID();
    keys.current.set(tenancyId,key);
    mutation.mutate({tenancyId,key});
  }
  return <section className="operation-panel required-users" aria-labelledby="required-users-title" aria-busy={result.isFetching}>
    <div className="required-users-heading">
      <h2 id="required-users-title">Required users</h2>
      <div className="required-users-actions">
      <button className="button primary" disabled={!data?.check_available || checking || result.isPending} onClick={checkNow}>
        {checking ? "Checking…" : ownMutation && mutation.isError ? "Retry check request" : "Check now"}
      </button>
      <button className="button secondary" disabled={result.isFetching} onClick={() => void result.refetch()}>
        {result.isPending ? "Loading records…" : result.isFetching ? "Refreshing records…" : result.isError ? "Try again" : "Refresh records"}
      </button>
      </div>
    </div>
    <p className="muted">Presence checks use local simulated fixture data. They do not verify live OCI access or administrative permissions.</p>
    {result.isPending && <p role="status">Loading required user records…</p>}
    {result.isError && <p className="alert" role="alert">{data ? "Unable to refresh records. Previously loaded records are shown." : "Unable to load required user records. Try again."}</p>}
    {ownMutation && mutation.isError && !authorizationLost && <p className="alert" role="alert">Unable to confirm the check request. Retry uses the same request to avoid duplicate operations.</p>}
    {data && !data.check_available && <p className="muted">{blocked[data.check_unavailable_reason ?? "not_configured"]}</p>}
    {data?.pending_operation_id && <p role="status">Checking required-user presence… Previous results remain dated below.</p>}
    {data && <>
      {data.tenancy_status === "pending" && <p className="notice">Setup is still in progress. Recorded identities do not mean the tenancy is ready.</p>}
      {!["active", "pending"].includes(data.tenancy_status) && <p className="notice">These identity records are retained for tenancy history.</p>}
      <ul className="required-users-grid">
        {data.users.map(user => {
          const presence = {...user.presence,state:user.presence?.state ?? "not_checked",stale:user.presence?.stale ?? false};
          const label = presence.stale ? "Check out of date" : presenceNames[presence.state];
          return <li key={user.purpose} className="required-user-card">
          <h3>{purposes[user.purpose]}</h3>
          <dl className="required-user-facts">
            <div><dt>Username</dt><dd>{user.identity?.user_name ?? "Not recorded"}</dd></div>
            <div><dt>Identity record</dt><dd><span className="badge required-user-state">{states[user.identity_state]}</span></dd></div>
            <div><dt>Presence</dt><dd><span className={"badge " + (presence.stale ? "review-open" : presence.state === "present" ? "active" : presence.state === "missing" ? "presence-missing" : "required-user-state")}>{label}</span>
              {presence.stale && <span className="muted"> · Last result: {presenceNames[presence.state]}</span>}</dd></div>
            <div><dt>Permissions</dt><dd>Not checked</dd></div>
            {presence.checked_at && <div><dt>{presence.state === "unknown" ? "Last attempt (UTC)" : "Checked (UTC)"}</dt><dd>{new Date(presence.checked_at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}
              {presence.operation_id && <> · <a href={"/operations/"+encodeURIComponent(presence.operation_id)} onClick={event=>followLink(event,"/operations/"+encodeURIComponent(presence.operation_id!),navigate)}>View check</a></>}</dd></div>}
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
        </li>;})}
      </ul>
    </>}
  </section>;
}
