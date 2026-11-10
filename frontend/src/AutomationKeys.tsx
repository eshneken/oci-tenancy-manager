import {SigningKeyRotation} from "./SigningKeyRotation";
import type {AutomationKeysView} from "./contracts";
import {operationHref} from "./operationNavigation";
import {followLink} from "./navigation";

const names={within_limit:"Under 30 days",due_soon:"Due within 1 day",overdue:"30 days or older",unknown:"Age unknown",inactive:"Inactive"};

// Display dated public inventory only; a key row is never a usable credential or compliance claim.
export function AutomationKeys({inventory,historical=false,navigate,tenancyId,expired}:{inventory?:AutomationKeysView|null;historical?:boolean;navigate:(path:string)=>void;tenancyId?:string;expired?:()=>void}) {
  const state=inventory?.state??"not_checked";
  const rows=inventory?.keys??[];
  const known=state==="known"||state==="stale";
  const checkedDate=inventory?.checked_at?new Date(inventory.checked_at).toLocaleDateString("en-US",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"}):"";
  const checkedTitle=inventory?.checked_at?new Date(inventory.checked_at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"}):"";
  const href=inventory?.operation_id?operationHref(inventory.operation_id,"automation-keys"):null;
  // Dates stay compact; a native tooltip preserves the exact recorded UTC instant.
  function date(at:string|null|undefined) {
    if(!at)return "Unknown";
    return <time dateTime={at} title={new Date(at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}>{new Date(at).toLocaleDateString("en-US",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"})}</time>;
  }
  return <section id="automation-keys" tabIndex={-1} className="operation-panel signing-key-panel" aria-labelledby="automation-keys-title">
    <div className="required-users-heading"><h2 id="automation-keys-title">Automation signing keys</h2><span className="badge required-user-state">Simulated inventory</span></div>
    <p className="muted">Public key metadata only. Rotation and credential custody are not verified.{!historical&&" Refresh user data above to check this inventory."}</p>
    {state==="not_checked"&&<p className="notice">Signing-key inventory has not been checked.</p>}
    {state==="unavailable"&&<p className="notice">Signing-key inventory is unavailable. Older simulated setups may not have recorded key metadata. Refresh does not create or enroll keys.</p>}
    {state==="stale"&&<p className="notice">Inventory is out of date. These are the last recorded keys.</p>}
    {known&&rows.length===0&&<p className="notice">No signing keys were found in the complete authorized inventory.</p>}
    {known&&Boolean(rows.length)&&<ul className="signing-key-list">{rows.map(key=><li key={key.provider_key_id} className="signing-key-row">
      <div className="signing-key-fingerprint"><span className="muted">Fingerprint</span><code title={key.provider_key_id}>{key.fingerprint}</code></div>
      <dl className="signing-key-facts"><div><dt>Created (UTC)</dt><dd>{date(key.created_at)}</dd></div><div><dt>Key age</dt><dd><span className={"badge "+(key.age_state==="overdue"?"presence-missing":key.age_state==="due_soon"?"review-open":"required-user-state")}>{names[key.age_state]}</span>{key.age_days!=null&&<span className="muted"> · {key.age_days} days</span>}</dd></div><div><dt>30-day date (UTC)</dt><dd>{date(key.retirement_due_at)}</dd></div></dl>
    </li>)}</ul>}
    {inventory?.checked_at&&<p className="muted signing-key-provenance">{historical?"Recorded check":"Inventory checked"}: {href&&!historical?<a href={href} aria-label={`View automation signing-key inventory check, ${checkedDate}`} title={checkedTitle} onClick={event=>followLink(event,href,navigate)}>{date(inventory.checked_at)}</a>:date(inventory.checked_at)}{inventory.age_as_of&&<> · {historical?"Age at observation":"Age assessed"}: {date(inventory.age_as_of)}</>}</p>}
    {!historical&&tenancyId&&expired&&<SigningKeyRotation key={tenancyId} tenancyId={tenancyId} expired={expired} navigate={navigate}/>}
  </section>;
}
