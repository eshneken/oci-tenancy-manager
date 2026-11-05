import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { CostCells, CostFreshness, CostNumber, CostPanel, RefreshCosts, costPrecision, formatCost } from "../src/FinancialCosts";
import { Tenancies } from "../src/Tenancies";
import { api, ApiError } from "../src/api";
import type { CostView, TenancyDirectory } from "../src/contracts";

const cost: CostView = { state: "current", actual: "201.0000", budget: "200.0000", forecast: "320.0000", currency: "USD", retrieved_at: "2026-11-05T12:00:00Z", actual_over_budget: true, forecast_over_budget: true, can_refresh: true };

// Each scenario owns its query cache and never calls a live cloud or saved application.
function mount(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  const rendered = render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  return { ...rendered, client };
}

// Exact formatting survives values beyond JS integer precision and shows sub-cent overruns.
it("formats money exactly, expanding hidden overruns and retaining signed adjustments", () => {
  expect(formatCost("9999999999999999.9999", "USD", 4)).toBe("$9,999,999,999,999,999.9999");
  expect(formatCost("-1.2350", null)).toBe("−1.24");
  expect(formatCost(null, "USD")).toBe("—");
  expect(costPrecision({budget:"100.0000",actual:"100.0001"})).toBe(4);
  expect(costPrecision({forecast:"100.0001"})).toBe(2);
  expect(costPrecision(cost)).toBe(2);
});

// Only independently qualified values receive red/amber/green backgrounds, with accessible meanings.
it("colors actual and forecast independently and keeps unknown facts neutral", () => {
  const { rerender } = render(<CostNumber cost={cost} field="actual"/>);
  expect(screen.getByLabelText(/actual:.*over budget/)).toHaveClass("cost-over");
  rerender(<CostNumber cost={cost} field="forecast"/>);
  expect(screen.getByLabelText(/forecast:.*over budget/)).toHaveClass("cost-forecast-over");
  rerender(<CostNumber cost={{...cost,actual:"100.0000",actual_over_budget:false}} field="actual"/>);
  expect(screen.getByLabelText(/actual:.*within budget/)).toHaveClass("cost-within");
  rerender(<CostNumber cost={{...cost,state:"stale"}} field="actual"/>);
  expect(screen.getByLabelText(/actual:/)).not.toHaveClass("cost-over");
  rerender(<CostNumber cost={cost} field="budget"/>);
  expect(screen.getByLabelText(/budget:/)).not.toHaveClass("cost-within");
});

// Retrieval time works for keyboard and touch, clamps to the viewport, and dismisses cleanly.
it("opens and dismisses the retrieval tooltip through keyboard, pointer and viewport movement", async () => {
  const c = render(<CostFreshness cost={cost}/>);
  const button=screen.getByRole("button",{name:"Cost retrieval time"});
  fireEvent.focus(button); expect(screen.getByRole("tooltip")).toHaveTextContent("OTM retrieved");
  fireEvent.keyDown(button,{key:"Escape"});expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.click(button);expect(screen.getByRole("tooltip")).toBeVisible();
  fireEvent.pointerDown(document.body);expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.mouseEnter(button.parentElement!);fireEvent.mouseLeave(button.parentElement!);await waitFor(()=>expect(screen.queryByRole("tooltip")).toBeNull());
  fireEvent.click(button);fireEvent(window,new Event("resize"));expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.click(button);fireEvent.blur(button);expect(screen.queryByRole("tooltip")).toBeNull();
  c.rerender(<CostFreshness cost={{state:"not_collected"}}/>);fireEvent.focus(button);expect(screen.getByRole("tooltip")).toHaveTextContent("No cost retrieval");
  c.unmount();
});

// Missing, partial and prior-cycle evidence remains visible alongside retained numbers.
it("shows partial/pending and prior-month states without manufacturing values", () => {
  const {rerender}=render(<table><tbody><tr><CostCells cost={{...cost,state:"partial",forecast:null,pending:true}}/></tr></tbody></table>);
  expect(screen.getByText("Partial data")).toBeVisible();expect(screen.getByText("Refreshing…")).toBeVisible();expect(screen.getByText("—")).toBeVisible();
  rerender(<table><tbody><tr><CostCells cost={{...cost,state:"prior_cycle"}}/></tr></tbody></table>);expect(screen.getByText("Prior month")).toBeVisible();
  rerender(<table><tbody><tr><CostCells/></tr></tbody></table>);expect(screen.getByText("Not collected")).toBeVisible();
});

// Transport failure retries retain the command key; success invalidates inventory and operation views.
it("queues a refresh, reuses failed command keys and blocks pending duplicates", async () => {
  vi.spyOn(api,"operation").mockResolvedValue({operation:{state:"queued"}} as never);
  const refresh=vi.spyOn(api,"refreshCosts").mockRejectedValueOnce(new ApiError(503)).mockResolvedValue({operation_ids:["operation"],accepted_count:2,joined_count:1,skipped_count:1,accepted_at:"2026-11-05T12:00:00Z"});
  const c=mount(<RefreshCosts expired={vi.fn()}/>);
  const invalidate=vi.spyOn(c.client,"invalidateQueries");
  await userEvent.click(screen.getByRole("button",{name:"Refresh costs"}));await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button",{name:"Refresh costs"}));await screen.findByRole("status");
  expect(refresh.mock.calls[0][0].client_request_key).toBe(refresh.mock.calls[1][0].client_request_key);
  expect(screen.getByRole("status")).toHaveTextContent("2 new, 1 already pending, 1 unavailable");expect(invalidate).toHaveBeenCalledWith({queryKey:["tenancies"]});
  c.client.clear();
});

// Authentication failures expire the session, while an unbound child never enables a read command.
it("handles expired refresh authority and disabled unbound targets", async () => {
  vi.spyOn(api,"refreshCosts").mockRejectedValue(new ApiError(401));const expired=vi.fn();
  const c=mount(<RefreshCosts tenancyId="child" expired={expired}/>);
  await userEvent.click(screen.getByRole("button",{name:"Refresh costs"}));await waitFor(()=>expect(expired).toHaveBeenCalled());
  c.rerender(<QueryClientProvider client={c.client}><RefreshCosts disabled expired={expired}/></QueryClientProvider>);expect(screen.getByRole("button",{name:"Refresh costs"})).toBeDisabled();c.client.clear();
});

// Details distinguish desired configuration from the observed comparison budget and preserve source provenance.
it("shows current-month detail and optional source diagnostics", async () => {
  const c=mount(<CostPanel tenancyId="child" cost={{...cost,desired_budget:"500.0000",computed_at:null,period_start:null,cycle_facts:{reset_period:"MONTHLY",processing_period_type:"MONTH",budget_processing_period_start_offset:1}}} expired={vi.fn()}/>);
  expect(screen.getByText(/Desired budget:/)).toHaveTextContent("$500.00");
  await userEvent.click(screen.getByText("Source details"));expect(screen.getByText("OCI calculation time")).toBeVisible();expect(screen.getByText("MONTHLY · MONTH · day 1")).toBeVisible();
  c.client.clear();
});

// Inventory sorts Actual and Budget independently while retaining five visual columns and shared filtering.
it("renders consolidated inventory and independent monetary sorting",async()=>{
  const row={id:"child",name:"Example child",kind:"shared",status:"active",created_at:"2026-11-05T12:00:00Z",member_count:3,owner_name:"Example owner",owner_email:"owner@example.test",lob_name:"Example segment",costs:cost};
  const directory={items:[row],page:1,pages:1,page_size:10,total:1,total_tenancies:1,shared_count:1,individual_count:0,pending_count:0,can_refresh_costs:true} as TenancyDirectory;
  const list=vi.spyOn(api,"tenancies").mockResolvedValue(directory);
  const c=mount(<Tenancies identifier={null} expired={vi.fn()} navigate={vi.fn()}/>);
  await screen.findByText("Example child");expect(screen.getAllByRole("columnheader")).toHaveLength(5);expect(screen.getByText("shared · 3 members")).toBeVisible();
  await userEvent.click(screen.getByRole("button",{name:"Sort by actual"}));await waitFor(()=>expect(list.mock.lastCall![0]).toMatchObject({sort:"actual",direction:"asc",page:1}));
  await userEvent.click(screen.getByRole("button",{name:"Sort by budget"}));await waitFor(()=>expect(list.mock.lastCall![0]).toMatchObject({sort:"budget"}));
  await userEvent.click(screen.getByRole("button",{name:/Forecast/}));await waitFor(()=>expect(list.mock.lastCall![0]).toMatchObject({sort:"forecast"}));
  c.client.clear();
});


// A lost progress observer never pretends work failed; it expires auth or offers an explicit read retry.
it.each([401,503])("handles %s progress-read failures and clears a terminal acceptance notice", async status=>{
  vi.spyOn(api,"refreshCosts").mockResolvedValue({operation_ids:["operation"],accepted_count:1,joined_count:0,skipped_count:0,accepted_at:"2026-11-05T12:00:00Z"});
  const progress=vi.spyOn(api,"operation").mockRejectedValueOnce(new ApiError(status)).mockResolvedValue({operation:{state:"succeeded"}} as never);
  const expired=vi.fn();const c=mount(<RefreshCosts expired={expired}/>);
  await userEvent.click(screen.getByRole("button",{name:"Refresh costs"}));
  await screen.findByRole("button",{name:"Retry progress check"});expect(screen.queryByText(/Refresh queued/)).toBeNull();
  if(status===401)expect(expired).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Retry progress check"}));
  await waitFor(()=>expect(screen.queryByRole("button",{name:"Retry progress check"})).toBeNull());
  expect(progress).toHaveBeenCalledTimes(2);expect(screen.queryByRole("status")).toBeNull();c.client.clear();
});
