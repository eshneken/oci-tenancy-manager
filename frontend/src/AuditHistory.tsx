import {operationHref} from "./operationNavigation";
import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { baselineHref } from "./baselineNavigation";
import { followLink } from "./navigation";
import type { AuditQuery, AuditEntry, AuditExportQuery } from "./contracts";

type AuditFilters = Required<AuditQuery>;
const initialQuery: AuditFilters = {
  page: 1,
  page_size: 10,
  sort: "at",
  direction: "desc",
  category: "",
  query: "",
  from_at: null,
  to_at: null,
};
const categories: Record<AuditEntry["category"], string> = {
  authentication: "Authentication",
  administration: "Administration",
  operations: "Operations",
  organization: "Organization",
  email_delivery: "Email delivery",
};
const columns = [
  ["at", "Time · UTC"],
  ["kind", "Event"],
  ["actor_name", "Actor"],
] as const;

// Turn an allowed recorded event kind into a readable label without inventing an outcome.
function eventLabel(kind: AuditEntry["kind"]) {
  const labels: Record<AuditEntry["kind"], string> = {
    signing_key_outcome:"Signing-key maintenance",signing_key_requested:"Signing-key rotation requested",
    configuration_review_staged: "Override review staged",
    baseline_draft_saved: "Baseline draft saved",
    baseline_published: "Baseline published",
    baseline_default_changed: "Baseline default changed",
    recovery_password_disclosed:"Recovery password requested",recovery_password_outcome:"Recovery password outcome",operation_intent: "Operation intent recorded",
    inspection_dispatch: "Inspection dispatched",
    inspection_outcome: "Inspection outcome",
    administrator_revoked: "Administrator access revoked",
    administrator_bootstrapped: "Administrator bootstrapped",
    local_credentials_reset: "Local credentials reset",
    local_sign_in_succeeded: "Local sign-in succeeded",
    local_sign_in_failed: "Local sign-in failed",
    session_logged_out: "Session signed out",
    audit_export: "Audit export prepared",
    organization_configured: "Organization configured",
    organization_feed_received: "Organization feed received",
    organization_feed_rejected: "Organization feed rejected",
    organization_published: "Organization metadata applied",
    organization_action_outcome: "Simulated lifecycle result",
    onboarding_action: "Onboarding action",
    onboarding_outcome: "Onboarding check",
    configuration_outcome: "Configuration verification",
    cost_refresh_requested: "Cost refresh requested",
    cost_collection_outcome: "Cost collection result",
    required_user_check_outcome: "User presence check result",
    recovery_network_outcome: "Recovery network repair result",
    configuration_check_outcome: "Configuration check result",
    configuration_retry: "Configuration retry",
    operation_responsibility_changed: "Operation responsibility changed",
    email_delivery: "Email delivery",
    organization_review_decided: "Organization decision recorded",
  };
  return labels[kind];
}

// Render a stable UTC timestamp for the recorded audit event, independent of browser time zone.
function stamp(value: string) {
  return (
    new Date(value).toLocaleString("en-US", {
      timeZone: "UTC",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }) + " UTC"
  );
}

// Native date fields can retain out-of-range years; validate before serializing or issuing a request.
function utcInput(value: string): string | null | undefined {
  if (!value) return null;
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?$/.test(value) ||
    value.startsWith("0000-")
  )
    return undefined;
  const date = new Date(value + "Z");
  const iso = Number.isFinite(date.getTime()) ? date.toISOString() : undefined;
  return iso?.slice(0, 16) === value.slice(0, 16) ? iso : undefined;
}

// Browse and export scoped immutable history; record rows never expose edit or resolution controls.
export function AuditHistory({
  expired,
  navigate,
}: {
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const [query, setQuery] = useState<AuditFilters>(
    () =>
      client.getQueryData<AuditFilters>(["audit-history", "view"]) ??
      initialQuery,
  );
  const [search, setSearch] = useState(query.query);
  const [fromInput, setFromInput] = useState(query.from_at?.slice(0, 16) ?? "");
  const [toInput, setToInput] = useState(query.to_at?.slice(0, 16) ?? "");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportNotice, setExportNotice] = useState("");
  const exportController = useRef<AbortController | null>(null);
  const fromDate = utcInput(fromInput);
  const toDate = utcInput(toInput);
  const invalidDates = fromDate === undefined || toDate === undefined;
  const invalidRange = Boolean(fromDate && toDate && fromDate >= toDate);
  useEffect(() => () => exportController.current?.abort(), []);
  useEffect(() => {
    client.setQueryData(["audit-history", "view"], query);
  }, [client, query]);
  useEffect(() => {
    const timer = setTimeout(
      () =>
        setQuery((previous) =>
          previous.query === search
            ? previous
            : { ...previous, query: search, page: 1 },
        ),
      200,
    );
    return () => clearTimeout(timer);
  }, [search]);
  const result = useQuery({
    queryKey: ["audit-history", "list", query],
    queryFn: ({ signal }) => api.auditHistory(query, signal),
    retry: false,
  });
  useEffect(() => {
    if (
      result.error instanceof ApiError &&
      (result.error.status === 401 || result.error.status === 403)
    )
      expired();
  }, [result.error, expired]);
  const data = result.data;
  const filtered = Boolean(
    query.query || query.category || fromInput || toInput,
  );
  const page = data?.page ?? 1;
  const pageCount = data?.pages ?? 1;
  const firstPage = Math.max(1, Math.min(page - 2, pageCount - 4));
  const pages = Array.from(
    { length: Math.min(5, pageCount) },
    (_, index) => firstPage + index,
  );
  // Sorting preserves user filters and row count, resetting the page only when ordering changes.
  function sort(key: AuditFilters["sort"]) {
    setQuery((previous) => ({
      ...previous,
      sort: key,
      direction:
        previous.sort === key && previous.direction === "asc" ? "desc" : "asc",
      page: 1,
    }));
  }
  // Date inputs explicitly represent UTC; invalid ranges retain the last valid server query.
  function setDates(from: string, before: string) {
    setFromInput(from);
    setToInput(before);
    const fromAt = utcInput(from);
    const toAt = utcInput(before);
    if (
      fromAt === undefined ||
      toAt === undefined ||
      (fromAt && toAt && fromAt >= toAt)
    )
      return;
    setQuery((previous) => ({
      ...previous,
      page: 1,
      from_at: fromAt,
      to_at: toAt,
    }));
  }
  // Keep CSV bytes outside React Query and stop late downloads when navigation or logout unmounts the page.
  async function exportCsv() {
    if (exportController.current) return;
    const controller = new AbortController();
    exportController.current = controller;
    setExporting(true);
    setExportError("");
    setExportNotice("");
    const filters: AuditExportQuery = {
      category: query.category,
      query: query.query,
      sort: query.sort,
      direction: query.direction,
      from_at: query.from_at,
      to_at: query.to_at,
    };
    try {
      const content = await api.exportAudit(filters, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(content);
      const link = document.createElement("a");
      try {
        link.href = url;
        link.download = "audit-history.csv";
        document.body.append(link);
        link.click();
      } finally {
        link.remove();
        URL.revokeObjectURL(url);
      }
      setExportNotice("Export prepared. Your browser download has started.");
      await client.invalidateQueries({ queryKey: ["audit-history", "list"] });
    } catch (error) {
      if (controller.signal.aborted) return;
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403)
      )
        expired();
      else
        setExportError(
          error instanceof ApiError && error.status === 413
            ? "This export exceeds 10,000 events. Narrow the date range or other filters, then try again."
            : "Unable to export audit history. Please try again.",
        );
    } finally {
      if (exportController.current === controller)
        exportController.current = null;
      if (!controller.signal.aborted) setExporting(false);
    }
  }
  // Clear search, category and dates while retaining the current ordering and rows-per-page preference.
  function clearFilters() {
    setSearch("");
    setFromInput("");
    setToInput("");
    setQuery((previous) => ({
      ...previous,
      query: "",
      category: "",
      from_at: null,
      to_at: null,
      page: 1,
    }));
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ACTIVITY &amp; HISTORY</span>
          <h1 tabIndex={-1}>Audit history</h1>
          <p className="muted">Review recorded application activity.</p>
        </div>
      </div>
      <p className="notice">
        Read-only, immutable history. These records show past activity and are
        not an action inbox.
      </p>
      <p id="audit-actor-help" className="field-help">
        Recorded actors include administrators and background workers. Failed
        sign-ins are unverified attempts.
      </p>
      <section className="table-panel" aria-label="Audit history directory">
        <div className="table-toolbar audit-toolbar">
          <label className="search-field">
            Search audit history
            <input
              type="search"
              value={search}
              maxLength={128}
              placeholder="Actor / administrator name or ID"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="state-filter">
            Category
            <Select
              aria-label="Category"
              value={query.category}
              onChange={(event) =>
                setQuery((previous) => ({
                  ...previous,
                  category: event.target.value as AuditFilters["category"],
                  page: 1,
                }))
              }
            >
              <option value="">All categories</option>
              {Object.entries(categories).map(([key, label]) => (
                <option value={key} key={key}>
                  {label}
                </option>
              ))}
            </Select>
          </label>
          <label className="audit-date-field">
            From (UTC)
            <input
              type="datetime-local"
              aria-label="From (UTC)"
              max="9999-12-31T23:59"
              value={fromInput}
              aria-invalid={invalidDates || invalidRange}
              aria-describedby="audit-date-help"
              onChange={(event) => setDates(event.target.value, toInput)}
            />
          </label>
          <label className="audit-date-field">
            Before (UTC)
            <input
              type="datetime-local"
              aria-label="Before (UTC)"
              max="9999-12-31T23:59"
              value={toInput}
              aria-invalid={invalidDates || invalidRange}
              aria-describedby="audit-date-help"
              onChange={(event) => setDates(fromInput, event.target.value)}
            />
          </label>
          <button
            className="button secondary"
            disabled={result.isFetching}
            onClick={() => void result.refetch()}
          >
            Refresh
          </button>
          <button
            className="button secondary"
            onClick={() => void exportCsv()}
            disabled={
              exporting ||
              result.isFetching ||
              result.isError ||
              !data?.total ||
              invalidDates ||
              invalidRange ||
              search !== query.query
            }
          >
            {exporting ? "Preparing export…" : "Export CSV"}
          </button>
          {filtered && (
            <button className="button secondary" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>
        <p className="audit-filter-help" id="audit-date-help">
          Dates use UTC. From is inclusive; Before is exclusive. CSV exports
          include all matching events, up to 10,000.
        </p>
        {invalidDates && (
          <p className="audit-feedback alert" role="alert">
            Enter valid UTC dates between years 0001 and 9999. Results use the
            last valid range.
          </p>
        )}
        {!invalidDates && invalidRange && (
          <p className="audit-feedback alert" role="alert">
            From must be earlier than Before. Results use the last valid range.
          </p>
        )}
        {exportError && (
          <p className="audit-feedback alert" role="alert">
            {exportError}
          </p>
        )}
        {exportNotice && (
          <p className="audit-feedback notice" role="status">
            {exportNotice}
          </p>
        )}
        {result.isPending ? (
          <p className="table-feedback" role="status">
            Loading audit history…
          </p>
        ) : result.isError ? (
          <p className="table-feedback alert" role="alert">
            Unable to load audit history. Use Refresh to try again.
          </p>
        ) : (
          <>
            {data?.total === 0 ? (
              <div className="table-feedback">
                <h2>
                  {filtered
                    ? "No events match your filters"
                    : "No audit history yet"}
                </h2>
                <p>
                  {filtered
                    ? "Change or clear the search, category or date filters."
                    : "Recorded activity will appear here when available."}
                </p>
              </div>
            ) : (
              <div
                className="table-scroll"
                role="region"
                aria-label="Scrollable audit history table"
                tabIndex={0}
              >
                <table className="audit-table">
                  <caption className="sr-only">
                    Immutable audit history with redacted event summaries
                  </caption>
                  <thead>
                    <tr>
                      {columns.map(([key, label]) => (
                        <th
                          key={key}
                          scope="col"
                          aria-describedby={
                            key === "actor_name"
                              ? "audit-actor-help"
                              : undefined
                          }
                          aria-sort={
                            query.sort === key
                              ? query.direction === "asc"
                                ? "ascending"
                                : "descending"
                              : "none"
                          }
                        >
                          <button
                            className="sort-button"
                            onClick={() => sort(key)}
                          >
                            {label}
                            <span aria-hidden="true">
                              {query.sort === key
                                ? query.direction === "asc"
                                  ? "↑"
                                  : "↓"
                                : "↕"}
                            </span>
                          </button>
                        </th>
                      ))}
                      <th scope="col">Category</th>
                      <th scope="col">Target</th>
                      <th scope="col">Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.items.map((entry) => (
                      <tr key={entry.id}>
                        <td>
                          <time dateTime={entry.at}>{stamp(entry.at)}</time>
                        </td>
                        <td>
                          <strong>{eventLabel(entry.kind)}</strong>
                          <span className="technical-id audit-event-id">
                            {entry.id}
                          </span>
                        </td>
                        <td>
                          {entry.kind === "local_sign_in_failed" ? (
                            <span className="muted">Unverified attempt</span>
                          ) : (
                            (entry.actor_name ?? (
                              <span className="muted">Not recorded</span>
                            ))
                          )}
                        </td>
                        <td>
                          <span className="audit-category">
                            {categories[entry.category]}
                          </span>
                        </td>
                        <td>
                          {entry.operation_id && (
                            <div className="audit-target">
                              <span>Operation</span>
                              <a
                                className="operation-link technical-id"
                                href={operationHref(entry.operation_id)}
                                onClick={(event) =>
                                  followLink(
                                    event,
                                    operationHref(entry.operation_id),
                                    navigate,
                                  )
                                }
                              >
                                {entry.operation_id}
                              </a>
                            </div>
                          )}
                          {!!entry.resources?.length && <div className="audit-resources">{entry.resources.length>3?<details><summary>{entry.resources.length} affected resources</summary>{entry.resources.map(resource=><div key={resource.kind+resource.id}>{resource.kind==="tenancy"?<a href={"/tenancies/"+resource.id} onClick={event=>followLink(event,"/tenancies/"+resource.id,navigate)}>{resource.name}</a>:<span>{resource.name}</span>}</div>)}</details>:entry.resources.map(resource=><div key={resource.kind+resource.id}><span className="cell-secondary">{resource.kind==="tenancy"?"Tenancy":"Employee"}</span>{resource.kind==="tenancy"?<a href={"/tenancies/"+resource.id} onClick={event=>followLink(event,"/tenancies/"+resource.id,navigate)}>{resource.name}</a>:<strong>{resource.name}</strong>}</div>)}</div>}
                          {entry.administrator_id && (
                            <div className="audit-target">
                              <span>Administrator</span>
                              <strong title="Current administrator display name">
                                {entry.administrator_name ?? "Name unavailable"}
                              </strong>
                              <span className="technical-id">
                                {entry.administrator_id}
                              </span>
                            </div>
                          )}
                          {entry.baseline_id && <a href={baselineHref(entry.baseline_id!,"/audit-history")} onClick={event => followLink(event, baselineHref(entry.baseline_id!,"/audit-history"), navigate)}>{entry.kind === "baseline_draft_saved" ? "Baseline draft" : "Published baseline"}</a>}
                          {!entry.operation_id && !entry.administrator_id && !entry.baseline_id && (
                            <span className="muted">
                              {entry.organization_subject_name ??
                                (entry.category === "organization"
                                  ? "Workspace organization"
                                  : "No recorded target")}
                            </span>
                          )}
                        </td>
                        <td>
                          {entry.summary ??
                            (entry.safe_code ? (
                              <code>{entry.safe_code}</code>
                            ) : (
                              <span className="muted">—</span>
                            ))}
                          {!!entry.changes?.length && (
                            <details className="audit-changes">
                              <summary>
                                View changes ({entry.changes.length})
                              </summary>
                              <ul>
                                {entry.changes.map((change, index) => (
                                  <li key={index}>{change}</li>
                                ))}
                              </ul>
                            </details>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="table-footer">
              <p role="status">
                {data?.total
                  ? `Showing ${(data.page - 1) * data.page_size + 1}–${Math.min(data.page * data.page_size, data.total)} of ${data.total}`
                  : "0 events"}
              </p>
              <div className="pagination">
                <label>
                  Rows{" "}
                  <Select
                    aria-label="Audit rows per page"
                    value={query.page_size}
                    onChange={(event) =>
                      setQuery((previous) => ({
                        ...previous,
                        page: 1,
                        page_size: Number(
                          event.target.value,
                        ) as AuditFilters["page_size"],
                      }))
                    }
                  >
                    {[10, 25, 50, 100].map((size) => (
                      <option key={size}>{size}</option>
                    ))}
                  </Select>
                </label>
                <button
                  className="button secondary"
                  disabled={page === 1}
                  onClick={() =>
                    setQuery((previous) => ({ ...previous, page: page - 1 }))
                  }
                >
                  Previous
                </button>
                <nav className="page-numbers" aria-label="Audit history pages">
                  {pages.map((number) => (
                    <button
                      className="button secondary"
                      key={number}
                      aria-label={`Page ${number}`}
                      aria-current={number === page ? "page" : undefined}
                      onClick={() =>
                        setQuery((previous) => ({ ...previous, page: number }))
                      }
                    >
                      {number}
                    </button>
                  ))}
                </nav>
                <span>
                  Page {page} of {pageCount}
                </span>
                <button
                  className="button secondary"
                  disabled={page === pageCount}
                  onClick={() =>
                    setQuery((previous) => ({ ...previous, page: page + 1 }))
                  }
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </>
  );
}
