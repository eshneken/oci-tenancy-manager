import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTable } from "@tanstack/react-table";
import { api, ApiError } from "./api";
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
  const [target, setTarget] = useState<AdministratorView | null>(null);
  const [message, setMessage] = useState("");
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
    onSuccess: () => setMessage("Administrator access revoked."),
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
          disabled
          aria-describedby="corporate-help"
        >
          Add administrator
        </button>
      </div>
      <p id="corporate-help" className="notice">
        Additional administrators require a verified corporate identity.
        Corporate sign-in is not configured.
      </p>
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
                            Revoke
                          </button>
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
