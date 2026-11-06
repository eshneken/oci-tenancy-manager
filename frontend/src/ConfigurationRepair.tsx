import {useEffect,useRef,useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import {api,ApiError} from "./api";
import {followLink} from "./navigation";
import type {ConfigurationCheckSummary,ConfigurationPreview,ConfigurationRepairRequest} from "./contracts";

type Category=ConfigurationRepairRequest["categories"][number];
const labels:Record<Category,string>={policy:"Policy statements",quota:"Quota statements",budget:"Monthly budget",tags:"Tag defaults"};

// Render closed managed JSON as text; policy and quota statements retain their exact line order.
function repairValue(value:string){
 try{const data=JSON.parse(value) as {statements?:unknown;monthly_amount?:unknown};if(Array.isArray(data.statements))return data.statements.join("\n");if(typeof data.monthly_amount==="string")data.monthly_amount=data.monthly_amount.replace(/\.0+$/,"");return JSON.stringify(data,null,2);}catch{return value;}
}

// Explicit selected-object repair stays on the tenancy's assigned version and never edits overrides.
export function ConfigurationRepair({summary,expired,navigate}:{summary:ConfigurationCheckSummary;expired:()=>void;navigate:(path:string)=>void}) {
 const client=useQueryClient();
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [selected,setSelected]=useState<Category[]>([]),[preview,setPreview]=useState<ConfigurationPreview|null>(null);
 const [operation,setOperation]=useState<string|null>(null),[uncertain,setUncertain]=useState(false);
 const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),launch=useRef<HTMLButtonElement>(null);
 const status=useRef<HTMLParagraphElement>(null);
 const key=useRef(crypto.randomUUID()),controller=useRef<AbortController|null>(null);
 const progress=useQuery({queryKey:["configuration-repair",operation],queryFn:({signal})=>api.configurationProgress(operation!,signal),enabled:Boolean(operation),retry:false,refetchInterval:query=>["queued","running"].includes(query.state.data?.state??"queued")?1500:false});
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{if(open){if(!dialog.current?.open)dialog.current?.showModal();heading.current?.focus();}else dialog.current?.close();},[open,Boolean(preview)]);
 useEffect(()=>{if(operation)status.current?.focus();},[operation]);
 useEffect(()=>{if(progress.data&&!['queued','running'].includes(progress.data.state))void Promise.all(["configuration-check","configuration-drift","tenancies","operations","audit-history"].map(name=>client.invalidateQueries({queryKey:[name]})));},[progress.data?.state,client]);
 useEffect(()=>{if(progress.error instanceof ApiError&&[401,403].includes(progress.error.status))expired();},[progress.error,expired]);
 const eligible=summary.can_check&&!summary.stale&&summary.state==="drifted";
 const issues=summary.categories.filter(issue=>["missing","different"].includes(issue.state));
 // Each newly opened preview has its own replay key; uncertain submissions retain it across modal close and reopen.
 function start(){if(uncertain){setOpen(true);return;}setSelected(issues.map(issue=>issue.category));setPreview(null);setError("");key.current=crypto.randomUUID();setOpen(true);}
 // Keep focus with the launch action and prevent dismissing an unresolved in-flight submission.
 function close(){if(busy)return;dialog.current?.close();setOpen(false);launch.current?.focus();}
 // Fetch a guarded preview or commit its exact fingerprint; browser values never supply OCI content.
 async function submit(){
  if(busy)return;setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
  try {
   if(!preview){const result=await api.previewConfigurationRepair({tenancy_id:summary.tenancy_id,categories:selected as ConfigurationRepairRequest["categories"]},signal);if(!signal.aborted)setPreview(result);}
   else {const receipt=await api.startConfigurationUpdate({client_request_key:key.current,tenancy_id:summary.tenancy_id,preview_hash:preview.preview_hash,repair_categories:selected as ConfigurationRepairRequest["categories"]},signal);if(signal.aborted)return;setUncertain(false);dialog.current?.close();setOperation(receipt.operation_id);setOpen(false);await Promise.all(["configuration-check","configuration-drift","operations","tenancies"].map(name=>client.invalidateQueries({queryKey:[name]})));}
  } catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else if(failure instanceof ApiError&&[400,404,409].includes(failure.status)){setUncertain(false);setPreview(null);setError("The repair context changed or cannot be verified. Run a complete check, then preview again.");}else {if(preview)setUncertain(true);setError("The repair request could not be confirmed. Retry the same request or review Operations before starting new work.");}}
  finally{if(!signal.aborted)setBusy(false);}
 }
 const ready=Boolean(preview&&preview.baseline&&preview.tenancy_id===summary.tenancy_id&&preview.ready_count===1&&!preview.blockers.length&&!preview.pending_count&&selected.every(category=>Boolean(preview.repair_expected?.[category])&&Object.hasOwn(preview.repair_observed??{},category)));
 return <>
  {(eligible||uncertain)&&<button ref={launch} className="button secondary" onClick={start}>{uncertain?"Recover repair request":"Repair configuration"}</button>}
  {operation&&<section className="operation-panel" aria-label="Configuration repair progress"><p ref={status} tabIndex={-1} role="status">{progress.data?.state==="succeeded"?"Selected objects verified. Current check results are shown below.":progress.data?.state==="needs_attention"?"Repair could not be verified. Existing findings remain open.":"Configuration repair queued or running. Findings remain until verification."} <a href={`/operations/${operation}`} onClick={event=>followLink(event,`/operations/${operation}`,navigate)}>View operation</a></p>{progress.isError&&<p role="alert">Repair progress could not be loaded. <button className="button secondary" onClick={()=>void progress.refetch()}>Refresh progress</button></p>}</section>}
  <dialog ref={dialog} className="workflow-dialog" aria-labelledby="repair-title" onCancel={event=>{event.preventDefault();close();}}>
   <h2 id="repair-title" ref={heading} tabIndex={-1}>{preview?"Confirm configuration repair":"Select configuration to repair"}</h2>
   <p>{summary.tenancy_name} · Assigned baseline v{preview?.baseline?.version_number??summary.baseline_version_number}</p>
   <p className="notice">Repair restores selected OTM-managed objects to the assigned baseline and accepted overrides. Other objects and baseline assignments stay unchanged.</p>
   <fieldset disabled={busy||Boolean(preview)}><legend>Confirmed differences</legend>{issues.map(issue=><label className="workflow-check" key={issue.category}><input type="checkbox" checked={selected.includes(issue.category)} onChange={event=>setSelected(previous=>event.target.checked?[...previous,issue.category]:previous.filter(category=>category!==issue.category))}/><span>{labels[issue.category]} · {issue.state==="missing"?"Missing":"Different"}</span></label>)}</fieldset>
   {preview&&ready&&selected.map(category=><section key={category} className="operation-panel"><h3>{labels[category]}</h3><div className="drift-comparison"><section><h4>Currently observed</h4><pre className="drift-evidence-text">{preview.repair_observed?.[category]===null?"Object absent":repairValue(preview.repair_observed![category]!)}</pre></section><section><h4>Expected after repair</h4><pre className="drift-evidence-text">{repairValue(preview.repair_expected![category])}</pre></section></div></section>)}
   {preview&&ready&&<p>Ready to repair {selected.length} managed object{selected.length===1?"":"s"}. The worker will recheck access and bindings, then verify all four categories.</p>}
   {preview&&!ready&&<p role="alert" className="alert">Repair is unavailable for this preview. Run a complete check and review the current assignment before trying again.</p>}
   {uncertain&&<p className="notice">The submission result is unknown. Its selection and request identity are preserved. <a href="/operations" onClick={event=>followLink(event,"/operations",navigate)}>Review Operations</a> before starting different work.</p>}
   {error&&<p role="alert" className="alert">{error}</p>}
   <div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={close}>Cancel</button>{preview&&!uncertain&&<button className="button secondary" disabled={busy} onClick={()=>{setPreview(null);setError("");}}>Change selection</button>}<button className="button primary" disabled={busy||!selected.length||Boolean(preview&&!ready)} onClick={()=>void submit()}>{busy?"Checking…":uncertain?"Retry same request":preview?"Repair selected objects":"Preview repair"}</button></div>
  </dialog>
 </>;
}
