import {useEffect,useRef,useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import {api,ApiError} from "./api";
import {followLink} from "./navigation";
import type {RecoveryConsoleView,RecoveryNetworkPreview,RecoveryNetworkRequest} from "./contracts";

// Repair one existing owned perimeter; recovery passwords and unrelated IAM rules are untouched.
export function RecoveryNetworkRepair({tenancyId,eligible,policy,expired,navigate}:{
  tenancyId:string;eligible:boolean;policy?:RecoveryConsoleView;expired:()=>void;navigate:(path:string)=>void;
}) {
  const client=useQueryClient();
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[consent,setConsent]=useState(false);
  const [preview,setPreview]=useState<RecoveryNetworkPreview|null>(null),[error,setError]=useState("");
  const [operation,setOperation]=useState<string|null>(null),[uncertain,setUncertain]=useState(false);
  const [refreshFailed,setRefreshFailed]=useState(false);
  const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),launch=useRef<HTMLButtonElement>(null);
  const status=useRef<HTMLDivElement>(null);
  const restoreFocus=useRef(false);
  const controller=useRef<AbortController|null>(null),key=useRef(crypto.randomUUID());
  const submitted=useRef<RecoveryNetworkRequest|null>(null),refreshed=useRef<string|null>(null);
  const context=JSON.stringify([eligible,policy?.checked_at,policy?.desired_fingerprint,policy?.observed_fingerprint]);
  const activeContext=useRef(context);activeContext.current=context;
  const progress=useQuery({queryKey:["operations","recovery-network",operation],queryFn:({signal})=>api.operation(operation!,signal),enabled:Boolean(operation),retry:false,refetchInterval:query=>["queued","running"].includes(query.state.data?.operation.state??"queued")?1500:false});
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{if(!open&&!busy&&restoreFocus.current){restoreFocus.current=false;(launch.current??document.getElementById("required-users-title"))?.focus();}},[open,busy]);
  useEffect(()=>{if(operation)status.current?.focus();},[operation]);
  useEffect(()=>{if(open){if(!dialog.current?.open)dialog.current?.showModal();heading.current?.focus();}else dialog.current?.close();},[open,Boolean(preview)]);
  useEffect(()=>{setConsent(false);if(!uncertain){if(preview||open)setError("The preview is out of date. Refresh user data and review a new preview before submitting.");setPreview(null);}},[context]);
  useEffect(()=>{
    if(progress.error instanceof ApiError&&[401,403].includes(progress.error.status))expired();
  },[progress.error,expired]);
  useEffect(()=>{
    if(!operation||!progress.data||["queued","running"].includes(progress.data.operation.state)||refreshed.current===operation)return;
    refreshed.current=operation;
    void Promise.all(["tenancies","operations","audit-history"].map(name=>client.invalidateQueries({queryKey:[name]})));
    if(progress.data.operation.state!=="succeeded")return;
    // A separate real check reads the persisted provider result; no success toast invents evidence.
    void api.checkRequiredUsers(tenancyId,{client_request_key:crypto.randomUUID()}).then(()=>client.invalidateQueries({queryKey:["tenancies","required-users",tenancyId]})).catch(failure=>{
      if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setRefreshFailed(true);
    });
  },[operation,progress.data,client,tenancyId,expired]);

  // Closing restores focus; an in-flight command cannot be dismissed or retargeted.
  function close(){if(busy&&submitted.current)return;controller.current?.abort();restoreFocus.current=true;setBusy(false);dialog.current?.close();setOpen(false);}
  // Every new context starts unchecked; uncertain delivery retains the original replay command.
  async function start(){
    if(uncertain){setOpen(true);return;}
    setOpen(true);setBusy(true);setConsent(false);setPreview(null);setError("");
    submitted.current=null;
    key.current=crypto.randomUUID();controller.current=new AbortController();const signal=controller.current.signal;
    const requestedContext=activeContext.current;
    try {const result=await api.previewRecoveryNetworks(tenancyId,signal);if(!signal.aborted){if(result.tenancy_id!==tenancyId||requestedContext!==activeContext.current)throw new Error("Changed target or context");setPreview(result);}}
    catch(failure){if(signal.aborted)return;if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();else setError("Repair is unavailable or the reviewed context changed. Refresh user data and review the current recovery boundary before trying again.");}
    finally{if(!signal.aborted)setBusy(false);}
  }
  // Programmatic submission obeys the same unchecked-consent and exact-preview guards as clicks.
  async function submit(event:React.FormEvent){
    event.preventDefault();if(busy||!consent||!preview||preview.tenancy_id!==tenancyId||(!uncertain&&!eligible))return;
    setBusy(true);setError("");controller.current=new AbortController();const signal=controller.current.signal;
    const command=uncertain&&submitted.current?submitted.current:{client_request_key:key.current,preview_hash:preview.preview_hash,acknowledged:true};
    submitted.current=command;
    try {const receipt=await api.repairRecoveryNetworks(tenancyId,command,signal);if(signal.aborted)return;
      dialog.current?.close();setOperation(receipt.operation_id);setUncertain(false);setOpen(false);
      await Promise.all(["tenancies","operations","audit-history"].map(name=>client.invalidateQueries({queryKey:[name]})));
    } catch(failure){if(signal.aborted)return;
      if(failure instanceof ApiError&&[401,403].includes(failure.status))expired();
      else if(failure instanceof ApiError&&[400,404,409].includes(failure.status)){setPreview(null);setConsent(false);setUncertain(false);setError("The repair preview changed or repair is blocked. Refresh user data, then open a new preview.");}
      else {setUncertain(true);setError("The request result is unknown. Retry this same request or review Operations before starting different work.");}
    } finally{if(!signal.aborted)setBusy(false);}
  }
  const state=progress.data?.operation.state;
  return <>
    {(eligible||uncertain)&&<button ref={launch} type="button" className="button secondary" disabled={busy||Boolean(operation&&(!state||["queued","running","needs_attention"].includes(state)))} onClick={()=>void start()}>{uncertain?"Recover repair request":"Repair approved networks"}</button>}
    {operation&&<div ref={status} tabIndex={-1} className="notice" role="status"><p>{state==="succeeded"?"Approved networks verified in simulation. Review the separately dated user checks below.":state==="needs_attention"?"Repair has an uncertain effect. Independent reconciliation is required; do not retry the write.":state==="failed"?"Repair was blocked or its context changed. Review the operation before taking further action.":"Approved-network repair queued or running."} <a href={`/operations/${operation}`} onClick={event=>followLink(event,`/operations/${operation}`,navigate)}>View operation</a></p>
      {progress.isError&&<p role="alert">Unable to load repair progress. <button className="button secondary" onClick={()=>void progress.refetch()}>Refresh</button></p>}
      {refreshFailed&&<p role="alert">Repair finished, but a user-data refresh could not be started. Use Refresh user data to check the current boundary.</p>}
    </div>}
    <dialog ref={dialog} className="workflow-dialog" aria-labelledby="network-repair-title" onCancel={event=>{event.preventDefault();close();}}>
      <form onSubmit={event=>void submit(event)}>
        <h2 id="network-repair-title" ref={heading} tabIndex={-1}>Repair approved recovery networks</h2>
        <p className="notice">Local simulation only. No OCI resources, users or credentials will be changed.</p>
        {busy&&!preview&&<p role="status">Checking the exact owned perimeter and conditional-write authority…</p>}
        {preview&&<><h3>{preview.tenancy_name}</h3><div className="drift-comparison"><section><h4>Current network configuration</h4><p>{preview.current_network_count} approved network range{preview.current_network_count===1?"":"s"}</p><p className="technical-id" title={preview.observed_fingerprint}>Revision {preview.observed_fingerprint.slice(0,12)}</p></section><section><h4>Configured replacement</h4><p>{preview.desired_network_count} approved network range{preview.desired_network_count===1?"":"s"}</p><p className="technical-id" title={preview.desired_fingerprint}>Revision {preview.desired_fingerprint.slice(0,12)}</p></section></div>
        <p>This replaces only this recovery user's owned network perimeter with the administrator-configured network list. It may change where recovery administrators can sign in. Existing MFA exemption and deny-outside rules must remain intact.</p>
        <label className="workflow-check"><input type="checkbox" checked={consent} disabled={busy} onChange={event=>setConsent(event.target.checked)}/><span>I reviewed this tenancy and understand that replacing the approved networks may restrict or expand recovery sign-in locations.</span></label></>}
        {error&&<p className="alert" role="alert">{error}</p>}
        <div className="dialog-actions"><button type="button" className="button secondary" disabled={busy&&Boolean(submitted.current)} onClick={close}>Cancel</button><button type="submit" className="button primary" disabled={busy||!preview||!consent||(!uncertain&&!eligible)}>{busy?submitted.current?"Submitting…":"Checking…":uncertain?"Retry same request":"Confirm network repair"}</button></div>
      </form>
    </dialog>
  </>;
}
