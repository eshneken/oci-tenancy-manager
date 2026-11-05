import {useEffect,useRef,useState} from "react";
import type {ConfigurationPlanView,OverrideConflict,SaveConfigurationReview} from "./contracts";

// Show the exact three versions and stage one complete-list choice per affected category.
export function OverrideConflictReview({plan,conflict,busy,error,save,back,reload}:{plan:ConfigurationPlanView;conflict:OverrideConflict;busy:boolean;error:string;save:(choices:SaveConfigurationReview)=>Promise<void>;back:()=>void;reload:()=>Promise<void>}){
 const [policy,setPolicy]=useState(conflict.policy_choice??"");
 const [quota,setQuota]=useState(conflict.quota_choice??"");
 const heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>heading.current?.focus(),[]);
 const categories=[{key:"policy" as const,title:"Policy statements",needed:conflict.policy_review,choice:policy,set:setPolicy,old:conflict.old_baseline?.content.policy_statements,new:plan.preview.baseline?.content.policy_statements,override:conflict.overrides.policy_override_statements},{key:"quota" as const,title:"Quota statements",needed:conflict.quota_review,choice:quota,set:setQuota,old:conflict.old_baseline?.content.quota_statements,new:plan.preview.baseline?.content.quota_statements,override:conflict.overrides.quota_override_statements}];
 return <>
  <a className="baseline-backlink" href={location.href} onClick={event=>{event.preventDefault();back();}}>← Back to update preview</a>
  <h2 id="override-review-title" ref={heading} tabIndex={-1}>Review overrides · {conflict.tenancy_name}</h2>
  <p>These decisions are staged. No tenancy changes until the entire update is started.</p>
  {categories.filter(category=>category.needed).map(category=><section className="baseline-block" key={category.key}><h3>{category.title}</h3><div className="override-comparison">{[{title:`Old baseline v${conflict.old_baseline?.version_number??"?"}`,value:category.old},{title:`New baseline v${plan.preview.baseline?.version_number??"?"}`,value:category.new},{title:"Current override",value:category.override}].map(block=><div key={block.title}><h4>{block.title}</h4><pre tabIndex={0}>{block.value?.join("\n")??"Not available"}</pre></div>)}</div>
    <fieldset disabled={busy} className="override-choices"><legend>Choose {category.key} content for this update</legend><label className="workflow-check"><input type="radio" name={category.key+"-review"} checked={category.choice==="use_new_baseline"} onChange={()=>category.set("use_new_baseline")}/>Use new baseline</label><label className="workflow-check"><input type="radio" name={category.key+"-review"} checked={category.choice==="keep_override"} onChange={()=>category.set("keep_override")}/>Keep override</label></fieldset>
  </section>)}
  <p className="notice">Keep override retains its complete statement list. New baseline statements are never merged into it.</p>
  {error&&<p className="alert" role="alert">{error} <button type="button" className="button secondary" disabled={busy} onClick={()=>void reload()}>Reload saved review</button></p>}
  <div className="dialog-actions"><button type="button" className="button secondary" disabled={busy} onClick={back}>Back</button><button className="button primary" disabled={busy||Boolean(conflict.policy_review&&!policy)||Boolean(conflict.quota_review&&!quota)} onClick={()=>void save({expected_revision:plan.revision,tenancy_id:conflict.tenancy_id,policy_choice:policy?policy as "use_new_baseline"|"keep_override":null,quota_choice:quota?quota as "use_new_baseline"|"keep_override":null})}>{busy?"Saving…":"Save review"}</button></div>
 </>;
}
