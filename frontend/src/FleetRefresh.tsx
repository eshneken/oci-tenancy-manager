import {useEffect, useRef, useState} from "react";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {api, ApiError} from "./api";
import type {FleetRefreshReceipt} from "./contracts";

const labels = {costs: "Costs", users: "Required users, permissions, recovery & signing keys", configuration: "Configuration drift"};
const caches = ["tenancies", "configuration-drift", "configuration-check", "operations", "navigation-counts", "audit-history"];

// Retain uncertain command keys and terminal feedback; a completed read job is not a health claim.
export function FleetRefresh({expired}: {expired: () => void}) {
 const client = useQueryClient();
 const key = useRef<string | null>(null);
 const sending = useRef(false);
 const [busy, setBusy] = useState(false);
 const [error, setError] = useState(false);
 const [receipt, setReceipt] = useState<FleetRefreshReceipt | null>(null);
 const ids = receipt?.categories.flatMap(category => category.operation_ids) ?? [];
 const progress = useQuery({
  queryKey: ["fleet-refresh-progress", ids],
  queryFn: ({signal}) => api.refreshAllStatus(ids, signal),
  enabled: ids.length > 0, retry: false, refetchOnWindowFocus: false,
  refetchInterval: value => value.state.error ? false : !value.state.data || value.state.data.jobs.some(job => job.state === "pending") ? 2000 : false,
 });
 const statuses = new Map(progress.data?.jobs.map(job => [job.operation_id, job.state]));
 const pending = ids.some(id => !statuses.has(id) || statuses.get(id) === "pending");
 const failures = (receipt?.categories.reduce((sum, category) => sum + category.failed_count, 0) ?? 0) + (progress.data?.jobs.filter(job => ["failed", "unavailable"].includes(job.state)).length ?? 0);
 const skipped = receipt?.categories.reduce((sum, category) => sum + category.skipped_count, 0) ?? 0;
 useEffect(() => {
  if (progress.error instanceof ApiError && [401,403].includes(progress.error.status)) expired();
 }, [progress.error, expired]);
 useEffect(() => {
  if (receipt) for (const name of caches) void client.invalidateQueries({queryKey: [name]});
 }, [receipt, progress.data, client]);
 // The same UUID survives an uncertain queue response; native jobs own provider acquisition.
 async function refresh() {
  if (sending.current || pending) return;
  sending.current = true; setBusy(true); setError(false); setReceipt(null);
  key.current ??= crypto.randomUUID();
  for (const name of caches) void client.invalidateQueries({queryKey: [name]});
  try {
   const result = await api.refreshAllData({client_request_key: key.current});
   setReceipt(result); key.current = null;
  } catch (failure) {
   if (failure instanceof ApiError && [401,403].includes(failure.status)) expired();
   else setError(true);
  } finally {sending.current = false; setBusy(false);}
 }
 return <div className="fleet-refresh">
  <button type="button" className="button secondary" disabled={busy || pending} onClick={() => void refresh()}>{busy ? "Queuing refresh…" : pending ? "Refreshing data…" : error ? "Retry refresh" : "Refresh all data"}</button>
  {error && <p className="alert" role="alert">Refresh acceptance could not be confirmed. Retry uses the same request keys; work already accepted remains queued.</p>}
  {receipt && <section className="fleet-refresh-progress" aria-label="Fleet refresh progress">
   <strong role="status">{!receipt.tenancy_count ? "No eligible active child tenancies" : pending ? "Refreshing tenancy data" : failures ? "Refresh finished with issues" : skipped ? "Refresh finished with skipped checks" : "Refresh finished"}</strong>
   <p className="muted">{receipt.tenancy_count} active registered {receipt.tenancy_count === 1 ? "tenancy" : "tenancies"} · Includes tenancies outside this page and current filters.</p>
   <dl aria-live="polite" aria-atomic="true">{receipt.categories.map(category => {
    const finished = category.operation_ids.filter(id => statuses.get(id) === "finished").length;
    const failed = category.failed_count + category.operation_ids.filter(id => ["failed", "unavailable"].includes(statuses.get(id) ?? "")).length;
    const waiting = category.operation_ids.length - finished - (failed - category.failed_count);
    return <div key={category.category}><dt>{labels[category.category]}</dt><dd>{finished} jobs finished · {waiting} pending · {failed} failed · {category.skipped_count} tenancies skipped</dd></div>;
   })}</dl>
   {progress.isError && <p className="alert" role="alert">Refresh was accepted, but progress could not be loaded. <button type="button" className="text-link" disabled={progress.isFetching} onClick={() => void progress.refetch()}>Retry progress check</button></p>}
   <p className="muted">Finished jobs can report drift, missing users or unavailable data. Review the dated results in the tenancy and drift views. Skipped checks may be busy or lack the required setup.</p>
  </section>}
 </div>;
}
