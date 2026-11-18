import {followLink} from "./navigation";
import {operationHref} from "./operationNavigation";
import type {ImportedAccessView} from "./contracts";

const names={not_checked:"Not checked",matching:"Verified in simulation",drifted:"Access drift",unavailable:"Unable to verify",stale:"Check out of date"};
const memberNames={matching:"Matching",missing:"Missing identity",different:"Access changed",unknown:"Unable to verify"};

// Imported humans have separate access evidence; required service-user health cannot cover them.
export function ImportedAccess({value,navigate}:{value:ImportedAccessView;navigate:(path:string)=>void}) {
  const members=value.members??[], unmanaged=value.unmanaged_user_ocids??[];
  return <section className="operation-panel imported-access" aria-labelledby="imported-access-title">
    <div className="recovery-user-heading"><h3 id="imported-access-title">Adopted member access</h3><span className={"badge "+(value.state==="matching"?"active":value.state==="drifted"?"presence-missing":"required-user-state")}>{names[value.state??"not_checked"]}</span></div>
    <p className="muted">Refresh user data checks adopted identities, their recorded grants and scopes, and newly discovered unmanaged accounts. Checks do not change access.</p>
    {members.length>0&&<ul>{members.map(member=><li key={member.association_id}>{member.user_name}: {memberNames[member.state]}{value.state==="stale"?" (earlier evidence)":""}</li>)}</ul>}
    {unmanaged.length>0&&<details><summary>{unmanaged.length} newly discovered unmanaged accounts</summary><ul>{unmanaged.map(id=><li key={id} className="technical-id">{id}</li>)}</ul><p>Review these identities with the tenancy administrator in OCI. Atlas does not change unmanaged accounts or offer adoption after import.</p></details>}
    {value.checked_at&&<p className="muted">Checked (UTC): <time dateTime={value.checked_at}>{new Date(value.checked_at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}</time>{value.operation_id&&<> · <a href={operationHref(value.operation_id)} onClick={event=>followLink(event,operationHref(value.operation_id!),navigate)}>View check operation</a></>}</p>}
  </section>;
}
