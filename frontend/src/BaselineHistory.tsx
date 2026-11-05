import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { Select } from "./Select";
import { baselineHref, baselineReturn } from "./baselineNavigation";
import { followLink } from "./navigation";
import type { BaselineDirectory, BaselineVersion } from "./contracts";

// Render frozen recipe values without enabling edits, application, assignment or current selection.
export function PublishedBaseline({ version, navigate, back, headingId }: { version: BaselineVersion; navigate: (path: string) => void; headingId?:string; back?:{path:string;label:string;close:()=>void} }) {
  const origin=back??baselineReturn();
  return <section className="operation-panel baseline-editor">
    <a className="baseline-backlink" href={origin.path} onClick={event => { if(back && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && !event.button) {event.preventDefault();back.close();} else followLink(event,origin.path,navigate);}}>← {origin.label}</a>
    <h2 id={headingId} tabIndex={-1}>Published baseline v{version.version_number}</h2>
    <p>Published by {version.published_by_name} · {new Date(version.published_at!).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}</p>
    <p className="notice">Simulated validation. This immutable version has not been validated or applied in OCI.</p>
    {(["policy_statements","quota_statements"] as const).map((field,index)=><section className="baseline-block" key={field}>
      <label><span id={`published-${field}`}>{index===0?"Policy statements":"Quota statements"}</span><textarea aria-labelledby={`published-${field}`} readOnly rows={8} value={version.content[field].join("\n")}/></label>
    </section>)}
    <section className="baseline-block"><h3>Monthly root budget</h3><p>{String(version.content.monthly_budget_amount).replace(/\.0+$/,"")} {version.content.budget_currency} / month</p></section>
    <section className="baseline-block"><h3>OTM tag defaults</h3>{version.content.tag_defaults?.length ? <dl>{version.content.tag_defaults.map(tag=><div key={tag.key}><dt>{tag.key}</dt><dd>{tag.value}</dd></div>)}</dl>:<p>No tag defaults.</p>}</section>
    {version.based_on_id && !back && <p className="muted">Derived from a <a href={baselineHref(version.based_on_id!,origin.path)} onClick={event=>followLink(event,baselineHref(version.based_on_id!,origin.path),navigate)}>previous published version</a>.</p>}
  </section>;
}

// Keep publication as an explicit saved-draft transition, with native modal focus and safe retries.
export function BaselineHistory({ data, openDraft, navigate, expired, published, pageChanged, sizeChanged }: {
  data: BaselineDirectory; openDraft: () => void; navigate: (path:string)=>void;
  expired: () => void; published: (version: BaselineVersion)=>Promise<void>;
  pageChanged:(page:number)=>void; sizeChanged:(size:10|25|50)=>void;
}) {
  const [target,setTarget]=useState<BaselineVersion|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const dialog=useRef<HTMLDialogElement>(null);
  const controller=useRef<AbortController|null>(null);
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{ if(target) { dialog.current?.showModal(); heading.current?.focus(); } },[target]);

  // Dismiss only before dispatch completes; abandoning an unknown response does not undo publication.
  function cancel() {
    if(busy) return;
    dialog.current?.close(); setTarget(null);setError("");
  }

  // Exact identity/revision makes a lost-response retry safe; no arbitrary content is sent to publish.
  async function confirm() {
    if(!target || busy) return;
    setBusy(true);setError("");controller.current=new AbortController();
    const signal=controller.current.signal;
    try {
      const version=await api.publishBaseline({baseline_id:target.id,expected_revision:target.edit_revision},signal);
      if(signal.aborted) return;
      await published(version);
      if(signal.aborted) return;
      dialog.current?.close();setTarget(null);
    } catch(failure) {
      if(signal.aborted) return;
      if(failure instanceof ApiError && [401,403].includes(failure.status)) expired();
      else setError(failure instanceof ApiError && failure.status===409
        ? "The draft changed. Close this dialog and refresh before continuing."
        : failure instanceof ApiError && failure.status===400
        ? "Local validation failed. This profile requires a whole-unit USD budget. Save corrections before publishing."
        : "Publication could not be confirmed. Retry safely or close and refresh to check the saved version.");
    } finally { if(!signal.aborted) setBusy(false); }
  }

  const versions=[...(data.draft?[data.draft]:[]),...(data.items??[])];
  return <>
    <p className="notice">Latest published baseline (default for new tenancies): {data.latest ? <a href={`/configuration?baseline=${data.latest.id}`} onClick={event=>followLink(event,`/configuration?baseline=${data.latest!.id}`,navigate)}>Version {data.latest.version_number}</a> : "None published"}. Publication alone leaves existing tenancies and already-started operations unchanged.</p>
    <p className="notice">Published versions are immutable snapshots. Local validation checks structure and the simulated USD profile; Updates here use local simulation; live OCI validation and application are not enabled.</p>
    <section className="table-panel"><div className="table-scroll" role="region" aria-label="Baseline versions" tabIndex={0}><table><caption className="sr-only">Baseline versions, newest publications first</caption>
      <thead><tr><th>Version</th><th>Status</th><th>Created / published (UTC)</th><th>Published by</th><th>Action</th></tr></thead>
      <tbody>{versions.map(version=><tr key={version.id}>
        <td>Version {version.version_number}{version.id===data.latest?.id && <div className="muted">Latest published</div>}</td>
        <td><span className="baseline-version-status">{version.published_at?"Published · simulated":"Draft"}</span></td>
        <td>{new Date(version.published_at??version.created_at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"})}</td>
        <td>{version.published_by_name??"—"}</td>
        <td>{version.published_at?<div className="baseline-version-actions"><a href={`/configuration?baseline=${version.id}`} onClick={event=>followLink(event,`/configuration?baseline=${version.id}`,navigate)}>View version</a></div>:<div className="baseline-version-actions"><button className="button secondary" onClick={openDraft}>Open draft</button><button className="button primary" disabled={!data.publication_available} onClick={()=>{setTarget(version);setError("");}}>Publish</button></div>}</td>
      </tr>)}</tbody>
    </table></div>
    {!versions.length && <div className="table-feedback"><h2>No baseline draft yet</h2><p>Create the shared recipe to review before publication.</p></div>}
    <div className="table-footer"><p>{data.total??0} published versions{data.draft?" · one editable draft":""}</p><div className="pagination">
      <label>Versions per page<Select value={data.page_size??10} onChange={event=>sizeChanged(Number(event.target.value) as 10|25|50)}><option value="10">10</option><option value="25">25</option><option value="50">50</option></Select></label>
      <button className="button secondary" disabled={(data.page??1)<=1} onClick={()=>pageChanged((data.page??1)-1)}>Previous</button><span>Page {data.page??1} of {data.pages??1}</span><button className="button secondary" disabled={(data.page??1)>=(data.pages??1)} onClick={()=>pageChanged((data.page??1)+1)}>Next</button>
    </div></div>
    {!data.publication_available && data.draft && <p className="notice">Publication is unavailable because no baseline validator is configured.</p>}
    </section>
    <dialog ref={dialog} className="workflow-dialog" aria-labelledby="publish-baseline-title" onCancel={event=>{event.preventDefault();cancel();}}>
      <h2 ref={heading} tabIndex={-1} id="publish-baseline-title">Publish baseline v{target?.version_number}?</h2>
      <p>The saved draft becomes immutable and automatically becomes the default for new create/import operations. Start a new baseline for later changes.</p>
      <p>{target?.content.policy_statements.length} policy statements · {target?.content.quota_statements.length} quota statements · {String(target?.content.monthly_budget_amount??"").replace(/\.0+$/,"")} {target?.content.budget_currency} / month</p>
      <p>Local simulation checks only. No tenancy will be changed. Existing tenancies and already-started operations are unchanged.</p>
      {error && <p role="alert" className="alert">{error}</p>}
      <div className="dialog-actions"><button className="button secondary" disabled={busy} onClick={cancel}>Cancel</button><button className="button primary" disabled={busy} onClick={()=>void confirm()}>{busy?"Publishing…":"Publish baseline"}</button></div>
    </dialog>
  </>;
}
