import {operationHref} from "./operationNavigation";
import { Select } from "./Select";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { ReviewQuery, ReviewView } from "./contracts";
import { PersonActions } from "./PersonActions";
import { followLink } from "./navigation";

const names: Record<string, string> = {
  TENANCY_SETUP_REVIEW: "New employee",
  PERSON_ABSENCE_REVIEW: "Absence review",
  LOB_MAPPING_REVIEW: "Industry segment mapping review",
  LOB_LEADER_REVIEW: "Leader needs attention",
  DESIGNEE_INVALID: "Designee needs attention",
  OVERRIDE_CONFLICT: "Override conflict",
  TOP_MANAGER_MISMATCH: "Top manager mismatch",
  MANAGER_PROFILE_MISSING: "Manager profile missing",
  ANCESTRY_UNRESOLVED: "Reporting chain incomplete",
  ORGANIZATION_BASELINE: "Organization baseline",
  EMPLOYEE_ADDED: "Employee added",
  METADATA_UPDATED: "Metadata updated",
  LIFECYCLE_COMPLETED: "Simulated lifecycle verified",
};
const descriptions: Record<string, string> = {
  TENANCY_SETUP_REVIEW:
    "Choose tenancy onboarding or record that no tenancy is required.",
  PERSON_ABSENCE_REVIEW:
    "Review all registered associations before deciding how to offboard or retain this employee.",
  LOB_MAPPING_REVIEW:
    "Repair Organization Mapping before provisioning this employee. This review closes automatically when the mapping is valid.",
  LOB_LEADER_REVIEW:
    "Review the accountable leader's current reporting structure.",
  DESIGNEE_INVALID:
    "Review the nominated designee in organization configuration.",
  OVERRIDE_CONFLICT:
    "An administrator correction differs from the incoming source.",
  TOP_MANAGER_MISMATCH:
    "Correct the reported top manager or reporting relationships in the source.",
  MANAGER_PROFILE_MISSING:
    "A referenced manager has no employee row. Supply that profile in the source.",
  ANCESTRY_UNRESOLVED: "Correct the incomplete reporting chain in the source.",
};
const fieldNames: Record<string, string> = {
  full_name: "Name",
  email: "Email",
  manager_email: "Manager",
  lob_id: "Industry segment",
  accountable_leader_email: "Accountable leader",
  designee_emails: "Designees",
};

// All screen dates use UTC, matching the source-time confirmation and immutable audit history.
function stamp(value: string) {
  return new Date(value).toLocaleString("en-US", {
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

// Show bounded historical change fields with pinned display labels, never raw source/configuration.
function Changes({ row }: { row: ReviewView }) {
  if (row.kind === "ORGANIZATION_BASELINE")
    return (
      <span>
        {String(row.data.count ?? 0)} employees in the initial baseline.
      </span>
    );
  if (row.kind === "LIFECYCLE_COMPLETED")
    return (
      <span>
        Registry and access association changes were verified by the local
        simulator.
      </span>
    );
  const before = row.data.before as Record<string, unknown> | undefined;
  const after = row.data.after as Record<string, unknown> | undefined;
  // Preserve ID-based change detection while displaying safe server-resolved segment names.
  function value(profile: Record<string, unknown> | undefined, key: string) {
    const item = key === "lob_id" ? profile?.lob_name : profile?.[key];
    return Array.isArray(item) ? item.join(", ") : String(item ?? "—");
  }
  if (after) {
    const keys = Object.keys(fieldNames).filter(
      (key) => JSON.stringify(before?.[key]) !== JSON.stringify(after[key]),
    );
    return (
      <details className="review-changes">
        <summary>
          {before
            ? keys.map((key) => fieldNames[key]).join(", ") + " updated"
            : "Employee profile added"}
        </summary>
        <dl>
          {keys.map((key) => (
            <div key={key}>
              <dt>{fieldNames[key]}</dt>
              <dd>
                {before ? value(before, key) + " → " : ""}
                {value(after, key)}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    );
  }
  return (
    <span>{descriptions[row.kind] ?? "Recorded organization review."}</span>
  );
}

// Separate the actionable inbox from latest-feed information and optional retained history.
export function OrganizationReviews({
  expired,
  navigate,
}: {
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const [query, setQuery] = useState<ReviewQuery>({
    category: "actionable",
    query: "",
    page: 1,
    page_size: 10,
    sort: "first_seen_at",
    direction: "asc",
  });
  const [showAllHistory, setShowAllHistory] = useState(false);
  const [selected, setSelected] = useState<{
    person: string;
    review: string | null;
  } | null>(null);
  const result = useQuery({
    queryKey: ["organization-reviews", query],
    queryFn: ({ signal }) => api.organizationReviews(query, signal),
    placeholderData: (previous, previousQuery) =>
      (previousQuery?.queryKey[1] as ReviewQuery | undefined)?.category ===
      query.category
        ? previous
        : undefined,
    retry: false,
    refetchInterval: 5000,
  });
  const data = result.data;
  useEffect(() => {
    if (
      result.error instanceof ApiError &&
      [401, 403].includes(result.error.status)
    )
      expired();
  }, [result.error, expired]);
  const pageStart = Math.max(
    1,
    Math.min((data?.page ?? 1) - 2, (data?.pages ?? 1) - 4),
  );
  const pages = Array.from(
    { length: Math.min(5, data?.pages ?? 1) },
    (_, index) => pageStart + index,
  );

  // Sorting always restarts at page one while preserving the chosen review family and search.
  function sort(column: "name" | "kind" | "first_seen_at" | "status") {
    setQuery({
      ...query,
      page: 1,
      sort: column,
      direction:
        query.sort === column && query.direction === "asc" ? "desc" : "asc",
    });
  }

  return (
    <>
      <div className="org-tabs" role="group" aria-label="Drift category">
        <button
          className={
            "button " +
            (query.category === "actionable" ? "primary" : "secondary")
          }
          aria-pressed={query.category === "actionable"}
          onClick={() =>
            setQuery({
              ...query,
              category: "actionable",
              page: 1,
              direction: "asc",
            })
          }
        >
          Actionable <span>{data?.actionable_count ?? "—"}</span>
        </button>
        <button
          className={
            "button " + (query.category !== "actionable" ? "primary" : "secondary")
          }
          aria-pressed={query.category !== "actionable"}
          onClick={() =>
            setQuery({
              ...query,
              category: showAllHistory ? "history" : "informational",
              page: 1,
              direction: "desc",
            })
          }
        >
          Informational &amp; history <span>{(showAllHistory ? data?.history_count : data?.informational_count) ?? "—"}</span>
        </button>
      </div>
      <p className="muted">
        {query.category === "actionable"
          ? "Reviews remain here until an administrator decides or hands work to an operation."
          : showAllHistory
            ? "All retained source warnings, metadata changes and completed decisions."
            : "Informational alerts and metadata changes from the latest applied feed."}
      </p>
      <section className="table-panel">
        <div className="table-toolbar">
          <label className="search-field">
            Search organization reviews
            <input
              type="search"
              maxLength={128}
              value={query.query}
              placeholder="Employee, email or review"
              onChange={(event) =>
                setQuery({ ...query, query: event.target.value, page: 1 })
              }
            />
          </label>
          {query.category !== "actionable" && (
            <label className="workflow-check directory-filter">
              <input
                type="checkbox"
                checked={showAllHistory}
                onChange={(event) => {
                  const all = event.target.checked;
                  setShowAllHistory(all);
                  setQuery({ ...query, category: all ? "history" : "informational", page: 1 });
                }}
              />
              Show all history
            </label>
          )}
          <button
            className="button secondary"
            disabled={result.isFetching}
            onClick={() => void result.refetch()}
          >
            Refresh
          </button>
        </div>
        {result.isPending ? (
          <p className="table-feedback" role="status">
            Loading organization reviews…
          </p>
        ) : result.isError ? (
          <p className="table-feedback alert" role="alert">
            Reviews could not be loaded. Use Refresh to try again.
          </p>
        ) : (
          data && (
            <>
              <div
                className="table-scroll"
                role="region"
                tabIndex={0}
                aria-label="Organization review results"
              >
                <table>
                  <caption className="sr-only">
                    {query.category === "actionable"
                      ? "Actionable organization reviews"
                      : showAllHistory ? "Organization informational history" : "Latest feed information"}
                  </caption>
                  <thead>
                    <tr>
                      <th
                        scope="col"
                        aria-sort={
                          query.sort === "name"
                            ? query.direction === "asc"
                              ? "ascending"
                              : "descending"
                            : "none"
                        }
                      >
                        <button
                          className="sort-button"
                          onClick={() => sort("name")}
                        >
                          Employee{" "}
                          <span aria-hidden="true">
                            {query.sort === "name"
                              ? query.direction === "asc"
                                ? "↑"
                                : "↓"
                              : "↕"}
                          </span>
                        </button>
                      </th>
                      <th
                        scope="col"
                        aria-sort={
                          query.sort === "kind"
                            ? query.direction === "asc"
                              ? "ascending"
                              : "descending"
                            : "none"
                        }
                      >
                        <button
                          className="sort-button"
                          onClick={() => sort("kind")}
                        >
                          Review / event{" "}
                          <span aria-hidden="true">
                            {query.sort === "kind"
                              ? query.direction === "asc"
                                ? "↑"
                                : "↓"
                              : "↕"}
                          </span>
                        </button>
                      </th>
                      <th scope="col">Details</th>
                      <th
                        scope="col"
                        aria-sort={
                          query.sort === "first_seen_at"
                            ? query.direction === "asc"
                              ? "ascending"
                              : "descending"
                            : "none"
                        }
                      >
                        <button
                          className="sort-button"
                          onClick={() => sort("first_seen_at")}
                        >
                          First observed{" "}
                          <span aria-hidden="true">
                            {query.sort === "first_seen_at"
                              ? query.direction === "asc"
                                ? "↑"
                                : "↓"
                              : "↕"}
                          </span>
                        </button>
                      </th>
                      <th scope="col">
                        {query.category === "actionable" ? "Action" : "Result"}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((row) => (
                      <tr key={row.id}>
                        <td>
                          {row.person_id ? (
                            <button
                              className="text-link"
                              onClick={() =>
                                setSelected({
                                  person: row.person_id!,
                                  review:
                                    row.category === "actionable" &&
                                    row.status === "open" &&
                                    ![
                                      "LOB_LEADER_REVIEW",
                                      "DESIGNEE_INVALID",
                                    ].includes(row.kind)
                                      ? row.id
                                      : null,
                                })
                              }
                            >
                              {row.name}
                            </button>
                          ) : (
                            <strong>{row.name}</strong>
                          )}
                          {row.email && (
                            <span className="cell-secondary">{row.email}</span>
                          )}
                        </td>
                        <td>
                          {names[row.kind] ?? row.kind.replaceAll("_", " ")}
                          {row.category === "informational" && (
                            <span
                              className={
                                "badge " +
                                (row.status === "open"
                                  ? "review-open"
                                  : "revoked")
                              }
                            >
                              {row.status === "open"
                                ? "Current warning"
                                : "Resolved"}
                            </span>
                          )}
                        </td>
                        <td>
                          <Changes row={row} />
                          {row.data.segment_name ? (
                            <span className="cell-secondary">
                              Industry segment: {String(row.data.segment_name)}
                            </span>
                          ) : null}
                        </td>
                        <td>
                          <time
                            dateTime={row.first_seen_at}
                            title={"Last observed " + stamp(row.last_seen_at)}
                          >
                            {stamp(row.first_seen_at)}
                          </time>
                        </td>
                        <td>
                          {row.status === "open" &&
                          ["LOB_LEADER_REVIEW", "DESIGNEE_INVALID"].includes(
                            row.kind,
                          ) ? (
                            <a
                              className="button secondary"
                              href={
                                "/organization-mapping#segment-" +
                                String(row.data.segment_id ?? "")
                              }
                              onClick={(event) =>
                                followLink(
                                  event,
                                  "/organization-mapping#segment-" +
                                    String(row.data.segment_id ?? ""),
                                  navigate,
                                )
                              }
                            >
                              Repair mapping
                            </a>
                          ) : query.category === "actionable" &&
                            row.category === "actionable" &&
                            row.status === "open" &&
                            row.person_id ? (
                            <button
                              className="button secondary"
                              onClick={() =>
                                setSelected({
                                  person: row.person_id!,
                                  review: row.id,
                                })
                              }
                            >
                              Review
                            </button>
                          ) : (
                            <>
                              {row.resolution && (
                                <span>
                                  {row.resolution.replaceAll("_", " ")}
                                </span>
                              )}
                              {row.operation_id && (
                                <a
                                  className="cell-secondary"
                                  href={operationHref(row.operation_id)}
                                  onClick={(event) =>
                                    followLink(
                                      event,
                                      operationHref(row.operation_id),
                                      navigate,
                                    )
                                  }
                                >
                                  View operation
                                </a>
                              )}
                            </>
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
                      ? "No reviews match your search"
                      : query.category === "actionable"
                        ? "No actionable organization drift"
                        : showAllHistory ? "No organization history yet" : "No information for the latest feed"}
                  </h2>
                  <p>
                    {query.query
                      ? "Try another search or clear the search field."
                      : query.category === "informational"
                        ? "Informational alerts and metadata changes from the next applied feed will appear here."
                        : "New feed results and administrator decisions will appear here."}
                  </p>
                </div>
              )}
              <div className="table-footer">
                <label>
                  Rows per page{" "}
                  <Select
                    aria-label="Review rows per page"
                    value={query.page_size}
                    onChange={(event) =>
                      setQuery({
                        ...query,
                        page: 1,
                        page_size: Number(event.target.value) as 10 | 25 | 50,
                      })
                    }
                  >
                    {[10, 25, 50].map((size) => (
                      <option key={size}>{size}</option>
                    ))}
                  </Select>
                </label>
                <span>
                  {data.total} records · Page {data.page} of {data.pages}
                </span>
                <div className="pagination">
                  <button
                    className="button secondary"
                    disabled={data.page <= 1}
                    onClick={() => setQuery({ ...query, page: data.page - 1 })}
                  >
                    Previous
                  </button>
                  <nav className="page-numbers" aria-label="Review pages">
                    {pages.map((page) => (
                      <button
                        className="button secondary"
                        key={page}
                        aria-label={"Page " + page}
                        aria-current={page === data.page ? "page" : undefined}
                        onClick={() => setQuery({ ...query, page })}
                      >
                        {page}
                      </button>
                    ))}
                  </nav>
                  <button
                    className="button secondary"
                    disabled={data.page >= data.pages}
                    onClick={() => setQuery({ ...query, page: data.page + 1 })}
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )
        )}
      </section>
      {selected && (
        <PersonActions
          personId={selected.person}
          reviewId={selected.review}
          expired={expired}
          navigate={navigate}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
