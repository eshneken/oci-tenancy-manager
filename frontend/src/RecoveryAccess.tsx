import {operationHref} from "./operationNavigation";
import {useEffect,useRef,useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import {api,ApiError} from "./api";
import {followLink} from "./navigation";
import type {RecoveryPasswordDisclosure,RecoveryPasswordRequest} from "./contracts";

const names={not_prepared:"Not prepared",preparing:"Preparing",ready:"Ready",exposed:"Access window open",overdue:"Rotation overdue",rotating:"Rotating",attention:"Reconciliation required",unavailable:"Checks required",inactive:"Inactive"};

// Retrieve only on explicit consent; passwords never enter query/storage/history state.
export function RecoveryAccess({tenancyId,checksRevision,expired,navigate}:{tenancyId:string;checksRevision:string|number;expired:()=>void;navigate:(path:string)=>void}) {
 const client=useQueryClient();
 const metadata=useQuery({queryKey:["tenancies","administrator-access",tenancyId],queryFn:({signal})=>api.administratorAccess(tenancyId,signal),retry:false});
 const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[consent,setConsent]=useState(false);
 const [disclosed,setDisclosed]=useState<RecoveryPasswordDisclosure|null>(null),[visible,setVisible]=useState(false),[copied,setCopied]=useState(false),[error,setError]=useState("");
 const [uncertain,setUncertain]=useState(false);
 const passwordInput=useRef<HTMLInputElement>(null);
 const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),launch=useRef<HTMLButtonElement>(null);
 const controller=useRef<AbortController|null>(null),command=useRef<RecoveryPasswordRequest|null>(null);
 const currentTarget=useRef(tenancyId);currentTarget.current=tenancyId;
 const data=metadata.data;
 // Aborting browser delivery never cancels the durable original rotation obligation.
 useEffect(()=>{
   // A hidden page must not retain or accept a late secret response.
   function hide(){if(document.visibilityState==="hidden"){controller.current?.abort();setDisclosed(null);setVisible(false);setCopied(false);setConsent(false);setBusy(false);setOpen(false);}}
   document.addEventListener("visibilitychange",hide);
   return ()=>{controller.current?.abort();document.removeEventListener("visibilitychange",hide);};
 },[]);
 useEffect(()=>{controller.current?.abort();setDisclosed(null);setVisible(false);setCopied(false);setConsent(false);command.current=null;setUncertain(false);},[tenancyId]);
 useEffect(()=>{controller.current?.abort();setBusy(false);setConsent(false);setDisclosed(null);setVisible(false);setCopied(false);void client.invalidateQueries({queryKey:["tenancies","administrator-access",tenancyId]});},[checksRevision,client,tenancyId]);
 useEffect(()=>{controller.current?.abort();setBusy(false);setConsent(false);setDisclosed(null);setVisible(false);setCopied(false);},[data?.preview_hash,data?.available]);
 useEffect(()=>{if(open){if(!dialog.current?.open)dialog.current?.showModal();heading.current?.focus();}else dialog.current?.close();},[open]);
 useEffect(()=>{if(metadata.error instanceof ApiError&&[401,403].includes(metadata.error.status)){setDisclosed(null);expired();}},[metadata.error,expired]);
 // Closing clears values but preserves an uncertain original request for deliberate retry.
 function close(){controller.current?.abort();setBusy(false);setDisclosed(null);setVisible(false);setCopied(false);setConsent(false);dialog.current?.close();setOpen(false);launch.current?.focus();void metadata.refetch();}
 // Known new requests get new audit records; an uncertain request retains its replay key.
 function start(){setDisclosed(null);setVisible(false);setCopied(false);setConsent(false);setError("");setOpen(true);if(!uncertain)command.current=null;void metadata.refetch();}
 // Programmatic submission obeys the same consent/target guard as click and Enter.
 async function submit(event:React.FormEvent){
   event.preventDefault();if(busy||!consent||!data?.available||!data.preview_hash||data.tenancy_id!==tenancyId)return;
   const target=tenancyId,body=command.current??{client_request_key:crypto.randomUUID(),preview_hash:data.preview_hash,acknowledged:true};
   command.current=body;controller.current=new AbortController();const signal=controller.current.signal;
   setBusy(true);setError("");setDisclosed(null);setVisible(false);setCopied(false);setUncertain(true);
   try{
     const result=await api.recoveryPassword(target,body,signal);
     if(signal.aborted||currentTarget.current!==target)return;
     if(!Number.isFinite(Date.parse(result.rotation_due_at))||Date.parse(result.rotation_due_at)<=Date.now()){
       setDisclosed(null);setConsent(false);setUncertain(false);command.current=null;
       setError("The original access window has ended or its deadline could not be verified. Refresh the access state before requesting access again.");void metadata.refetch();return;
     }
     setDisclosed(result);setUncertain(false);command.current=null;setConsent(false);
     void Promise.all([["tenancies","list"],["tenancies","detail",target],["operations"],["audit-history"]].map(queryKey=>client.invalidateQueries({queryKey})));
   }catch(failure){
     if(signal.aborted)return;
     if(failure instanceof ApiError&&[401,403].includes(failure.status)){setDisclosed(null);expired();}
     else if(failure instanceof ApiError&&[400,404,409,422].includes(failure.status)){
       setUncertain(false);command.current=null;setConsent(false);setError("Access is no longer available with these checks. Refresh user data and review the current access state.");void metadata.refetch();
     }else setError("The request may have been accepted. Retry the same request; its original rotation deadline will not change.");
   }finally{if(!signal.aborted)setBusy(false);}
 }
 // Copy is explicit; the browser/OS owns clipboard retention after this interaction.
 async function copy(){if(!disclosed)return;try{await navigator.clipboard.writeText(disclosed.password);setCopied(true);}catch{setError("Clipboard access is unavailable. Use Show password to copy it manually.");}}
 const due=disclosed?.rotation_due_at??data?.rotation_due_at;
 const operationId=disclosed?.operation_id??data?.operation_id;
 useEffect(()=>{if(disclosed)passwordInput.current?.focus();},[Boolean(disclosed)]);
 useEffect(()=>{if(!due)return;const timer=setTimeout(()=>{controller.current?.abort();setBusy(false);setDisclosed(null);setVisible(false);setConsent(false);void metadata.refetch();},Math.max(0,new Date(due).getTime()-Date.now()));return ()=>clearTimeout(timer);},[due]);
 const guidance=data?.state==="not_prepared"?"Password custody was not prepared for this tenancy. New tenancy setup prepares access; this dialog does not configure it.":data?.state==="preparing"?"Password setup is still in progress. Review the setup operation.":data?.state==="rotating"?"The password is being rotated. Access will become available after verification.":data&&["overdue","attention"].includes(data.state)?"Password rotation requires administrator attention. Review the operation and the independent recovery procedure; do not retry a password reset.":"Access requires current user and recovery-control checks plus enabled operational notices. Review those requirements before requesting access.";
 return <section className="recovery-access administrator-access-card" aria-label="Administrator access">
  <div className="recovery-user-heading"><h3>Administrator access</h3><button type="button" ref={launch} className="button secondary" disabled={metadata.isPending||!data||data.state==="inactive"} onClick={start}>Request password</button></div>
  <div className="recovery-access-summary"><span className={"badge "+(data?.state==="ready"?"active":data&&["attention","overdue"].includes(data.state)?"presence-missing":"required-user-state")}>{data?names[data.state]:metadata.isError?"Access unavailable":"Loading access…"}</span></div>
  {due&&<p className="muted">Password rotation due <time dateTime={due}>{new Date(due).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}</time></p>}
  {metadata.isError&&<p role="alert" className="alert">Unable to load access state. <button className="text-link" onClick={()=>void metadata.refetch()}>Retry access state</button></p>}
  <dialog ref={dialog} className="workflow-dialog" aria-labelledby="recovery-access-title" onCancel={event=>{event.preventDefault();close();}}>
   {open&&<form onSubmit={event=>void submit(event)}>
    <h2 id="recovery-access-title" ref={heading} tabIndex={-1}>Administrator access</h2><h3>{data?.tenancy_name??"Tenancy"}</h3>
    <p className="notice">Local simulation only. This password cannot be used to sign in to OCI.</p>
    {data?.user_name&&<p>Recovery username: <strong>{data.user_name}</strong></p>}
    {due&&<p className="notice">The current access window ends at <strong>{new Date(due).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}</strong>. Requesting the password again does not extend it.</p>}
    {!data?.available&&<p className="notice">{guidance}</p>}
    <details className="operator-instructions"><summary>Access and cleanup instructions</summary><p>Requests are audited and notify the owner, manager and other administrators. Password rotation is scheduled four hours after the first authorized request, even if you close this dialog or sign out. Rotation does not promise to end an existing OCI console session.</p><p>Keep the password private. It is cleared from this page when the dialog closes or the page is hidden. Copying places it on your operating system clipboard; clear that clipboard after use.</p></details>
    {disclosed?<div className="recovery-password-value"><label htmlFor="recovery-password">Recovery password</label><input ref={passwordInput} id="recovery-password" type={visible?"text":"password"} value={disclosed.password} readOnly autoComplete="off" spellCheck={false}/><div className="dialog-actions"><button type="button" className="button secondary" onClick={()=>setVisible(value=>!value)}>{visible?"Hide password":"Show password"}</button><button type="button" className="button secondary" onClick={()=>void copy()}>{copied?"Copied":"Copy password"}</button></div></div>:<label className="workflow-check"><input type="checkbox" checked={consent} disabled={busy||!data?.available} onChange={event=>setConsent(event.target.checked)}/><span>I understand this request is audited, notifies the responsible contacts and starts or joins the original four-hour rotation window.</span></label>}
    {error&&<p className="alert" role="alert">{error}</p>}
    <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>Close</button>{!disclosed&&<button type="submit" className="button primary" disabled={busy||!consent||!data?.available}>{busy?"Retrieving…":uncertain?"Retry same request":"Get password"}</button>}</div>
    {operationId&&<p className="recovery-access-operation"><a href={operationHref(operationId)} onClick={event=>{close();followLink(event,operationHref(operationId),navigate);}}>View password operation</a></p>}
   </form>}
  </dialog>
 </section>;
}
