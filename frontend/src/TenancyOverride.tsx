import {useEffect,useRef,useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import {api,ApiError} from "./api";
import {baselineHref} from "./baselineNavigation";
import {followLink} from "./navigation";
import type {ConfigurationPreview,OverrideValues,OverrideEditor} from "./contracts";

// Preserve untouched stored statement boundaries; explicitly edited blocks follow one-line statements.
function list(block:string,original:readonly string[]):string[]{return block===original.join("\n")?[...original]:block.split(/\r\n|\r|\n/).filter(line=>line.trim().length>0);}

// Edit independent authored replacements against the assigned baseline and preview before acceptance.
export function TenancyOverride({tenancyId,expired,navigate}:{tenancyId:string;expired:()=>void;navigate:(path:string)=>void}){
 const client=useQueryClient();
 const autoOpen=new URLSearchParams(location.search).get("override")==="1";
 const [open,setOpen]=useState(autoOpen);
 const queryOpen=useRef(autoOpen);
 const data=useQuery({queryKey:["tenancy-override",tenancyId],queryFn:({signal})=>api.overrideEditor(tenancyId,signal),enabled:open,retry:false});
 const [snapshot,setSnapshot]=useState<OverrideEditor|null>(null);
 const [policy,setPolicy]=useState(false),[quota,setQuota]=useState(false),[budget,setBudget]=useState(false);
 const [policyText,setPolicyText]=useState(""),[quotaText,setQuotaText]=useState(""),[amount,setAmount]=useState("");
 const [review,setReview]=useState<ConfigurationPreview|null>(null),[values,setValues]=useState<OverrideValues|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState("");
 const key=useRef(crypto.randomUUID()),controller=useRef<AbortController|null>(null);
 const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),launch=useRef<HTMLButtonElement>(null);
 useEffect(()=>()=>controller.current?.abort(),[]);
 // Back/Forward tracks explicit editor links without closing ordinarily opened local dialogs.
 useEffect(()=>{if(queryOpen.current===autoOpen)return;queryOpen.current=autoOpen;controller.current?.abort();setBusy(false);setOpen(autoOpen);setSnapshot(null);setReview(null);setValues(null);setError("");if(autoOpen)void data.refetch();},[autoOpen]);
 useEffect(()=>{if(open){dialog.current?.showModal();heading.current?.focus();}else dialog.current?.close();},[open,Boolean(snapshot),Boolean(review)]);
 useEffect(()=>{if(data.error instanceof ApiError&&[401,403].includes(data.error.status))expired();},[data.error,expired]);
 useEffect(()=>{if(open&&data.data&&!data.isFetching&&!snapshot){const current=data.data;setSnapshot(current);setPolicy(current.values.policy_override_statements!=null);setQuota(current.values.quota_override_statements!=null);setBudget(current.values.monthly_budget_override_amount!=null);setPolicyText((current.values.policy_override_statements??current.baseline.content.policy_statements).join("\n"));setQuotaText((current.values.quota_override_statements??current.baseline.content.quota_statements).join("\n"));setAmount(String(current.values.monthly_budget_override_amount??current.baseline.content.monthly_budget_amount).replace(/\.0+$/,""));}},[open,data.data,data.isFetching,snapshot]);

 // Closing discards only local edits; no live configuration or statement object is deleted.
 function close(){if(busy)return;dialog.current?.close();setOpen(false);setSnapshot(null);setReview(null);setValues(null);setError("");if(autoOpen)navigate("/tenancies/"+tenancyId);launch.current?.focus();}

 // Build the exact independent nullable values, then fingerprint them against fresh server context.
 async function preview(){
  if(!snapshot||busy)return;
  const policies=list(policyText,snapshot.values.policy_override_statements??snapshot.baseline.content.policy_statements),quotas=list(quotaText,snapshot.values.quota_override_statements??snapshot.baseline.content.quota_statements);
  if((policy&&(policies.length<1||policies.length>50||policies.some(line=>line.length>2000)))||(quota&&(quotas.length<1||quotas.length>50||quotas.some(line=>line.length>2000)))){setError("Enter 1–50 complete statements per enabled block, one per nonempty line, up to 2,000 characters each.");return;}
  if(budget&&(!/^[0-9]+$/.test(amount)||!/[1-9]/.test(amount))){setError("Enter a positive whole monthly amount without cents.");return;}
  const next:OverrideValues={policy_override_statements:policy?policies as OverrideValues["policy_override_statements"]:null,quota_override_statements:quota?quotas as OverrideValues["quota_override_statements"]:null,monthly_budget_override_amount:budget?amount:null};
  setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
  try{const result=await api.previewOverride({tenancy_id:tenancyId,values:next,context:{tenancy_revision:snapshot.tenancy_revision,baseline_version_id:snapshot.baseline.id,configuration_id:snapshot.configuration?.id??null}},signal);if(!signal.aborted){setValues(next);setReview(result);key.current=crypto.randomUUID();}}
  catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setError("Override preview could not be loaded. Check the values or reload the assigned configuration.");}
  finally{if(!signal.aborted)setBusy(false);}
 }

 // Acceptance freezes this assigned baseline and values; later latest publication cannot retarget it.
 async function apply(){
  if(!review||!values||busy||review.blockers.length||!review.ready_count)return;
  setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
  try{const receipt=await api.applyOverride({client_request_key:key.current,tenancy_id:tenancyId,preview_hash:review.preview_hash,override_mode:true,overrides:values,override_context:{tenancy_revision:snapshot!.tenancy_revision,baseline_version_id:snapshot!.baseline.id,configuration_id:snapshot!.configuration?.id??null}},signal);if(signal.aborted)return;setOpen(false);setSnapshot(null);setReview(null);await Promise.all(["tenancies","tenancy-override","configuration-preview","operations","audit-history"].map(key=>client.invalidateQueries({queryKey:[key]})));if(signal.aborted)return;navigate("/tenancies/"+tenancyId);document.querySelector<HTMLElement>("h1")?.focus();void receipt;}
  catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setError(failure instanceof ApiError&&failure.status===409?"The assigned configuration changed. Reload and review again before applying.":"Acceptance could not be confirmed. Retry safely with the same values or check Operations.");}
  finally{if(!signal.aborted)setBusy(false);}
 }

 return <><button className="button secondary" ref={launch} onClick={()=>{setOpen(true);setError("");void data.refetch();}}>Manage overrides</button>
 <dialog className="workflow-dialog override-dialog" aria-labelledby="tenancy-override-title" ref={dialog} onCancel={event=>{event.preventDefault();close();}}><h2 id="tenancy-override-title" tabIndex={-1} ref={heading}>{review?"Review override changes":"Tenancy overrides"}</h2>
 {data.isPending&&!snapshot?<p role="status">Loading assigned configuration…</p>:data.isError&&!snapshot?<p className="alert" role="alert">Assigned configuration could not be loaded. <button className="button secondary" onClick={()=>void data.refetch()}>Retry</button></p>:snapshot&&<><p><strong>{snapshot.tenancy_name}</strong> · Assigned <a href={baselineHref(snapshot.baseline.id,"/tenancies/"+tenancyId)} target="_blank" rel="noopener noreferrer">baseline v{snapshot.baseline.version_number}</a>{snapshot.configuration?` · Configuration r${snapshot.configuration.revision_number}`:" · Baseline inheritance"}</p><p className="muted">Overrides use this assigned version. A newer published baseline is not applied by editing here.</p>
 <p className="notice">Local simulation only. No OCI resources or accounts will be changed.</p>
 {!review?<><p>Enabled categories replace their complete authored values. Clearing an override inherits the assigned baseline and does not delete the managed object.</p><fieldset className="override-fields" disabled={busy||!snapshot.can_edit}>
 <section className="baseline-block"><label className="workflow-check"><input type="checkbox" checked={policy} onChange={event=>setPolicy(event.target.checked)}/>Override policy statements</label>{policy&&<label><span id="override-policy-label">Policy statement override</span><textarea aria-labelledby="override-policy-label" rows={8} spellCheck={false} maxLength={105000} value={policyText} onChange={event=>setPolicyText(event.target.value)}/></label>}<p className="muted">{policy?"Complete replacement, one statement per nonempty line (1–50 statements).":"Inherits the assigned baseline policy statements."}</p></section>
 <section className="baseline-block"><label className="workflow-check"><input type="checkbox" checked={quota} onChange={event=>setQuota(event.target.checked)}/>Override quota statements</label>{quota&&<label><span id="override-quota-label">Quota statement override</span><textarea aria-labelledby="override-quota-label" rows={8} spellCheck={false} maxLength={105000} value={quotaText} onChange={event=>setQuotaText(event.target.value)}/></label>}<p className="muted">{quota?"Complete replacement, one statement per nonempty line (1–50 statements).":"Inherits the assigned baseline quota statements."}</p></section>
 <section className="baseline-block"><label className="workflow-check"><input type="checkbox" checked={budget} onChange={event=>setBudget(event.target.checked)}/>Override monthly budget</label>{budget&&<label>Monthly budget override ({snapshot.baseline.content.budget_currency})<input inputMode="numeric" pattern="[0-9]+" maxLength={16} value={amount} onChange={event=>setAmount(event.target.value)}/></label>}<p className="muted">{budget?"Positive whole currency units only; currency and monthly period stay fixed.":`Inherits ${String(snapshot.baseline.content.monthly_budget_amount).replace(/\.0+$/,"")} ${snapshot.baseline.content.budget_currency} per month.`}</p></section>
 </fieldset><p className="notice">Tags always inherit the baseline. Required automation and recovery access are managed separately from these authored statements.</p>{!snapshot.can_edit&&<p role="alert">Override changes are unavailable. Review registration or finish the current tenancy operation first.</p>}</>:<><dl className="override-summary"><div><dt>Policy</dt><dd>{values?.policy_override_statements?`${values.policy_override_statements.length} replacement statements`:"Inherit assigned baseline"}</dd></div><div><dt>Quota</dt><dd>{values?.quota_override_statements?`${values.quota_override_statements.length} replacement statements`:"Inherit assigned baseline"}</dd></div><div><dt>Monthly budget</dt><dd>{String(values?.monthly_budget_override_amount??snapshot.baseline.content.monthly_budget_amount).replace(/\.0+$/,"")} {snapshot.baseline.content.budget_currency}{values?.monthly_budget_override_amount?" · Override":" · Inherited"}</dd></div><div><dt>Tags</dt><dd>Inherit assigned baseline</dd></div></dl><div className="override-effective">{[{label:"Effective policy statements",statements:values?.policy_override_statements??snapshot.baseline.content.policy_statements,source:values?.policy_override_statements?"Override":"Assigned baseline"},{label:"Effective quota statements",statements:values?.quota_override_statements??snapshot.baseline.content.quota_statements,source:values?.quota_override_statements?"Override":"Assigned baseline"}].map(block=><details key={block.label}><summary>{block.label} · {block.source}</summary><pre tabIndex={0}>{block.statements.join("\n")}</pre></details>)}<details><summary>Tag defaults · Assigned baseline</summary>{snapshot.baseline.content.tag_defaults?.length?<dl>{snapshot.baseline.content.tag_defaults.map(tag=><div key={tag.key}><dt>{tag.key}</dt><dd>{tag.value}</dd></div>)}</dl>:<p>No tag defaults.</p>}</details></div>{!!review.blockers.length&&<p className="alert" role="alert">This tenancy cannot accept changes yet. Finish its other operation or correct registration, then reload the preview.</p>}<p>Confirming queues application and independent readback. It does not mark the override verified.</p></>}
 {error&&<p className="alert" role="alert">{error}</p>}
 <div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={close}>Cancel</button>{review?<><button className="button secondary" disabled={busy} onClick={()=>{setReview(null);setError("");}}>Back to editing</button><button className="button primary" disabled={busy||Boolean(review.blockers.length)||!review.ready_count} onClick={()=>void apply()}>{busy?"Starting…":"Apply overrides"}</button></>:<button className="button primary" disabled={busy||!snapshot.can_edit} onClick={()=>void preview()}>{busy?"Checking…":"Preview changes"}</button>}{error&&<button className="button secondary" disabled={busy} onClick={()=>{setSnapshot(null);setReview(null);void data.refetch();setError("");}}>Reload configuration</button>}</div>
 </>}{(!snapshot)&&<div className="dialog-actions"><button className="button secondary" onClick={close}>Close</button></div>}</dialog></>;
}
