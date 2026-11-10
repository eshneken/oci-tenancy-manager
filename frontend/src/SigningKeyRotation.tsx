import {useEffect,useRef,useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import {api,ApiError} from "./api";
import type {SigningKeyRequest,SigningKeyView} from "./contracts";
import {operationHref} from "./operationNavigation";
import {followLink} from "./navigation";

const names:Record<SigningKeyView["state"],string>={not_prepared:"Rotation not prepared",preparing:"Preparing signing credential",scheduled:"Next rotation scheduled",rotating:"Rotation in progress",attention:"Rotation needs attention",overdue:"Retirement overdue",inactive:"Tenancy inactive",unavailable:"Rotation unavailable"};

// Only explicit preview-bound requests start/resume work; status reads never retrieve key material.
export function SigningKeyRotation({tenancyId,expired,navigate}:{tenancyId:string;expired:()=>void;navigate:(path:string)=>void}) {
  const client=useQueryClient(),dialog=useRef<HTMLDialogElement>(null),launch=useRef<HTMLButtonElement>(null),heading=useRef<HTMLHeadingElement>(null),status=useRef<HTMLDivElement>(null);
  const queryKey=["tenancies","signing-key-rotation",tenancyId];
  const query=useQuery({queryKey,queryFn:({signal})=>api.signingKeyRotation(tenancyId,signal),retry:false,refetchInterval:query=>["preparing","rotating","overdue"].includes(query.state.data?.state??"")?1000:false});
  const [open,setOpen]=useState(false),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState("");
  const command=useRef<SigningKeyRequest|null>(null),controller=useRef<AbortController|null>(null),currentTarget=useRef(tenancyId);
  currentTarget.current=tenancyId;
  const denied=query.error instanceof ApiError&&[401,403].includes(query.error.status);
  const data=denied?undefined:query.data;
  useEffect(()=>{if(denied)expired();},[denied,expired]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{setConsent(false);},[data?.preview_hash]);
  useEffect(()=>{controller.current?.abort();setConsent(false);setOpen(false);setBusy(false);setUncertain(false);command.current=null;},[tenancyId]);
  useEffect(()=>{if(open){if(!dialog.current?.open)dialog.current?.showModal();heading.current?.focus();}else dialog.current?.close();},[open]);
  // Only metadata is refreshed here; completed work invalidates other cached views without SDK calls.
  useEffect(()=>{
    if(!data)return;
    for(const key of [["tenancies","list"],["tenancies","detail",tenancyId],["tenancies","required-users",tenancyId],["operations"],["audit-history"]])void client.invalidateQueries({queryKey:key});
  },[data?.state,data?.generation,tenancyId,client]);
  // Closing a dialog does not cancel accepted durable work or discard an uncertain retry key.
  function close(){setConsent(false);setOpen(false);dialog.current?.close();launch.current?.focus();}
  // Every new confirmation opens unchecked and obtains a fresh server-owned preview.
  function start(){if(!uncertain)command.current=null;setConsent(false);setError("");setOpen(true);void query.refetch();}
  // Click, Enter and programmatic form submission require the same consent and exact target guard.
  async function submit(event:React.FormEvent){
    event.preventDefault();
    if(!consent||busy||!data||data.tenancy_id!==tenancyId||query.isFetching)return;
    if(!command.current&&(!data.available||!data.preview_hash))return;
    const target=tenancyId;
    const body:SigningKeyRequest=command.current??{client_request_key:crypto.randomUUID(),preview_hash:data.preview_hash!,acknowledged:true,action:data.state==="attention"?"resume":"rotate"};
    command.current=body;controller.current=new AbortController();const signal=controller.current.signal;
    setBusy(true);setUncertain(true);setError("");
    try{
      const receipt=await api.requestSigningKeyRotation(target,body,signal);
      if(signal.aborted||currentTarget.current!==target)return;
      command.current=null;setUncertain(false);setConsent(false);setOpen(false);dialog.current?.close();
      client.setQueryData<SigningKeyView>(queryKey,value=>value?{...value,state:"rotating",available:false,operation_id:receipt.operation_id}:value);
      void client.invalidateQueries({queryKey});
      for(const key of [["tenancies","required-users",target],["tenancies","detail",target],["tenancies","list"],["operations"],["audit-history"]])void client.invalidateQueries({queryKey:key});
      status.current?.focus();
    }catch(failure){
      if(signal.aborted)return;
      if(failure instanceof ApiError&&[401,403].includes(failure.status)){setUncertain(false);expired();}
      else if(failure instanceof ApiError&&[400,404,409,422].includes(failure.status)){
        command.current=null;setUncertain(false);setConsent(false);setError("The preview changed or rotation is unavailable. Reload the preview and review the current state.");void query.refetch();
      }else setError("The request may have been accepted. Retry the same request to avoid starting another rotation.");
    }finally{if(!signal.aborted)setBusy(false);}
  }
  // Date-only text stays compact; the full UTC instant is available on hover/focus.
  function date(at:string){return <time dateTime={at} title={new Date(at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}>{new Date(at).toLocaleDateString("en-US",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"})}</time>;}
  if(query.isPending)return <p role="status" className="muted">Loading rotation status…</p>;
  return <div className="signing-rotation" aria-label="Automatic key rotation" role="region" ref={status} tabIndex={-1}>
    {query.isError&&<p role="alert" className="notice">Unable to load signing-key rotation status. <button className="text-link" type="button" disabled={query.isFetching} onClick={()=>void query.refetch()}>Retry rotation status</button></p>}
    {data&&<>
      <div className="required-users-heading"><h3>Automatic rotation</h3>
      {(data.available||uncertain)&&<button type="button" ref={launch} className="button secondary" onClick={start}>{uncertain?"Recover request":data.state==="attention"?"Resume rotation":"Rotate key"}</button>}</div>
      <p className="signing-rotation-summary"><span className={"badge "+(["attention","overdue"].includes(data.state)?"presence-missing":"required-user-state")}>{names[data.state]}</span>{(data.generation??0)>0&&<span>Current key: generation {data.generation}</span>}</p>
      {data.state==="not_prepared"&&<p className="muted">This tenancy has not completed versioned signing-credential setup. Refreshing inventory does not enroll it.</p>}
      {data.state==="scheduled"&&<p className="muted">Rotate key requests rotation now. Waiting for the scheduled date does not pause provider work.</p>}
      {data.state==="rotating"&&<p className="notice" role="status">New provider requests are paused for this tenancy. Existing work and recovery access finish before the key is switched.</p>}
      {data.state==="overdue"&&<p className="notice" role="status">The original retirement deadline has passed. Provider work remains restricted while this obligation is resolved.</p>}
      {data.state==="attention"&&<p className="notice">The original rotation is unresolved. {data.available?"Resume it to retry verification; no new key pair will be generated.":"Review the rotation operation and restore the required context before resuming."} Use independent recovery if automation access is unavailable.</p>}
      <dl className="signing-key-facts">{data.starts_at&&data.state==="scheduled"&&<div><dt>Next automatic rotation (UTC)</dt><dd>{date(data.starts_at)}</dd></div>}{data.retire_at&&<div><dt>Retirement deadline (UTC)</dt><dd>{date(data.retire_at)}</dd></div>}{data.last_rotated_at&&data.last_rotation_operation_id&&<div><dt>Last completed rotation (UTC)</dt><dd><a href={operationHref(data.last_rotation_operation_id)} onClick={event=>followLink(event,operationHref(data.last_rotation_operation_id),navigate)} aria-label="View last completed key rotation">{date(data.last_rotated_at)}</a></dd></div>}</dl>
      {data.operation_id&&<p className="muted"><a href={operationHref(data.operation_id)} onClick={event=>followLink(event,operationHref(data.operation_id),navigate)}>{data.state==="scheduled"?"View scheduled rotation":"View rotation operation"}</a></p>}
    </>}
    <dialog ref={dialog} className="workflow-dialog" aria-labelledby="signing-rotation-title" onCancel={event=>{event.preventDefault();if(!busy)close();}}>
      {open&&<form onSubmit={event=>void submit(event)}>
        <h2 ref={heading} tabIndex={-1} id="signing-rotation-title">{uncertain?"Recover rotation request":data?.state==="attention"?"Resume key rotation":"Rotate automation signing key"}</h2><h3>{data?.tenancy_name}</h3>
        <p className="notice">Local simulation. No OCI keys or credentials will be changed.</p>
        <p>{uncertain?"This retries the original request without creating another rotation.":data?.state==="attention"?"This resumes the unresolved operation without generating another key pair.":"This starts the existing scheduled operation now. It does not create another rotation."} An accepted rotation pauses new provider requests while the replacement is verified and the old key is retired. Other tenancies remain available.</p>
        <details className="operator-instructions"><summary>Rotation steps</summary><ol><li>Wait for existing work and any recovery-password window to finish.</li><li>Stage one recoverable candidate, upload it and verify its exact signer.</li><li>Switch credentials, then delete the managed old key and verify its absence.</li></ol></details>
        <label className="workflow-check"><input type="checkbox" checked={consent} disabled={busy||query.isFetching} onChange={event=>setConsent(event.target.checked)}/><span>I understand new provider requests for {data?.tenancy_name} will pause until this rotation completes.</span></label>
        {error&&<p className="alert" role="alert">{error}</p>}
        <div className="dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={close}>Cancel</button><button type="submit" className="button primary" disabled={!consent||busy||query.isFetching||(!data?.available&&!uncertain)}>{busy?"Submitting…":uncertain?"Retry same request":data?.state==="attention"?"Resume rotation":"Rotate now"}</button></div>
      </form>}
    </dialog>
  </div>;
}
