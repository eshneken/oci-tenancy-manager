import {OverrideChooser} from "./OverrideChooser";
import { ConfigurationRollout } from "./ConfigurationRollout";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BaselineHistory, PublishedBaseline } from "./BaselineHistory";
import { api, ApiError } from "./api";
import { followLink } from "./navigation";
import type { BaselineContent } from "./contracts";

type BaselineForm = Omit<BaselineContent, "policy_statements" | "quota_statements" | "monthly_budget_amount"> & {
  monthly_budget_amount: string;
  policy_statements: string;
  quota_statements: string;
};

// Show one editable block; existing stored statement arrays remain the transport/persistence format.
function editContent(content: BaselineContent): BaselineForm {
  return { ...structuredClone(content), monthly_budget_amount: String(content.monthly_budget_amount).replace(/\.0+$/, ""), policy_statements: content.policy_statements.join("\n"), quota_statements: content.quota_statements.join("\n") };
}

// Each nonblank physical line is one statement; normalize platform newlines without rewriting text.
function statementLines(block: string): string[] {
  return block.split(/\r\n|\r|\n/).filter(line => line.trim().length > 0);
}

const empty: BaselineContent = { policy_statements: [""], quota_statements: [""], monthly_budget_amount: "", budget_currency: "", budget_period: "MONTHLY", tag_namespace: "OTM", tag_defaults: [] };

// Author one policy block and one quota block, converting their lines only at explicit save.
export function Baselines({ expired, navigate }: { expired: () => void; navigate: (path: string) => void }) {
  const client = useQueryClient();
  const requested = new URLSearchParams(location.search).get("baseline");
  const [page,setPage] = useState(1);
  const [pageSize,setPageSize] = useState<10|25|50>(10);
  const queryKey=["baselines", page, pageSize, requested];
  const validId=requested && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requested) ? requested : undefined;
  const result = useQuery({ queryKey, queryFn: ({ signal }) => api.baselines(signal, { page, page_size:pageSize, baseline_id:validId }), retry: false });
  const editorHeading = useRef<HTMLHeadingElement>(null);
  const pageHeading = useRef<HTMLHeadingElement>(null);
  const [form, setForm] = useState<BaselineForm | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [validation, setValidation] = useState("");
  const [message, setMessage] = useState("");
  const saved = useRef(result.data?.draft);
  const basedOn = useRef<string|null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { if (result.error instanceof ApiError && [401,403].includes(result.error.status)) expired(); }, [result.error, expired]);
  useEffect(() => { (editing ? editorHeading : pageHeading).current?.focus(); }, [editing]);
  const data = result.data;

  // Freeze the draft revision being edited; background reads must not silently rebase local changes.
  function start() {
    saved.current = data?.draft;
    setForm(editContent(data?.draft?.content ?? data?.latest?.content ?? empty));
    basedOn.current=data?.draft ? (data.draft.based_on_id??null) : (data?.latest?.id??null);
    setEditing(true); setError(""); setValidation(""); setMessage("");
  }

  // Retrying unchanged content is safe after a lost response; conflicts preserve the local form.
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form || busy) return;
    if (!/^[0-9]+$/.test(form.monthly_budget_amount) || !/[1-9]/.test(form.monthly_budget_amount)) {
      setValidation("Enter a positive whole-number monthly budget, without cents.");
      return;
    }
    const policies = statementLines(form.policy_statements), quotas = statementLines(form.quota_statements);
    if ([policies, quotas].some(lines => lines.length < 1 || lines.length > 50 || lines.some(line => line.length > 2000))) {
      setValidation("Enter 1–50 statements in each block, one per nonempty line, with up to 2,000 characters per statement.");
      return;
    }
    // These length-checked lists now satisfy the generated contract's bounded tuple union.
    const content: BaselineContent = { ...form, policy_statements: policies as BaselineContent["policy_statements"], quota_statements: quotas as BaselineContent["quota_statements"] };
    setValidation("");
    setBusy(true); setError(""); controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      const draft = await api.saveBaselineDraft({ baseline_id: saved.current?.id ?? null, expected_revision: saved.current?.edit_revision ?? null, based_on_id: basedOn.current, content }, signal);
      if (signal.aborted) return;
      client.setQueryData(queryKey, { ...data, configured: true, draft });
      await client.invalidateQueries({ queryKey: ["audit-history"] });
      if (signal.aborted) return;
      setEditing(false); setForm(null); setMessage("Baseline draft saved.");
    } catch (failure) {
      if (signal.aborted) return;
      if (failure instanceof ApiError && [401,403].includes(failure.status)) expired();
      else setError(failure instanceof ApiError && failure.status === 409 ? "This draft changed. Reload the saved draft before saving again." : "The draft could not be saved. Check the values or retry without changing them.");
    } finally { if (!signal.aborted) setBusy(false); }
  }

  // Reload only on explicit request so a stale-save conflict cannot erase unsaved edits silently.
  async function reload() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const fresh = await result.refetch();
      if (!fresh.data || fresh.isError) {
        setError("The saved draft could not be reloaded. Your edits are retained.");
        return;
      }
      if(saved.current && !fresh.data.draft) {
        setEditing(false);setForm(null);setMessage("The draft is no longer editable. Start a new baseline for further changes.");navigate("/configuration");return;
      }
      saved.current = fresh.data.draft;
      basedOn.current=fresh.data.draft ? (fresh.data.draft.based_on_id??null) : (fresh.data.latest?.id??null);
      setForm(editContent(fresh.data.draft?.content ?? fresh.data.latest?.content ?? empty));
      setValidation("");
      editorHeading.current?.focus();
    } finally { setBusy(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">CONFIGURATION</p><h1 tabIndex={-1} ref={pageHeading}>Configuration</h1><p>Prepare the shared recipe for root policies, quotas, budgets and tag defaults.</p></div>
      <div className="baseline-toolbar">{!editing&&!requested&&data?.configured&&<OverrideChooser expired={expired} navigate={navigate}/>}{!editing && <button className="button secondary" onClick={()=>void result.refetch()}>Refresh</button>}{!editing && data?.configured && (!requested || requested === data.draft?.id) && <button className="button primary" onClick={start}>{data.draft ? "Edit draft" : "New baseline"}</button>}</div>
    </div>
    {result.isPending ? <p role="status">Loading baselines…</p> : result.isError && !data ? <div className="alert" role="alert">Baselines could not be loaded. <button className="button secondary" onClick={() => void result.refetch()}>Retry</button></div> : !data?.configured ? <p className="notice">Configure <a href="/organization-mapping" onClick={event => followLink(event, "/organization-mapping", navigate)}>Organization Mapping</a> before creating a baseline draft.</p> : requested && requested !== data.draft?.id && !data.selected ? <p className="alert" role="alert">This baseline is not available. <a href="/configuration" onClick={event => followLink(event, "/configuration", navigate)}>Return to Configuration</a></p> : <>
      {!editing && data.latest && (!requested || requested===data.latest.id) && <ConfigurationRollout initialOperationId={new URLSearchParams(location.search).get("update")??undefined} expired={expired} navigate={navigate}/>}
      {message && <p role="status" className="notice">{message}</p>}
      {editing && form ? <form className="operation-panel baseline-editor" onSubmit={event => void save(event)}>
        <h2 tabIndex={-1} ref={editorHeading}>{saved.current ? `Edit draft v${saved.current.version_number}` : "New baseline draft"}</h2><p className="muted">Saving a draft does not change any tenancy. Enter one complete statement per line. Blank lines are ignored when saving.</p>
        {validation && <p className="alert" role="alert">{validation}</p>}
        {error && <div className="alert" role="alert">{error} <button type="button" className="button secondary" disabled={busy} onClick={() => void reload()}>Reload saved draft</button></div>}
        <p className="notice">Automation and recovery access are managed separately from the authored policy statements.</p>
        <fieldset disabled={busy}>
        {(["policy_statements", "quota_statements"] as const).map((field, section) => <section key={field} className="baseline-block"><h3>{section === 0 ? "Root policy statements" : "Root quota statements"}</h3>
          <label><span id={`${field}-label`}>{section === 0 ? "Policy statements" : "Quota statements"}</span><textarea aria-labelledby={`${field}-label`} aria-describedby={`${field}-help`} required maxLength={105000} rows={8} spellCheck={false} value={form[field]} onChange={event => { setForm({ ...form, [field]: event.target.value }); setValidation(""); }}/></label>
          <p className="muted" id={`${field}-help`}>One statement per line, up to 50 statements. Each statement may contain up to 2,000 characters.</p>
        </section>)}
        <section className="baseline-block"><h3>Monthly root budget</h3><div className="workflow-fields"><label>Monthly amount<input required inputMode="numeric" pattern="[0-9]+" maxLength={16} aria-describedby="monthly-budget-help" title="Enter a positive whole amount without cents" value={form.monthly_budget_amount} onChange={event => setForm({ ...form, monthly_budget_amount: event.target.value })}/></label><label>Currency code<input required pattern="[A-Z]{3}" maxLength={3} placeholder="USD" value={form.budget_currency} onChange={event => setForm({ ...form, budget_currency: event.target.value.toUpperCase() })}/></label></div><p className="muted" id="monthly-budget-help">Whole currency units only, without cents; no budget alert rules. Currency is proposed until publication is validated.</p></section>
        <section className="baseline-block"><h3>OTM tag defaults</h3><p className="muted">Static values in the OTM namespace, with defaults at the root compartment.</p>{(form.tag_defaults ?? []).map((tag,index) => <div className="baseline-tag" key={index}><label>Tag key {index+1}<input required maxLength={100} value={tag.key} onChange={event => setForm({ ...form, tag_defaults: form.tag_defaults!.map((old,i) => i===index ? { ...old, key: event.target.value } : old) })}/></label><label>Static value {index+1}<input required maxLength={1000} value={tag.value} onChange={event => setForm({ ...form, tag_defaults: form.tag_defaults!.map((old,i) => i===index ? { ...old, value: event.target.value } : old) })}/></label><button type="button" className="button secondary" aria-label={`Remove tag ${index+1}`} onClick={() => setForm({ ...form, tag_defaults: form.tag_defaults!.filter((_,i) => i!==index) })}>Remove</button></div>)}<button type="button" className="button secondary" disabled={(form.tag_defaults?.length ?? 0)>=100} onClick={() => setForm({ ...form, tag_defaults: [...form.tag_defaults ?? [], { key: "", value: "" }] })}>Add tag default</button></section>
        </fieldset><div className="page-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => { setEditing(false); setForm(null); setError(""); }}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Saving…" : "Save draft"}</button></div>
      </form> : requested && data.selected?.published_at ? <PublishedBaseline version={data.selected} navigate={navigate}/> : <BaselineHistory data={data} openDraft={start} navigate={navigate} expired={expired}
        pageChanged={setPage} sizeChanged={size=>{setPageSize(size);setPage(1);}}
        published={async version=>{
          setPage(1);await client.invalidateQueries({queryKey:["baselines"]});
          await client.invalidateQueries({queryKey:["audit-history"]});
          await client.invalidateQueries({queryKey:["person-workflow"],refetchType:"none"});
          await client.invalidateQueries({queryKey:["configuration-preview"]});
          setMessage(`Baseline v${version.version_number} published with simulated validation.`);
          navigate(`/configuration?baseline=${version.id}`);
        }}/>}
    </>}
  </>;
}
