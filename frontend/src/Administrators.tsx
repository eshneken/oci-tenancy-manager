import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTable } from "@tanstack/react-table";
import { api, ApiError, type AdministratorEnrollmentPreview } from "./api";
import type { AdministratorQuery, AdministratorView } from "./contracts";

const labels = [
  ["display_name", "Administrator"],
  ["email", "Email"],
  ["identity_kind", "Sign-in source"],
  ["status", "Status"],
] as const;
const initialQuery: AdministratorQuery = {
  page: 1,
  page_size: 10,
  sort: "display_name",
  direction: "asc",
  query: "",
};

// Show real grants with server paging and safe data rendering; never join credentials into this view.
export function Administrators({ expired }: { expired: () => void }) {
  const client = useQueryClient();
  const [query, setQuery] = useState(initialQuery);
  const [search, setSearch] = useState("");
  const searchInput = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState<AdministratorView | null>(null);
  const [message, setMessage] = useState("");
  const onboarding = useQuery({
    queryKey: ["administrator-onboarding"],
    queryFn: ({ signal }) => api.administratorOnboarding(signal),
    retry: false,
  });
  const canOnboard = onboarding.data?.enabled === true;
  const addDialog = useRef<HTMLDialogElement>(null);
  const [lookup, setLookup] = useState("");
  const [name, setName] = useState({ first_name: "", last_name: "" });
  const [review, setReview] = useState<AdministratorEnrollmentPreview | null>(null);
  const [addError, setAddError] = useState("");
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  const lookupInput = useRef<HTMLInputElement>(null);
  const [cleanupResults, setCleanupResults] = useState<Record<string, "pending" | "complete" | "failed">>({});
  useEffect(() => {
    if (!addDialog.current?.open) return;
    if (review) reviewHeading.current?.focus();
    else lookupInput.current?.focus();
  }, [review, addError]);
  const preview = useMutation({
    gcTime: 0,
    mutationFn: api.previewAdministrator,
    onSuccess: (current) => {
      if (current.existing_account) setName({ first_name: "", last_name: "" });
      setReview(current);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) expired();
      else setAddError(
        error instanceof ApiError && error.status === 409
          ? "This administrator already has Atlas access."
          : "Atlas could not prepare access for this email. Check the address and account status.",
      );
    },
  });
  const confirm = useMutation({
    gcTime: 0,
    mutationFn: (command: { confirmation: string; name?: Parameters<typeof api.confirmAdministrator>[2] }) =>
      api.confirmAdministrator(lookup.trim(), command.confirmation, command.name),
    onSuccess: () => {
      addDialog.current?.close();
      setMessage("Administrator access granted.");
      void client.invalidateQueries({ queryKey: ["administrators"] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) expired();
      else {
        setReview(null);
        setAddError("Grant could not be confirmed. Refresh the administrator list and verify the identity before retrying.");
        void client.invalidateQueries({ queryKey: ["administrators"] });
      }
    },
  });
  const cleanup = useMutation({
    mutationFn: (row: AdministratorView) =>
      api.retryAdministratorCleanup(row.id, row.authorization_revision),
    onMutate: () => {
      setMessage("Retrying OCI group cleanup…");
      return { trigger: document.activeElement instanceof HTMLButtonElement
        && document.activeElement.getAttribute("aria-label")?.startsWith("Retry OCI group cleanup for ")
          ? document.activeElement : null };
    },
    onSuccess: (result, row, context) => {
      if (result.group_cleanup === "complete" && context?.trigger && document.activeElement === context.trigger) {
        searchInput.current?.focus();
      }
      setCleanupResults((previous) => ({
        ...previous, [row.id + row.authorization_revision]: result.group_cleanup,
      }));
      setMessage(result.group_cleanup === "complete"
        ? "OCI group cleanup complete."
        : "Cleanup is still pending after the retry. Atlas access remains revoked.");
    },
    onError: (error, row) => {
      if (error instanceof ApiError && error.status === 401) {
        expired();
        return;
      }
      if (error instanceof ApiError && error.status === 409) {
        setMessage("This administrator changed. Review the refreshed list before retrying.");
        return;
      }
      setCleanupResults((previous) => ({
        ...previous, [row.id + row.authorization_revision]: "failed",
      }));
      setMessage("OCI group cleanup failed. Review the administrator row before retrying.");
    },
    onSettled: () => void client.invalidateQueries({ queryKey: ["administrators"] }),
  });
  const adding = preview.isPending || confirm.isPending;
  const dialog = useRef<HTMLDialogElement>(null);
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
  const directory = useQuery({
    queryKey: ["administrators", query],
    queryFn: ({ signal }) => api.directory(query, signal),
    retry: false,
  });
  useEffect(() => {
    // A denied directory read invalidates the current administrator view; target-specific denial does not.
    if (
      directory.error instanceof ApiError &&
      (directory.error.status === 401 || directory.error.status === 403)
    )
      expired();
  }, [directory.error, expired]);
  useEffect(() => {
    if (target) dialog.current?.showModal();
  }, [target]);
  const revoke = useMutation({
    mutationFn: (row: AdministratorView) =>
      api.revoke(row.id, row.authorization_revision),
    retry: false,
    onSuccess: (result, row) => {
      if (result && typeof result === "object" && "group_cleanup" in result
        && (result.group_cleanup === "complete" || result.group_cleanup === "pending") && dialog.current?.open) {
        dialog.current.close();
        searchInput.current?.focus();
      }
      if (result && typeof result === "object" && "group_cleanup" in result) {
        const state = result.group_cleanup;
        if ("authorization_revision" in result && typeof result.authorization_revision === "string"
          && (state === "pending" || state === "complete")) {
          const revision = result.authorization_revision;
          setCleanupResults((previous) => ({ ...previous, [row.id + revision]: state }));
        }
        if (state === "pending") {
          setMessage("Atlas access is revoked. OCI group cleanup can be retried.");
          return;
        }
      }
      setMessage("Administrator access revoked.");
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) expired();
      else
        setMessage(
          error instanceof ApiError && error.status === 409
            ? "This administrator changed. Refresh the list and review the current state."
            : "Revocation could not be confirmed. Refresh the list before trying again.",
        );
    },
    onSettled: () => {
      dialog.current?.close();
      setTarget(null);
      void client.invalidateQueries({ queryKey: ["administrators"] });
    },
  });
  const data = directory.data;
  const table = useTable({
    features: {},
    data: data?.items ?? [],
    columns: labels.map(([key, label]) => ({
      accessorKey: key,
      header: label,
    })),
  });
  // Pending privilege changes cannot be dismissed; Cancel is the safe initial modal focus.
  function cancel() {
    if (!revoke.isPending) {
      dialog.current?.close();
      setTarget(null);
    }
  }
  const first = data?.total ? (data.page - 1) * data.page_size + 1 : 0;
  const last = data ? Math.min(data.page * data.page_size, data.total) : 0;
  // Show a bounded page window while retaining access to neighboring destinations.
  const currentPage = data?.page ?? 1;
  const pageCount = data?.pages ?? 1;
  const pageStart = Math.max(1, Math.min(currentPage - 2, pageCount - 4));
  const pageNumbers = Array.from(
    { length: Math.min(5, pageCount) },
    (_, index) => pageStart + index,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">APPLICATION SETTINGS</span>
          <h1>Administrators</h1>
          <p className="muted">Control who can administer this application.</p>
        </div>
        <button
          className="button primary"
          disabled={!canOnboard}
          aria-describedby={canOnboard ? undefined : "corporate-help"}
          onClick={() => {
            setLookup("");
            setReview(null);
            setAddError("");
            addDialog.current?.showModal();
          }}
        >
          Add administrator
        </button>
      </div>
      {!canOnboard && (
        <p id="corporate-help" className="notice">
          Administrator onboarding is unavailable on this instance.
        </p>
      )}
      <div className="metrics" aria-label="Administrator statistics">
        {[
          ["Administrators", data?.statistics.total],
          ["Active", data?.statistics.active],
          ["Protected recovery", data?.statistics.protected_recovery],
        ].map(([label, value]) => (
          <div className="metric" key={label}>
            <span>{label}</span>
            <strong>{value ?? "—"}</strong>
          </div>
        ))}
      </div>
      {message && (
        <p className="notice" role="status">
          {message}
        </p>
      )}
      <section className="table-panel" aria-label="Administrator directory">
        <div className="table-toolbar">
          <label className="search-field">
            Search administrators
            <input
              ref={searchInput}
              type="search"
              placeholder="Name or email"
              value={search}
              maxLength={128}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <button
            className="button secondary"
            disabled={directory.isFetching}
            onClick={() => void directory.refetch()}
          >
            Refresh
          </button>
        </div>
        {directory.isPending ? (
          <p className="table-feedback" role="status">
            Loading administrators…
          </p>
        ) : directory.isError ? (
          <p className="table-feedback alert" role="alert">
            Unable to load administrators. Use Refresh to try again.
          </p>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <caption className="sr-only">
                  Application administrator access
                </caption>
                <thead>
                  <tr>
                    {labels.map(([key, label]) => (
                      <th
                        key={key}
                        scope="col"
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
                            setQuery((previous) => ({
                              ...previous,
                              page: 1,
                              sort: key,
                              direction:
                                previous.sort === key &&
                                previous.direction === "asc"
                                  ? "desc"
                                  : "asc",
                            }))
                          }
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
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.original.display_name}</strong>
                        {row.original.identity_kind === "local_recovery" && (
                          <span className="protected-label">
                            Protected recovery account
                          </span>
                        )}
                      </td>
                      <td>
                        {row.original.email ?? (
                          <span className="muted">No email</span>
                        )}
                      </td>
                      <td>
                        {row.original.identity_kind === "local_recovery"
                          ? "Local recovery"
                          : "Corporate SSO"}
                      </td>
                      <td>
                        <span className={"badge " + row.original.status}>
                          {row.original.status === "active"
                            ? "Active"
                            : "Revoked"}
                        </span>
                      </td>
                      <td>
                        {row.original.identity_kind === "local_recovery" ? (
                          <span className="muted">Operator-managed</span>
                        ) : row.original.status === "active" ? (
                          <button
                            className="button compact secondary"
                            onClick={() => setTarget(row.original)}
                          >
                            {canOnboard ? "Remove access" : "Revoke"}
                          </button>
                        ) : canOnboard ? (
                          cleanupResults[row.original.id + row.original.authorization_revision] === "complete" ? (
                            <span className="muted">Group cleanup complete</span>
                          ) : (
                            <>
                              <button className="button compact secondary" aria-disabled={cleanup.isPending}
                                aria-label={`Retry OCI group cleanup for ${row.original.display_name}`}
                                onClick={() => { if (!cleanup.isPending) cleanup.mutate(row.original); }}>
                                {cleanup.isPending && cleanup.variables?.id === row.original.id
                                  ? "Retrying…" : "Retry OCI group cleanup"}
                              </button>
                              {cleanupResults[row.original.id + row.original.authorization_revision] === "failed" && (
                                <div className="muted">Cleanup failed</div>
                              )}
                              {cleanupResults[row.original.id + row.original.authorization_revision] === "pending" && (
                                <div className="muted">Cleanup pending</div>
                              )}
                            </>
                          )
                        ) : (
                          <span className="muted">No action</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data?.total === 0 && (
              <div className="table-feedback">
                <h2>No administrators match your search</h2>
                <p>Try a different name or email.</p>
                <button
                  className="button secondary"
                  onClick={() => setSearch("")}
                >
                  Clear search
                </button>
              </div>
            )}
            <div className="table-footer">
              <p role="status">
                {data?.total
                  ? "Showing " + first + "–" + last + " of " + data.total
                  : "0 results"}
              </p>
              <div className="pagination">
                <label>
                  Rows{" "}
                  <Select
                    aria-label="Rows per page"
                    value={query.page_size}
                    onChange={(event) =>
                      setQuery((previous) => ({
                        ...previous,
                        page: 1,
                        page_size: Number(
                          event.target.value,
                        ) as AdministratorQuery["page_size"],
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
                  disabled={data?.page === 1}
                  onClick={() =>
                    setQuery((previous) => ({
                      ...previous,
                      page: (data?.page ?? 1) - 1,
                    }))
                  }
                >
                  Previous
                </button>
                <nav className="page-numbers" aria-label="Administrator pages">
                  {pageNumbers.map((page) => (
                    <button
                      key={page}
                      className="button secondary"
                      aria-label={`Page ${page}`}
                      aria-current={page === currentPage ? "page" : undefined}
                      onClick={() =>
                        setQuery((previous) => ({ ...previous, page }))
                      }
                    >
                      {page}
                    </button>
                  ))}
                </nav>
                <span>
                  Page {data?.page} of {data?.pages}
                </span>
                <button
                  className="button secondary"
                  disabled={data?.page === data?.pages}
                  onClick={() =>
                    setQuery((previous) => ({
                      ...previous,
                      page: (data?.page ?? 1) + 1,
                    }))
                  }
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
      <dialog
        ref={addDialog}
        aria-labelledby="administrator-add-title"
        onClose={() => {
          setLookup("");
          setName({ first_name: "", last_name: "" });
          setReview(null);
          setAddError("");
          preview.reset();
          confirm.reset();
        }}
        onCancel={(event) => { if (adding) event.preventDefault(); }}
      >
        <h2 id="administrator-add-title">Add administrator</h2>
        <form onSubmit={(event) => {
          event.preventDefault();
          if (adding) return;
          setAddError("");
          if (!review) {
            preview.mutate(lookup.trim());
          } else if (review.existing_account) {
            confirm.mutate({ confirmation: review.confirmation });
          } else {
            const first_name = name.first_name.trim();
            const last_name = name.last_name.trim();
            if (first_name && last_name) confirm.mutate({ confirmation: review.confirmation, name: { first_name, last_name } });
          }
        }}>
          {review ? (
            <>
              <h3 ref={reviewHeading} tabIndex={-1}>Review administrator access</h3>
              <dl className="administrator-review-details">
                {review.display_name !== review.work_email && (
                  <><dt>OCI display name</dt><dd>{review.display_name}</dd></>
                )}
                <dt>Work email</dt><dd>{review.work_email}</dd>
                <dt>Environment</dt><dd>{review.environment}</dd>
                <dt>Access</dt><dd>{review.role}</dd>
              </dl>
              {review.existing_account
                ? <p>Atlas will use the existing OCI account. Sign-in to Atlas requires Oracle SSO.</p>
                : <>
                  <p>Atlas will create a federated OCI account for this email. Enter the person’s name and check the address before granting access.</p>
                  <div className="administrator-name-fields">
                    <label className="administrator-form-field">
                      First name
                      <input value={name.first_name} onChange={(event) => setName({ ...name, first_name: event.target.value })}
                        autoComplete="off" pattern={String.raw`.*\S.*`} required maxLength={100} disabled={adding} />
                    </label>
                    <label className="administrator-form-field">
                      Last name
                      <input value={name.last_name} onChange={(event) => setName({ ...name, last_name: event.target.value })}
                        autoComplete="off" pattern={String.raw`.*\S.*`} required maxLength={100} disabled={adding} />
                    </label>
                  </div>
                </>}
            </>
          ) : (
            <label className="administrator-form-field">
              Corporate work email
              <input ref={lookupInput} type="email" autoComplete="off" value={lookup} onChange={(event) => {
                setLookup(event.target.value);
                if (lookup.trim() !== event.target.value.trim()) setName({ first_name: "", last_name: "" });
              }}
                required maxLength={254} disabled={adding} />
            </label>
          )}
          {addError && <p role="alert" className="alert">{addError}</p>}
          <div className="dialog-actions">
            <button type="button" className="button secondary" disabled={adding}
              onClick={() => addDialog.current?.close()}>Cancel</button>
            <button key={review ? "grant" : "verify"} type="submit" className="button primary" disabled={adding}>
              {adding ? "Working…" : review ? "Grant access" : "Review access"}
            </button>
          </div>
        </form>
      </dialog>
      <dialog
        ref={dialog}
        aria-labelledby="revoke-title"
        onCancel={(event) => {
          event.preventDefault();
          cancel();
        }}
      >
        <h2 id="revoke-title">Revoke administrator access?</h2>
        <p>
          <strong>{target?.display_name}</strong> will lose access to this
          application and their active sessions will end.
        </p>
        {canOnboard && target && (
          <>
            <dl className="administrator-review-details">
              <dt>{target.email ? "Work email" : "Atlas grant reference"}</dt>
              <dd>{target.email ?? target.id}</dd>
              <dt>Environment</dt><dd>{onboarding.data?.environment}</dd>
            </dl>
            <p>Atlas will remove this environment’s app-group membership. The OCI account and other groups will remain.</p>
          </>
        )}
        <p>Tenancy ownership and resources are not changed.</p>
        <div className="dialog-actions">
          <button
            className="button secondary"
            autoFocus
            disabled={revoke.isPending}
            onClick={cancel}
          >
            Cancel
          </button>
          <button
            className="button danger"
            disabled={revoke.isPending}
            onClick={() => target && revoke.mutate(target)}
          >
            {revoke.isPending ? "Revoking…" : "Revoke access"}
          </button>
        </div>
      </dialog>
    </>
  );
}
