import type { ConfigurationCheckSummary } from "./contracts";

export type ConfigurationMessage = { kind:"drift"|"stale"|"unavailable"|"not_checked"|"checking"|"matching"; label:string };

// Confirmed differences and observation health are independent; a failed, aged or pending read never manufactures or clears drift.
export function configurationMessages({state,stale=false,confirmed=0}:{state:ConfigurationCheckSummary["state"];stale?:boolean;confirmed?:number}):ConfigurationMessage[] {
  const result:ConfigurationMessage[]=[];
  if(confirmed>0)result.push({kind:"drift",label:`Configuration drift · ${confirmed} ${confirmed===1?"category":"categories"}`});
  if(stale)result.push({kind:"stale",label:"Check out of date"});
  if(state==="checking")result.push({kind:"checking",label:"Checking"});
  else if(state==="unavailable")result.push({kind:"unavailable",label:"Unable to verify"});
  else if((state==="not_checked"||state==="superseded")&&!stale)result.push({kind:"not_checked",label:"Not checked"});
  else if(state==="matching"&&!stale&&!confirmed)result.push({kind:"matching",label:"Matching"});
  return result.length?result:[{kind:"not_checked",label:"Not checked"}];
}

// The same named status uses the same visual treatment in inventory, tenancy detail and check evidence.
export function configurationMessageClass(kind:ConfigurationMessage["kind"]) {
  return kind==="matching"?"active":kind==="checking"?"waiting":kind==="not_checked"?"configuration-unverified":"review-open";
}
