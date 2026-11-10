import {AutomationKeys} from "./AutomationKeys";
import {operationHref,operationReturn} from "./operationNavigation";
import {RecoveryPasswordOperation} from "./RecoveryPasswordOperation";
import { EmailNotifications } from "./EmailNotifications";
import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Onboarding } from "./Onboarding";
import { SimulationInspection } from "./SimulationInspection";
import { followLink } from "./navigation";
import type { OperationQuery, OperationSummary } from "./contracts";
type OperationFilters = Required<OperationQuery>;
type OperationState = OperationSummary["state"];

const states: Record<OperationState, string> = {
  queued: "Queued",
  running: "Running",
  waiting: "Waiting",
  needs_attention: "Needs attention",
  succeeded: "Succeeded",
  cancelled: "Cancelled",
  failed: "Failed",
};
const initialQuery: OperationFilters = {
  page: 1,
  page_size: 10,
  sort: "accepted_at",
  direction: "desc",
  state: "",
  query: "",
};
const columns = [
  ["state", "State"],
  ["stage", "Stage"],
  ["accepted_at", "Accepted · UTC"],
  ["updated_at", "Updated · UTC"],
] as const;
const simulationNotice =
  "Provider operations run locally in simulation. No OCI resources or accounts are changed.";

// Format recorded timestamps consistently in UTC, without implying a provider observation time.
function stamp(value: string | null) {
  return value
    ? new Date(value).toLocaleString("en-US", {
        timeZone: "UTC",
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }) + " UTC"
    : "Not recorded";
}

// Translate persisted stage tokens without inventing progress or completion percentages.
function stageLabel(value: string) {
  return ({configuration_check_complete:"Configuration check complete",check_assigned_configuration:"Check assigned configuration"} as Record<string,string>)[value] ?? value.replaceAll("_", " ");
}

// A blocked local workflow retains pending obligations; a pure inspection has no repair action.
function simulationIssue(operation: OperationSummary) {
  return (
    operation.state === "needs_attention" &&
    (operation.provider_mode ?? "simulated") === "simulated"
  );
}
// Keep raw state filters stable while making the current simulated outcome understandable.
function stateLabel(operation: OperationSummary) {
  return simulationIssue(operation)
    ? operation.kind === "configuration_check" ? "Check incomplete" : operation.kind !== "inspect_import"
      ? "Workflow blocked"
      : "Simulation issue"
    : states[operation.state];
}

// End the privileged view only for a denied read, keeping service outages retryable.
function useReadDenial(error: unknown, expired: () => void) {
  useEffect(() => {
    if (
      error instanceof ApiError &&
      (error.status === 401 || error.status === 403)
    )
      expired();
  }, [error, expired]);
}

// Select recorded progress by native URL; the separately gated control admits synthetic inspections only.
export function Operations({
  operationId,
  expired,
  navigate,
}: {
  operationId: string | null;
  expired: () => void;
  navigate: (path: string) => void;
}) {
  return operationId === null ? (
    <OperationList expired={expired} navigate={navigate} />
  ) : (
    <OperationDetail
      key={operationId}
      operationId={operationId}
      expired={expired}
      navigate={navigate}
    />
  );
}

// Retain list controls in the scoped query cache so opening a detail and returning preserves context.
function OperationList({
  expired,
  navigate,
}: {
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const [query, setQuery] = useState<OperationFilters>(
    () =>
      client.getQueryData<OperationFilters>(["operations", "view"]) ??
      initialQuery,
  );
  const [search, setSearch] = useState(query.query);
  useEffect(() => {
    client.setQueryData(["operations", "view"], query);
  }, [client, query]);
  useEffect(() => {
    const timer = setTimeout(
      () =>
        setQuery((previous) =>
          previous.query === search
            ? previous
            : { ...previous, query: search, page: 1 },
        ),
      200,
    );
    return () => clearTimeout(timer);
  }, [search]);
  const result = useQuery({
    queryKey: ["operations", "list", query],
    queryFn: ({ signal }) => api.operations(query, signal),
    retry: false,
    refetchInterval: 15_000,
  });
  useReadDenial(result.error, expired);
  const data = result.data;
  const filtered = Boolean(query.query || query.state);
  const page = data?.page ?? 1;
  const pageCount = data?.pages ?? 1;
  const firstPage = Math.max(1, Math.min(page - 2, pageCount - 4));
  const pages = Array.from(
    { length: Math.min(5, pageCount) },
    (_, index) => firstPage + index,
  );
  // A different sort begins ascending; repeat activation toggles direction and resets only the page.
  function sort(key: OperationFilters["sort"]) {
    setQuery((previous) => ({
      ...previous,
      page: 1,
      sort: key,
      direction:
        previous.sort === key && previous.direction === "asc" ? "desc" : "asc",
    }));
  }
  // Clearing a no-match state resets both user filters while preserving ordering and row count.
  function clearFilters() {
    setSearch("");
    setQuery((previous) => ({ ...previous, query: "", state: "", page: 1 }));
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">RECORDED WORK</span>
          <h1 tabIndex={-1}>Operations</h1>
          <p className="muted">
            Review recorded workflows, inspections and their outcomes.
          </p>
        </div>
        <SimulationInspection expired={expired} navigate={navigate} />
      </div>
      <p className="notice">
        <strong>Simulated provider.</strong> {simulationNotice}
      </p>
      <section className="table-panel" aria-label="Operations directory">
        <div className="table-toolbar operations-toolbar">
          <label className="search-field">
            Search operations
            <input
              type="search"
              placeholder="Operation ID or tenancy OCID"
              maxLength={128}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="state-filter">
            State
            <Select
              aria-label="State"
              value={query.state}
              onChange={(event) =>
                setQuery((previous) => ({
                  ...previous,
                  state: event.target.value as OperationFilters["state"],
                  page: 1,
                }))
              }
            >
              <option value="">All states</option>
              {Object.entries(states).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </Select>
          </label>
          <button
            className="button secondary"
            disabled={result.isFetching}
            onClick={() => void result.refetch()}
          >
            Refresh
          </button>
        </div>
        {result.isPending ? (
          <p className="table-feedback" role="status">
            Loading operations…
          </p>
        ) : result.isError ? (
          <p className="table-feedback alert" role="alert">
            Unable to load operations. Use Refresh to try again.
          </p>
        ) : (
          <>
            {data?.total === 0 ? (
              <div className="table-feedback">
                <h2>
                  {filtered
                    ? "No operations match your filters"
                    : "No operations yet"}
                </h2>
                <p>
                  {filtered
                    ? "Change or clear the search and state filter."
                    : "Recorded operations will appear here after a workflow or inspection is accepted."}
                </p>
                {filtered && (
                  <button className="button secondary" onClick={clearFilters}>
                    Clear filters
                  </button>
                )}
              </div>
            ) : (
              <div
                className="table-scroll"
                role="region"
                aria-label="Scrollable operations table"
                tabIndex={0}
              >
                <table className="operations-table">
                  <caption className="sr-only">
                    Recorded operations with simulated provider outcomes
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Operation</th>
                      <th scope="col">Tenancy</th>
                      {columns.map(([key, label]) => (
                        <th
                          key={key}
                          scope="col"
                          aria-sort={
                            query.sort === key
                              ? query.direction === "asc"
                                ? "ascending"
                                : "descending"
                              : "none"
                          }
                        >
                          <button
                            className="sort-button"
                            onClick={() => sort(key)}
                          >
                            {label}
                            <span aria-hidden="true">
                              {query.sort === key
                                ? query.direction === "asc"
                                  ? "↑"
                                  : "↓"
                                : "↕"}
                            </span>
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data?.items.map((operation) => (
                      <tr key={operation.id}>
                        <td>
                          <a
                            className="operation-link"
                            href={operationHref(operation.id)}
                            onClick={(event) =>
                              followLink(
                                event,
                                operationHref(operation.id),
                                navigate,
                              )
                            }
                          >
                            {operation.title ?? (operation.kind === "configuration_check" ? "Configuration check" : "Import inspection")}
                            <span className="technical-id">{operation.id}</span>
                          </a>
                          <span className="badge simulated">Simulated</span>
                        </td>
                        <td className="technical-id">
                          {operation.target_label ??
                            operation.target_tenancy_ocid}
                        </td>
                        <td>
                          <span
                            className={
                              "badge operation-state " + operation.state
                            }
                          >
                            {stateLabel(operation)}
                          </span>
                          {simulationIssue(operation) && (
                            <p className="operation-issue-note">
                              {operation.kind === "recovery_password"
                                ? "Password work requires reconciliation. Review the recorded outcome before further access."
                                : operation.kind === "recovery_network_repair"
                                ? "Repair effect is unverified. Review the operation for independent reconciliation; do not retry the write."
                                : operation.kind === "organization_action"
                                ? "Local workflow is blocked. Review the employee or tenancy record."
                                : "Simulation ended with an issue. No action is required."}
                            </p>
                          )}
                        </td>
                        <td>{stageLabel(operation.stage)}</td>
                        <td>
                          <time dateTime={operation.accepted_at}>
                            {stamp(operation.accepted_at)}
                          </time>
                        </td>
                        <td>
                          <time dateTime={operation.updated_at}>
                            {stamp(operation.updated_at)}
                          </time>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="table-footer">
              <p role="status">
                {data?.total
                  ? `Showing ${(data.page - 1) * data.page_size + 1}–${Math.min(data.page * data.page_size, data.total)} of ${data.total}`
                  : "0 operations"}
              </p>
              <div className="pagination">
                <label>
                  Rows{" "}
                  <Select
                    aria-label="Operations rows per page"
                    value={query.page_size}
                    onChange={(event) =>
                      setQuery((previous) => ({
                        ...previous,
                        page: 1,
                        page_size: Number(
                          event.target.value,
                        ) as OperationFilters["page_size"],
                      }))
                    }
                  >
                    {[10, 25, 50, 100].map((size) => (
                      <option key={size}>{size}</option>
                    ))}
                  </Select>
                </label>
                <button
                  className="button secondary"
                  disabled={page === 1}
                  onClick={() =>
                    setQuery((previous) => ({ ...previous, page: page - 1 }))
                  }
                >
                  Previous
                </button>
                <nav className="page-numbers" aria-label="Operations pages">
                  {pages.map((number) => (
                    <button
                      className="button secondary"
                      key={number}
                      aria-label={`Page ${number}`}
                      aria-current={number === page ? "page" : undefined}
                      onClick={() =>
                        setQuery((previous) => ({ ...previous, page: number }))
                      }
                    >
                      {number}
                    </button>
                  ))}
                </nav>
                <span>
                  Page {page} of {pageCount}
                </span>
                <button
                  className="button secondary"
                  disabled={page === pageCount}
                  onClick={() =>
                    setQuery((previous) => ({ ...previous, page: page + 1 }))
                  }
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </>
  );
}

// Administrator handoff changes who handles this workload, while preserving its original creator and activation mailbox.
function Responsibility({operation,expired}:{operation:OperationSummary;expired:()=>void}) {
  const client=useQueryClient();
  const [target,setTarget]=useState<{revision:number;name:string}|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const panelHeading=useRef<HTMLHeadingElement>(null);
  const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),launch=useRef<HTMLButtonElement>(null),status=useRef<HTMLParagraphElement>(null);
  const requestKey=useRef(crypto.randomUUID()),controller=useRef<AbortController|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{if(target){dialog.current?.showModal();heading.current?.focus();}},[target]);
  useEffect(()=>{if(notice)status.current?.focus();},[notice]);

  // Closing an untouched or failed confirmation does not change the current administrator.
  function close() {if(busy)return;dialog.current?.close();setTarget(null);setError("");(launch.current??panelHeading.current)?.focus();}

  // Preserve the exact reviewed responsibility revision even if background polling returns a newer one.
  function open() {
    if(!operation.can_take_responsibility||operation.responsibility_revision==null)return;
    requestKey.current=crypto.randomUUID();setError("");setNotice("");
    setTarget({revision:operation.responsibility_revision,name:operation.responsible_administrator_name??"Not recorded"});
  }

  // A stable command identity permits safe retry when the first response is lost.
  async function confirm() {
    if(!target||busy)return;
    setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    try {
      await api.takeResponsibility(operation.id,{client_request_key:requestKey.current,expected_revision:target.revision},signal);
      if(signal.aborted)return;
      await Promise.all([client.invalidateQueries({queryKey:["operations"]}),client.invalidateQueries({queryKey:["onboarding"]})]);
      if(signal.aborted)return;
      dialog.current?.close();setTarget(null);setNotice("Responsibility change recorded.");
    } catch(failure) {
      if(signal.aborted)return;
      if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();
      else setError(failure instanceof ApiError&&failure.status===409?"Responsibility or operation eligibility changed. Close this dialog and refresh before trying again.":"The responsibility change could not be confirmed. Retry safely or close and refresh the operation.");
    } finally {if(!signal.aborted)setBusy(false);}
  }

  return <section className="operation-panel" aria-labelledby="operation-responsibility-title">
    <h2 id="operation-responsibility-title" ref={panelHeading} tabIndex={-1}>Administrator responsibility</h2>
    <dl className="operation-facts"><div><dt>Initiated by</dt><dd>{operation.initiated_by??"Not recorded"}</dd></div><div><dt>Responsible administrator</dt><dd>{operation.responsible_administrator_name??"Not recorded"}</dd></div></dl>
    {notice&&<p ref={status} role="status" tabIndex={-1} className="notice">{notice}</p>}
    {operation.can_take_responsibility&&operation.responsibility_revision!=null&&<button ref={launch} className="button secondary" onClick={open}>Take responsibility</button>}
    <dialog ref={dialog} className="workflow-dialog" aria-labelledby="take-responsibility-title" onCancel={event=>{event.preventDefault();close();}}>
      <h2 id="take-responsibility-title" ref={heading} tabIndex={-1}>Take responsibility?</h2>
      <p>You will become the administrator responsible for continuing this operation. Current responsible administrator: {target?.name}.</p>
      <p>This changes workload responsibility only. The original initiator, activation email address and tenancy owner remain unchanged.</p>
      {error&&<p role="alert" className="alert">{error}</p>}
      <div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={close}>Cancel</button><button className="button primary" disabled={busy} onClick={()=>void confirm()}>{busy?"Updating responsibility…":"Take responsibility"}</button></div>
    </dialog>
  </section>;
}

// Read immutable intent and progress; completion describes only the qualified operation milestone.
function OperationDetail({
  operationId,
  expired,
  navigate,
}: {
  operationId: string;
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const result = useQuery({
    queryKey: ["operations", "detail", operationId],
    queryFn: ({ signal }) => api.operation(operationId, signal),
    retry: false,
    // Poll active work or pending mail submissions; these reads never renew the idle session.
    refetchInterval: (query) =>
      ["queued", "running", "waiting"].includes(
        query.state.data?.operation.state ?? "",
      )
        || query.state.data?.notifications?.some(notice=>notice.state==="pending"||notice.state==="sending") ? 5_000
        : false,
  });
  useReadDenial(result.error, expired);
  const detail = result.data;
  const operation = detail?.operation;
  const userChecks=detail?.events.find(event=>event.user_checks?.length)?.user_checks??[];
  const keyInventory=detail?.events.find(event=>event.automation_keys)?.automation_keys;
  // Deep links wait for recorded results; never fetch current tenancy facts as historical evidence.
  const checkAnchor=location.hash.slice(1);
  useEffect(()=>{
    const anchor=checkAnchor;
    if(!userChecks.some(check=>check.anchor===anchor) && !(anchor==="automation-keys"&&keyInventory))return;
    const frame=requestAnimationFrame(()=>{const section=document.getElementById(anchor);section?.scrollIntoView?.({block:"start"});section?.focus();});
    return ()=>cancelAnimationFrame(frame);
  },[detail,checkAnchor]);

  const back=operationReturn();
  const HistoryContainer = operation?.guided_onboarding ? "details" : "div";
  const notFound =
    result.error instanceof ApiError && result.error.status === 404;
  const eventNames = {
    recovery_password_disclosed:"Recovery password requested",recovery_password_outcome:"Recovery password outcome",operation_intent: "Operation accepted",
    inspection_dispatch: "Inspection dispatched",
    inspection_outcome: "Inspection outcome",
    organization_action_outcome: "Simulated lifecycle result",
    onboarding_action: "Onboarding action",
    onboarding_outcome: "Onboarding check",
    configuration_outcome: "Configuration verification",
    cost_collection_outcome: "Cost collection result",
    required_user_check_outcome: "Required-user check results",
    recovery_network_outcome: "Recovery network repair result",
    configuration_check_outcome: "Configuration check result",
    configuration_retry: "Configuration retry",
    operation_responsibility_changed: "Operation responsibility changed",
    email_delivery: "Email delivery",
  };
  return (
    <>
      <a
        className="back-link"
        href={back.path}
        onClick={(event) => followLink(event, back.path, navigate)}
      >
        ← {back.label}
      </a>
      <div className="page-heading">
        <div>
          <span className="eyebrow">RECORDED OPERATION</span>
          <h1 tabIndex={-1}>
            {notFound
              ? "Operation not found"
              : (operation?.title ?? (operation?.kind === "configuration_check" ? "Configuration check" : "Import inspection"))}
          </h1>
          <p className="technical-id">{operationId}</p>
        </div>
        <button
          className="button secondary"
          disabled={result.isFetching}
          onClick={() => void result.refetch()}
        >
          Refresh
        </button>
      </div>
      {result.isPending ? (
        <p className="notice" role="status">
          Loading operation…
        </p>
      ) : result.isError ? (
        <p className="alert" role="alert">
          {notFound
            ? "This operation is not available. Return to the operations list."
            : "Unable to load this operation. Use Refresh to try again."}
        </p>
      ) : (
        operation && (
          <>
            <p className="notice">
              <strong>Simulated provider.</strong> {simulationNotice}
            </p>
            <div className="operation-status">
              <span className={"badge operation-state " + operation.state}>
                {stateLabel(operation)}
              </span>
              <span>Stage: {stageLabel(operation.stage)}</span>
            </div>
            {detail.recovery_password&&<RecoveryPasswordOperation operation={operation} progress={detail.recovery_password} navigate={navigate}/>}
            {simulationIssue(operation) && operation.kind!=="recovery_password" && (
              <p className="notice" role="status">
                {operation.kind === "recovery_network_repair" ? "The network repair has an uncertain effect. The tenancy remains reserved until independent reconciliation. Do not retry the write or start another repair." : operation.kind === "cost_collection" ? "Cost reads exhausted retries or their collection context changed. Open the tenancy to retry eligible current-month reads. No tenancy settings were changed." : operation.kind === "configuration_check" ? "The read-only check did not complete. Review configuration checks; no tenancy settings were changed." : operation.kind === "configuration_update"
                  ? "Baseline update is blocked. Open its configuration progress to review incomplete tenancies and available retries."
                  : operation.kind !== "inspect_import"
                  ? "Local workflow is blocked. Review the employee or tenancy record; pending associations remain until handled."
                  : "Simulation ended with an issue. No action is required."}
              </p>
            )}
            {operation.state === "succeeded" && (
              <p className="notice">
                {operation.kind === "recovery_password" ? "Recovery password operation verified in local simulation. Review the recorded outcome above." : operation.kind === "recovery_network_repair" ? "Approved recovery networks verified in simulation. Review the separately dated user checks; no OCI resources or credentials were changed." : operation.kind === "required_user_check" ? "Simulated user check completed. Review the tenancy for presence, automation and recovery administrator assignments and recovery-policy results; completion does not establish recovery readiness. Password readiness and all effective permissions were not checked." : operation.kind === "cost_collection" ? "Cost collection completed in local simulation. Review each tenancy for partial or unqualified source data; no OCI resources were changed." : operation.kind === "configuration_check" ? "Read-only configuration check completed. Review its results for differences or categories that could not be verified; completion does not mean the configuration matches." : operation.kind === "configuration_update" ? "Baseline update verified in local simulation; no OCI resources were changed." : operation.kind === "organization_action"
                  ? "Local lifecycle simulation completed. Registry changes are verified; no OCI resources were changed."
                  : "Inspection completed successfully. This tenancy has not been adopted by this inspection."}
                {!["configuration_check","recovery_password"].includes(operation.kind) && operation.result_tenancy_id && (
                  <>
                    {" "}
                    <a
                      href={"/tenancies/" + operation.result_tenancy_id}
                      onClick={(event) =>
                        followLink(
                          event,
                          "/tenancies/" + operation.result_tenancy_id,
                          navigate,
                        )
                      }
                    >
                      Open tenancy
                    </a>
                  </>
                )}
              </p>
            )}
            {operation.kind === "configuration_check" && <p><a href={"/configuration/drift"+(operation.result_tenancy_id?"/"+operation.result_tenancy_id+"?returnTo="+encodeURIComponent(operationHref(operationId)):"?tab=checks")} onClick={event=>followLink(event,"/configuration/drift"+(operation.result_tenancy_id?"/"+operation.result_tenancy_id+"?returnTo="+encodeURIComponent(operationHref(operationId)):"?tab=checks"),navigate)}>View configuration checks</a></p>}
            {operation.kind === "configuration_update" && <p><a href={"/configuration?update="+operationId} onClick={event=>followLink(event,"/configuration?update="+operationId,navigate)}>Open baseline update</a></p>}
            {operation.guided_onboarding && <Responsibility key={"responsibility-"+operationId} operation={operation} expired={expired}/>}
            {operation.guided_onboarding && (
              <Onboarding
                key={operationId}
                operationId={operationId}
                showTenancyLink={false}
                expired={expired}
                navigate={navigate}
              />
            )}
            {(operation.guided_onboarding||Boolean(detail.notifications?.length))&&<EmailNotifications notifications={detail.notifications??[]}/>}
            {userChecks.length>0&&<section className="operation-panel" aria-label="Recorded user check results">
              <h2>Recorded user check results</h2>
              <p className="muted">Historical observations from this operation in local simulation. These results do not establish current access or password readiness.</p>
              <div className="required-users-grid">{userChecks.map(check=><section key={check.anchor} id={check.anchor} tabIndex={-1} className="required-user-card">
                <h3>{{"automation-presence":"Automation user · Presence","automation-assignment":"Automation user · Assignments","recovery-presence":"Recovery user · Presence","recovery-assignment":"Recovery user · Assignments","recovery-policy":"Recovery user · Console policy"}[check.anchor]}</h3>
                <dl className="required-user-facts">{check.facts.map(fact=><div key={fact.label}><dt>{fact.label}</dt><dd><span className={"badge "+(["present","verified"].includes(fact.state)?"active":["missing","drift"].includes(fact.state)?"presence-missing":"required-user-state")}>{{not_checked:"Not checked",present:"Present",missing:"Missing",unknown:"Unable to verify",verified:"Verified in simulation",drift:"Drift detected"}[fact.state]}</span></dd></div>)}</dl>
                <p className="muted">Checked: {stamp(check.checked_at??null)}</p>
              </section>)}</div>
            </section>}
            {keyInventory && <AutomationKeys inventory={keyInventory} historical navigate={navigate}/>}
            <HistoryContainer
              className={
                operation.guided_onboarding ? "onboarding-history" : undefined
              }
            >
              {operation.guided_onboarding && (
                <summary>Operation details and history</summary>
              )}
              <dl className="operation-facts">
                <div>
                  <dt>Target tenancy</dt>
                  <dd className="technical-id">
                    {operation.target_label ?? operation.target_tenancy_ocid}
                  </dd>
                </div>
                {!operation.guided_onboarding&&<div>
                  <dt>Initiated by</dt>
                  <dd>{operation.initiated_by ?? "Not recorded"}</dd>
                </div>}
                <div>
                  <dt>Accepted</dt>
                  <dd>{stamp(operation.accepted_at)}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{stamp(operation.updated_at)}</dd>
                </div>
                <div>
                  <dt>Completed</dt>
                  <dd>{stamp(operation.completed_at)}</dd>
                </div>
                <div>
                  <dt>Provider</dt>
                  <dd>Simulated</dd>
                </div>
              </dl>
              <section
                className="operation-panel"
                aria-labelledby="steps-title"
              >
                <h2 id="steps-title">Steps and verification</h2>
                {detail.steps.length ? (
                  <ol className="operation-timeline">
                    {detail.steps.map((step) => (
                      <li key={step.step_key}>
                        <h3>
                          {step.step_key.startsWith("recovery_password:") ? detail.recovery_password?.phase==="setup"?"Prepare recovery password custody":"Rotate recovery password" : step.step_key.startsWith("required_users:") ? "Check required users, assignments and recovery policy" : step.step_key.startsWith("cost:") ? "Read current month costs" : step.step_key.startsWith("configuration_check:") ? "Check assigned managed configuration" : step.step_key === "inspect_target"
                            ? "Inspect target"
                            : step.step_key.startsWith("remove_member_groups:") ? "Remove user group memberships" : step.step_key.startsWith("delete_member_user:") ? "Delete tenancy user" : step.step_key === "apply_lifecycle"
                              ? "Apply simulated lifecycle"
                              : stageLabel(step.step_key)}
                        </h3>
                        <p>
                          <span className={"badge " + step.state}>
                            {step.state === "verified"
                              ? ["configuration_check", "cost_collection", "required_user_check"].includes(operation.kind) ? "Completed" : "Verified"
                              : step.state === "needs_attention"
                                ? "Simulation issue"
                                : "Running"}
                          </span>{" "}
                          <span>Attempt {step.attempt_number}</span>
                        </p>
                        <p>{["configuration_check", "cost_collection", "required_user_check"].includes(operation.kind) ? "Completed" : "Verified"}: {stamp(step.verified_at)}</p>
                        {step.safe_code && (
                          <p>
                            Outcome code: <code>{step.safe_code}</code>
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted">No workflow steps recorded yet.</p>
                )}
              </section>
              <section
                className="operation-panel"
                aria-labelledby="events-title"
              >
                <h2 id="events-title">Recent events</h2>
                <p className="muted">
                  {detail.events_limited
                    ? "Showing the most recent 50 events. Earlier events are not shown."
                    : "Recorded acceptance, dispatch and workflow outcomes."}
                </p>
                {detail.events.length ? (
                  <ol className="operation-timeline">
                    {detail.events.map((event, index) => (
                      <li key={index}>
                        <h3>{eventNames[event.kind]}</h3>
                        <p>
                          <time dateTime={event.at}>{stamp(event.at)}</time>
                        </p>
                        {event.safe_code && (
                          <p>
                            Outcome code: <code>{event.safe_code}</code>
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted">No events recorded yet.</p>
                )}
              </section>
            </HistoryContainer>
          </>
        )
      )}
    </>
  );
}
