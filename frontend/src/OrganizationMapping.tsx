import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { refreshOrganization } from "./PersonActions";
import type {
  MappingCandidate,
  MappingPreview,
  MappingRole,
} from "./contracts";

type Draft = {
  root_email: string;
  segments: {
    id: string | null;
    label: string;
    leader_email: string;
    designees: string;
  }[];
};
const empty: Draft = {
  root_email: "",
  segments: [{ id: null, label: "", leader_email: "", designees: "" }],
};
const ancestryLabels: Record<string, string> = {
  root: "Organization leader",
  resolved: "Within organization",
  incomplete: "Reporting chain incomplete",
};
const statuses: Record<MappingRole["status"], string> = {
  healthy: "Eligible",
  departed: "Confirmed absence requires review",
  excluded: "Excluded profile",
  profile_missing: "Employee profile missing from latest feed",
  ancestry_incomplete: "Reporting chain incomplete",
  branch_changed: "Reporting position is not eligible",
  not_verified: "Not yet verified by a feed",
};

// Keep editable email text separate from normalized API tuples so multiline typing stays natural.
function draft(candidate: MappingCandidate | null): Draft {
  return candidate
    ? {
        root_email: candidate.root_email,
        segments: candidate.segments.map((s) => ({
          id: s.id ?? null,
          label: s.label,
          leader_email: s.leader_email,
          designees: (s.designee_emails ?? []).join("\n"),
        })),
      }
    : structuredClone(empty);
}

// Show nomination health separately from managed-directory status and tenancy cleanup obligations.
function Roles({
  roles,
  hasFeed = true,
}: {
  roles: MappingRole[];
  hasFeed?: boolean;
}) {
  const warnings = roles.filter((r) => r.status !== "healthy");
  return (
    <section className="operation-panel" aria-label="Organization role health">
      <h2>Organization role health</h2>
      <p className="muted">
        {hasFeed
          ? "Repair these nominations in the matching industry segment. Tenancy cleanup is separate."
          : "Nominations await the first feed; reporting positions have not been verified."}
      </p>
      {warnings.length ? (
        <ul className="mapping-warnings">
          {warnings.map((r) => (
            <li key={r.segment_id + r.role + r.email}>
              <strong>
                {r.segment_name}:{" "}
                {r.status === "not_verified"
                  ? r.role === "leader"
                    ? "Leader verification pending"
                    : "Designee verification pending"
                  : r.role === "leader"
                    ? "Leader needs attention"
                    : "Designee needs attention"}
              </strong>
              <span className="cell-secondary">
                {r.email} · {statuses[r.status]}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>
          {hasFeed
            ? "No role defects detected."
            : "No reporting relationships verified yet."}
        </p>
      )}
    </section>
  );
}

// Explain actual blockers without exposing internal codes or implying an acknowledgment fixes them.
function Blockers({ values }: { values: string[] }) {
  if (!values.length) return null;
  const messages: Record<string, string> = {
    PENDING_LIFECYCLE:
      "A tenancy workflow is unsettled. Open Operations to view its status and complete or cancel it.",
    UNAPPLIED_ORGANIZATION:
      "An organization proposal has not been applied. Settle that proposal before changing mappings.",
    INELIGIBLE_REPLACEMENT_LEADER:
      "A proposed leader is not eligible. Choose a current employee who reports directly to the root manager.",
  };
  return (
    <div className="notice" role="status">
      <strong>Apply is blocked</strong>
      <ul>
        {values.map((value) => (
          <li key={value}>
            {messages[value] ?? "Refresh saved settings before continuing."}
            {value === "PENDING_LIFECYCLE" && (
              <>
                {" "}
                <a href="/operations">Open Operations</a>
              </>
            )}
            {value === "UNAPPLIED_ORGANIZATION" && (
              <>
                {" "}
                <a href="/organization">Open Organization</a>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Preview and Apply are explicit; editing invalidates both completed and in-flight previews.
export function OrganizationMapping({
  expired,
  segmentId,
}: {
  expired: () => void;
  segmentId?: string | undefined;
}) {
  const client = useQueryClient();
  const result = useQuery({
    queryKey: ["organization-mapping"],
    queryFn: ({ signal }) => api.mapping(signal),
    retry: false,
  });
  const [changingRoot, setChangingRoot] = useState(false);
  const [rootConfirmed, setRootConfirmed] = useState(false);
  const [form, setForm] = useState<Draft | null>(null);
  const [preview, setPreview] = useState<MappingPreview | null>(null);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  const [mustRefresh, setMustRefresh] = useState(false),
    [search, setSearch] = useState("");
  const previewRegion = useRef<HTMLDialogElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const previewButton = useRef<HTMLButtonElement>(null);
  const rootEmail = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (changingRoot) rootEmail.current?.focus();
  }, [changingRoot]);
  const [designeeQueries, setDesigneeQueries] = useState<
    Record<number, string>
  >({});
  const generation = useRef(0),
    controller = useRef<AbortController | null>(null);
  const data = result.data;
  const suggestions = useQuery({
    queryKey: ["organization", "mapping-suggestions", search],
    queryFn: ({ signal }) =>
      api.organization(
        {
          page: 1,
          page_size: 10,
          query: search.slice(0, 128),
          sort: "full_name",
          direction: "asc",
        },
        signal,
      ),
    enabled: Boolean(data?.has_feed && search.length >= 2),
    retry: false,
  });
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (result.data && form === null) setForm(draft(result.data.candidate));
  }, [result.data, form]);
  useEffect(() => {
    const failure = result.error ?? suggestions.error;
    if (failure instanceof ApiError && [401, 403].includes(failure.status))
      expired();
  }, [result.error, suggestions.error, expired]);

  useEffect(() => {
    const dialog = previewRegion.current;
    if (preview && dialog && !dialog.open) {
      dialog.showModal();
      previewHeading.current?.focus();
    }
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, [Boolean(preview)]);
  useEffect(() => {
    if (segmentId && form)
      document
        .getElementById("segment-" + segmentId)
        ?.querySelector<HTMLInputElement>("input")
        ?.focus();
  }, [segmentId, form === null]);

  // Close natively before removing the dialog; restore launch focus when that control is enabled.
  function closePreview() {
    const wasOpen = previewRegion.current?.open;
    if (wasOpen) previewRegion.current?.close();
    setPreview(null);
    if (wasOpen) previewButton.current?.focus();
  }

  // Preserve the entered draft on failed reads/conflicts; Cancel explicitly restores saved settings.
  function edit(next: Draft) {
    generation.current++;
    controller.current?.abort();
    setBusy(false);
    setForm(next);
    closePreview();
    setError("");
    setMessage("");
  }

  // Commands use the exact normalized server preview rather than merging stale browser impact data.
  async function submit(apply: boolean, page = 1) {
    if (!data || !form || (apply && !preview)) return;
    const epoch = ++generation.current;
    controller.current?.abort();
    controller.current = new AbortController();
    const signal = controller.current.signal;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (apply) {
        const saved = await api.applyMapping(
          {
            context: preview!.context,
            change_root: changingRoot,
            candidate: preview!.candidate,
            preview_token: preview!.preview_token,
          },
          signal,
        );
        if (epoch !== generation.current || signal.aborted) return;
        client.setQueryData(["organization-mapping"], saved);
        setForm(draft(saved.candidate));
        setChangingRoot(false);
        setDesigneeQueries({});
        setSearch("");
        closePreview();
        setMustRefresh(false);
        await refreshOrganization(client);
        setMessage(
          "Organization mapping applied. Industry segment assignments are up to date.",
        );
      } else {
        const segments = form.segments.map((s) => ({
          id: s.id,
          label: s.label,
          leader_email: s.leader_email,
          designee_emails: s.designees
            .split(/[,;\n]/)
            .map((v) => v.trim())
            .filter(Boolean),
        }));
        if (!segments[0]) return;
        const candidate: MappingCandidate = {
          root_email: form.root_email,
          segments: [segments[0], ...segments.slice(1)],
        };
        const checked = await api.previewMapping(
          { context: data.context, candidate, change_root: changingRoot },
          page,
          signal,
        );
        if (epoch !== generation.current || signal.aborted) return;
        setRootConfirmed(false);
        setPreview(checked);
      }
    } catch (failure) {
      if (epoch !== generation.current || signal.aborted) return;
      closePreview();
      if (failure instanceof ApiError && [401, 403].includes(failure.status))
        expired();
      else if (
        apply ||
        (failure instanceof ApiError && failure.status === 409)
      ) {
        setMustRefresh(true);
        setError(
          "Settings or organization work may have changed. Refresh saved settings and preview again before applying. Your edits are retained.",
        );
      } else
        setError(
          "Preview unavailable. Check email addresses, unique segment names and leaders, then try again.",
        );
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  }

  if (result.isPending || (!form && !result.isError))
    return <p role="status">Loading organization mapping…</p>;
  if (result.isError || !data || !form)
    return (
      <section className="operation-panel">
        <h1>Organization Mapping</h1>
        <p role="alert">Unable to load saved settings.</p>
        <button
          className="button secondary"
          onClick={() => void result.refetch()}
        >
          Refresh saved settings
        </button>
      </section>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">APPLICATION SETTINGS</span>
          <h1>Organization Mapping</h1>
          <p>Map accountable leaders and designees to industry segments.</p>
        </div>
        <button
          className="button secondary"
          disabled={busy}
          onClick={async () => {
            const refreshed = await result.refetch();
            if (!refreshed.isError) setMustRefresh(false);
          }}
        >
          Refresh saved settings
        </button>
      </div>
      {!data.available && (
        <p className="notice">
          An operator must configure the trusted organization source policy
          before setup is available.
        </p>
      )}
      <p className="notice">
        {data.has_feed
          ? "Apply recalculates assignments immediately. It does not change the source reporting graph, tenancy associations or OCI access."
          : "Save the root and at least one industry segment before uploading a CSV. Saved emails are nominations; reporting relationships are verified by the first feed."}
      </p>
      {message && (
        <p className="notice" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <Roles roles={data.roles} hasFeed={data.has_feed} />
      <Blockers values={data.blockers} />
      <form
        className="operation-panel mapping-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(false);
        }}
      >
        <h2>{data.configured ? "Edit saved mappings" : "Initial setup"}</h2>
        <span className="badge">
          {JSON.stringify(form) !== JSON.stringify(draft(data.candidate))
            ? "Unsaved changes"
            : data.configured
              ? "Saved settings"
              : "Not configured"}
        </span>
        <label>
          Root manager email
          <input
            required
            type="email"
            maxLength={320}
            ref={rootEmail}
            value={form.root_email}
            readOnly={!data.root_editable && !changingRoot}
            disabled={busy}
            onChange={(e) => edit({ ...form, root_email: e.target.value })}
          />
        </label>
        {!data.root_editable && (
          <div className="mapping-actions">
            <button
              type="button"
              className="button secondary"
              disabled={busy || changingRoot}
              onClick={() => {
                setChangingRoot(true);
                edit(form);
              }}
            >
              Change organization leader
            </button>
            <p className="muted">
              A replacement changes the reporting boundary. Review the impact
              before applying.
            </p>
          </div>
        )}
        <datalist id="mapping-employees">
          {suggestions.data?.items.map((p) => (
            <option key={p.id} value={p.email}>
              {p.full_name}
            </option>
          ))}
        </datalist>
        {form.segments.map((s, index) => (
          <fieldset
            key={s.id ?? index}
            id={s.id ? "segment-" + s.id : undefined}
            disabled={busy}
          >
            <legend>Industry segment {index + 1}</legend>
            <div className="workflow-fields">
              <label>
                Segment name
                <input
                  required
                  maxLength={128}
                  value={s.label}
                  onChange={(e) =>
                    edit({
                      ...form,
                      segments: form.segments.map((v, i) =>
                        i === index ? { ...v, label: e.target.value } : v,
                      ),
                    })
                  }
                />
              </label>
              <label>
                Leader email
                <input
                  required
                  type="email"
                  maxLength={320}
                  value={s.leader_email}
                  onChange={(e) => {
                    edit({
                      ...form,
                      segments: form.segments.map((v, i) =>
                        i === index
                          ? { ...v, leader_email: e.target.value }
                          : v,
                      ),
                    });
                  }}
                />
              </label>
              <div className="full-field mapping-designees">
                {data.has_feed && (
                  <div className="mapping-designee">
                    <label>
                      Find designee
                      <input
                        type="text"
                        list="mapping-employees"
                        maxLength={320}
                        aria-label={"Find designee for segment " + (index + 1)}
                        value={designeeQueries[index] ?? ""}
                        onChange={(e) => {
                          setDesigneeQueries({
                            ...designeeQueries,
                            [index]: e.target.value,
                          });
                          setSearch(e.target.value);
                        }}
                      />
                    </label>
                    <button
                      type="button"
                      className="button secondary"
                      disabled={
                        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
                          designeeQueries[index] ?? "",
                        )
                      }
                      onClick={() => {
                        const value = designeeQueries[index].trim();
                        edit({
                          ...form,
                          segments: form.segments.map((v, i) =>
                            i === index
                              ? {
                                  ...v,
                                  designees: [v.designees, value]
                                    .filter(Boolean)
                                    .join("\n"),
                                }
                              : v,
                          ),
                        });
                        setDesigneeQueries({ ...designeeQueries, [index]: "" });
                      }}
                    >
                      Add designee
                    </button>
                  </div>
                )}
                <label>
                  Designee emails (optional)
                  <textarea
                    rows={2}
                    maxLength={16000}
                    value={s.designees}
                    placeholder="One email per line"
                    onChange={(e) => {
                      setSearch(e.target.value.split(/[,;\n]/).at(-1) ?? "");
                      edit({
                        ...form,
                        segments: form.segments.map((v, i) =>
                          i === index ? { ...v, designees: e.target.value } : v,
                        ),
                      });
                    }}
                  />
                </label>
              </div>
            </div>
            <button
              type="button"
              className="button secondary"
              disabled={form.segments.length === 1}
              onClick={() => {
                setDesigneeQueries({});
                setSearch("");
                edit({
                  ...form,
                  segments: form.segments.filter((_, i) => i !== index),
                });
              }}
            >
              Remove segment {index + 1}
            </button>
          </fieldset>
        ))}
        <div className="mapping-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy || form.segments.length >= 50}
            onClick={() =>
              edit({
                ...form,
                segments: [
                  ...form.segments,
                  { id: null, label: "", leader_email: "", designees: "" },
                ],
              })
            }
          >
            Add industry segment
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => {
              setDesigneeQueries({});
              setSearch("");
              setChangingRoot(false);
              edit(draft(data.candidate));
              setMustRefresh(false);
            }}
          >
            Cancel edits
          </button>
          <button
            type="submit"
            ref={previewButton}
            className="button primary"
            disabled={busy || !data.available || mustRefresh}
          >
            Preview changes
          </button>
        </div>
        <p className="muted">
          Unsaved edits do not affect the organization. Every edit requires a
          new preview.
        </p>
      </form>
      {preview && (
        <dialog
          className="workflow-dialog mapping-preview"
          aria-labelledby="mapping-preview-title"
          ref={previewRegion}
          onCancel={(event) => {
            event.preventDefault();
            if (!busy) closePreview();
          }}
        >
          <span className="eyebrow">ORGANIZATION MAPPING</span>
          <h2 id="mapping-preview-title" tabIndex={-1} ref={previewHeading}>
            Mapping change preview
          </h2>
          <p className="muted">
            Review the proposed assignments before applying. Your saved settings
            stay unchanged until you apply.
          </p>
          {preview.root_before &&
            preview.root_before !== preview.candidate.root_email && (
              <section
                className="notice"
                aria-label="Organization leader replacement"
              >
                <strong>Organization leader replacement</strong>
                <p>
                  {preview.root_before} → {preview.candidate.root_email}
                </p>
                {!preview.root_present && (
                  <p>
                    The new leader is not in the latest feed. Upload an updated
                    feed after applying.
                  </p>
                )}
                <p>
                  {preview.unresolved_count} employees have unresolved reporting
                  chains. Reporting relationships and tenancy associations will
                  not be changed.
                </p>
                <label className="workflow-check">
                  <input
                    type="checkbox"
                    checked={rootConfirmed}
                    disabled={busy}
                    onChange={(event) => setRootConfirmed(event.target.checked)}
                  />
                  I reviewed this leader replacement and its reporting gaps.
                </label>
              </section>
            )}
          <div className="mapping-summary">
            <div>
              <strong>{preview.affected_count}</strong>
              <span>Affected employees</span>
            </div>
            <div>
              <strong>{preview.unassigned_count}</strong>
              <span>Becoming unassigned</span>
            </div>
          </div>
          {!preview.has_feed && (
            <p>Employee impact cannot be calculated until the first feed.</p>
          )}
          <Blockers values={preview.blockers} />
          <h3>Segment changes</h3>
          <ul className="mapping-warnings mapping-changes">
            {preview.changes.map((c) => (
              <li key={c.segment_id}>
                <strong>
                  {c.before?.label ?? "New segment"} →{" "}
                  {c.after?.label ?? "Removed"}
                </strong>
                <span className="cell-secondary">
                  Leader: {c.before?.leader_email ?? "None"} →{" "}
                  {c.after?.leader_email ?? "None"}
                </span>
                <span className="cell-secondary">
                  Designees: {c.before?.designee_emails?.join(", ") || "None"} →{" "}
                  {c.after?.designee_emails?.join(", ") || "None"}
                </span>
              </li>
            ))}
          </ul>
          <Roles roles={preview.roles} hasFeed={preview.has_feed} />
          <h3>Employee impact</h3>
          {!preview.items.length && (
            <p className="muted">No employee assignments change.</p>
          )}
          <ul className="mapping-warnings mapping-changes">
            {preview.items.map((p) => (
              <li key={p.person_id}>
                <strong>{p.name}</strong> · {p.email}
                {p.before_ancestry !== p.after_ancestry && (
                  <span className="cell-secondary">
                    Reporting chain:{" "}
                    {ancestryLabels[p.before_ancestry] ?? "Unknown"} →{" "}
                    {ancestryLabels[p.after_ancestry] ?? "Unknown"}
                  </span>
                )}
                <span className="cell-secondary">
                  {p.before_segment ?? "Unassigned"} →{" "}
                  {p.after_segment ?? "Unassigned"}
                </span>
                <span className="cell-secondary">
                  Leader: {p.before_leader ?? "None"} →{" "}
                  {p.after_leader ?? "None"}
                </span>
                <span className="cell-secondary">
                  Designees: {p.before_designees.join(", ") || "None"} →{" "}
                  {p.after_designees.join(", ") || "None"}
                </span>
              </li>
            ))}
          </ul>
          <div className="mapping-actions">
            <button
              className="button secondary"
              disabled={busy || preview.page <= 1}
              onClick={() => void submit(false, preview.page - 1)}
            >
              Previous impact page
            </button>
            <span>
              Page {preview.page} of {preview.pages}
            </span>
            <button
              className="button secondary"
              disabled={busy || preview.page >= preview.pages}
              onClick={() => void submit(false, preview.page + 1)}
            >
              Next impact page
            </button>
          </div>
          <div className="dialog-actions">
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => closePreview()}
            >
              Back to editing
            </button>
            <button
              className="button primary"
              disabled={
                busy ||
                mustRefresh ||
                preview.blockers.length > 0 ||
                (preview.root_before !== null &&
                  preview.root_before !== preview.candidate.root_email &&
                  !rootConfirmed)
              }
              onClick={() => void submit(true)}
            >
              Apply changes
            </button>
          </div>
        </dialog>
      )}
    </>
  );
}
