import { configurationMessages, configurationMessageClass } from "./configurationStatus";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Select } from "./Select";
import { baselineHref } from "./baselineNavigation";
import { followLink } from "./navigation";
import type { ConfigurationDriftQuery, ConfigurationIssue, ConfigurationCheckSummary, ActionReceipt } from "./contracts";

const categories = { policy: "Policy statements", quota: "Quota statements", budget: "Monthly budget", tags: "Tag defaults" };
const states: Record<string,string> = { matching:"Matching", drifted:"Confirmed drift", unavailable:"Unable to verify", conflict:"Binding conflict", missing:"Missing", different:"Different", not_checked:"Not checked", checking:"Checking", superseded:"Not checked", stale:"Check out of date" };
const initial: ConfigurationDriftQuery = { tab:"confirmed",query:"",state:"all",sort:"name",direction:"asc",page:1,page_size:10 };

// Report evidence time in a single explicit timezone without implying provider recalculation time.
function stamp(value:string|null|undefined) { return value ? new Date(value).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"}) : "Not checked"; }

// Return navigation accepts only the two drift views or an exact registered-tenancy route.
function returnPath() {
  const candidate = new URLSearchParams(location.search).get("returnTo") ?? "";
  return /^\/(?:tenancies|operations)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(candidate) || candidate === "/tenancies" || candidate === "/configuration/drift?tab=checks"
    ? candidate : "/configuration/drift";
}

// Age invalidates freshness without inventing a failed provider read in either category view.
function categoryLabel(issue:ConfigurationIssue) { return issue.safe_code==="CHECK_STALE"?"Check out of date":states[issue.state]; }

// Evidence is text only: familiar payload fields remain readable, with exact unknown content retained.
function Evidence({value,category}:{value:string;category:keyof typeof categories}) {
  let parsed: Record<string,unknown>;
  try { parsed=JSON.parse(value) as Record<string,unknown>; }
  catch { return <pre className="drift-evidence-text">{value}</pre>; }
  if(!parsed || typeof parsed!=="object" || Array.isArray(parsed)) return <pre className="drift-evidence-text">{value}</pre>;
  return <dl className="drift-values">{Object.entries(parsed).map(([key,item]) => <div key={key}>
    <dt>{({statements:"Statements",monthly_amount:"Monthly amount",currency:"Currency",period:"Period",namespace:"Namespace",defaults:"Defaults"} as Record<string,string>)[key] ?? key}</dt>
    <dd>{Array.isArray(item) && key==="statements" ? <pre className="drift-evidence-text">{item.join("\n")}</pre>
      : Array.isArray(item) && key==="defaults" ? item.length ? <ul>{item.map((tag,index)=><li key={index}>{typeof tag==="object" && tag !== null ? Object.entries(tag).map(([field,text])=>`${field}: ${String(text)}`).join(" · ") : String(tag)}</li>)}</ul> : "No tag defaults"
      : typeof item==="object" ? <pre className="drift-evidence-text">{JSON.stringify(item,null,2)}</pre> : category==="budget"&&key==="monthly_amount" ? String(item).replace(/\.0+$/,"") : String(item)}</dd>
  </div>)}</dl>;
}

// A category never substitutes a failed read for observed absence; retained findings keep their age.
function CategoryEvidence({issue,current,stale}:{issue:ConfigurationIssue;current:boolean;stale:boolean}) {
  const aged=issue.safe_code==="CHECK_STALE";
  const unavailable=["unavailable","conflict","not_checked"].includes(issue.state);
  return <section className="operation-panel drift-category" id={`category-${issue.category}`} aria-labelledby={`drift-${issue.category}`}>
    <div className="drift-category-heading"><h2 id={`drift-${issue.category}`} tabIndex={-1}>{categories[issue.category]}</h2><span className={`badge ${issue.state==="matching"&&current?"active":"review-open"}`}>{categoryLabel(issue)}{issue.state==="matching"&&!current?" (earlier check)":""}</span></div>
    <p className="muted">Evidence: {stamp(issue.evidence_at)}</p>
    {issue.binding_ocid && <p className="technical-id">Managed object: {issue.binding_ocid}</p>}
    {issue.retained && <p className="notice">{stale?"Earlier confirmed drift is retained. Its evidence is out of date; a new complete check is needed before these findings can be cleared.":"Earlier confirmed drift is retained. The latest check could not verify the complete assigned configuration; this evidence has not been cleared."}</p>}
    {issue.state==="missing" && <p>A complete authorized read confirmed that this managed object was missing.</p>}
    {aged&&<p className="notice">This observation is out of date. Earlier values are shown for reference; run a new check to verify the assigned configuration.</p>}
    {unavailable&&!aged && <p className="notice">{issue.state==="not_checked" ? "This category has not been checked against the assigned configuration." : "The check could not verify this managed object. No absence or matching configuration has been established."}</p>}
    <div className="drift-comparison"><section><h3>Expected</h3>{issue.expected ? <Evidence value={issue.expected} category={issue.category}/> : <p>Expected configuration is unavailable.</p>}</section><section><h3>{aged?"Observed (earlier check)":"Observed"}</h3>{aged ? issue.observed?<Evidence value={issue.observed} category={issue.category}/>:<p>No earlier verified observation.</p> : unavailable ? <p>No verified observation.</p> : issue.observed ? <Evidence value={issue.observed} category={issue.category}/> : <p>Object absent.</p>}</section></div>
  </section>;
}

// Summary messages preserve confirmed category counts even while the latest read is incomplete or out of date.
function StatusMessages({summary}:{summary:ConfigurationCheckSummary}) {
  return <span className="configuration-status-messages">{configurationMessages({state:summary.state,stale:summary.stale,confirmed:summary.confirmed_issue_count}).map(message=><span key={message.kind} className={"badge "+configurationMessageClass(message.kind)}>{message.label}</span>)}</span>;
}

// Queue read-only checks with a stable retry key; accepted work never clears prior observations.
export function ConfigurationDrift({identifier,expired,navigate}:{identifier:string|null;expired:()=>void;navigate:(path:string)=>void}) {
  const client=useQueryClient();
  const search=location.search;
  const params=new URLSearchParams(search);
  const [query,setQuery]=useState<ConfigurationDriftQuery>(()=>({...initial,tab:params.get("tab")==="checks"?"checks":"confirmed",...(params.get("tenancy_id")?{tenancy_id:params.get("tenancy_id")!}:{})}));
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[receipt,setReceipt]=useState<ActionReceipt|null>(null);
  const requestKey=useRef(crypto.randomUUID());
  const controller=useRef<AbortController|null>(null),message=useRef<HTMLParagraphElement>(null);
  const focusedCategory=useRef("");
  const completedOperations=useRef(new Set<string>());
  const readDenied=useRef(false);
  const previousPending=useRef<string|null>(null);
  const previousFleetPending=useRef(0);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{setQuery(previous=>({...previous,tab:new URLSearchParams(search).get("tab")==="checks"?"checks":"confirmed",page:1}));},[search]);
  const directory=useQuery({queryKey:["configuration-drift",query],queryFn:({signal})=>api.configurationDrift(query,signal),enabled:!identifier,retry:false,refetchOnWindowFocus:false,placeholderData:(previous,previousQuery)=>{const scope=previousQuery?.queryKey[1] as ConfigurationDriftQuery|undefined;return scope?.tab===query.tab&&scope?.tenancy_id===query.tenancy_id?previous:undefined;},refetchInterval:result=>result.state.data?.checking_count?3000:false});
  const detail=useQuery({queryKey:["configuration-check",identifier],queryFn:({signal})=>api.configurationCheck(identifier!,signal),enabled:Boolean(identifier),retry:false,refetchOnWindowFocus:false,refetchInterval:result=>result.state.data?.pending_operation_id?3000:false});
  const acceptedOperation=useQuery({queryKey:["operations","detail",receipt?.operation_id],queryFn:({signal})=>api.operation(receipt!.operation_id!,signal),enabled:Boolean(receipt?.operation_id),retry:false,refetchOnWindowFocus:false,refetchInterval:result=>["queued","running","waiting"].includes(result.state.data?.operation.state??"queued")?3000:false});

  // Observe actual completion, including fast fleet checks whose matching rows disappear from the confirmed queue.
  useEffect(()=>{
    const operation=acceptedOperation.data?.operation;
    if(!operation||!["succeeded","failed","cancelled","needs_attention"].includes(operation.state)||completedOperations.current.has(operation.id))return;
    completedOperations.current.add(operation.id);
    void Promise.all([client.invalidateQueries({queryKey:["tenancies"]}),client.invalidateQueries({queryKey:["configuration-drift"]}),client.invalidateQueries({queryKey:["configuration-check"]})]);
  },[acceptedOperation.data,client]);

  // A check started elsewhere may finish while this view is open; refresh both management directories then too.
  useEffect(()=>{
    if(identifier ? !detail.data : !directory.data)return;
    const current=detail.data?.pending_operation_id??null,fleet=directory.data?.checking_count??0;
    const completed=Boolean(previousPending.current&&!current)||(previousFleetPending.current>0&&fleet===0);
    previousPending.current=current;previousFleetPending.current=fleet;
    if(completed)void Promise.all([client.invalidateQueries({queryKey:["tenancies"]}),client.invalidateQueries({queryKey:["configuration-drift"]}),client.invalidateQueries({queryKey:["configuration-check"]})]);
  },[detail.data,directory.data,client,identifier]);
  const result=identifier?detail:directory;
  useEffect(()=>{if(!readDenied.current&&[result.error,acceptedOperation.error].some(failure=>failure instanceof ApiError&&[401,403].includes(failure.status))){readDenied.current=true;expired();}},[result.error,acceptedOperation.error,expired]);
  useEffect(()=>{if(receipt)message.current?.focus();},[receipt]);
  useEffect(()=>{
    const category=new URLSearchParams(search).get("category");
    let active=true;
    // The shell focuses the new page first; a requested category then receives focus once.
    if(identifier&&detail.data&&category&&category in categories&&focusedCategory.current!==identifier+category)queueMicrotask(()=>{if(active){document.getElementById(`drift-${category}`)?.focus();focusedCategory.current=identifier+category;}});
    return()=>{active=false;};
  },[identifier,detail.data,search]);

  // An unknown response can be retried with the same request key without admitting duplicate work.
  async function check() {
    if(busy)return;
    setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    try {
      const accepted=await api.startConfigurationCheck({client_request_key:requestKey.current,tenancy_id:identifier},signal);
      if(signal.aborted)return;
      setReceipt(accepted);requestKey.current=crypto.randomUUID();
      await Promise.all([client.invalidateQueries({queryKey:["configuration-drift"]}),client.invalidateQueries({queryKey:["configuration-check"]}),client.invalidateQueries({queryKey:["tenancies"]})]);
    } catch(failure) {
      if(signal.aborted)return;
      if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();
      else setError(failure instanceof ApiError&&failure.status===409 ? "A conflicting operation is in progress or the assignment changed. Refresh the checks before trying again." : failure instanceof ApiError&&failure.status===400 ? "No eligible tenancy could be checked. Refresh and confirm the tenancy is registered with an assigned configuration." : "The check request could not be confirmed. Retry safely or review Operations before trying again.");
    } finally {if(!signal.aborted)setBusy(false);}
  }

  // Sorting and filters share the directory's existing server-side bounded pagination.
  function change(values:Partial<ConfigurationDriftQuery>) {setQuery(previous=>({...previous,...values,page:values.page??1}));}
  // Change only the selected sort and reset the directory page.
  function sort(field:NonNullable<ConfigurationDriftQuery["sort"]>) {change({sort:field,direction:query.sort===field&&query.direction==="asc"?"desc":"asc"});}
  // Keep native browser Back/Forward aligned with the selected checks scope.
  function tab(value:"confirmed"|"checks") {change({tab:value,state:"all"});navigate("/configuration/drift"+(value==="checks"?"?tab=checks":""));}
  const data=directory.data,tenancy=detail.data;
  const pending=Boolean(tenancy?.pending_operation_id||busy);
  const receiptComplete=Boolean(receipt&&((tenancy?.last_operation_id===receipt.operation_id&&!tenancy?.pending_operation_id)||(acceptedOperation.data?.operation.id===receipt.operation_id&&["succeeded","failed","cancelled","needs_attention"].includes(acceptedOperation.data.operation.state))));
  const back=returnPath();
  return <>
    {identifier&&<a className="baseline-backlink" href={back} onClick={event=>followLink(event,back,navigate)}>← {back.startsWith("/operations/")?"Back to operation":back.startsWith("/tenancies/")?"Back to tenancy":back==="/tenancies"?"Back to tenancies":"Back to configuration drift"}</a>}
    <div className="page-heading"><div><p className="eyebrow">CONFIGURATION</p><h1 tabIndex={-1}>{identifier?tenancy?.tenancy_name??"Configuration check":"Configuration drift"}</h1><p>Compare managed objects with the assigned baseline and accepted overrides.</p></div><div className="drift-heading-actions"><button className="button secondary" disabled={result.isFetching||busy} onClick={()=>void result.refetch()}>Refresh</button><button className="button primary" disabled={identifier?pending||!tenancy?.can_check:busy||Boolean(data?.checking_count)} onClick={()=>void check()}>{busy?"Queueing check…":identifier?"Check now":"Check all tenancies"}</button></div></div>
    <p className="notice">Read-only local simulation. These checks do not read or change live OCI resources. A newer published baseline is not configuration drift.</p>
    {error&&<p role="alert" className="alert">{error}</p>}
    {receipt&&!receiptComplete&&<p ref={message} tabIndex={-1} role="status" className="notice">Check request accepted. Results below reflect the latest available evidence; review Operations for execution progress. <a href={`/operations/${receipt.operation_id}`} onClick={event=>followLink(event,`/operations/${receipt.operation_id}`,navigate)}>View operation</a></p>}
    {result.isError&&<p role="alert" className="alert">{result.error instanceof ApiError&&result.error.status===404?"This tenancy check could not be found.":"Configuration checks could not be loaded. Earlier loaded evidence, if any, remains below."} <button className="button secondary" disabled={result.isFetching} onClick={()=>void result.refetch()}>Retry</button></p>}
    {result.isPending&&<p role="status">Loading configuration checks…</p>}
    {identifier ? tenancy&&<>
      <section className="operation-panel"><div className="drift-category-heading"><h2>Assigned configuration</h2><StatusMessages summary={tenancy}/></div><p><a href={`/tenancies/${identifier}`} onClick={event=>followLink(event,`/tenancies/${identifier}`,navigate)}>Open tenancy</a>{tenancy.baseline_id&&<> · <a href={baselineHref(tenancy.baseline_id!,`/configuration/drift/${identifier}`)} onClick={event=>followLink(event,baselineHref(tenancy.baseline_id!,`/configuration/drift/${identifier}`),navigate)}>Assigned baseline v{tenancy.baseline_version_number}</a></>}</p><p>Overrides: {tenancy.override_categories.length?tenancy.override_categories.map(category=>categories[category]).join(", "):"None; all categories inherit the assigned baseline"}</p><p>Last attempt: {stamp(tenancy.checked_at)}</p>{tenancy.stale&&<p className="notice">Check out of date. Earlier results are shown for reference; run a new check to verify the current assigned configuration.</p>}{tenancy.pending_operation_id&&<p role="status">A check or configuration operation is in progress. <a href={`/operations/${tenancy.pending_operation_id}`} onClick={event=>followLink(event,`/operations/${tenancy.pending_operation_id}`,navigate)}>View pending operation</a></p>}{!tenancy.can_check&&!tenancy.pending_operation_id&&<p className="notice">A check is currently unavailable. Review the tenancy's registration and configuration operation before retrying.</p>}{tenancy.state==="unavailable"&&<p className="notice">The latest attempt did not verify all four categories. Earlier confirmed differences remain visible; this tenancy has not been verified as matching.</p>}</section>
      {tenancy.categories.map(issue=><CategoryEvidence key={issue.category} issue={issue} current={!tenancy.stale&&["matching","drifted"].includes(tenancy.state)} stale={Boolean(tenancy.stale)}/>)}
    </> : data&&<>
      <div className="org-tabs" role="group" aria-label="Configuration checks"><button className={"button "+(query.tab==="confirmed"?"primary":"secondary")} aria-pressed={query.tab==="confirmed"} onClick={()=>tab("confirmed")}>Confirmed drift <span>{data.confirmed_count}</span></button><button className={"button "+(query.tab==="checks"?"primary":"secondary")} aria-pressed={query.tab==="checks"} onClick={()=>tab("checks")}>Checks</button></div>
      <p className="muted">{query.tab==="confirmed"?"Tenancies with confirmed missing or different managed objects.":"Latest check attempts for all current managed child tenancies."} {data.stale_count??0} out of date · {data.unavailable_count} unable to verify · {data.unchecked_count} not checked · {data.checking_count} checking</p>
      <section className="table-panel"><div className="table-toolbar drift-toolbar"><label className="search-field">Search tenancies<input type="search" maxLength={128} value={query.query} placeholder="Tenancy name" onChange={event=>change({query:event.target.value})}/></label>{query.tab==="checks"&&<label className="state-filter">Check status<Select value={query.state} onChange={event=>change({state:event.target.value as ConfigurationDriftQuery["state"]})}>{["all","matching","drifted","unavailable","stale","not_checked","checking"].map(state=><option key={state} value={state}>{state==="all"?"All checks":states[state]}</option>)}</Select></label>}{(query.query||query.state!=="all"||query.tenancy_id)&&<button className="button secondary" onClick={()=>setQuery({...initial,tab:query.tab})}>Clear filters</button>}</div>
      {directory.isFetching&&<p className="muted" role="status">Updating check results…</p>}<div className="table-scroll" role="region" aria-label="Configuration check results" aria-busy={directory.isFetching} tabIndex={0}><table><caption className="sr-only">Configuration check results, counts refer to tenancies</caption><thead><tr>{([['name','Tenancy'],['issue_count','Configuration status'],['checked_at','Last attempt (UTC)']] as const).map(([field,label])=><th key={field} aria-sort={query.sort===field?query.direction==="asc"?"ascending":"descending":"none"}><button className="sort-button" onClick={()=>sort(field)}>{label} {query.sort===field?(query.direction==="asc"?"↑":"↓"):"↕"}</button></th>)}<th>Managed objects</th></tr></thead><tbody>{data.items.map(row=><tr key={row.tenancy_id}><td><a href={`/configuration/drift/${row.tenancy_id}?returnTo=${encodeURIComponent(query.tab==="checks"?"/configuration/drift?tab=checks":"/configuration/drift")}`} onClick={event=>followLink(event,`/configuration/drift/${row.tenancy_id}?returnTo=${encodeURIComponent(query.tab==="checks"?"/configuration/drift?tab=checks":"/configuration/drift")}`,navigate)}>{row.tenancy_name}</a></td><td><StatusMessages summary={row}/></td><td>{stamp(row.checked_at)}</td><td><ul className="drift-object-list">{row.categories.map(issue=><li key={issue.category}>{categories[issue.category]}: {categoryLabel(issue)}{issue.retained?" (earlier evidence)":""}</li>)}</ul></td></tr>)}</tbody></table></div>
      {!data.items.length&&<div className="table-feedback"><h2>{query.query||query.state!=="all"||query.tenancy_id?"No checks match these filters":query.tab==="confirmed"?"No confirmed configuration drift":"No current tenancy checks"}</h2><p>{query.tab==="confirmed"?`Check status: ${data.stale_count??0} out of date · ${data.unchecked_count} not checked · ${data.unavailable_count} unable to verify. These states are not confirmed drift.`:"Registered child tenancies appear here even before their first check."}</p>{query.tab==="confirmed"&&<button className="button secondary" onClick={()=>tab("checks")}>View checks</button>}</div>}
      <div className="table-footer"><p>{data.total} tenancies · Page {data.page} of {data.pages}</p><div className="pagination"><label>Rows per page<Select value={query.page_size} onChange={event=>change({page_size:Number(event.target.value) as 10|25|50})}>{[10,25,50].map(size=><option key={size} value={size}>{size}</option>)}</Select></label><button className="button secondary" disabled={data.page<=1} onClick={()=>change({page:data.page-1})}>Previous</button><span>{data.page}</span><button className="button secondary" disabled={data.page>=data.pages} onClick={()=>change({page:data.page+1})}>Next</button></div></div></section>
    </>}
  </>;
}
