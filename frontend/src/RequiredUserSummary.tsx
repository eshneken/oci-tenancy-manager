import type { RequiredUsersSummary } from "./contracts";
import { followLink } from "./navigation";

const names = {not_checked:"Not checked",present:"2/2 present",missing:"Missing",unavailable:"Unable to verify",stale:"Check out of date"};
const individual = {not_checked:"Not checked",present:"Present",missing:"Missing",unknown:"Unable to verify"};

// One compact link exposes existence results without implying permission or credential health.
export function RequiredUserSummary({id,name,status,summary,navigate}:{
  id:string;name:string;status:string;summary?:RequiredUsersSummary;navigate:(path:string)=>void;
}) {
  if(status!=="active")return null;
  // Missing wire facts cannot render a positive label, even from an older incompatible response.
  const supplied=summary?.state??"not_checked";
  const fresh=[summary?.automation,summary?.recovery].filter(user=>user&&!user.stale&&user.checked_at&&user.operation_id);
  const state=(supplied==="present"&&(fresh.length!==2||fresh.some(user=>user?.state!=="present"))) ||
    (supplied==="missing"&&!fresh.some(user=>user?.state==="missing"))?"unavailable":supplied;
  const href="/tenancies/"+encodeURIComponent(id)+"#required-users";
  const descriptionId="required-users-summary-"+id;
  const facts=(["automation","recovery"] as const).map(purpose=>{
    const user=summary?.[purpose];
    const label=user?.stale?"Check out of date (last result: "+individual[user.state??"not_checked"]+")":individual[user?.state??"not_checked"];
    const at=user?.checked_at?" · "+new Date(user.checked_at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"}):"";
    return (purpose==="automation"?"Automation":"Recovery")+": "+label+at;
  });
  const description=[...facts,...(state==="unavailable"?["A current qualified result is unavailable."]:[]),"Presence is simulated locally and does not establish permissions. Review administrator assignments on the tenancy page.",...(summary?.checking?["A new check is running; previous results retain their original dates."]:[])].join("\n");
  return <span className="required-users-inventory">
    <a className={"badge required-users-inventory-link "+(state==="present"?"active":state==="missing"?"presence-missing":state==="stale"?"review-open":"required-user-state")}
      href={href} title={description} aria-label={`Users: ${names[state]} for ${name}`}
      aria-describedby={descriptionId} onClick={event=>followLink(event,href,navigate)}>Users: {names[state]}</a>
    {summary?.recovery_console && ["drift","stale"].includes(summary.recovery_console.state ?? "") &&
      <a className={"badge " + (summary.recovery_console.state === "drift" ? "presence-missing" : "review-open")} href={href}
        aria-label={`Recovery policy ${summary.recovery_console.state === "drift" ? "drift" : "out of date"} for ${name}`}
        onClick={event=>followLink(event,href,navigate)}>{summary.recovery_console.state === "drift" ? "Recovery policy drift" : "Recovery policy out of date"}</a>}
    {(["automation","recovery"] as const).map(purpose=>{
      const access=purpose==="automation"?summary?.administrator_access:summary?.recovery_administrator_access;
      const label=purpose==="automation"?"Automation":"Recovery";
      return access && (access.stale || [access.group,access.domain_role].includes("missing")) ? <a key={purpose} className={"badge "+(access.stale?"review-open":"presence-missing")} href={href} aria-label={`${label} assignments ${access.stale?"out of date":"missing"} for ${name}`} onClick={event=>followLink(event,href,navigate)}>{label} assignments {access.stale?"out of date":"missing"}</a>:null;
    })}
    {summary?.checking&&<span className="muted">Checking…</span>}
    <span className="sr-only" id={descriptionId}>{description}</span>
  </span>;
}
