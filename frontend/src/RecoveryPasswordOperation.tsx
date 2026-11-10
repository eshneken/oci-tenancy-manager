import {useEffect,useState} from "react";
import type {OperationSummary, RecoveryPasswordProgress} from "./contracts";
import {followLink} from "./navigation";

// Retain the original obligation even when a later credential generation is already active.
export function RecoveryPasswordOperation({operation,progress,navigate}:{operation:OperationSummary;progress:RecoveryPasswordProgress;navigate:(path:string)=>void}) {
  const [observedNow,setObservedNow]=useState(()=>Date.now());
  // Refresh display at the recorded deadline even if polling returns structurally identical data.
  useEffect(()=>{
    const now=Date.now();setObservedNow(now);
    const due=progress.rotation_due_at?Date.parse(progress.rotation_due_at):null;
    if(due===null||due<=now)return;
    const timer=setTimeout(()=>setObservedNow(Date.now()),due-now);
    return ()=>clearTimeout(timer);
  },[progress.rotation_due_at]);
  const setup=progress.phase==="setup";
  const attention=["needs_attention","failed","cancelled"].includes(operation.state);
  const overdue=!setup&&operation.state!=="succeeded"&&Boolean(progress.rotation_due_at&&Date.parse(progress.rotation_due_at)<=observedNow);
  const label=operation.state==="succeeded"?(setup?"Prepared in simulation":"Rotated in simulation"):
    attention?"Reconciliation required":operation.state==="running"?(setup?"Preparing":"Rotating"):
    overdue?"Rotation overdue":setup?"Preparation pending":"Scheduled";
  const href="/tenancies/"+progress.tenancy_id;
  return <section className="operation-panel recovery-password-progress" aria-labelledby="recovery-progress-title">
    <div className="required-users-heading"><h2 id="recovery-progress-title">{setup?"Password preparation":"Password rotation"}</h2><span className={"badge "+(operation.state==="succeeded"?"active":attention||overdue?"presence-missing":"required-user-state")}>{label}</span></div>
    <dl className="operation-facts">
      <div><dt>Recovery username</dt><dd>{progress.user_name}</dd></div>
      {!setup&&<div><dt title="Authorized intentional requests, including attempts whose response was lost. Retrying the same request does not increase this count.">Authorized requests</dt><dd>{progress.request_count}</dd></div>}
      {progress.first_request_at&&<div><dt>First authorized request (UTC)</dt><dd><time dateTime={progress.first_request_at}>{timestamp(progress.first_request_at)}</time></dd></div>}
      {progress.rotation_due_at&&<div><dt>Original rotation deadline (UTC)</dt><dd><time dateTime={progress.rotation_due_at}>{timestamp(progress.rotation_due_at)}</time></dd></div>}
      {operation.completed_at&&<div><dt>{operation.state==="succeeded"?"Verified":"Operation ended"} (UTC)</dt><dd><time dateTime={operation.completed_at}>{timestamp(operation.completed_at)}</time></dd></div>}
    </dl>
    {(attention||overdue)&&<p className="alert" role="alert">{attention&&setup?"Password custody has not been verified by this operation. Review the recorded setup outcome before continuing onboarding.":attention?"Review the recorded outcome and the independent recovery procedure. A failed or uncertain operation does not clear the original rotation obligation.":"The original deadline has passed without a verified rotation. Review the recorded operation; the deadline has not been extended."}</p>}
    <a href={href} onClick={event=>followLink(event,href,navigate)}>Open tenancy</a>
    {!setup&&<details className="operator-instructions"><summary>How the access window works</summary><p>The first authorized request fixes the four-hour rotation deadline, even if password delivery fails. Further requests join that window. Closing the dialog or signing out does not cancel rotation. Verified rotation changes the password; it does not guarantee termination of existing console sessions.</p><p>This is the record for this operation. Later access requests after a verified rotation are tracked in a new operation.</p></details>}
  </section>;
}

// Display exact recorded UTC instants consistently without converting them into a new deadline.
function timestamp(value:string) {
  return new Date(value).toLocaleString("en-US",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false})+" UTC";
}
