import {operationHref} from "./operationNavigation";
import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, CsvUploadError } from "./api";
import type { OrganizationQuery } from "./contracts";
import { OrganizationReviews } from "./OrganizationReviews";
import { PersonActions, refreshOrganization } from "./PersonActions";
import { followLink } from "./navigation";

const initial: OrganizationQuery = {
  page: 1,
  page_size: 10,
  sort: "full_name",
  direction: "asc",
  query: "",
};
const columns = [
  ["full_name", "Employee"],
  ["email", "Email"],
  ["manager_name", "Direct manager"],
  ["leader_name", "Accountable leader"],
  ["lob_name", "Industry segment"],
  ["tenancy_count", "Tenancies"],
] as const;
const labels: Record<string, string> = {
  PERSON_ABSENCE_REVIEW: "Absence review",
  LOB_MAPPING_REVIEW: "Industry segment mapping review",
  ANCESTRY_UNRESOLVED: "Reporting chain incomplete",
  TOP_MANAGER_MISMATCH: "Top manager mismatch",
  MANAGER_PROFILE_MISSING: "Manager profile missing",
  LOB_LEADER_REVIEW: "Leader needs attention",
  DESIGNEE_INVALID: "Designee needs attention",
  OVERRIDE_CONFLICT: "Override conflict",
  EMPLOYEE_ADDED: "Employee added",
  METADATA_UPDATED: "Metadata updated",
};

// Keep the approved directory and drift flow on live, scoped organization data.
export function Organization({
  drift,
  expired,
  navigate,
}: {
  drift: boolean;
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const [selectedPerson, setSelectedPerson] = useState<string | null>(null);
  const [query, setQuery] = useState(initial);
  const [tab, setTab] = useState<"actionable" | "informational">("actionable");
  const [resetOpen, setResetOpen] = useState(false);
  const resetDialog = useRef<HTMLDialogElement>(null);
  const resetHeading = useRef<HTMLHeadingElement>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [asOf, setAsOf] = useState("");
  const [complete, setComplete] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const controller = useRef<AbortController | null>(null);
  const delivery = useRef("");
  const read = useQuery({
    queryKey: ["organization", query],
    queryFn: ({ signal }) => api.organization(query, signal),
    placeholderData: (previous) => previous,
    retry: false,
    refetchInterval: (value) =>
      value.state.data?.pending_workflows ? 2000 : false,
  });
  const data = read.data;
  useEffect(() => {
    if (
      read.error instanceof ApiError &&
      [401, 403].includes(read.error.status)
    )
      expired();
  }, [read.error, expired]);
  useEffect(() => {
    if (uploadOpen) dialog.current?.showModal();
  }, [uploadOpen]);
  useEffect(() => {
    if (resetOpen) {
      resetDialog.current?.showModal();
      resetHeading.current?.focus();
    }
  }, [resetOpen]);
  // Leaving the page discards the selected file and prevents late upload results restoring private state.
  useEffect(() => () => controller.current?.abort(), []);
  const actionable =
    data?.findings.filter((item) => item.category === "actionable") ?? [];
  const information =
    data?.findings.filter((item) => item.category !== "actionable") ?? [];
  const findings = tab === "actionable" ? actionable : information;

  // Default from the server UTC clock; require the administrator to attest the export's actual time.
  async function openUpload() {
    const fresh = await read.refetch();
    if (fresh.error || !fresh.data) return;
    setFile(null);
    setError("");
    setComplete(true);
    delivery.current = "";
    setAsOf(fresh.data.server_time.slice(0, 19));
    setUploadOpen(true);
  }

  // Close natively before removing the dialog so keyboard focus returns to its trigger.
  function closeReset() {
    resetDialog.current?.close();
    setResetOpen(false);
  }

  // Native dialog cancellation remains safe; an in-flight upload cannot be dismissed as completed.
  function closeUpload() {
    if (!busy) {
      dialog.current?.close();
      setUploadOpen(false);
      setFile(null);
    }
  }

  // Preserve a request UUID on uncertain transport failure; selecting/changing input starts a new delivery.
  async function submit() {
    if (!file) {
      setError("Choose an organization CSV.");
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setError("CSV exceeds the 2 MiB upload limit.");
      return;
    }
    if (
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(asOf) ||
      !Number.isFinite(Date.parse(asOf + "Z")) ||
      new Date(asOf + "Z").toISOString().slice(0, asOf.length) !== asOf ||
      asOf.startsWith("0000-")
    ) {
      setError("Confirm a valid organization data date and time.");
      return;
    }
    delivery.current ||= crypto.randomUUID();
    controller.current = new AbortController();
    const signal = controller.current.signal;
    setBusy(true);
    setError("");
    try {
      const result = await api.uploadOrganization(
        file,
        new Date(asOf + "Z").toISOString(),
        delivery.current,
        complete,
        signal,
      );
      if (signal.aborted) return;
      setNotice(
        result.state === "published" || result.original_state === "published"
          ? "Organization feed processed. Valid metadata is up to date."
          : "Feed was not applied. Review the intake diagnostics; the current organization is unchanged.",
      );
      dialog.current?.close();
      setUploadOpen(false);
      setFile(null);
      await refreshOrganization(client);
    } catch (failure) {
      if (signal.aborted) return;
      if (failure instanceof ApiError && [401, 403].includes(failure.status))
        expired();
      else
        setError(
          failure instanceof CsvUploadError
            ? failure.guidance
            : "Upload could not be confirmed. Retry here with unchanged inputs to reuse this request. Before starting a new upload, check the latest intake result.",
        );
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  const pageCount = data?.pages ?? 1;
  const pageStart = Math.max(1, Math.min((data?.page ?? 1) - 2, pageCount - 4));
  const pageNumbers = Array.from(
    { length: Math.min(5, pageCount) },
    (_, index) => pageStart + index,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ORGANIZATION</span>
          <h1 tabIndex={-1}>{drift ? "Organization drift" : "Organization"}</h1>
          <p className="muted">
            {drift
              ? "Review organization exceptions separately from informational changes."
              : "Current employees and their accountability structure."}
          </p>
        </div>
        {!drift && (
          <div className="organization-actions">
            {data?.test_reset_enabled && (
              <button
                className="button secondary"
                onClick={() => setResetOpen(true)}
              >
                Reset test organization
              </button>
            )}
            <button
              className="button primary"
              disabled={!data?.upload_enabled}
              onClick={() => void openUpload()}
            >
              Upload organization CSV
            </button>
          </div>
        )}
      </div>
      <div className="metrics" aria-label="Organization statistics">
        {[
          ["Employees", data?.employee_count],
          ["Absence reviews", data?.absence_count],
          [
            "Actionable items",
            data
              ? data.workflows_enabled
                ? data.actionable_count
                : actionable.length
              : undefined,
          ],
        ].map(([label, value]) => (
          <div className="metric" key={label}>
            <span>{label}</span>
            <strong>{value ?? "—"}</strong>
          </div>
        ))}
      </div>
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {read.isPending ? (
        <p role="status">Loading organization…</p>
      ) : read.isError ? (
        <div role="alert">
          <p>Organization could not be loaded.</p>
          <button
            className="button secondary"
            onClick={() => void read.refetch()}
          >
            Try again
          </button>
        </div>
      ) : (
        data && (
          <>
            {!data.upload_enabled && (
              <p className="notice">
                Save Organization Mapping before uploading the first feed.{" "}
                <a
                  href="/organization-mapping"
                  onClick={(e) =>
                    followLink(e, "/organization-mapping", navigate)
                  }
                >
                  Open Organization Mapping
                </a>
              </p>
            )}
            {data.applied_at && (
              <p className="muted">
                Organization data as of{" "}
                {new Date(data.source_as_of!).toLocaleString("en-US", {
                  timeZone: "UTC",
                  timeZoneName: "short",
                })}{" "}
                ·{" "}
                {data.absence_eligible
                  ? "Complete census qualified for absence checks"
                  : "Absence checks not qualified for this feed"}
              </p>
            )}
            {data.latest && (data.latest.diagnostics?.length ?? 0) > 0 && (
              <details
                className="panel intake-diagnostics"
                open={
                  data.latest.state === "rejected" ||
                  data.latest.state === "superseded"
                }
              >
                <summary>Intake diagnostics · {data.latest.state}</summary>
                <ul>
                  {data.latest.diagnostics?.map((item, index) => (
                    <li key={index}>
                      <strong>{item.code.replaceAll("_", " ")}</strong>
                      {item.affected_email && <> · {item.affected_email}</>}
                      {item.fatal && " · Feed not applied"}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {drift && data.workflows_enabled ? (
              <OrganizationReviews expired={expired} navigate={navigate} />
            ) : drift ? (
              <>
                <div
                  className="org-tabs"
                  role="group"
                  aria-label="Drift category"
                >
                  <button
                    className={
                      "button " +
                      (tab === "actionable" ? "primary" : "secondary")
                    }
                    aria-pressed={tab === "actionable"}
                    onClick={() => setTab("actionable")}
                  >
                    Actionable <span>{actionable.length}</span>
                  </button>
                  <button
                    className={
                      "button " +
                      (tab === "informational" ? "primary" : "secondary")
                    }
                    aria-pressed={tab === "informational"}
                    onClick={() => setTab("informational")}
                  >
                    Informational &amp; changes{" "}
                    <span>{information.length}</span>
                  </button>
                </div>
                <p className="notice">
                  Tenancy workflows are not connected yet. This screen does not
                  create or delete tenancies, remove employees, or close
                  reviews.
                </p>
                <section className="table-panel">
                  <div
                    className="table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label={
                      drift
                        ? "Organization drift results"
                        : "Organization directory"
                    }
                  >
                    <table>
                      <caption className="sr-only">
                        {drift
                          ? "Organization drift findings"
                          : "Current organization employees"}
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Employee</th>
                          <th scope="col">Finding</th>
                          <th scope="col">Details</th>
                          <th scope="col">Observed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {findings.map((item, index) => (
                          <tr key={index}>
                            <td>
                              <strong>{item.employee_name}</strong>
                              <br />
                              <span className="muted">{item.email}</span>
                            </td>
                            <td>
                              {labels[item.code] ??
                                item.code.replaceAll("_", " ")}
                            </td>
                            <td>{item.detail}</td>
                            <td>
                              {new Date(item.at).toLocaleString("en-US", {
                                timeZone: "UTC",
                                timeZoneName: "short",
                              })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {findings.length === 0 && (
                    <div className="table-feedback">
                      <h2>
                        {tab === "actionable"
                          ? "No actionable organization drift"
                          : "No informational changes"}
                      </h2>
                      <p>New feed results will appear here.</p>
                    </div>
                  )}
                </section>
                <p className="muted">
                  Changes show the latest applied feed. Earlier snapshots remain
                  in the database; administrative activity is available in Audit
                  history.
                </p>
              </>
            ) : (
              <>
                <section className="table-panel">
                  <div className="table-toolbar organization-toolbar directory-toolbar">
                    <label className="search-field">
                      Search employees
                      <input
                        type="search"
                        maxLength={128}
                        value={query.query}
                        onChange={(event) =>
                          setQuery({
                            ...query,
                            query: event.target.value,
                            page: 1,
                          })
                        }
                        placeholder="Name, email, manager or industry segment"
                      />
                    </label>
                    {data.workflows_enabled && (
                      <label className="workflow-check directory-filter">
                        <input
                          type="checkbox"
                          checked={query.include_removed ?? false}
                          onChange={(event) =>
                            setQuery({
                              ...query,
                              include_removed: event.target.checked,
                              page: 1,
                            })
                          }
                        />
                        Include excluded profiles
                      </label>
                    )}
                    <a
                      href="/organization/drift"
                      onClick={(event) =>
                        followLink(event, "/organization/drift", navigate)
                      }
                    >
                      View organization drift (
                      {data.workflows_enabled
                        ? data.actionable_count
                        : actionable.length}
                      )
                    </a>
                  </div>
                  <div
                    className="table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label={
                      drift
                        ? "Organization drift results"
                        : "Organization directory"
                    }
                  >
                    <table>
                      <caption className="sr-only">
                        {drift
                          ? "Organization drift findings"
                          : "Current organization employees"}
                      </caption>
                      <thead>
                        <tr>
                          {columns.map(([key, label]) => (
                            <th
                              scope="col"
                              key={key}
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
                                onClick={() =>
                                  setQuery({
                                    ...query,
                                    page: 1,
                                    sort: key,
                                    direction:
                                      query.sort === key &&
                                      query.direction === "asc"
                                        ? "desc"
                                        : "asc",
                                  })
                                }
                              >
                                {label}{" "}
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
                        </tr>
                      </thead>
                      <tbody>
                        {data.items.map((item) => (
                          <tr key={item.id}>
                            <td>
                              {data.workflows_enabled ? (
                                <button
                                  className="text-link"
                                  onClick={() => setSelectedPerson(item.id)}
                                >
                                  {item.full_name}
                                </button>
                              ) : (
                                <strong>{item.full_name}</strong>
                              )}
                              {item.directory_status &&
                                item.directory_status !== "included" && (
                                  <span className="cell-secondary">
                                    {
                                      {
                                        exempt: "No tenancy required",
                                        offboarded: "Offboarded",
                                        outside: "Outside organization",
                                        merged: "Merged identity",
                                      }[item.directory_status]
                                    }
                                  </span>
                                )}
                              {item.pending_operation_id && (
                                <a
                                  className="cell-secondary"
                                  href={
                                    operationHref(item.pending_operation_id)
                                  }
                                  onClick={(event) =>
                                    followLink(
                                      event,
                                      operationHref(item.pending_operation_id),
                                      navigate,
                                    )
                                  }
                                >
                                  Operation pending
                                </a>
                              )}
                              {item.absence_review && (
                                <span className="org-review">
                                  Absence review
                                </span>
                              )}
                            </td>
                            <td>{item.email}</td>
                            <td>{item.manager_name ?? "—"}</td>
                            <td>{item.leader_name ?? "—"}</td>
                            <td>{item.lob_name ?? "Unmapped"}</td>
                            <td>
                              {item.tenancy_count ?? 0}
                              {Boolean(item.pending_tenancy_count) && (
                                <span className="cell-secondary">
                                  {item.pending_tenancy_count} pending
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.items.length === 0 && (
                    <div className="table-feedback">
                      <h2>
                        {query.query
                          ? "No employees match your search"
                          : "No organization feed loaded"}
                      </h2>
                      <p>
                        {query.query
                          ? "Try another name, email or industry segment."
                          : "Upload a CSV to populate the directory and review organization drift."}
                      </p>
                    </div>
                  )}
                  <div className="table-footer">
                    <label>
                      Rows per page{" "}
                      <Select
                        aria-label="Organization rows per page"
                        value={query.page_size}
                        onChange={(event) =>
                          setQuery({
                            ...query,
                            page: 1,
                            page_size: Number(event.target.value) as
                              10 | 25 | 50,
                          })
                        }
                      >
                        {[10, 25, 50].map((size) => (
                          <option key={size}>{size}</option>
                        ))}
                      </Select>
                    </label>
                    <span>
                      {data.total} {data.total === 1 ? "employee" : "employees"}{" "}
                      · Page {data.page} of {data.pages}
                    </span>
                    <div className="pagination">
                      <button
                        className="button secondary"
                        disabled={data.page <= 1}
                        onClick={() =>
                          setQuery({ ...query, page: data.page - 1 })
                        }
                      >
                        Previous
                      </button>
                      <nav
                        className="page-numbers"
                        aria-label="Organization pages"
                      >
                        {pageNumbers.map((number) => (
                          <button
                            key={number}
                            className="button secondary"
                            aria-label={"Page " + number}
                            aria-current={
                              number === data.page ? "page" : undefined
                            }
                            onClick={() => setQuery({ ...query, page: number })}
                          >
                            {number}
                          </button>
                        ))}
                      </nav>
                      <button
                        className="button secondary"
                        disabled={data.page >= data.pages}
                        onClick={() =>
                          setQuery({ ...query, page: data.page + 1 })
                        }
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </section>
              </>
            )}
          </>
        )
      )}
      {selectedPerson && (
        <PersonActions
          personId={selectedPerson}
          expired={expired}
          navigate={navigate}
          onClose={() => setSelectedPerson(null)}
        />
      )}
      {resetOpen && (
        <dialog
          className="org-upload-dialog"
          ref={resetDialog}
          aria-labelledby="org-reset-title"
          onCancel={(event) => {
            event.preventDefault();
            closeReset();
          }}
        >
          <h2 id="org-reset-title" tabIndex={-1} ref={resetHeading}>
            Reset test organization
          </h2>
          <p>
            Run from the project directory in a local terminal. Replace the
            installation path with the directory for the instance you intend to
            reset; do not omit --directory.
          </p>
          <pre className="reset-command">
            {
              'uv run --project backend otm-local reset-organization --directory "/absolute/path/to/this/installation" --confirm-reset-organization'
            }
          </pre>
          <p>
            This clears organization feeds, employee records, versions, current
            findings and imported organization configuration. Your configured
            trusted source policy remains available; save Organization Mapping
            again before the next upload.
          </p>
          <p>
            Baseline drafts are also removed. Administrators, credentials, sessions, operations and audit history
            are preserved. This control does not execute the command.
          </p>
          <p className="muted">
            After the command succeeds, refresh the organization below.
          </p>
          <div className="dialog-actions">
            <button className="button secondary" onClick={closeReset}>
              Close
            </button>
            <button
              className="button secondary"
              onClick={() => {
                closeReset();
                setNotice("");
                setQuery(initial);
                void client.invalidateQueries({ queryKey: ["organization"] });
              }}
            >
              Refresh organization
            </button>
          </div>
        </dialog>
      )}
      {uploadOpen && (
        <dialog
          className="org-upload-dialog"
          ref={dialog}
          aria-labelledby="org-upload-title"
          onCancel={(event) => {
            event.preventDefault();
            closeUpload();
          }}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <div className="dialog-heading">
              <h2 id="org-upload-title">Upload organization CSV</h2>
            </div>
            <p>
              Use UTF-8 CSV with exactly EMPLOYEE_FULL_NAME, EMAIL, MGR and
              TOP_MGR. Maximum 2 MiB and 5,000 employees.
            </p>
            <label>
              Organization CSV
              <input
                type="file"
                accept=".csv,text/csv"
                disabled={busy}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  delivery.current = "";
                  setError("");
                }}
              />
            </label>
            <label>
              Organization data as of (UTC)
              <input
                type="datetime-local"
                step="1"
                value={asOf}
                required
                disabled={busy}
                onChange={(event) => {
                  setAsOf(event.target.value);
                  delivery.current = "";
                }}
              />
            </label>
            <p className="muted">
              Confirm when the exported organization data was current. Upload
              time may be different.
            </p>
            <label className="org-check">
              <input
                type="checkbox"
                checked={complete}
                disabled={busy}
                onChange={(event) => {
                  setComplete(event.target.checked);
                  delivery.current = "";
                }}
              />
              This file contains the complete organization
            </label>
            <p className="muted">
              Partial feeds update metadata but cannot identify absent
              employees. Valid metadata updates automatically.
            </p>
            {error && (
              <p className="alert" role="alert">
                {error}
              </p>
            )}
            <div className="dialog-actions">
              <button
                type="button"
                className="button secondary"
                disabled={busy}
                onClick={closeUpload}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? "Processing…" : "Process feed"}
              </button>
            </div>
          </form>
        </dialog>
      )}
    </>
  );
}
