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
import { describe, expect, it, vi } from "vitest";
import { AuditHistory } from "../src/AuditHistory";
import { App } from "../src/App";
import { api, ApiError } from "../src/api";
import type { AuditDirectory, AuditQuery } from "../src/contracts";

const operationId = "33333333-3333-4333-8333-333333333333";
const adminId = "44444444-4444-4444-8444-444444444444";
const directory: AuditDirectory = {
  items: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      at: "2026-10-30T12:00:00Z",
      kind: "operation_intent",
      category: "operations",
      actor_name: "Recorded initiator",
      operation_id: operationId,
      administrator_id: null,
      administrator_name: null,
      safe_code: "TENANCY_INSPECTED",
    },
    {
      id: "22222222-2222-4222-8222-222222222222",
      at: "2026-10-30T12:00:01Z",
      kind: "administrator_revoked",
      category: "administration",
      actor_name: "<script>unit actor</script>",
      operation_id: null,
      administrator_id: adminId,
      administrator_name: "<script>target administrator</script>",
      safe_code: null,
    },
    {
      id: "55555555-5555-4555-8555-555555555555",
      at: "2026-10-30T12:00:02Z",
      kind: "local_sign_in_failed",
      category: "authentication",
      actor_name: null,
      operation_id: null,
      administrator_id: adminId,
      administrator_name: "<script>target administrator</script>",
      safe_code: null,
    },
    {
      id: "66666666-6666-4666-8666-666666666666",
      at: "2026-10-30T12:00:03Z",
      kind: "session_logged_out",
      category: "authentication",
      actor_name: null,
      operation_id: null,
      administrator_id: null,
      administrator_name: null,
      safe_code: null,
    },
  ],
  page: 1,
  page_size: 10,
  pages: 3,
  total: 21,
};

// Isolate every history scenario from transport, database state and another authenticated cache.
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

// Return the requested page metadata while keeping the fixture immutable.
function readPage(query: AuditQuery) {
  return Promise.resolve({
    ...directory,
    page: query.page ?? 1,
    page_size: query.page_size ?? 10,
  });
}

describe("Immutable audit history", () => {
  // Users can filter/order/page real history fields without gaining edits or invented profile links.
  it("renders redacted recorded fields and updates server filter, sort and paging controls", async () => {
    const read = vi.spyOn(api, "auditHistory").mockImplementation(readPage);
    const navigate = vi.fn();
    const { container } = mount(
      <AuditHistory expired={vi.fn()} navigate={navigate} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading audit history",
    );
    expect(await screen.findByText("Recorded initiator")).toBeInTheDocument();
    expect(screen.getByText(/immutable history/)).toHaveTextContent(
      "not an action inbox",
    );
    expect(
      screen.getByText(
        "Recorded actors include administrators and background workers. Failed sign-ins are unverified attempts.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Unverified attempt")).toBeInTheDocument();
    expect(screen.getByText("No recorded target")).toBeInTheDocument();
    expect(screen.getByText("<script>unit actor</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(
      screen.getAllByText("<script>target administrator</script>"),
    ).toHaveLength(2);
    expect(screen.getAllByText(adminId)).toHaveLength(2);
    expect(
      screen.queryByRole("link", { name: adminId }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveAttribute("maxlength", "128");
    const category = screen.getByLabelText("Category");
    expect(within(category).getAllByRole("option")).toHaveLength(6);
    expect(
      screen.queryByRole("button", { name: /Edit|Resolve/ }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Event/ }));
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "kind", direction: "asc" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /Event/ }));
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "kind", direction: "desc" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.selectOptions(category, "authentication");
    await userEvent.type(screen.getByRole("searchbox"), "recorded");
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({
          category: "authentication",
          query: "recorded",
          page: 1,
        }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Audit rows per page"),
      "25",
    );
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ page_size: 25 }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Page 2 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await screen.findByText("Page 1 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Page 3" }));
    await screen.findByText("Page 3 of 3");
    await userEvent.click(screen.getByRole("link", { name: operationId }));
    expect(navigate).toHaveBeenCalledWith("/operations/" + operationId);
  });

  // Missing directory records retain their audit UUID instead of hiding or fabricating the target.
  it("keeps a readable fallback when a target name is unavailable", async () => {
    vi.spyOn(api, "auditHistory").mockResolvedValue({
      ...directory,
      items: [{ ...directory.items[1], administrator_name: null }],
    });
    mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()} />);
    expect(await screen.findByText("Name unavailable")).toBeInTheDocument();
    expect(screen.getByText(adminId)).toBeInTheDocument();
  });

  // Source-service attribution is distinct from an initiating administrator and exposes no raw feed.
  it("renders organization events as workspace history", async () => {
    const kinds = [
      "organization_configured",
      "organization_feed_received",
      "organization_feed_rejected",
      "organization_published",
    ] as const;
    vi.spyOn(api, "auditHistory").mockResolvedValue({
      ...directory,
      items: kinds.map((kind, index) => ({
        ...directory.items[0],
        id: "77777777-7777-4777-8777-" + String(index).padStart(12, "0"),
        kind,
        category: "organization",
        actor_name: "Organization synchronization",
        operation_id: null,
        administrator_id: null,
        administrator_name: null,
      })),
      total: 4,
      pages: 1,
    });
    mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()} />);
    expect(
      await screen.findByText("Organization metadata applied"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Review recorded application activity."),
    ).toBeInTheDocument();
    expect(screen.getByText("Organization feed received")).toBeInTheDocument();
    expect(screen.getAllByText("Workspace organization")).toHaveLength(4);
    expect(screen.getAllByText("Organization synchronization")).toHaveLength(4);
    expect(screen.queryByText("No recorded target")).not.toBeInTheDocument();
  });

  // A quiet empty audit history is distinct from a filtered no-match result.
  it("distinguishes no history from no matches and resets both filters", async () => {
    const read = vi
      .spyOn(api, "auditHistory")
      .mockResolvedValue({ ...directory, total: 0, pages: 1, items: [] });
    mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()} />);
    expect(await screen.findByText("No audit history yet")).toBeInTheDocument();
    expect(screen.getByText("0 events")).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("Category"),
      "operations",
    );
    await userEvent.type(screen.getByRole("searchbox"), "missing");
    expect(
      await screen.findByText("No events match your filters"),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Clear filters" }),
    );
    await screen.findByText("No audit history yet");
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: "", query: "" }),
        expect.any(AbortSignal),
      ),
    );
    expect(screen.getByLabelText("Category")).toHaveValue("");
    expect(screen.getByRole("searchbox")).toHaveValue("");
  });

  // Unknown individual attribution stays unknown; a failed sign-in never claims the target was the verified actor.
  it("labels failed authentication as an unverified attempt even if an old snapshot contains the target name", async () => {
    vi.spyOn(api, "auditHistory").mockResolvedValue({
      ...directory,
      items: [{ ...directory.items[2], actor_name: "Recovery target name" }],
      total: 1,
      pages: 1,
    });
    mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()} />);
    expect(await screen.findByText("Unverified attempt")).toBeInTheDocument();
    expect(screen.queryByText("Recovery target name")).not.toBeInTheDocument();
  });

  // Service failure remains retryable, while denied reads leave the privileged history view.
  it.each([401, 403, 503])(
    "handles audit status %s without exposing server diagnostics",
    async (status) => {
      const expired = vi.fn();
      vi.spyOn(api, "auditHistory")
        .mockRejectedValueOnce(new ApiError(status))
        .mockResolvedValue(directory);
      mount(<AuditHistory expired={expired} navigate={vi.fn()} />);
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Unable to load audit history",
      );
      if (status === 503) expect(expired).not.toHaveBeenCalled();
      else await waitFor(() => expect(expired).toHaveBeenCalled());
      await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
      expect(await screen.findByText("Recorded initiator")).toBeInTheDocument();
    },
  );

  // Detail/back navigation restores the user's history controls from the same account-scoped cache.
  it("restores list context when the history page is mounted again", async () => {
    vi.spyOn(api, "auditHistory").mockImplementation(readPage);
    const view = mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()} />);
    await screen.findByText("Recorded initiator");
    await userEvent.type(screen.getByRole("searchbox"), "remember");
    await waitFor(() =>
      expect(view.client.getQueryData(["audit-history", "view"])).toMatchObject(
        { query: "remember" },
      ),
    );
    view.rerender(
      <QueryClientProvider client={view.client}>
        <div>Another page</div>
      </QueryClientProvider>,
    );
    view.rerender(
      <QueryClientProvider client={view.client}>
        <AuditHistory expired={vi.fn()} navigate={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("searchbox")).toHaveValue("remember");
  });
});

describe("Activity & History navigation", () => {
  // The new group preserves real operation/bookmark URLs and clears cached history on logout.
  it("renders a direct audit URL, links Operations, and purges history on sign-out", async () => {
    history.replaceState(null, "", "/audit-history");
    vi.spyOn(api, "session").mockResolvedValue({
      display_name: "Test operator",
      workspace_id: "unit",
      expires_at: "",
    });
    vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
    vi.spyOn(api, "logout").mockResolvedValue(undefined);
    vi.spyOn(api, "operation").mockResolvedValue({
      operation: {
        id: operationId,
        kind: "inspect_import",
        state: "queued",
        stage: "inspect_target",
        accepted_at: directory.items[0].at,
        updated_at: directory.items[0].at,
        completed_at: null,
        initiated_by: "Test operator",
        target_tenancy_ocid: "ocid1.tenancy.oc1..unit",
        provider_mode: "simulated",
      },
      steps: [],
      events: [],
      events_limited: false,
    });
    const { client } = mount(<App />);
    await screen.findByRole("heading", { name: "Audit history" });
    await screen.findByText("Recorded initiator");
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByText("ACTIVITY & HISTORY")).toBeInTheDocument();
    expect(within(nav).getByText("APPLICATION SETTINGS")).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "Audit history" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(nav).getByRole("link", { name: "Administrators" }),
    ).not.toHaveAttribute("aria-current");
    await userEvent.click(screen.getByRole("link", { name: operationId }));
    expect(location.pathname).toBe("/operations/" + operationId);
    await screen.findByText("Steps and verification");
    await userEvent.click(
      within(nav).getByRole("link", { name: "Audit history" }),
    );
    await screen.findByRole("heading", { name: "Audit history" });
    act(() => {
      history.pushState(null, "", "/audit-history");
      fireEvent.popState(window);
    });
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await screen.findByLabelText("Password");
    expect(client.getQueriesData({ queryKey: ["audit-history"] })).toEqual([]);
  });

  // Denied history reads use the same race-safe session/cache boundary as deliberate sign-out.
  it.each([401, 403])(
    "purges the history cache after read denial %s",
    async (status) => {
      history.replaceState(null, "", "/audit-history");
      vi.spyOn(api, "session").mockResolvedValue({
        display_name: "Test operator",
        workspace_id: "unit",
        expires_at: "",
      });
      vi.spyOn(api, "auditHistory").mockRejectedValue(new ApiError(status));
      const { client } = mount(<App />);
      expect(
        await screen.findByText("Your session ended. Sign in again."),
      ).toBeInTheDocument();
      expect(client.getQueriesData({ queryKey: ["audit-history"] })).toEqual(
        [],
      );
      expect(client.getQueryData(["session"])).toBeNull();
    },
  );
});

// Worker audit snapshots identify the actual background actor rather than attributing dispatch to the initiator.
it("shows a recorded inspection worker as the actor", async () => {
  vi.spyOn(api, "auditHistory").mockResolvedValue({
    ...directory,
    items: [
      {
        ...directory.items[0],
        kind: "inspection_dispatch",
        actor_name: "Inspection worker",
      },
    ],
    total: 1,
    pages: 1,
  });
  mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()} />);
  expect(await screen.findByText("Inspection worker")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Actor/ })).toBeInTheDocument();
  expect(screen.queryByText("Recorded initiator")).not.toBeInTheDocument();
});

// Auditors can inspect actual recorded edits without an editable record or untrusted HTML rendering.
it("shows readable organization changes with an expandable history", async () => {
  vi.spyOn(api, "auditHistory").mockResolvedValue({
    ...directory,
    items: [
      {
        ...directory.items[0],
        kind: "organization_configured",
        category: "organization",
        operation_id: null,
        summary: "Updated organization mappings",
        changes: [
          "Organization leader: old@example.test → new@example.test",
          "Segment name: <script>old</script> → Updated Alpha",
        ],
      },
    ],
  });
  const { container } = mount(
    <AuditHistory expired={vi.fn()} navigate={vi.fn()} />,
  );
  expect(
    await screen.findByText("Updated organization mappings"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "Details" }),
  ).toBeInTheDocument();
  const toggle = screen.getByText("View changes (2)");
  expect(toggle.closest("details")).not.toHaveAttribute("open");
  await userEvent.click(toggle);
  expect(toggle.closest("details")).toHaveAttribute("open");
  expect(
    screen.getByText(
      "Organization leader: old@example.test → new@example.test",
    ),
  ).toBeVisible();
  expect(
    screen.getByText("Segment name: <script>old</script> → Updated Alpha"),
  ).toBeVisible();
  expect(container.querySelector("script")).toBeNull();
  await userEvent.click(toggle);
  expect(toggle.closest("details")).not.toHaveAttribute("open");
});

// Baseline history links to the recorded recipe and renders literal changes without HTML execution.
it("opens the exact baseline target and displays recorded recipe changes", async () => {
  const baseline = "77777777-7777-4777-8777-777777777777";
  vi.spyOn(api, "auditHistory").mockResolvedValue({
    ...directory, pages: 1, total: 1,
    items: [{ ...directory.items[0], operation_id: null, baseline_id: baseline,
      kind: "baseline_draft_saved", category: "administration",
      summary: "Saved baseline draft v1, revision 2",
      changes: ["Monthly budget amount: 200.0000 → 500.0000", "Tag Note: Not set → <script>literal</script>"] }],
  });
  const navigate = vi.fn();
  const { container } = mount(<AuditHistory expired={vi.fn()} navigate={navigate} />);
  const link = await screen.findByRole("link", { name: "Baseline draft" });
  expect(link).toHaveAttribute("href", `/configuration?baseline=${baseline}&returnTo=%2Faudit-history`);
  await userEvent.click(link);
  expect(navigate).toHaveBeenCalledWith(`/configuration?baseline=${baseline}&returnTo=%2Faudit-history`);
  expect(screen.getByText("Saved baseline draft v1, revision 2")).toBeInTheDocument();
  expect(screen.getByText("Monthly budget amount: 200.0000 → 500.0000")).toBeInTheDocument();
  expect(container.querySelector("script")).toBeNull();
});

// Default changes reference an immutable publication, never an editable draft.
it.each(["baseline_published","baseline_default_changed"] as const)("links %s to its published target",async kind=>{
  const baseline="77777777-7777-4777-8777-777777777777";
  vi.spyOn(api,"auditHistory").mockResolvedValue({...directory,pages:1,total:1,items:[{...directory.items[0],operation_id:null,baseline_id:baseline,kind,category:"administration"}]});
  const navigate=vi.fn();
  mount(<AuditHistory expired={vi.fn()} navigate={navigate}/>);
  const link=await screen.findByRole("link",{name:"Published baseline"});
  expect(link).toHaveAttribute("href",`/configuration?baseline=${baseline}&returnTo=%2Faudit-history`);
  expect(screen.queryByRole("link",{name:"Baseline draft"})).toBeNull();
});

// The operation remains addressable while tenancy/user labels identify what it actually affected.
it("shows friendly lifecycle resources alongside the operation and collapses large batches",async()=>{
 const entry={...directory.items[0],resources:[{kind:"person" as const,id:adminId,name:"Example employee"},{kind:"tenancy" as const,id:adminId,name:"Example shared tenancy"}]};
 const read=vi.spyOn(api,"auditHistory").mockResolvedValue({...directory,items:[entry]});
 const navigate=vi.fn();mount(<AuditHistory expired={vi.fn()} navigate={navigate}/>);
 await screen.findByText("Example employee");await userEvent.click(screen.getByRole("link",{name:"Example shared tenancy"}));expect(navigate).toHaveBeenCalledWith("/tenancies/"+adminId);
 expect(screen.getByRole("link",{name:operationId})).toHaveAttribute("href","/operations/"+operationId);
 read.mockResolvedValue({...directory,items:[{...entry,resources:[...entry.resources,{kind:"tenancy",id:operationId,name:"Another child"},{kind:"tenancy",id:entry.id,name:"Third child"}]}]});
 await userEvent.click(screen.getByRole("button",{name:"Refresh"}));
 await userEvent.click(await screen.findByText("4 affected resources"));expect(screen.getByRole("link",{name:"Third child"})).toBeVisible();
});

// Read observations remain audit history and use a neutral result label, even when no match was verified.
it("labels configuration read-check outcomes without claiming configuration verification",async()=>{
 vi.spyOn(api,"auditHistory").mockResolvedValue({...directory,items:[{...directory.items[0],kind:"configuration_check_outcome",safe_code:"READ_UNAVAILABLE"}]});
 mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()}/>);
 await screen.findByText("Configuration check result");expect(screen.getByText("READ_UNAVAILABLE")).toBeVisible();expect(screen.queryByText("Configuration verification")).toBeNull();
});


// Email transitions use their own server category; choosing Operations removes delivery rows.
it("filters email delivery independently while retaining operation links", async () => {
  const mail = {...directory.items[0], kind:"email_delivery" as const, category:"email_delivery" as const, actor_name:"Email delivery worker", safe_code:null};
  const read = vi.spyOn(api,"auditHistory").mockImplementation(async query => ({...directory,items:query.category==="operations"?[]:[mail],total:query.category==="operations"?0:1,pages:1,page:1}));
  mount(<AuditHistory expired={vi.fn()} navigate={vi.fn()}/>);
  await screen.findByText("Email delivery worker");
  await userEvent.selectOptions(screen.getByLabelText("Category"),"email_delivery");
  await waitFor(()=>expect(read).toHaveBeenLastCalledWith(expect.objectContaining({category:"email_delivery",page:1}),expect.any(AbortSignal)));
  expect(screen.getByRole("option",{name:/^Email delivery$/})).toBeInTheDocument();
  expect(screen.getByRole("link",{name:operationId})).toHaveAttribute("href","/operations/"+operationId);
  await userEvent.selectOptions(screen.getByLabelText("Category"),"operations");
  await screen.findByText("No events match your filters");
  expect(screen.queryByText("Email delivery worker")).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Category"),"");
  expect(await screen.findByText("Email delivery worker")).toBeInTheDocument();
});
