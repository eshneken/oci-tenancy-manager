import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { CostView } from "./contracts";

const labels: Record<NonNullable<CostView["state"]>, string> = {
  current: "", partial: "Partial data", stale: "Stale data", prior_cycle: "Prior month",
  unavailable: "Read unavailable", unqualified: "Currency or cycle unverified", not_collected: "Not collected",
};

// Work in integer ten-thousandths so large amounts and sub-cent overruns never lose precision.
export function scaledMoney(value: string) { return BigInt(value.replace(".", "")); }

// Expand all row values to four places when normal currency rounding would conceal an overrun.
export function costPrecision(cost: CostView) {
  if (cost.budget == null) return 2;
  const budget = scaledMoney(cost.budget);
  return [cost.actual, cost.forecast].some(value => value != null && scaledMoney(value) > budget && (scaledMoney(value) + 50n) / 100n === (budget + 50n) / 100n) ? 4 : 2;
}

// Format exact decimals without passing database money through a JavaScript floating point value.
export function formatCost(value: string | null | undefined, currency: string | null | undefined, places = 2) {
  if (value == null) return "—";
  const scaled = scaledMoney(value), negative = scaled < 0n, absolute = negative ? -scaled : scaled;
  const divisor = places === 4 ? 1n : 100n;
  const rounded = (absolute + divisor / 2n) / divisor;
  const base = 10n ** BigInt(places);
  return `${negative ? "−" : ""}${currency === "USD" ? "$" : ""}${(rounded / base).toLocaleString("en-US")}.${(rounded % base).toString().padStart(places, "0")}`;
}

// Retain a single OTM retrieval timestamp in a keyboard/touch-accessible, viewport-clamped popover.
export function CostFreshness({ cost, name }: { cost: CostView; name?: string }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 8, top: 8 });
  const container = useRef<HTMLSpanElement>(null);
  const id = useId();
  const pointerWasOpen = useRef(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // A short hover grace period lets the pointer cross from the trigger into its fixed popover.
  function keepOpen() { if (hideTimer.current) clearTimeout(hideTimer.current); }
  function hideSoon() { keepOpen(); hideTimer.current = setTimeout(() => setOpen(false), 160); }
  useEffect(() => () => { if (hideTimer.current) clearTimeout(hideTimer.current); }, []);
  useEffect(() => {
    if (!open) return;
    // Dismiss an open popover on outside interaction or viewport movement rather than leaving it detached.
    function outside(event: PointerEvent) { if (!container.current?.contains(event.target as Node)) setOpen(false); }
    function close() { setOpen(false); }
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => { document.removeEventListener("pointerdown", outside); window.removeEventListener("resize", close); window.removeEventListener("scroll", close, true); };
  }, [open]);
  // Anchor a bounded tooltip above the control, clamping both narrow and scrolled viewports.
  function show() {
    keepOpen();
    const box = container.current!.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(box.left, window.innerWidth - 288)), top: Math.max(8, Math.min(box.top - 70, window.innerHeight - 80)) });
    setOpen(true);
  }
  return <span ref={container} className="cost-freshness" onMouseEnter={show} onMouseLeave={hideSoon}>
    <button type="button" className="cost-info" aria-label={"Cost retrieval time" + (name ? " for " + name : "")} aria-describedby={open ? id : undefined} aria-expanded={open} onFocus={show} onBlur={() => setOpen(false)} onPointerDown={() => { pointerWasOpen.current = open; }} onClick={event => { if (event.detail > 0 && pointerWasOpen.current) setOpen(false); else show(); }} onKeyDown={event => { if (event.key === "Escape") setOpen(false); }}>ⓘ</button>
    {open && <span id={id} role="tooltip" className="cost-tooltip" onMouseEnter={keepOpen} onMouseLeave={hideSoon} style={position}>{cost.retrieved_at ? `OTM retrieved ${new Date(cost.retrieved_at).toLocaleString("en-US", { timeZone: "UTC", timeZoneName: "short" })}` : "No cost retrieval recorded"}</span>}
  </span>;
}

// Color independently qualified actual/forecast values; retained degraded facts stay visibly neutral.
export function CostNumber({ cost, field }: { cost: CostView; field: "actual" | "budget" | "forecast" }) {
  const qualified = ["current", "partial"].includes(cost.state ?? "not_collected");
  const over = field === "actual" ? cost.actual_over_budget : field === "forecast" ? cost.forecast_over_budget : false;
  const tone = qualified && field !== "budget" && cost[field] != null && cost.budget != null ? over ? field === "actual" ? "cost-over" : "cost-forecast-over" : scaledMoney(cost[field]!) < scaledMoney(cost.budget) ? "cost-within" : "" : "";
  const qualifier = qualified && field !== "budget" && cost[field] != null && cost.budget != null ? over ? ", over budget" : ", within budget" : "";
  return <span role="img" className={"cost-number " + tone} aria-label={`${field}: ${formatCost(cost[field], cost.currency, costPrecision(cost))}${qualifier}`}>{formatCost(cost[field], cost.currency, costPrecision(cost))}</span>;
}

// Keep missing/stale/source qualification visible; a tooltip carries only the retrieval timestamp.
export function CostCells({ cost = { state: "not_collected" }, name }: { cost?: CostView; name?: string }) {
  return <><td className="cost-actual-cell"><div className="cost-pair"><CostNumber cost={cost} field="actual"/><span className="cost-separator" aria-hidden="true">/</span><CostNumber cost={cost} field="budget"/></div>{cost.actual == null && <span className="cell-secondary">Actual unavailable</span>}{cost.budget == null && <span className="cell-secondary">Budget unavailable</span>}{labels[cost.state ?? "not_collected"] && <span className="cell-secondary cost-health">{labels[cost.state ?? "not_collected"]}</span>}{cost.pending && <span className="cell-secondary">Refreshing…</span>}</td><td className="cost-forecast-cell"><div className="cost-forecast"><CostNumber cost={cost} field="forecast"/><CostFreshness cost={cost} name={name}/></div>{cost.forecast == null && <span className="cell-secondary">Forecast unavailable</span>}</td></>;
}

// Refresh records durable work, preserves a request key after transport loss and invalidates shared views.
export function RefreshCosts({ tenancyId, disabled, expired }: { tenancyId?: string; disabled?: boolean; expired: () => void }) {
  const client = useQueryClient();
  const request = useRef<string | null>(null);
  const mutation = useMutation({ mutationFn: () => api.refreshCosts({ client_request_key: request.current ??= crypto.randomUUID(), tenancy_id: tenancyId ?? null }), onSuccess: () => { request.current = null; void client.invalidateQueries({ queryKey: ["tenancies"] }); void client.invalidateQueries({ queryKey: ["operations"] }); void client.invalidateQueries({ queryKey: ["navigation-counts"] }); }, onError: error => { if (error instanceof ApiError && [401, 403].includes(error.status)) expired(); } });
  const progress = useQuery({ queryKey: ["operations", "cost-refresh", mutation.data?.operation_ids], queryFn: ({signal}) => Promise.all(mutation.data!.operation_ids.map(id => api.operation(id, signal))), enabled: mutation.isSuccess, retry: false, refetchInterval: value => value.state.data?.some(detail => ["queued", "running"].includes(detail.operation.state)) ? 2000 : false });
  useEffect(() => {
    if (progress.error instanceof ApiError && [401,403].includes(progress.error.status)) expired();
  }, [progress.error, expired]);
  useEffect(() => {
    if (progress.data && progress.data.every(detail => !["queued", "running"].includes(detail.operation.state))) {
      mutation.reset(); void client.invalidateQueries({queryKey:["tenancies"]});
    }
  }, [progress.data, client, mutation.reset]);
  return <div className="cost-refresh"><button type="button" className="button secondary" disabled={disabled || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? "Queuing…" : "Refresh costs"}</button>{mutation.isSuccess && !progress.error && <span className="muted" role="status">Refresh queued · {mutation.data.accepted_count} new, {mutation.data.joined_count} already pending{mutation.data.skipped_count ? `, ${mutation.data.skipped_count} unavailable` : ""}</span>}{mutation.isSuccess && progress.error && <span className="alert" role="alert">Refresh was accepted, but progress could not be loaded. <button className="text-link" onClick={() => void progress.refetch()}>Retry progress check</button></span>}{mutation.isError && <span className="alert" role="alert">Cost refresh could not be queued. Retry or refresh the view.</span>}</div>;
}

// Details expose desired-vs-observed budget and provenance without duplicating another tenancy list.
export function CostPanel({ cost = { state: "not_collected" }, tenancyId, expired }: { cost?: CostView; tenancyId: string; expired: () => void }) {
  return <section className="operation-panel" aria-labelledby="monthly-cost-heading"><div className="cost-panel-heading"><h2 id="monthly-cost-heading">Current month costs</h2><RefreshCosts tenancyId={tenancyId} disabled={!cost.can_refresh || cost.pending} expired={expired}/></div><p className="muted">Simulated Budget read · {cost.currency ?? "Currency unverified"}</p><dl className="cost-detail-values">{(["actual", "budget", "forecast"] as const).map(field => <div key={field}><dt>{field === "actual" ? "Actual" : field === "budget" ? "Observed budget" : "Month-end forecast"}</dt><dd><CostNumber cost={cost} field={field}/>{cost[field] == null && <span className="cell-secondary">Unavailable</span>}</dd></div>)}</dl><div className="cost-detail-health">{labels[cost.state ?? "not_collected"] && <span className="badge review-open">{labels[cost.state ?? "not_collected"]}</span>}{cost.pending && <span role="status">Refreshing…</span>}<CostFreshness cost={cost}/></div>{cost.desired_budget != null && cost.desired_budget !== cost.budget && <p className="notice">Desired budget: {formatCost(cost.desired_budget, cost.currency)}. This is not the observed budget used for spend comparisons.</p>}{cost.retrieved_at && <details><summary>Source details</summary><dl className="operation-facts"><div><dt>OTM retrieved</dt><dd>{cost.retrieved_at}</dd></div><div><dt>OCI calculation time</dt><dd>{cost.computed_at ?? "Unavailable"}</dd></div><div><dt>Source period (UTC)</dt><dd>{cost.period_start ?? "Unverified"} → {cost.period_end ?? "Unverified"}</dd></div><div><dt>Budget cycle</dt><dd>{cost.cycle_facts ? `${cost.cycle_facts.reset_period} · ${cost.cycle_facts.processing_period_type} · day ${cost.cycle_facts.budget_processing_period_start_offset ?? "unknown"}` : "Unverified"}</dd></div></dl></details>}</section>;
}
