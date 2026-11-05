import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Operations } from "../src/Operations";
import { App } from "../src/App";
import { followLink } from "../src/navigation";
import { api, ApiError } from "../src/api";
import type {
  OperationDetail,
  OperationDirectory,
  OperationQuery,
  OperationSummary,
} from "../src/contracts";

const id = "11111111-1111-4111-8111-111111111111";
const row: OperationSummary = {
  id,
  kind: "inspect_import",
  state: "succeeded",
  stage: "inspection_complete",
  accepted_at: "2026-10-30T12:00:00Z",
  updated_at: "2026-10-30T12:01:00Z",
  completed_at: "2026-10-30T12:01:00Z",
  initiated_by: "Test operator",
  target_tenancy_ocid: "ocid1.tenancy.oc1..unit-test-only",
  provider_mode: "simulated",
};
const directory: OperationDirectory = {
  items: [row],
  total: 21,
  page: 1,
  page_size: 10,
  pages: 3,
};
const detail: OperationDetail = {
  operation: row,
  steps: [
    {
      step_key: "inspect_target",
      state: "verified",
      attempt_number: 1,
      verified_at: row.completed_at,
      safe_code: "inspection_verified",
    },
  ],
  events: [
    { kind: "operation_intent", at: row.accepted_at, safe_code: null },
    { kind: "inspection_dispatch", at: row.accepted_at, safe_code: null },
    {
      kind: "inspection_outcome",
      at: row.updated_at,
      safe_code: "inspection_verified",
    },
  ],
  events_limited: false,
};

// Keep optional sandbox discovery explicitly unavailable in read-only list scenarios.
beforeEach(() => {
  vi.spyOn(api, "inspectionSandbox").mockRejectedValue(new ApiError(404));
});

// Give each read-only scenario a fresh cache with no transport or database connection.
function mount(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return {
    ...render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    ),
    client,
  };
}

// Return page metadata matching the actual requested controls to exercise the UI contract.
function readPage(query: OperationQuery) {
  return Promise.resolve({
    ...directory,
    page: query.page ?? 1,
    page_size: query.page_size ?? 10,
  });
}

describe("Recorded operations list", () => {
  // Search, state, ordering and numbered paging remain server-owned and independent.
  it("reads and changes filters, sorts, row counts and pages without dispatching work", async () => {
    const read = vi.spyOn(api, "operations").mockImplementation(readPage);
    const navigate = vi.fn();
    mount(
      <Operations operationId={null} expired={vi.fn()} navigate={navigate} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading operations");
    expect(
      await screen.findByRole("link", { name: /Import inspection/ }),
    ).toHaveAttribute("href", "/operations/" + id);
    expect(
      screen.getByText(/No OCI resources or accounts are changed/),
    ).toBeInTheDocument();
    expect(screen.getByText("Simulated", { exact: true })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /State/ }));
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "state", direction: "asc" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /State/ }));
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "state", direction: "desc" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("State", { exact: true }),
      "needs_attention",
    );
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ state: "needs_attention", page: 1 }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.type(screen.getByRole("searchbox"), "unit");
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "unit", state: "needs_attention" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Operations rows per page"),
      "25",
    );
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ page_size: 25, page: 1 }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Page 2 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await screen.findByText("Page 1 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Page 3" }));
    await screen.findByText("Page 3 of 3");
    await userEvent.click(
      screen.getByRole("link", { name: /Import inspection/ }),
    );
    expect(navigate).toHaveBeenCalledWith("/operations/" + id);
  });

  // Filtered no-match results never masquerade as an empty operation history.
  it("distinguishes an empty history from no matches and clears both filters", async () => {
    const read = vi
      .spyOn(api, "operations")
      .mockResolvedValue({ ...directory, items: [], total: 0, pages: 1 });
    mount(
      <Operations operationId={null} expired={vi.fn()} navigate={vi.fn()} />,
    );
    expect(await screen.findByText("No operations yet")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Clear filters" }),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("State", { exact: true }),
      "failed",
    );
    await userEvent.type(screen.getByRole("searchbox"), "missing");
    expect(
      await screen.findByText("No operations match your filters"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Clear filters" }),
    );
    await screen.findByText("No operations yet");
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.getByLabelText("State", { exact: true })).toHaveValue("");
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ state: "", query: "" }),
        expect.any(AbortSignal),
      ),
    );
  });

  // Service outages preserve a clear retry while authorization denial leaves the privileged view.
  it.each([401, 403, 503])("handles list status %s safely", async (status) => {
    const expired = vi.fn();
    vi.spyOn(api, "operations")
      .mockRejectedValueOnce(new ApiError(status))
      .mockResolvedValue(directory);
    mount(
      <Operations operationId={null} expired={expired} navigate={vi.fn()} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to load operations",
    );
    if (status !== 503) await waitFor(() => expect(expired).toHaveBeenCalled());
    else expect(expired).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(
      await screen.findByRole("link", { name: /Import inspection/ }),
    ).toBeInTheDocument();
  });

  // Returning from a detail restores controls from the same authenticated cache.
  it("retains list context across detail navigation and back", async () => {
    vi.spyOn(api, "operations").mockImplementation(readPage);
    vi.spyOn(api, "operation").mockResolvedValue(detail);
    const navigate = vi.fn();
    const { rerender, client } = mount(
      <Operations operationId={null} expired={vi.fn()} navigate={navigate} />,
    );
    await screen.findByRole("link", { name: /Import inspection/ });
    await userEvent.type(screen.getByRole("searchbox"), "remember");
    await waitFor(() =>
      expect(client.getQueryData(["operations", "view"])).toMatchObject({
        query: "remember",
      }),
    );
    rerender(
      <QueryClientProvider client={client}>
        <Operations operationId={id} expired={vi.fn()} navigate={navigate} />
      </QueryClientProvider>,
    );
    await screen.findByText(
      "Inspection completed successfully. This tenancy has not been adopted by this inspection.",
    );
    await userEvent.click(
      screen.getByRole("link", { name: /Back to operations/ }),
    );
    expect(navigate).toHaveBeenCalledWith("/operations");
    rerender(
      <QueryClientProvider client={client}>
        <Operations operationId={null} expired={vi.fn()} navigate={navigate} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("searchbox")).toHaveValue("remember");
  });
});

describe("Recorded operation detail", () => {
  // Read persisted steps/events and keep simulated verification distinct from durable adoption.
  it("shows recorded evidence and the bounded recent-event disclosure", async () => {
    vi.spyOn(api, "operation").mockResolvedValue({
      ...detail,
      events_limited: true,
    });
    mount(<Operations operationId={id} expired={vi.fn()} navigate={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading operation");
    expect(
      await screen.findByText("Steps and verification"),
    ).toBeInTheDocument();
    expect(screen.getByText("Attempt 1")).toBeInTheDocument();
    expect(screen.getByText("Verified", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Operation accepted")).toBeInTheDocument();
    expect(screen.getByText("Inspection dispatched")).toBeInTheDocument();
    expect(screen.getByText("Inspection outcome")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Showing the most recent 50 events. Earlier events are not shown.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Start|Retry|Adopt|Cancel/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Test operator")).toBeInTheDocument();
  });

  // A pending inspection has no invented completion time, attempt evidence or successful result.
  it("shows unknown actor and empty progress honestly", async () => {
    vi.spyOn(api, "operation").mockResolvedValue({
      operation: {
        ...row,
        state: "queued",
        completed_at: null,
        initiated_by: null,
      },
      steps: [],
      events: [],
      events_limited: false,
    });
    mount(<Operations operationId={id} expired={vi.fn()} navigate={vi.fn()} />);
    expect(
      await screen.findByText("No workflow steps recorded yet."),
    ).toBeInTheDocument();
    expect(screen.getByText("No events recorded yet.")).toBeInTheDocument();
    expect(screen.getAllByText("Not recorded")).toHaveLength(2);
    expect(
      screen.queryByText(/Inspection completed successfully/),
    ).not.toBeInTheDocument();
  });

  // Failed/unverified steps never receive the verified label or fabricate verification time.
  it.each(["running", "needs_attention"] as const)(
    "shows step state %s with missing safe outcome",
    async (state) => {
      vi.spyOn(api, "operation").mockResolvedValue({
        ...detail,
        operation: { ...row, state: "running" },
        steps: [
          {
            step_key: "inspect_target",
            state,
            attempt_number: 2,
            verified_at: null,
            safe_code: null,
          },
        ],
        events: [
          { kind: "operation_intent", at: row.accepted_at, safe_code: null },
        ],
      });
      mount(
        <Operations operationId={id} expired={vi.fn()} navigate={vi.fn()} />,
      );
      await screen.findByText("Attempt 2");
      const steps = screen.getByRole("region", {
        name: "Steps and verification",
      });
      expect(
        within(steps).getByText(
          state === "running" ? "Running" : "Simulation issue",
          { exact: true },
        ),
      ).toBeInTheDocument();
      expect(within(steps).queryByText(/Outcome code/)).not.toBeInTheDocument();
    },
  );

  // Wrong-workspace/unknown identity uses one generic absence message; service failure stays retryable.
  it.each([401, 403, 404, 503])(
    "handles detail status %s without leaking diagnostics",
    async (status) => {
      const expired = vi.fn();
      vi.spyOn(api, "operation")
        .mockRejectedValueOnce(new ApiError(status))
        .mockResolvedValue(detail);
      mount(
        <Operations operationId={id} expired={expired} navigate={vi.fn()} />,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        status === 404
          ? "This operation is not available"
          : "Unable to load this operation",
      );
      if (status === 401 || status === 403)
        await waitFor(() => expect(expired).toHaveBeenCalled());
      else expect(expired).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
      expect(
        await screen.findByText("Steps and verification"),
      ).toBeInTheDocument();
    },
  );
});

describe("Native Operations navigation", () => {
  // Modified links retain ordinary browser navigation instead of forcing a same-tab route.
  it("does not intercept modified link activation", () => {
    const preventDefault = vi.fn();
    const navigate = vi.fn();
    followLink(
      {
        button: 0,
        metaKey: true,
        preventDefault,
      } as unknown as React.MouseEvent<HTMLAnchorElement>,
      "/operations",
      navigate,
    );
    expect(preventDefault).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  // The real shell recognizes direct detail URLs and browser history events without a router.
  it("renders direct detail routes, handles popstate and purges operation cache on logout", async () => {
    history.replaceState(null, "", "/operations/" + id);
    vi.spyOn(api, "directory").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      pages: 1,
      statistics: { total: 0, active: 0, protected_recovery: 0 },
    });
    vi.spyOn(api, "session").mockResolvedValue({
      workspace_id: "unit",
      display_name: "Test",
      expires_at: "",
    });
    vi.spyOn(api, "operation").mockResolvedValue(detail);
    vi.spyOn(api, "operations").mockResolvedValue(directory);
    vi.spyOn(api, "logout").mockResolvedValue(undefined);
    const { client } = mount(<App />);
    await screen.findByText("Steps and verification");
    expect(screen.getByRole("link", { name: "Operations" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await userEvent.click(
      screen.getByRole("link", { name: /Back to operations/ }),
    );
    expect(
      await screen.findByRole("heading", { name: "Operations" }),
    ).toBeInTheDocument();
    act(() => {
      history.pushState(null, "", "/operations/" + id);
      fireEvent.popState(window);
    });
    await screen.findByText("Steps and verification");
    await userEvent.click(screen.getByRole("link", { name: "Operations" }));
    await screen.findByRole("heading", { name: "Operations" });
    await userEvent.click(screen.getByRole("link", { name: "Administrators" }));
    await screen.findByRole("heading", { name: "Administrators" });
    await userEvent.click(
      screen.getByRole("link", { name: "OCI Tenancy Manager" }),
    );
    expect(location.pathname).toBe("/tenancies");
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await screen.findByLabelText("Password");
    expect(client.getQueriesData({ queryKey: ["operations"] })).toEqual([]);
  });
});

// Simulated terminal issues are recorded outcomes, not unresolved administrator tasks.
it("explains simulation issues in both recorded list and detail without changing the raw state filter", async () => {
  vi.spyOn(api, "operations").mockResolvedValue({
    ...directory,
    items: [{ ...row, state: "needs_attention" }],
  });
  const view = mount(
    <Operations operationId={null} expired={vi.fn()} navigate={vi.fn()} />,
  );
  expect(await screen.findByText("Simulation issue")).toBeInTheDocument();
  expect(
    screen.getByText("Simulation ended with an issue. No action is required."),
  ).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Needs attention" })).toHaveValue(
    "needs_attention",
  );
  view.unmount();
  vi.spyOn(api, "operation").mockResolvedValue({
    ...detail,
    operation: { ...row, state: "needs_attention", provider_mode: undefined },
  });
  mount(<Operations operationId={id} expired={vi.fn()} navigate={vi.fn()} />);
  expect(
    await screen.findByText(
      "Simulation ended with an issue. No action is required.",
    ),
  ).toHaveAttribute("role", "status");
  expect(
    screen.queryByRole("button", { name: /Retry|Resolve/ }),
  ).not.toBeInTheDocument();
});

// Lifecycle work must never inherit inspection-only 'not adopted' or 'no action required' messages.
it.each(["succeeded", "needs_attention"] as const)(
  "describes %s lifecycle outcomes accurately",
  async (state) => {
    const lifecycle = {
      ...row,
      kind: "organization_action" as const,
      state,
      title: "Create tenancy",
      target_label: "Synthetic employee",
    };
    vi.spyOn(api, "operation").mockResolvedValue({
      ...detail,
      operation: lifecycle,
    });
    mount(<Operations operationId={id} expired={vi.fn()} navigate={vi.fn()} />);
    if (state === "succeeded")
      expect(
        await screen.findByText(/Registry changes are verified/),
      ).toBeInTheDocument();
    else
      expect(
        await screen.findByText(/pending associations remain until handled/),
      ).toBeInTheDocument();
    expect(screen.queryByText(/not been adopted/)).toBeNull();
    expect(screen.queryByText(/No action is required/)).toBeNull();
  },
);

// Older successful lifecycle records have the same direct link, using the registered UUID rather than the operation UUID.
it("links a successful operation directly to its registered tenancy record", async () => {
  const target = "22222222-2222-4222-8222-222222222222";
  vi.spyOn(api, "operation").mockResolvedValue({
    ...detail,
    operation: {
      ...row,
      kind: "organization_action",
      result_tenancy_id: target,
    },
  });
  const navigate = vi.fn();
  mount(<Operations operationId={id} expired={vi.fn()} navigate={navigate} />);
  const link = await screen.findByRole("link", {
    name: "Open tenancy",
  });
  expect(link).toHaveAttribute("href", "/tenancies/" + target);
  await userEvent.click(link);
  expect(navigate).toHaveBeenCalledWith("/tenancies/" + target);
});

// Read-check completion describes execution, never certifies that the managed configuration matches.
it.each([id,null])("links completed configuration checks to their precise scope: %s",async(target)=>{
 vi.spyOn(api,"operation").mockResolvedValue({...detail,operation:{...row,kind:"configuration_check",result_tenancy_id:target,stage:"configuration_check_complete"},steps:[{...detail.steps[0],step_key:"configuration_check:"+id}],events:[{kind:"configuration_check_outcome",at:row.updated_at,safe_code:"READ_UNAVAILABLE"}]});
 const navigate=vi.fn();mount(<Operations operationId={id} expired={vi.fn()} navigate={navigate}/>);
 await screen.findByRole("heading",{name:"Configuration check"});
 expect(screen.getByText(/completion does not mean the configuration matches/)).toBeVisible();
 expect(screen.getByText("Check assigned managed configuration")).toBeVisible();expect(screen.getByText("Configuration check result")).toBeVisible();expect(screen.getByText("Completed",{selector:"span"})).toBeVisible();expect(screen.queryByText("Verified",{selector:"span"})).toBeNull();
 expect(screen.queryByRole("link",{name:"Open tenancy"})).toBeNull();
 const link=screen.getByRole("link",{name:"View configuration checks"});expect(link).toHaveAttribute("href",target?`/configuration/drift/${target}?returnTo=%2Foperations%2F${id}`:"/configuration/drift?tab=checks");await userEvent.click(link);expect(navigate).toHaveBeenCalled();
});

it("labels an incomplete read-only check without directing a destructive workflow",async()=>{
 vi.spyOn(api,"operation").mockResolvedValue({...detail,operation:{...row,kind:"configuration_check",state:"needs_attention"}});
 mount(<Operations operationId={id} expired={vi.fn()} navigate={vi.fn()}/>);
 await screen.findByText("Check incomplete");expect(screen.getByText(/read-only check did not complete/)).toBeVisible();expect(screen.queryByText(/pending associations remain/)).toBeNull();
});
