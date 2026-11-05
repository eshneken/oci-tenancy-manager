import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { OperationQuery, ReviewQuery } from "./contracts";

const operationQuery: Required<OperationQuery> = {
  page: 1, page_size: 10, sort: "accepted_at", direction: "desc", state: "", query: "",
};
const reviewQuery: Required<ReviewQuery> = {
  category: "actionable", query: "", page: 1, page_size: 10, sort: "first_seen_at", direction: "asc",
};

// Share existing private query keys so decisions, feed uploads and logout refresh/clear badges too.
export function NavigationCount({ kind, expired, navigationRevision = 0 }: {
  kind: "organization" | "operations";
  expired: () => void;
  navigationRevision?: number;
}) {
  const result = useQuery({
    queryKey: kind === "operations" ? ["operations", "list", operationQuery] : ["organization-reviews", reviewQuery],
    queryFn: async ({ signal }) => kind === "operations"
      ? await api.operations(operationQuery, signal)
      : await api.organizationReviews(reviewQuery, signal),
    select: (data) => "actionable_count" in data ? data.actionable_count : (data.attention_count ?? 0),
    retry: false,
    refetchInterval: 5_000,
  });
  const previousNavigation = useRef(navigationRevision);
  // Menu activation and Back/Forward observe worker progress without remounting the sidebar.
  useEffect(() => {
    if (previousNavigation.current === navigationRevision) return;
    previousNavigation.current = navigationRevision;
    void result.refetch();
  }, [navigationRevision, result.refetch]);
  useEffect(() => {
    if (result.error instanceof ApiError && [401, 403].includes(result.error.status)) expired();
  }, [result.error, expired]);
  const count = result.data;
  const label = kind === "operations" ? "operations requiring administrator action" : "actionable organization reviews";
  const description = count === undefined ? "Count unavailable" : `${count} ${label}${result.isError ? " (last known count)" : ""}`;
  return <>
    <span id={`navigation-${kind}-count`} className="sr-only">{description}</span>
    {count !== undefined && count > 0 && <span className="nav-count" aria-hidden="true" title={description}>{count}</span>}
  </>;
}
