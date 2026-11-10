import {operationHref} from "./operationNavigation";
import { useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { followLink } from "./navigation";
import type { AdministratorAccessView } from "./contracts";
import {AutomationKeys} from "./AutomationKeys";
import {RecoveryAccess} from "./RecoveryAccess";
import {RecoveryNetworkRepair} from "./RecoveryNetworkRepair";

const purposes = { automation: "Automation user", recovery: "Recovery user" };
const presenceNames = {not_checked:"Not checked", present:"Present", missing:"Missing", unknown:"Unable to verify"};
const blocked = {not_configured:"Presence checks require a registered automation connection and recorded user identities. This tenancy has not completed that setup. Existing tenancies are not enrolled automatically.", tenancy_inactive:"Presence checks are available for active tenancies.", tenancy_busy:"A tenancy operation is in progress. Check again when it finishes.", provider_unavailable:"The selected provider is currently unavailable."};
const policyNames = {not_checked:"Not checked",verified:"Verified in simulation",drift:"Policy drift",unknown:"Unable to verify",stale:"Check out of date"};
const assignmentNames = {not_checked:"Not checked",verified:"Verified in simulation",missing:"Missing or disabled",unknown:"Unable to verify"};
const states = { recorded: "Recorded", not_recorded: "Not recorded", retired: "Retired record" };

// Summarize only the two required assignments, never password readiness or effective privileges.
function AssignmentSummary({access}:{access?:AdministratorAccessView}) {
  const values=[access?.group??"not_checked",access?.domain_role??"not_checked"];
  const state=access?.stale?"stale":values.includes("missing")?"missing":values.every(value=>value==="verified")?"verified":values.every(value=>value==="not_checked")?"not_checked":"unknown";
  const names={stale:"Out of date",missing:"Missing",verified:"Assigned",not_checked:"Not checked",unknown:"Unverified"};
  return <span className={"badge "+(state==="verified"?"active":state==="missing"?"presence-missing":state==="stale"?"review-open":"required-user-state")} title="Simulated Administrators group and domain administrator role checks only. Expand Identity details for each result. This does not establish password readiness or all effective permissions." aria-label={`Administrator assignments: ${names[state]} (simulation)`}>{names[state]}</span>;
}

// Reuse exact assignment labels in the overview and recovery identity disclosure.
function AssignmentFacts({access}:{access?:AdministratorAccessView}) {
  return <>{(["group","domain_role"] as const).map(kind=>{
    const state=access?.[kind]??"not_checked";
    return <div key={kind}><dt>{kind==="group"?"Administrators group":"Domain administrator role"}</dt><dd><span className={"badge "+(access?.stale?"review-open":state==="verified"?"active":state==="missing"?"presence-missing":"required-user-state")}>{access?.stale?"Check out of date":assignmentNames[state]}</span></dd></div>;
  })}</>;
}

// Keep dated provenance compact while preserving the full UTC instant and exact operation target.
function CheckDate({label,kind,at,operationId,navigate,purpose}:{label:string;kind:string;purpose:string;at:string;operationId?:string|null;navigate:(path:string)=>void}) {
  const date=new Date(at).toLocaleDateString("en-US",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"});
  const full=new Date(at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"});
  const href=operationId?operationHref(operationId,purpose+"-"+kind):null;
  return <div><dt>{label} (UTC)</dt><dd>{href?<a href={href} aria-label={`View ${kind} check, ${date}`} title={full} onClick={event=>followLink(event,href,navigate)}><time dateTime={at}>{date}</time></a>:<time dateTime={at} title={full}>{date}</time>}</dd></div>;
}

// Show registered identities without suggesting OCI presence, usable credentials or admin access.
export function RequiredUsers({ tenancyId, expired, navigate }: {
  tenancyId: string; expired: () => void; navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const heading=useRef<HTMLHeadingElement>(null);
  const anchored=useRef(false);
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
      void client.invalidateQueries({queryKey:["tenancies","list"]});
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
  // Inventory read-time/age changes are independent; all recovery-readiness changes still invalidate.
  const recoveryChecksRevision=JSON.stringify({...data,automation_keys:undefined});
  // Stored result changes refresh inventory/history without fetching any provider from a GET.
  useEffect(()=>{
    if(!data)return;
    void client.invalidateQueries({queryKey:["tenancies","list"]});
    void client.invalidateQueries({queryKey:["tenancies","detail",tenancyId]});
    void client.invalidateQueries({queryKey:["operations"]});
    void client.invalidateQueries({queryKey:["audit-history"]});
  },[result.dataUpdatedAt,Boolean(data),client,tenancyId]);
  // The inventory deep link waits for the initial read to settle before moving keyboard focus.
  useEffect(()=>{
    if(authorizationLost || result.isPending || anchored.current || location.hash!=="#required-users")return;
    const frame=requestAnimationFrame(()=>{
      heading.current?.scrollIntoView?.({block:"start"});
      heading.current?.focus();
      anchored.current=true;
    });
    return ()=>cancelAnimationFrame(frame);
  },[result.isPending,authorizationLost,tenancyId]);
  const ownMutation = mutation.variables?.tenancyId === tenancyId;
  const checking = Boolean(data?.pending_operation_id) || ownMutation && mutation.isPending;
  // Keep a command UUID after an uncertain response; retry must not enqueue a second operation.
  function checkNow() {
    const key = keys.current.get(tenancyId) ?? crypto.randomUUID();
    keys.current.set(tenancyId,key);
    mutation.mutate({tenancyId,key});
  }
  return <><section id="required-users" className="operation-panel required-users" aria-labelledby="required-users-title" aria-busy={result.isFetching}>
    <div className="required-users-heading">
      <h2 ref={heading} tabIndex={-1} id="required-users-title">Required users</h2>
      <div className="required-users-actions">
      <button className="button secondary" disabled={!data?.check_available || checking || result.isPending} aria-describedby={data && !data.check_available ? "required-users-unavailable" : undefined} onClick={checkNow}>
        {checking ? "Refreshing user data…" : ownMutation && mutation.isError ? "Retry user refresh" : "Refresh user data"}
      </button>
      </div>
    </div>
    <p className="muted">User and recovery-policy checks use local simulated data. They do not prove live OCI access, password readiness or all effective permissions.</p>
    {result.isPending && <p role="status">Loading required user records…</p>}
    {result.isError && <p className="alert" role="alert">{data ? "Unable to refresh records. Previously loaded records are shown." : "Unable to load required user records. Try again."} <button type="button" className="text-link" disabled={result.isFetching} onClick={() => void result.refetch()}>Retry loading users</button></p>}
    {ownMutation && mutation.isError && !authorizationLost && <p className="alert" role="alert">Unable to confirm the check request. Retry uses the same request to avoid duplicate operations.</p>}
    {data && !data.check_available && <div id="required-users-unavailable" className="notice">
      <p><strong>Refresh user data is unavailable.</strong> {blocked[data.check_unavailable_reason ?? "not_configured"]}</p>
      {(data.check_unavailable_reason ?? "not_configured")==="not_configured" && <p>For local testing, complete setup for a newly created or imported simulated tenancy. Refreshing does not configure access.</p>}
    </div>}
    {data?.pending_operation_id && <p role="status">Checking users and recovery policy… Previous results remain dated below.</p>}
    {data && <>
      {data.tenancy_status === "pending" && <p className="notice">Setup is still in progress. Recorded identities do not mean the tenancy is ready.</p>}
      {!["active", "pending"].includes(data.tenancy_status) && <p className="notice">These identity records are retained for tenancy history.</p>}
      <ul className="required-users-grid">
        {data.users.map(user => {
          const presence = {...user.presence,state:user.presence?.state ?? "not_checked",stale:user.presence?.stale ?? false};
          const consolePolicy = data.recovery_console;
          const administrator = user.administrator_access;
          const label = presence.stale ? "Check out of date" : presenceNames[presence.state];
          return <li key={user.purpose} className="required-user-column"><section className="required-user-card">
          <h3>{purposes[user.purpose]}</h3>
          <dl className={"required-user-facts"+(user.purpose === "recovery" ? " required-recovery-facts" : "")}>
            <div className="required-user-fact-wide"><dt>Username</dt><dd>{user.identity?.user_name ?? "Not recorded"}</dd></div>
            <div className="required-user-overview-fact"><dt>Identity record</dt><dd><span className="badge required-user-state">{states[user.identity_state]}</span></dd></div>
            <div className="required-user-overview-fact"><dt>Presence</dt><dd><span className={"badge " + (presence.stale ? "review-open" : presence.state === "present" ? "active" : presence.state === "missing" ? "presence-missing" : "required-user-state")}>{label}</span>
              {presence.stale && <span className="muted"> · Last result: {presenceNames[presence.state]}</span>}</dd></div>
            {user.purpose === "automation" ? <AssignmentFacts access={administrator}/> : <div className="required-user-overview-fact"><dt>Permissions</dt><dd><AssignmentSummary access={administrator}/></dd></div>}

            {user.purpose === "recovery" && (["mfa_exemption","network_boundary"] as const).map(control => {
              const policy = consolePolicy;
              const state = policy?.state === "stale" ? "stale" : policy?.[control] ?? "not_checked";
              return <div key={control}><dt>{control === "mfa_exemption" ? "Console MFA exemption" : "Approved-network restriction"}</dt>
                <dd><span className={"badge " + (state === "verified" ? "active" : state === "drift" ? "presence-missing" : state === "stale" ? "review-open" : "required-user-state")}>{policyNames[state]}</span></dd></div>;
            })}

          </dl>
          {(presence.checked_at || administrator?.checked_at || (user.purpose === "recovery" && consolePolicy?.checked_at)) && <dl className="required-user-checks">
            {administrator?.checked_at && <CheckDate purpose={user.purpose} label="Assignments checked" kind="assignment" at={administrator.checked_at} operationId={administrator.operation_id} navigate={navigate}/>}
            {presence.checked_at && <CheckDate purpose={user.purpose} label={presence.state === "unknown" ? "Presence last attempt" : "Presence checked"} kind="presence" at={presence.checked_at} operationId={presence.operation_id} navigate={navigate}/>}
            {user.purpose === "recovery" && consolePolicy?.checked_at && <CheckDate purpose={user.purpose} label="Policy checked" kind="policy" at={consolePolicy.checked_at} operationId={consolePolicy.operation_id} navigate={navigate}/>}
          </dl>}
          {user.purpose === "recovery" && <RecoveryNetworkRepair key={tenancyId} tenancyId={tenancyId} eligible={Boolean(data.check_available&&!checking&&presence.state==="present"&&!presence.stale&&consolePolicy?.state==="drift"&&consolePolicy.mfa_exemption==="verified"&&consolePolicy.network_boundary==="drift")} policy={consolePolicy} expired={expired} navigate={navigate}/>}
          {user.identity && <details className="required-user-details">
            <summary>Identity details</summary>
            <dl className="required-user-facts">
              {user.purpose === "recovery" && <AssignmentFacts access={administrator}/>}
              <div><dt>Domain OCID</dt><dd className="technical-id">{user.identity.domain_ocid}</dd></div>
              <div><dt>User OCID</dt><dd className="technical-id">{user.identity.user_ocid}</dd></div>
              <div><dt>SCIM resource ID</dt><dd className="technical-id">{user.identity.scim_resource_id}</dd></div>
              <div><dt>Recorded (UTC)</dt><dd>{new Date(user.identity.recorded_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}</dd></div>
              {user.identity.retired_at && <div><dt>Record retired (UTC)</dt><dd>{new Date(user.identity.retired_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}</dd></div>}
              <div><dt>Source</dt><dd><a href={operationHref(user.identity.source_operation_id)} onClick={event => followLink(event, operationHref(user.identity!.source_operation_id), navigate)}>View setup operation</a></dd></div>
            </dl>
          </details>}
          </section>
          {user.purpose === "automation" && <RecoveryAccess key={"password-"+tenancyId} tenancyId={tenancyId} checksRevision={recoveryChecksRevision} expired={expired} navigate={navigate}/>}
        </li>;})}
      </ul>
    </>}
  </section>{data && <AutomationKeys inventory={data.automation_keys} navigate={navigate} tenancyId={data.signing_rotation_available?tenancyId:undefined} expired={expired}/>}</>;
}
