import {Select} from "./Select";
import type {ImportAdoption, ImportReview} from "./contracts";

// Build only exact identity/person choices; observed scope and privileges remain server-owned.
export function adoptionChoice(review:ImportReview, selected:Record<string,string>, confirmed:boolean):ImportAdoption|null {
  const members=review.inventory.users.filter(user=>selected[user.user_ocid]).map(user=>({user_ocid:user.user_ocid,person_id:selected[user.user_ocid]}));
  if(!confirmed||!members.length||members.length>50||new Set(members.map(member=>member.person_id)).size!==members.length||!members.some(member=>member.person_id===review.owner_person_id))return null;
  if(members.some(member=>!review.people.some(person=>person.id===member.person_id)||member.person_id===review.owner_person_id&&!review.inventory.users.find(user=>user.user_ocid===member.user_ocid)?.administrator))return null;
  return {inventory_hash:review.inventory_hash,members:members as ImportAdoption["members"],lifecycle_confirmed:true};
}

// Adoption is an explicit owner-inclusive review, with the same later lifecycle as created accounts.
export function ImportMembers({review,selected,confirmed,busy,change,confirm,refresh}:{review:ImportReview;selected:Record<string,string>;confirmed:boolean;busy:boolean;change:(value:Record<string,string>)=>void;confirm:(value:boolean)=>void;refresh:()=>void}) {
  return <section className="import-members" aria-labelledby="import-members-title">
    <div className="recovery-user-heading"><h3 id="import-members-title">Existing users and access</h3><button type="button" className="button secondary" disabled={busy} onClick={refresh}>Refresh existing users</button></div>
    <p>Associate existing accounts with employees, including the accountable owner. Adoption preserves their identities, credentials and current permissions. Unselected accounts remain outside Atlas management.</p>
    <p className="notice">Root and administrator access may cover the entire tenancy. An Atlas member role does not reduce existing OCI privileges. Multiple people may share the same compartment.</p>
    <div className="table-scroll" role="region" aria-label="Existing accounts to adopt" tabIndex={0}><table><thead><tr><th>Existing account</th><th>Observed access</th><th>Organization employee</th></tr></thead><tbody>
      {review.inventory.users.map(user=><tr key={user.user_ocid}><td><strong>{user.user_name}</strong><br/>{user.email}<details><summary>Identity identifiers</summary><p>{user.user_ocid}</p><p>SCIM: {user.scim_id}</p></details></td><td>{user.administrator&&<span className="badge review-open">Administrator</span>}<ul>{user.scopes.map(scope=><li key={scope.ocid}>{scope.name}{scope.kind==="root"?" · shared root scope":""}</li>)}</ul><span className="muted">{(user.groups??[]).length} group assignments · {(user.roles??[]).length} domain role assignments</span></td><td><Select aria-label={`Employee for ${user.user_name} · ${user.email} · ${user.user_ocid}`} value={selected[user.user_ocid]??""} disabled={busy} onChange={event=>change({...selected,[user.user_ocid]:event.target.value})}><option value="">Leave unmanaged</option>{review.people.map(person=><option key={person.id} value={person.id} disabled={Boolean(Object.entries(selected).some(([id,value])=>id!==user.user_ocid&&value===person.id))||person.id===review.owner_person_id&&!user.administrator}>{person.name} · {person.email}{person.id===review.owner_person_id?" · Accountable owner":""}</option>)}</Select></td></tr>)}
    </tbody></table></div>
    {!review.inventory.users.length&&<p className="alert">No existing accounts were verified. Refresh the inventory or correct bootstrap access before continuing.</p>}
    <p className="muted">Adopt up to 50 accounts per import. {Object.values(selected).filter(Boolean).length} selected.</p>
    {Object.values(selected).filter(Boolean).length>50&&<p className="alert" role="alert">Select 50 or fewer accounts before continuing.</p>}
    <label className="workflow-check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>confirm(event.target.checked)}/><span>I reviewed the selected identities and access. Atlas will manage their full lifecycle, including user deletion when an explicit removal or offboarding requires it. Shared groups, compartments and resources are preserved.</span></label>
    {!adoptionChoice(review,selected,confirmed)&&<p className="muted">Select the existing administrator account for the owner, associate any additional members and confirm lifecycle adoption before starting setup.</p>}
  </section>;
}
