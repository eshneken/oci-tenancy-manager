import {OverrideConflictReview} from "./OverrideConflictReview";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { followLink } from "./navigation";
import { PublishedBaseline } from "./BaselineHistory";
import { baselineHref } from "./baselineNavigation";
import type { ConfigurationPreview,ConfigurationPlanView,OverrideConflict,SaveConfigurationReview } from "./contracts";

const blockerNames={TENANCY_BUSY:"Another operation must finish first",REGISTERED_CHILD_REQUIRED:"Registered child/parent scope needs review",PROVIDER_UNAVAILABLE:"Configuration execution is unavailable",OVERRIDE_REVIEW_REQUIRED:"An overridden statement block needs review",OVERRIDE_CONTEXT_UNAVAILABLE:"Assigned configuration needs review"};
const resultNames={CONFIGURATION_VERIFIED:"Verified locally",CONFIGURATION_UNVERIFIED:"Managed-object readback needs repair",AUTHORIZATION_CHANGED:"Initiating administrator authorization changed",TARGET_CHANGED:"Registered target changed; operator review required",LIFECYCLE_UNAVAILABLE:"Execution is paused or unavailable"};

// One reusable entry/preview/progress flow serves an individual tenancy and the complete fleet batch.
export function ConfigurationRollout({tenancyId,selectedId,initialOperationId,expired,navigate}:{tenancyId?:string;selectedId?:string|null;initialOperationId?:string;expired:()=>void;navigate:(path:string)=>void}) {
  const client=useQueryClient();
  const preview=useQuery({queryKey:["configuration-preview",tenancyId??"all"],queryFn:({signal})=>api.configurationPreview(tenancyId,signal),retry:false,refetchOnWindowFocus:false});
  const [operationId,setOperationId]=useState(initialOperationId);
  useEffect(()=>setOperationId(initialOperationId),[initialOperationId]);
  const progress=useQuery({queryKey:["configuration-update",operationId],queryFn:({signal})=>api.configurationProgress(operationId!,signal),enabled:Boolean(operationId),retry:false,
    refetchInterval:query=>["queued","running"].includes(query.state.data?.state??"")?1000:false});
  const [plan,setPlan]=useState<ConfigurationPlanView|null>(null);
  const [conflict,setConflict]=useState<OverrideConflict|null>(null);
  const requestedPlan=new URLSearchParams(location.search).get("plan");
  const loadedPlan=useQuery({queryKey:["configuration-plan",requestedPlan],queryFn:({signal})=>api.configurationPlan(requestedPlan!,signal),enabled:Boolean(requestedPlan&&requestedPlan!==plan?.id),retry:false});
  const [review,setReview]=useState<ConfigurationPreview|null>(null);
  useEffect(()=>{if(requestedPlan&&!loadedPlan.isFetching&&loadedPlan.data?.id===requestedPlan&&loadedPlan.data.id!==plan?.id){if(loadedPlan.data.state==="accepted"&&loadedPlan.data.operation_id){navigate("/configuration?update="+loadedPlan.data.operation_id);return;}setPlan(loadedPlan.data);setReview(loadedPlan.data.preview);}},[requestedPlan,loadedPlan.data,loadedPlan.isFetching,plan?.id,navigate]);
  useEffect(()=>{if(!requestedPlan&&plan){setReview(null);setPlan(null);setConflict(null);dialog.current?.close();document.querySelector<HTMLElement>("h1")?.focus();}},[requestedPlan]);
  const [showRecipe,setShowRecipe]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null);
  const progressHeading=useRef<HTMLHeadingElement>(null);
  const focusProgress=useRef(false);
  const focusCompletion=useRef(false);
  useEffect(()=>{if(tenancyId&&progress.data?.state==="succeeded"&&focusCompletion.current){document.querySelector<HTMLElement>("h1")?.focus();focusCompletion.current=false;}},[tenancyId,progress.data?.state]);
  useEffect(()=>{if(progress.data&&focusProgress.current){if(tenancyId&&progress.data.state==="succeeded")document.querySelector<HTMLElement>("h1")?.focus();else progressHeading.current?.focus();focusProgress.current=false;}},[progress.data]);
  const recipeLink=useRef<HTMLAnchorElement>(null);
  useEffect(()=>{if(showRecipe)dialog.current?.querySelector<HTMLElement>("#configuration-recipe-title")?.focus();else recipeLink.current?.focus();},[showRecipe]);
  const key=useRef(crypto.randomUUID());
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{if(review){dialog.current?.showModal();if(!conflict&&!showRecipe)heading.current?.focus();}},[Boolean(review),Boolean(conflict)]);
  useEffect(()=>{const failure=preview.error??progress.error??loadedPlan.error;if(failure instanceof ApiError && [401,403].includes(failure.status))expired();},[preview.error,progress.error,loadedPlan.error,expired]);
  const completed=progress.data?.targets.filter(t=>t.state==="verified").length;
  useEffect(()=>{
    if(!progress.data)return;
    void Promise.all(["tenancies","configuration-preview","operations","audit-history"].map(key=>client.invalidateQueries({queryKey:[key]})));
  },[client,progress.data?.state,completed]);

  // A fresh explicit preview is captured at open; later background reads cannot change its approval.
  async function open() {
    if(busy)return;
    setBusy(true);setError("");key.current=crypto.randomUUID();controller.current=new AbortController();const signal=controller.current.signal;
    try{const fresh=await api.createConfigurationPlan({client_request_key:key.current,tenancy_id:tenancyId??null},signal);if(signal.aborted)return;setPlan(fresh);setConflict(null);setReview(fresh.preview);navigate(location.pathname+"?plan="+fresh.id);}
    catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setError("Update preview could not be created. Refresh eligibility and try again.");}
    finally{if(!signal.aborted)setBusy(false);}
  }

  // Save the required exact choices in this plan; live configuration and native jobs stay unchanged.
  async function saveReview(choices:SaveConfigurationReview){
    if(!plan||busy)return;setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    try{const fresh=await api.reviewConfigurationPlan(plan.id,choices,signal);if(signal.aborted)return;setPlan(fresh);setReview(fresh.preview);setConflict(null);await client.invalidateQueries({queryKey:["audit-history"]});}
    catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setError("The review could not be saved. This plan may have changed; reload the preview before continuing.");}
    finally{if(!signal.aborted)setBusy(false);}
  }

  // Recover a lost staged-save response without discarding the plan or applying any live change.
  async function reloadPlan(){
    if(!plan||busy)return;setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    try{const fresh=await api.configurationPlan(plan.id,signal);if(signal.aborted)return;setPlan(fresh);setReview(fresh.preview);setConflict(null);}
    catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setError("Saved review could not be loaded. Try again or close this preview.");}
    finally{if(!signal.aborted)setBusy(false);}
  }

  // Closing an unsubmitted preview changes no desired configuration or queue state.
  function close() {
    if(busy)return;
    if(showRecipe){setShowRecipe(false);return;}
    if(conflict){setConflict(null);setError("");return;}
    dialog.current?.close();setReview(null);setPlan(null);setError("");if(requestedPlan)navigate(location.pathname);
  }

  // Preserve the request key on uncertain responses; accepted commands are replayed, never duplicated.
  async function start() {
    if(!review||!review.baseline||!review.ready_count||review.blockers.length||busy||plan?.state!=="draft")return;
    setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    try {
      const receipt=await api.startConfigurationUpdate({client_request_key:key.current,tenancy_id:tenancyId??null,preview_hash:review.preview_hash,plan_id:plan.id},signal);
      if(signal.aborted)return;
      focusCompletion.current=Boolean(tenancyId);focusProgress.current=Boolean(tenancyId);setOperationId(receipt.operation_id!);dialog.current?.close();setReview(null);setPlan(null);
      if(tenancyId&&requestedPlan)navigate(location.pathname);
      await Promise.all(["tenancies","operations","audit-history"].map(key=>client.invalidateQueries({queryKey:[key]})));
      if(signal.aborted)return;
      if(!tenancyId)navigate("/configuration?update="+receipt.operation_id);
    } catch(failure) {
      if(signal.aborted)return;
      if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();
      else setError(failure instanceof ApiError&&failure.status===409?"The baseline or tenancy set changed. Reload the preview before starting.":"The update could not be confirmed. Retry safely or refresh progress before submitting again.");
    } finally {if(!signal.aborted)setBusy(false);}
  }

  // Retry reuses the accepted baseline/targets and preserves successful per-tenancy results.
  async function retry() {
    if(!operationId||busy)return;
    setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    try {
      await api.retryConfigurationUpdate(operationId,signal);
      if(!signal.aborted)await progress.refetch();
    } catch(failure) {
      if(signal.aborted)return;
      if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();
      else setError("Retry could not be confirmed. Refresh update progress before trying again.");
    } finally {if(!signal.aborted)setBusy(false);}
  }

  const latest=preview.data?.baseline;
  const terminal=progress.data?.state==="succeeded";
  const hasWork=Boolean(preview.data?.ready_count||preview.data?.blockers.length);
  const thisTarget=progress.data?.targets.find(target=>target.tenancy_id===tenancyId);
  const activeProgress=Boolean(operationId&&!terminal&&(!tenancyId||thisTarget?.state!=="verified"));
  // Completed individual work is already represented by the tenancy's selected/verified fields.
  if(tenancyId&&!requestedPlan&&!preview.isError&&!progress.isError&&!review&&((terminal&&progress.data?.baseline.id===latest?.id)||(!hasWork&&!activeProgress)))return null;

  // Acknowledgement dismisses this receipt only; durable operation/audit history remains intact.
  function acknowledge(){setOperationId(undefined);setError("");navigate("/configuration");document.querySelector<HTMLElement>("h1")?.focus();}
  return <section className="operation-panel configuration-rollout" aria-label={tenancyId?"Tenancy baseline update":"Existing tenancy baseline updates"}>
    <h2>{tenancyId?"Baseline updates":"Update existing tenancies"}</h2>
    <div className="configuration-toolbar"><p className="muted">{latest?`Latest published: v${latest.version_number}. Policy, quota, monthly budget and tag defaults.`:"Publish a baseline to enable updates."}</p>
      {latest&&hasWork?<button className="button primary" disabled={busy||preview.isFetching} onClick={()=>void open()}>{tenancyId?`${selectedId===latest.id?"Apply":"Update to"} baseline v${latest.version_number}`:"Update existing tenancies"}</button>:latest&&!requestedPlan&&!operationId&&!preview.isError&&<span className="configuration-current" role="status">No active tenancies need updating.</span>}
    </div>
    {requestedPlan&&loadedPlan.isFetching&&<p role="status">Loading saved update preview…</p>}
    {loadedPlan.isError&&<p role="alert">This update plan could not be loaded. Create a fresh preview to continue.</p>}
    {preview.isError&&<p role="alert">Update eligibility could not be loaded. <button className="button secondary" onClick={()=>void preview.refetch()}>Refresh eligibility</button></p>}
    {progress.isError&&<p role="alert">Update progress could not be loaded. <button className="button secondary" onClick={()=>void progress.refetch()}>Refresh progress</button></p>}
    {error&&!review&&<p className="alert" role="alert">{error}</p>}
    {progress.data&&(!tenancyId||(!terminal&&thisTarget?.state!=="verified"))&&<section className="configuration-progress" aria-label="Baseline update progress"><div className="configuration-toolbar"><h3 ref={progressHeading} tabIndex={-1}>{progress.data.change_kind==="override_change"?"Override update":`Baseline v${progress.data.baseline.version_number}`} · {progress.data.state==="succeeded"?"Verified in simulation":progress.data.state==="needs_attention"?"Needs attention":"Update in progress"}</h3>{!terminal&&<button className="button secondary" onClick={()=>void progress.refetch()}>Refresh progress</button>}</div>
      <p role="status">{completed} of {progress.data.targets.length} {progress.data.targets.length===1?"tenancy":"tenancies"} verified. No OCI resources are changed in this local simulation.</p>
      <ul>{progress.data.targets.map(t=><li key={t.tenancy_id}><a href={"/tenancies/"+t.tenancy_id} onClick={event=>followLink(event,"/tenancies/"+t.tenancy_id,navigate)}>{t.name}</a><span>{t.state==="verified"?"Verified locally":t.state==="pending"?"Pending":resultNames[t.safe_code as keyof typeof resultNames]??"Needs attention"}</span></li>)}</ul>
      <div className="baseline-toolbar">{terminal&&!tenancyId&&<button className="button primary" onClick={acknowledge}>Acknowledge</button>}{progress.data.can_retry&&<button className="button primary" disabled={busy} onClick={()=>void retry()}>Retry incomplete updates</button>}<a href={"/operations/"+operationId} onClick={event=>followLink(event,"/operations/"+operationId,navigate)}>View operation history</a></div>
    </section>}
    <dialog className="workflow-dialog" ref={dialog} aria-labelledby={conflict?"override-review-title":showRecipe?"configuration-recipe-title":"configuration-update-title"} onCancel={event=>{event.preventDefault();close();}}>
      {conflict&&plan?<OverrideConflictReview key={conflict.tenancy_id+"-"+plan.revision} plan={plan} conflict={conflict} busy={busy} error={error} save={saveReview} reload={reloadPlan} back={()=>{setConflict(null);setError("");}}/>:showRecipe&&review?.baseline?<PublishedBaseline headingId="configuration-recipe-title" version={review.baseline} navigate={navigate} back={{path:location.pathname,label:"Back to baseline update",close:()=>setShowRecipe(false)}}/>:<>
        <h2 id="configuration-update-title" tabIndex={-1} ref={heading}>{tenancyId?"Update tenancy baseline":"Update existing tenancies"}</h2>
        {review?.baseline&&<p>Target: <a ref={recipeLink} href={baselineHref(review.baseline.id,location.pathname)} onClick={event=>{if(!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey&&!event.button){event.preventDefault();setShowRecipe(true);}}}>Baseline v{review.baseline.version_number}</a></p>}
        {plan?.state==="stale"&&<p className="alert" role="alert">This plan is stale. The baseline, overrides or tenancy context changed. Create a fresh preview before continuing.</p>}
        <p className="configuration-ready-count"><strong>{review?.ready_count??0}</strong> {review?.ready_count===1?"tenancy":"tenancies"} ready to update</p>
        <p>All exceptions must be cleared before this update can start. Each accepted tenancy runs independently; one failure does not undo successful updates.</p>
        {!!review?.pending_count&&<p className="notice">{review.pending_count} pending tenancies keep their original setup version and can be updated after activation.</p>}
        {!!review?.blockers.length&&<section aria-label="Update exceptions"><h3>Exceptions ({review.blockers.length})</h3><ul>{review.blockers.map(b=><li key={b.tenancy_id}><a href={"/tenancies/"+b.tenancy_id} onClick={event=>{close();followLink(event,"/tenancies/"+b.tenancy_id,navigate);}}>{b.name}</a> · {blockerNames[b.code]}{b.code==="OVERRIDE_REVIEW_REQUIRED"&&<button className="button secondary" disabled={busy||plan?.state!=="draft"} onClick={()=>{setConflict(review.conflicts?.find(c=>c.tenancy_id===b.tenancy_id)??null);setError("");}}>Review override</button>}</li>)}</ul></section>}
        {!!review?.conflicts?.some(c=>(!c.policy_review||c.policy_choice)&&(!c.quota_review||c.quota_choice))&&<details className="configuration-reviewed"><summary>Reviewed · staged</summary>{review.conflicts.filter(c=>(!c.policy_review||c.policy_choice)&&(!c.quota_review||c.quota_choice)).map(c=><div className="configuration-toolbar" key={c.tenancy_id}><span>{c.tenancy_name}</span><button className="button secondary" disabled={busy} onClick={()=>setConflict(c)}>Review decisions</button></div>)}</details>}
        {error&&<p className="alert" role="alert">{error}</p>}
        <p className="notice">Simulated application and readback only. No OCI resources or accounts will be changed.</p>
        <div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={close}>Cancel</button>{(error||plan?.state==="stale")&&<button className="button secondary" disabled={busy} onClick={()=>void open()}>Reload preview</button>}<button className="button primary" disabled={busy||plan?.state!=="draft"||!review?.baseline||!review.ready_count||Boolean(review.blockers.length)} onClick={()=>void start()}>{busy?"Starting…":"Start update"}</button></div>
      </>}
    </dialog>
  </section>;
}
