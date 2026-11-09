import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { PersonActions, refreshOrganization } from "../src/PersonActions";
import { OrganizationReviews } from "../src/OrganizationReviews";
import { Tenancies } from "../src/Tenancies";
import { api, ApiError, WorkflowError } from "../src/api";
import type {
  AssociationView,
  PersonWorkflow,
  ReviewDirectory,
  ReviewView,
  TenancyDetail,
  TenancyDirectory,
  TenancyView,
} from "../src/contracts";

const id = "11111111-1111-4111-8111-111111111111";
const other = "22222222-2222-4222-8222-222222222222";
const op = "33333333-3333-4333-8333-333333333333";
const time = "2026-10-30T12:00:00Z";
const employee = {
  id,
  name: "Synthetic <employee>",
  email: "employee@example.test",
};
const recipient = { id: other, name: "New owner", email: "owner@example.test" };
const tenant: TenancyView = {
  id,
  name: "Shared workspace",
  tenancy_ocid: "ocid1.tenancy.oc1..otmsimchild",
  parent_tenancy_ocid: "ocid1.tenancy.oc1..otmsimparent",
  home_region: "us-ashburn-1",
  kind: "shared",
  status: "active",
  origin: "create",
  provider_mode: "simulated",
  owner_person_id: id,
  owner_name: employee.name,
  owner_email: employee.email,
  manager_name: "Manager",
  leader_name: "Leader",
  lob_name: "Test LOB",
  member_count: 2,
  operation_id: op,
  operation_state: "succeeded",
  verified_at: time,
  created_at: time,
  cleanup_count: 1,
};
const association: AssociationView = {
  id,
  person_id: id,
  tenancy_id: id,
  tenancy_name: tenant.name,
  tenancy_kind: "shared",
  tenancy_status: "active",
  role: "owner",
  status: "active",
  compartment_ocid: "ocid1.compartment.oc1..otmsimchild",
  compartment_name: "Employee sandbox",
  cleanup_required: false,
  user_ocid: "ocid1.user.oc1..otmsimpersonal",
  operation_id: null,
  actions: ["transfer", "keep"],
};
const preview: PersonWorkflow = {
  current_baseline: {id,version_number:1,edit_revision:2,created_by:"test",created_at:time,published_by:"test",published_by_name:"Example administrator",published_at:time,publication_mode:"simulated",content_hash:"a".repeat(64),content:{policy_statements:["Allow example"],quota_statements:["set example quota"],monthly_budget_amount:"250.0000",budget_currency:"USD"}},
  creation_regions: [
    { identifier: "us-ashburn-1", name: "US East (Ashburn)" },
    { identifier: "us-phoenix-1", name: "US West (Phoenix)" },
  ],
  context: {
    applied_version_id: id,
    proposed_version_id: other,
    configuration_id: op,
    registry_revision: 1,
  },
  person: employee,
  review: null,
  source_present: true,
  is_manager: false,
  directory_status: "included",
  pending_operation_id: null,
  provider_mode: "simulated",
  actions: [
    "create_tenancy",
    "import_tenancy",
    "join_shared",
    "no_tenancy_required",
    "merge",
  ],
  associations: [],
  shared_tenancies: [tenant],
  transfer_recipients: [recipient],
  merge_partners: [recipient],
};
const detail: TenancyDetail = {
  tenancy: tenant,
  people: [employee],
  memberships: [association],
  compartment_parents: [{ name: "Projects", ocid: tenant.tenancy_ocid }],
};
const inventory: TenancyDirectory = {
  items: [tenant],
  total: 26,
  page: 1,
  pages: 3,
  page_size: 10,
  total_tenancies: 26,
  individual_count: 20,
  shared_count: 6,
  pending_count: 0,
  issue_count: 0,
};
const review: ReviewView = {
  id,
  kind: "TENANCY_SETUP_REVIEW",
  category: "actionable",
  status: "open",
  person_id: id,
  name: employee.name,
  email: employee.email,
  first_seen_at: time,
  last_seen_at: time,
  resolved_at: null,
  resolution: null,
  operation_id: null,
  data: {},
};
const reviews: ReviewDirectory = {
  items: [review],
  total: 26,
  page: 1,
  pages: 3,
  page_size: 10,
  actionable_count: 26,
  history_count: 5,
  informational_count: 3,
};

// Keep independent caches so acceptance invalidation cannot leak one synthetic person's data into another test.
function mount(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    ),
    client,
  };
}

// Real controls construct commands; the server boundary is stubbed without replacing form or query behavior.
function dialog(
  data: PersonWorkflow = preview,
  initialAction?: PersonWorkflow["actions"][number],
) {
  vi.spyOn(api, "personWorkflow").mockResolvedValue(data);
  vi.spyOn(api, "tenancy").mockResolvedValue(detail);
  const submit = vi.spyOn(api, "organizationAction").mockResolvedValue({
    operation_id: op,
    state: "queued",
    provider_mode: "simulated",
    accepted_at: time,
  });
  const navigate = vi.fn(),
    expired = vi.fn(),
    onClose = vi.fn();
  return {
    ...mount(
      <PersonActions
        personId={id}
        initialAction={initialAction}
        expired={expired}
        navigate={navigate}
        onClose={onClose}
      />,
    ),
    submit,
    navigate,
    expired,
    onClose,
  };
}

// Labels remain accessible and literal employee values are rendered as text, never markup.
describe("Organization action dialogs", () => {
  // General entry never infers an action, even if creation is the only currently available choice.
  it("requires an explicit action before showing fields or enabling submission", async () => {
    const c = dialog({ ...preview, actions: ["create_tenancy"] });
    const control = await screen.findByLabelText("Action");
    expect(control).toHaveValue("");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(screen.queryByLabelText("Tenancy type")).toBeNull();
    fireEvent.submit(control.closest("form")!);
    expect(c.submit).not.toHaveBeenCalled();
    await userEvent.selectOptions(control, "create_tenancy");
    expect(screen.getByLabelText("Tenancy type")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create tenancy" }),
    ).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Requested tenancy name"),
      "examplechild",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Home region"),
      "us-phoenix-1",
    );
    expect(
      screen.getByRole("button", { name: "Create tenancy" }),
    ).toBeEnabled();
    await userEvent.selectOptions(control, "");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  // A registry name conflict rejects admission without dismissing the form or losing other choices.
  it("keeps create choices and retries a corrected name after a definitive registry conflict", async () => {
    const c = dialog(preview, "create_tenancy");
    c.submit.mockRejectedValueOnce(
      new WorkflowError(409, "DISTINCT_TENANCY_NAME_REQUIRED"),
    );
    const name = await screen.findByLabelText("Requested tenancy name");
    await userEvent.type(name, "takenchild");
    await userEvent.selectOptions(
      screen.getByLabelText("Home region"),
      "us-phoenix-1",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Tenancy type"),
      "shared",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Create tenancy" }),
    );
    await screen.findByText(/That tenancy name is already registered in OTM/);
    expect(screen.queryByText("Operation accepted")).toBeNull();
    expect(c.onClose).not.toHaveBeenCalled();
    expect(name).toHaveValue("takenchild");
    await waitFor(() => expect(name).toHaveFocus());
    expect(screen.getByLabelText("Home region")).toHaveValue("us-phoenix-1");
    expect(screen.getByLabelText("Tenancy type")).toHaveValue("shared");
    await userEvent.clear(name);
    await userEvent.type(name, "availablechild");
    await userEvent.click(
      screen.getByRole("button", { name: "Create tenancy" }),
    );
    await screen.findByText("Operation accepted");
    const first = c.submit.mock.calls[0][0],
      second = c.submit.mock.calls[1][0];
    expect(second).toEqual(
      expect.objectContaining({
        name: "availablechild",
        home_region: "us-phoenix-1",
        tenancy_kind: "shared",
      }),
    );
    expect(second.client_request_key).not.toBe(first.client_request_key);
    expect(c.submit).toHaveBeenCalledTimes(2);
  });

  // A stale or unavailable task link cannot fall back to a different available operation.
  it("keeps the placeholder when a requested task is unavailable", async () => {
    dialog(preview, "transfer_owner");
    expect(await screen.findByLabelText("Action")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  // Create/import share fields but only import carries the exact existing tenancy OCID.
  it("submits create and import fields and preserves accepted receipts through invalidation", async () => {
    const c = dialog();
    await userEvent.selectOptions(
      await screen.findByLabelText("Action"),
      "create_tenancy",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Tenancy type"),
      "shared",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Action"),
      "import_tenancy",
    );
    fireEvent.change(screen.getByLabelText("Simulated tenancy OCID"), {
      target: { value: "ocid1.tenancy.oc1..otmsimimport" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Import tenancy" }),
    );
    expect(await screen.findByText("Operation accepted")).toBeInTheDocument();
    expect(c.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "import_tenancy",
        tenancy_kind: "shared",
        import_ocid: "ocid1.tenancy.oc1..otmsimimport",
      }),
      expect.any(AbortSignal),
    );
    expect(c.container.querySelector("employee")).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "View operation" }));
    expect(c.navigate).toHaveBeenCalledWith("/operations/" + op);
    expect(c.onClose).toHaveBeenCalled();
  });

  // Existing parents are fetched and selected explicitly, and retry is available after discovery failure.
  it("loads shared parents, retries discovery, and submits the exact selected compartment", async () => {
    const c = dialog();
    vi.mocked(api.tenancy).mockRejectedValueOnce(new Error("private"));
    await screen.findByLabelText("Action");
    await userEvent.selectOptions(
      screen.getByLabelText("Action"),
      "join_shared",
    );
    await userEvent.selectOptions(screen.getByLabelText("Shared tenancy"), id);
    await userEvent.click(
      await screen.findByRole("button", { name: "Retry compartments" }),
    );
    await waitFor(() =>
      expect(
        screen.getByLabelText("Existing parent compartment"),
      ).toBeEnabled(),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Existing parent compartment"),
      tenant.tenancy_ocid,
    );
    fireEvent.change(screen.getByLabelText("Employee compartment name"), {
      target: { value: "Project A" },
    });
    expect(
      screen.getByText("Selected parent: " + tenant.tenancy_ocid),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Add to shared tenancy" }),
    );
    await screen.findByText("Operation accepted");
    expect(c.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "join_shared",
        tenancy_id: id,
        parent_compartment_ocid: tenant.tenancy_ocid,
        compartment_name: "Project A",
      }),
      expect.any(AbortSignal),
    );
  });

  // Offboarding requires a complete association plan and explicit manager/shared impact acknowledgment.
  it("plans mixed associations and transfer recipients without a reason field", async () => {
    const personal = {
      ...association,
      id: other,
      tenancy_id: other,
      tenancy_name: "Personal child",
      tenancy_kind: "individual" as const,
      actions: ["delete", "transfer", "keep"] as AssociationView["actions"],
    };
    const c = dialog({
      ...preview,
      is_manager: true,
      actions: ["offboard_person"],
      associations: [association, personal],
    });
    await userEvent.selectOptions(
      await screen.findByLabelText("Action"),
      "offboard_person",
    );
    const first = await screen.findByLabelText("Action for " + tenant.name);
    fireEvent.submit(first.closest("form")!);
    expect(c.submit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", {name:"Offboard employee"})).toBeDisabled();
    await userEvent.selectOptions(first, "transfer");
    await userEvent.selectOptions(
      screen.getByLabelText("New owner for " + tenant.name),
      other,
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Action for Personal child"),
      "delete",
    );
    await userEvent.click(screen.getByLabelText(/This employee is a manager/));
    await userEvent.click(
      screen.getByLabelText(/I reviewed the shared tenancy impact/),
    );
    expect(screen.queryByLabelText(/Reason/)).toBeNull();
    await userEvent.click(screen.getByLabelText(/I acknowledge the consequences/));
    await userEvent.click(
      screen.getByRole("button", { name: "Offboard employee" }),
    );
    await screen.findByText("Operation accepted");
    expect(c.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        confirm_manager: true,
        confirm_shared: true,
        plan: [
          {
            association_id: id,
            action: "transfer",
            recipient_person_id: other,
            former_owner_disposition: "remove",
          },
          {
            association_id: other,
            action: "delete",
            recipient_person_id: null,
          },
        ],
      }),
      expect.any(AbortSignal),
    );
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(c.onClose).toHaveBeenCalled();
  });

  // Direct role actions scope to the selected tenancy, preserving other personal/shared associations.
  it.each(["delete_tenancy", "remove_member", "transfer_owner"] as const)(
    "submits scoped %s",
    async (action) => {
      const a = {
        ...association,
        actions: [
          "delete",
          "remove",
          "transfer",
          "keep",
        ] as AssociationView["actions"],
      };
      const c = dialog(
        { ...preview, actions: [action], associations: [a] },
        action,
      );
      await userEvent.selectOptions(
        await screen.findByLabelText("Tenancy"),
        id,
      );
      if (action === "transfer_owner")
        await userEvent.selectOptions(
          screen.getByLabelText("New owner"),
          other,
        );
      if(action === "transfer_owner") await userEvent.selectOptions(screen.getByLabelText("Former owner"),"remove");
      await userEvent.click(
        screen.getByLabelText(/I reviewed the shared tenancy impact/),
      );
      await userEvent.click(screen.getByLabelText(/I acknowledge the consequences/));
      fireEvent.submit(screen.getByLabelText("Tenancy").closest("form")!);
      await screen.findByText("Operation accepted");
      expect(c.submit).toHaveBeenCalledWith(
        expect.objectContaining({ action, tenancy_id: id }),
        expect.any(AbortSignal),
      );
    },
  );

  // Real metadata decisions complete immediately and do not pretend to have changed OCI resources.
  it.each([
    "ignore",
    "resolve",
    "no_tenancy_required",
    "merge",
    "offboard_person",
    "cancel_simulation",
  ] as const)(
    "records %s and displays the appropriate completion",
    async (action) => {
      const c = dialog({
        ...preview,
        actions: [action],
        pending_operation_id: action === "cancel_simulation" ? op : null,
      });
      c.submit.mockResolvedValue({
        operation_id: action === "cancel_simulation" ? op : null,
        state: action === "cancel_simulation" ? "cancelled" : "succeeded",
        provider_mode: "application",
        accepted_at: time,
      });
      const control = await screen.findByLabelText("Action");
      await userEvent.selectOptions(control, action);
      if (action === "merge")
        await userEvent.selectOptions(
          screen.getByLabelText("Matching identity"),
          other,
        );
      if (action === "offboard_person")
        await userEvent.click(
          screen.getByLabelText(/I verified that no tenancy associations/),
        );
      if (action === "merge" || action === "offboard_person")
        await userEvent.click(screen.getByLabelText(/I acknowledge the consequences/));
      fireEvent.submit(control.closest("form")!);
      await screen.findByText(
        action === "cancel_simulation"
          ? "Simulation cancelled"
          : "Decision saved",
      );
      expect(c.submit).toHaveBeenCalledWith(
        expect.objectContaining({ action }),
        expect.any(AbortSignal),
      );
    },
  );

  // A conflict can be re-previewed; untrusted provider errors never become dialog content.
  it("keeps unchanged retry keys and reloads stale previews", async () => {
    const c = dialog();
    c.submit
      .mockRejectedValueOnce(
        new WorkflowError(409, "ORGANIZATION_PREVIEW_CHANGED"),
      )
      .mockRejectedValueOnce(new Error("private SQL details"));
    const control = await screen.findByLabelText("Action");
    await userEvent.selectOptions(control, "create_tenancy");
    await userEvent.type(
      screen.getByLabelText("Requested tenancy name"),
      "retrychild",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Home region"),
      "us-phoenix-1",
    );
    const form = control.closest("form")!;
    fireEvent.submit(form);
    await screen.findByText(/The organization or associations changed/);
    fireEvent.submit(form);
    await screen.findByText(/The action could not be confirmed/);
    expect(c.submit.mock.calls[0][0].client_request_key).toBe(
      c.submit.mock.calls[1][0].client_request_key,
    );
    expect(screen.queryByText("private SQL details")).toBeNull();
    await userEvent.click(
      screen.getByRole("button", { name: "Reload preview" }),
    );
    await waitFor(() => expect(api.personWorkflow).toHaveBeenCalledTimes(2));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(c.onClose).toHaveBeenCalled();
  });

  // Unauthorized reads expire the shared session while harmless unavailable cases retain close/retry controls.
  it("handles preview failure, no available actions and escape", async () => {
    const c = dialog();
    await screen.findByLabelText("Action");
    vi.mocked(api.personWorkflow).mockRejectedValueOnce(new ApiError(401));
    await c.client.invalidateQueries({ queryKey: ["person-workflow"] });
    await screen.findByRole("alert");
    expect(c.expired).toHaveBeenCalled();
    vi.mocked(api.personWorkflow).mockResolvedValue({
      ...preview,
      actions: [],
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Reload preview" }),
    );
    await screen.findByText(/No action is currently available/);
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { bubbles: true, cancelable: true }),
    );
    expect(c.onClose).toHaveBeenCalled();
  });
});

// Inventory and review screens use server-authoritative paging and the same dialog entry points.
describe("Tenancy inventory and organization inbox", () => {
  // Each header has its own server sort and owner-inclusive totals remain distinct from filtered results.
  it("sorts, searches and pages registered tenancies and opens an owner dialog", async () => {
    const read = vi
      .spyOn(api, "tenancies")
      .mockImplementation(async (query) => ({
        ...inventory,
        items: [{ ...tenant, operation_state: "queued" }],
        page: query.page ?? 1,
      }));
    vi.spyOn(api, "personWorkflow").mockResolvedValue(preview);
    const navigate = vi.fn();
    mount(
      <Tenancies identifier={null} expired={vi.fn()} navigate={navigate} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading tenancies");
    await screen.findByText(tenant.name);
    for (const label of [
      "Tenancy",
      "Owner",
      "Sort by actual",
      "Sort by budget",
      "Forecast",
    ]) {
      await userEvent.click(
        screen.getByRole("button", { name: new RegExp("^" + label + "$") }),
      );
    }
    await userEvent.type(screen.getByRole("searchbox"), "Shared");
    await userEvent.selectOptions(
      screen.getByLabelText("Tenancy rows per page"),
      "25",
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText(/Page 2 of 3/);
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Page 3" }));
    await screen.findByText(/Page 3 of 3/);
    expect(read).toHaveBeenLastCalledWith(
      expect.objectContaining({ query: "Shared", page: 3, page_size: 25 }),
      expect.any(AbortSignal),
    );
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await userEvent.click(screen.getByRole("link", { name: tenant.name }));
    expect(navigate).toHaveBeenCalledWith("/tenancies/" + id);
    await userEvent.click(screen.getByRole("link", { name: "View operation" }));
    expect(navigate).toHaveBeenCalledWith("/operations/" + op);
    await userEvent.click(
      screen.getByRole("link", { name: /Choose an owner/ }),
    );
    expect(navigate).toHaveBeenCalledWith("/organization");
    await userEvent.click(screen.getByRole("button", { name: employee.name }));
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  // Detail actions bind the person and tenancy, and removed memberships retain manual-cleanup guidance.
  it("shows child identity, owner/member actions and cleanup evidence", async () => {
    const member = {
      ...association,
      id: other,
      person_id: other,
      role: "member" as const,
      cleanup_required: true,
      actions: ["remove", "keep"] as AssociationView["actions"],
    };
    vi.spyOn(api, "tenancy").mockResolvedValue({
      ...detail,
      people: [employee, recipient],
      memberships: [association, member],
    });
    vi.spyOn(api, "personWorkflow").mockResolvedValue({
      ...preview,
      actions: ["transfer_owner", "remove_member"],
      associations: [association, member],
    });
    const navigate = vi.fn();
    mount(<Tenancies identifier={id} expired={vi.fn()} navigate={navigate} />);
    await screen.findByText("Accountability & registration");
    expect(screen.getByText("Manual cleanup guidance")).toBeInTheDocument();
    expect(screen.getAllByText(tenant.tenancy_ocid).length).toBeGreaterThan(0);
    await userEvent.click(
      screen.getByRole("button", { name: "Transfer owner" }),
    );
    expect(await screen.findByLabelText("Action")).toHaveValue(
      "transfer_owner",
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Remove member" }),
    );
    expect(await screen.findByLabelText("Action")).toHaveValue("remove_member");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: employee.name }));
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Manage owner & associations" })).toBeNull();
    expect(screen.getByRole("region", { name: "Overrides" })).toHaveTextContent("All categories inherit the assigned baseline.");
    expect(within(screen.getByRole("region", { name: "Overrides" })).getByRole("button", { name: "Manage overrides" })).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("link", { name: "View latest operation" }),
    );
    await userEvent.click(
      screen.getByRole("link", { name: /Back to tenancies/ }),
    );
    expect(navigate).toHaveBeenLastCalledWith("/tenancies");
  });

  // Unavailable records do not disclose provider data and refresh is possible after authorization expiration.
  it("handles empty inventory, literal search, and denied list/detail reads", async () => {
    const read = vi
      .spyOn(api, "tenancies")
      .mockResolvedValue({ ...inventory, items: [], total: 0 });
    const expired = vi.fn();
    const mounted = mount(
      <Tenancies identifier={null} expired={expired} navigate={vi.fn()} />,
    );
    await screen.findByText("No tenancies registered yet");
    await userEvent.type(screen.getByRole("searchbox"), "unknown");
    await screen.findByText("No tenancies match your search");
    read.mockRejectedValue(new ApiError(403));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("alert");
    expect(expired).toHaveBeenCalled();
    mounted.unmount();
    vi.spyOn(api, "tenancy").mockRejectedValue(new ApiError(401));
    mount(<Tenancies identifier={id} expired={expired} navigate={vi.fn()} />);
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  });

  // History never inherits live action buttons from a tab transition; expanded changes remain human-readable.
  it("separates inbox/history and supports sort, pagination, profile changes and action handoff", async () => {
    const history: ReviewView[] = [
      {
        ...review,
        id: "baseline",
        person_id: null,
        kind: "ORGANIZATION_BASELINE",
        category: "change",
        status: "resolved",
        data: { count: 5 },
      },
      {
        ...review,
        id: "metadata",
        kind: "METADATA_UPDATED",
        category: "change",
        status: "resolved",
        resolution: "create_tenancy",
        operation_id: op,
        data: {
          before: { full_name: "Old", designee_emails: [], lob_id: "segment-old", lob_name: "Previous segment" },
          after: {
            full_name: "New", lob_id: "segment-new", lob_name: "New segment",
            designee_emails: ["delegate@example.test"],
          },
        },
      },
      {
        ...review,
        id: "added",
        kind: "EMPLOYEE_ADDED",
        category: "change",
        status: "resolved",
        data: { after: { email: "added@example.test" } },
      },
      {
        ...review,
        id: "lifecycle",
        kind: "LIFECYCLE_COMPLETED",
        category: "change",
        status: "resolved",
      },
      {
        ...review,
        id: "warning",
        kind: "TOP_MANAGER_MISMATCH",
        category: "informational",
      },
      {
        ...review,
        id: "unknown",
        kind: "FUTURE_WARNING",
        category: "informational",
        status: "resolved",
      },
    ];
    const read = vi
      .spyOn(api, "organizationReviews")
      .mockImplementation(async (query) => ({
        ...reviews,
        page: query.page ?? 1,
        items: query.category !== "actionable" ? history : [review],
      }));
    vi.spyOn(api, "personWorkflow").mockResolvedValue({ ...preview, review });
    const navigate = vi.fn();
    mount(<OrganizationReviews expired={vi.fn()} navigate={navigate} />);
    await screen.findByRole("button", { name: "Review" });
    for (const label of ["Employee", "Review / event", "First observed"])
      await userEvent.click(
        screen.getByRole("button", {
          name: new RegExp("^" + label.replace("/", "\\/") + "$"),
        }),
      );
    await userEvent.type(screen.getByRole("searchbox"), "employee");
    await userEvent.selectOptions(
      screen.getByLabelText("Review rows per page"),
      "25",
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText(/Page 2 of 3/);
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await userEvent.click(screen.getByRole("button", { name: "Page 3" }));
    await screen.findByText(/Page 3 of 3/);
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Informational & history/ }),
    );
    await screen.findByText("5 employees in the initial baseline.");
    expect(screen.getByRole("button", { name: "Informational & history 3" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Show all history" })).not.toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Show all history" }));
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ category: "history", page: 1, query: "employee", sort: "first_seen_at", direction: "desc" }), expect.any(AbortSignal)));
    expect(screen.getByRole("button", { name: "Informational & history 5" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Actionable/ }));
    expect(screen.queryByRole("checkbox", { name: "Show all history" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Informational & history/ }));
    expect(screen.getByRole("checkbox", { name: "Show all history" })).toBeChecked();

    await userEvent.click(screen.getByRole("checkbox", { name: "Show all history" }));
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ category: "informational", page: 1 }), expect.any(AbortSignal)));

    expect(screen.queryByRole("button", { name: "Review" })).toBeNull();
    expect(screen.getByText("Current warning")).toBeInTheDocument();
    expect(screen.getByText("Employee profile added")).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Name, Industry segment, Designees updated/));
    expect(screen.getByText(/delegate@example.test/)).toBeInTheDocument();
    expect(screen.getByText("Previous segment → New segment")).toBeInTheDocument();
    expect(screen.queryByText(/segment-old/)).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "View operation" }));
    expect(navigate).toHaveBeenCalledWith("/operations/" + op);
    await userEvent.click(
      screen.getAllByRole("button", { name: employee.name })[0],
    );
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: /Actionable/ }));
    await screen.findByRole("button", { name: "Review" });
    expect(read).toHaveBeenCalled();
  });

  // Empty and failed inbox reads retain clear controls rather than a silent stale actionable list.
  it("renders empty/search/history states and expires denied review requests", async () => {
    const read = vi
      .spyOn(api, "organizationReviews")
      .mockResolvedValue({ ...reviews, items: [], total: 0 });
    const expired = vi.fn();
    mount(<OrganizationReviews expired={expired} navigate={vi.fn()} />);
    await screen.findByText("No actionable organization drift");
    await userEvent.type(screen.getByRole("searchbox"), "nobody");
    await screen.findByText("No reviews match your search");
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.click(
      screen.getByRole("button", { name: /Informational & history/ }),
    );
    await screen.findByText("No information for the latest feed");
    read.mockRejectedValue(new ApiError(401));
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("alert");
    expect(expired).toHaveBeenCalled();
  });
});

// A one-click shared view composes with search/paging and leaves whole-inventory cards unchanged.
it("shows only shared tenancies and returns to page one when toggled", async () => {
  const individual = {
    ...tenant,
    id: other,
    name: "Individual workspace",
    kind: "individual" as const,
  };
  const read = vi.spyOn(api, "tenancies").mockImplementation(async (query) => ({
    ...inventory,
    items: query.shared_only ? [tenant] : [tenant, individual],
    page: query.page ?? 1,
    total_tenancies: 26,
    shared_count: 6,
  }));
  mount(<Tenancies identifier={null} expired={vi.fn()} navigate={vi.fn()} />);
  await screen.findByText("Individual workspace");
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText(/Page 2 of 3/);
  const checkbox = screen.getByLabelText("Shared tenancies only");
  await userEvent.click(checkbox);
  await waitFor(() =>
    expect(screen.queryByText("Individual workspace")).toBeNull(),
  );
  expect(screen.getByRole("link", { name: tenant.name })).toBeInTheDocument();
  expect(read).toHaveBeenLastCalledWith(
    expect.objectContaining({ shared_only: true, page: 1 }),
    expect.any(AbortSignal),
  );
  expect(screen.getByLabelText("Tenancy statistics")).toHaveTextContent(
    "Total tenancies26",
  );
  await userEvent.type(screen.getByRole("searchbox"), "Shared");
  await waitFor(() =>
    expect(read).toHaveBeenLastCalledWith(
      expect.objectContaining({ shared_only: true, query: "Shared" }),
      expect.any(AbortSignal),
    ),
  );
  await userEvent.click(checkbox);
  await screen.findByText("Individual workspace");
  expect(read).toHaveBeenLastCalledWith(
    expect.objectContaining({ shared_only: false, page: 1, query: "Shared" }),
    expect.any(AbortSignal),
  );
  read.mockResolvedValue({ ...inventory, items: [], total: 0, pages: 1 });
  await userEvent.clear(screen.getByRole("searchbox"));
  await userEvent.click(checkbox);
  await screen.findByText("No shared tenancies registered yet");
});

// Create freezes both required SDK inputs; no inferred name or hidden Ashburn choice is submitted.
it("submits the explicitly chosen creation name and home region", async () => {
  const c = dialog(preview, "create_tenancy");
  await userEvent.type(
    await screen.findByLabelText("Requested tenancy name"),
    "phoenixchild",
  );
  expect(screen.getByRole("button", { name: "Create tenancy" })).toBeDisabled();
  await userEvent.selectOptions(
    screen.getByLabelText("Home region"),
    "us-phoenix-1",
  );
  await userEvent.click(screen.getByRole("button", { name: "Create tenancy" }));
  await screen.findByText("Operation accepted");
  expect(c.submit).toHaveBeenCalledWith(
    expect.objectContaining({
      action: "create_tenancy",
      name: "phoenixchild",
      home_region: "us-phoenix-1",
    }),
    expect.any(AbortSignal),
  );
});

// Role repair links into the exact segment while the person's separate association dialog remains usable.
it("links role repair separately from employee tenancy actions", async () => {
  const navigate = vi.fn();
  vi.spyOn(api, "organizationReviews").mockResolvedValue({
    ...reviews,
    items: [
      {
        ...review,
        kind: "LOB_LEADER_REVIEW",
        data: { segment_id: "one", segment_name: "Industry One" },
      },
    ],
  });
  const profile = vi.spyOn(api, "personWorkflow").mockResolvedValue(preview);
  mount(<OrganizationReviews expired={vi.fn()} navigate={navigate} />);
  const link = await screen.findByRole("link", { name: "Repair mapping" });
  expect(link).toHaveAttribute("href", "/organization-mapping#segment-one");
  await userEvent.click(link);
  expect(navigate).toHaveBeenCalledWith("/organization-mapping#segment-one");
  await userEvent.click(screen.getByRole("button", { name: employee.name }));
  await waitFor(() =>
    expect(profile).toHaveBeenCalledWith(id, null, expect.any(AbortSignal)),
  );
});

// An affected employee sees a clear repair route, while their independent cleanup stays available.
it("explains mapping-dependent provisioning blocks without blocking cleanup", async () => {
  const c = dialog({
    ...preview,
    mapping_required: true,
    actions: ["offboard_person"],
  });
  await screen.findByText(/Organization mapping must be corrected before/);
  const choices = screen.getByRole("combobox", { name: "Action" });
  expect(
    within(choices).queryByRole("option", { name: "Create tenancy" }),
  ).toBeNull();
  expect(
    within(choices).getByRole("option", { name: "Offboard employee" }),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("link", { name: "Repair Organization Mapping" }),
  );
  expect(c.navigate).toHaveBeenCalledWith("/organization-mapping");
});

// A decision refreshes cached mapping context before a later settings visit can reuse it.
it("refreshes inactive organization mapping context after a decision", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let context = "before-decision";
  await client.fetchQuery({ queryKey: ["organization-mapping"], queryFn: async () => context });
  context = "after-decision";
  await refreshOrganization(client);
  expect(client.getQueryData(["organization-mapping"])).toBe("after-decision");
  client.clear();
});

// Missing defaults block only new-tenancy provisioning and keep application-only choices available.
it("requires a published default for create/import without blocking no-tenancy decisions", async()=>{
  const c=dialog({...preview,current_baseline:null},"create_tenancy");
  await screen.findByText(/No published baseline/);
  expect(screen.getByRole("button",{name:"Create tenancy"})).toBeDisabled();
  await userEvent.selectOptions(screen.getByRole("combobox",{name:"Action"}),"import_tenancy");
  expect(screen.getByRole("button",{name:"Import tenancy"})).toBeDisabled();
  expect(screen.getByRole("link",{name:"Publish a baseline"})).toHaveAttribute("href","/configuration");
  await userEvent.selectOptions(screen.getByRole("combobox",{name:"Action"}),"no_tenancy_required");
  expect(screen.getByRole("button",{name:"No tenancy required"})).toBeEnabled();
  c.client.clear();
});

// Read-only baseline inspection leaves creation inputs mounted in state and restores keyboard focus.
it("returns to the same create form with name and region preserved",async()=>{
 const c=dialog(preview,"create_tenancy");
 const name=await screen.findByLabelText("Requested tenancy name");
 await userEvent.type(name,"retainedsandbox");
 await userEvent.selectOptions(screen.getByRole("combobox",{name:"Home region"}),"us-phoenix-1");
 const baseline=screen.getByRole("link",{name:"Version 1"});await userEvent.click(baseline);
 expect(screen.getByRole("heading",{name:"Published baseline v1"})).toBeInTheDocument();
 await userEvent.click(screen.getByRole("link",{name:/Back to create tenancy/}));
 await waitFor(()=>expect(screen.getByLabelText("Requested tenancy name")).toHaveValue("retainedsandbox"));
 expect(screen.getByRole("combobox",{name:"Home region"})).toHaveValue("us-phoenix-1");
 expect(screen.getByRole("link",{name:"Version 1"})).toHaveFocus();c.client.clear();
});

// Baseline context shares Status; completed operation dates do not become inventory actions.
it("groups assigned/latest baseline with status without completed operation links",async()=>{
 const read=vi.spyOn(api,"tenancies").mockResolvedValue({...inventory,latest_baseline_id:id,latest_baseline_version_number:2,items:[{...tenant,baseline_version_id:id,baseline_version_number:2,operation_completed_at:time}]});
 const navigate=vi.fn();mount(<Tenancies identifier={null} expired={vi.fn()} navigate={navigate}/>);
 const link=await screen.findByRole("link",{name:"Baseline v2"});expect(link.closest("td")).toHaveTextContent("Latest");
 expect(screen.queryByRole("link",{name:"Oct 30, 2026"})).toBeNull();
 expect(screen.queryByRole("link",{name:"View operation"})).toBeNull();
 read.mockResolvedValue({...inventory,latest_baseline_id:other,latest_baseline_version_number:3,items:[{...tenant,baseline_version_id:id,baseline_version_number:2}]});
 await userEvent.click(screen.getByRole("button",{name:"Refresh"}));
 expect(await screen.findByRole("link",{name:`Update ${tenant.name} to baseline v3`})).toHaveAttribute("href","/tenancies/"+id);
});


// Status creation metadata is available to keyboard users and dismisses without opening history.
it("describes creation on the focusable inventory status and dismisses its tooltip with Escape", async () => {
 vi.spyOn(api,"tenancies").mockResolvedValue({...inventory,items:[{...tenant,operation_completed_at:"2026-11-01T12:00:00Z"}]});
 mount(<Tenancies identifier={null} expired={vi.fn()} navigate={vi.fn()}/>);
 const status=await screen.findByText("✓ Active");
 expect(status).toHaveAttribute("tabindex","0");
 expect(status).toHaveAccessibleDescription("Created 10/30/2026, 12:00:00 PM UTC");
 status.focus();expect(status).toHaveFocus();
 await userEvent.keyboard("{ArrowRight}");expect(status.parentElement).not.toHaveAttribute("data-tooltip-dismissed");
 await userEvent.keyboard("{Escape}");expect(status.parentElement).toHaveAttribute("data-tooltip-dismissed");
 await userEvent.hover(status);expect(status.parentElement).not.toHaveAttribute("data-tooltip-dismissed");
 await userEvent.keyboard("{Escape}");status.blur();status.focus();
 await waitFor(()=>expect(status.parentElement).not.toHaveAttribute("data-tooltip-dismissed"));
 expect(screen.queryByRole("link",{name:/Nov 1/})).toBeNull();
});

// History remains reachable elsewhere; this compact inventory only links current work.
it.each([
 ["queued",false,"View operation"], ["running",false,"View operation"], ["waiting",false,"View operation"],
 ["needs_attention",true,"Review operation"], ["needs_attention",false,null], ["failed",true,null],
 ["succeeded",false,null], ["cancelled",false,null], [null,false,null],
] as const)("shows operation link for %s with pending=%s only when work remains",async(state,pending,label)=>{
 vi.spyOn(api,"tenancies").mockResolvedValue({...inventory,items:[{...tenant,operation_state:state,has_pending_operation:pending}]});
 mount(<Tenancies identifier={null} expired={vi.fn()} navigate={vi.fn()}/>);
 await screen.findByText(tenant.name);
 if(label)expect(screen.getByRole("link",{name:label})).toHaveAttribute("href","/operations/"+op);
 else expect(screen.queryByRole("link",{name:/^(View|Review) operation$/})).toBeNull();
});

// Overrides belong to their own section and never claim verification from missing evidence.
it.each([
 [id,id,"Verified in simulation"], [id,other,"Verification pending"], [undefined,undefined,"Verification pending"],
] as const)("shows override categories and verification evidence %s/%s",async(desired,verified,label)=>{
 vi.spyOn(api,"tenancy").mockResolvedValue({...detail,tenancy:{...tenant,override_categories:["policy","quota","budget"],desired_configuration_id:desired,last_verified_configuration_id:verified}});
 mount(<Tenancies identifier={id} expired={vi.fn()} navigate={vi.fn()}/>);
 const section=await screen.findByRole("region",{name:"Overrides"});
 expect(section).toHaveTextContent("Policy statements, Quota statements, Monthly budget");
 expect(section).toHaveTextContent(label);
 expect(within(section).getByRole("button",{name:"Manage overrides"})).toBeInTheDocument();
 expect(screen.queryByRole("button",{name:"Manage owner & associations"})).toBeNull();
});


// Existing-compartment membership binds the chosen child without sending creation-only fields.
it("adds a shared member to an existing nonroot compartment", async () => {
 const c=dialog();
 const existing="ocid1.compartment.oc1..existingproject";
 vi.mocked(api.tenancy).mockResolvedValue({...detail,compartment_parents:[{name:"Tenancy root",ocid:tenant.tenancy_ocid},{name:"Existing project",ocid:existing}]});
 await userEvent.selectOptions(await screen.findByLabelText("Action"),"join_shared");
 await userEvent.selectOptions(screen.getByLabelText("Shared tenancy"),id);
 await waitFor(()=>expect(screen.getByLabelText("Existing parent compartment")).toBeEnabled());
 await userEvent.selectOptions(screen.getByLabelText("Compartment assignment"),"existing");
 expect(screen.queryByLabelText("Employee compartment name")).toBeNull();
 expect(screen.queryByRole("option",{name:/Tenancy root/})).toBeNull();
 await userEvent.selectOptions(screen.getByLabelText("Existing compartment"),existing);
 expect(screen.getByText("Selected compartment: "+existing)).toBeInTheDocument();
 await userEvent.click(screen.getByRole("button",{name:"Add to shared tenancy"}));
 await screen.findByText("Operation accepted");
 expect(c.submit).toHaveBeenCalledWith(expect.objectContaining({action:"join_shared",tenancy_id:id,existing_compartment_ocid:existing}),expect.any(AbortSignal));
 const command=c.submit.mock.calls[0][0];
 expect(command).not.toHaveProperty("parent_compartment_ocid");
 expect(command).not.toHaveProperty("compartment_name");
});

// Switching modes clears the incompatible target while retaining the user's new-compartment name.
it("returns from an existing compartment to explicit compartment creation", async () => {
 const c=dialog();
 const existing="ocid1.compartment.oc1..existingproject";
 vi.mocked(api.tenancy).mockResolvedValue({...detail,compartment_parents:[{name:"Tenancy root",ocid:tenant.tenancy_ocid},{name:"Existing project",ocid:existing}]});
 await userEvent.selectOptions(await screen.findByLabelText("Action"),"join_shared");
 await userEvent.selectOptions(screen.getByLabelText("Shared tenancy"),id);
 await waitFor(()=>expect(screen.getByLabelText("Existing parent compartment")).toBeEnabled());
 await userEvent.clear(screen.getByLabelText("Employee compartment name"));
 await userEvent.type(screen.getByLabelText("Employee compartment name"),"Retained project");
 await userEvent.selectOptions(screen.getByLabelText("Compartment assignment"),"existing");
 await userEvent.selectOptions(screen.getByLabelText("Existing compartment"),existing);
 await userEvent.selectOptions(screen.getByLabelText("Compartment assignment"),"create");
 expect(screen.getByLabelText("Existing parent compartment")).toHaveValue("");
 expect(screen.getByLabelText("Employee compartment name")).toHaveValue("Retained project");
 expect(screen.getByRole("option",{name:/Tenancy root/})).toBeInTheDocument();
 await userEvent.selectOptions(screen.getByLabelText("Existing parent compartment"),tenant.tenancy_ocid);
 await userEvent.click(screen.getByRole("button",{name:"Add to shared tenancy"}));
 await screen.findByText("Operation accepted");
 expect(c.submit).toHaveBeenCalledWith(expect.objectContaining({action:"join_shared",tenancy_id:id,parent_compartment_ocid:tenant.tenancy_ocid,compartment_name:"Retained project"}),expect.any(AbortSignal));
 expect(c.submit.mock.calls[0][0]).not.toHaveProperty("existing_compartment_ocid");
});

// Confirmed differences and read-health labels independently open the same tenancy's evidence.
it.each([
 ["unavailable",false,0,["Unable to verify"]],
 ["drifted",false,2,["Configuration drift · 2 categories"]],
 ["unavailable",true,2,["Configuration drift · 2 categories","Check out of date","Unable to verify"]],
 ["checking",true,1,["Configuration drift · 1 category","Check out of date","Checking"]],
 ["not_checked",true,0,["Check out of date"]],
 ["not_checked",false,0,["Not checked"]],
 ["superseded",false,0,["Not checked"]],
] as const)("links independent configuration messages for %s stale=%s confirmed=%s",async(state,stale,confirmed,messages)=>{
 vi.spyOn(api,"tenancies").mockResolvedValue({...inventory,items:[{...tenant,configuration_issue_count:confirmed,configuration_confirmed_issue_count:confirmed,configuration_check_state:state,configuration_check_stale:stale}]});const navigate=vi.fn();mount(<Tenancies identifier={null} expired={vi.fn()} navigate={navigate}/>);
 for(const label of messages){const link=await screen.findByRole("link",{name:`Config: ${label.replace(/^Configuration drift/,"Drift")} for ${tenant.name}`});expect(link).toHaveAttribute("href",`/configuration/drift/${id}?returnTo=%2Ftenancies`);expect(link).toHaveClass(label==="Not checked"?"configuration-unverified":label==="Checking"?"waiting":"review-open");await userEvent.click(link);}
 expect(navigate).toHaveBeenCalled();expect(screen.queryByText(/configuration issues/)).toBeNull();
});

// Healthy or unchecked rows do not acquire a spurious exception indicator.
it("keeps a fresh matching inventory free of configuration warnings",async()=>{
 vi.spyOn(api,"tenancies").mockResolvedValue({...inventory,items:[{...tenant,configuration_issue_count:0,configuration_confirmed_issue_count:0,configuration_check_state:"matching"}]});mount(<Tenancies identifier={null} expired={vi.fn()} navigate={vi.fn()}/>);await screen.findByText(tenant.name);expect(screen.queryByRole("link",{name:/^Config:.*for/})).toBeNull();
});

it.each([false,true])("links tenancy check status and preserves its detail return, stale=%s",async(stale)=>{
 vi.spyOn(api,"tenancy").mockResolvedValue({...detail,tenancy:{...tenant,configuration_check_state:"unavailable",configuration_check_stale:stale,configuration_checked_at:time}});const navigate=vi.fn();mount(<Tenancies identifier={id} expired={vi.fn()} navigate={navigate}/>);const link=await screen.findByRole("link",{name:`${stale?"Check out of date":"Unable to verify"} for ${tenant.name}`});expect(link).toHaveAttribute("href",`/configuration/drift/${id}?returnTo=%2Ftenancies%2F${id}`);expect(screen.getByText(/Last attempt:/)).toBeVisible();await userEvent.click(link);expect(navigate).toHaveBeenCalled();
});

// Pending and retired tenancy routes remain browsable without linking to an active-only check endpoint.
it.each(["pending","terminated"] as const)("omits an unavailable check link on a %s tenancy",async(status)=>{
 vi.spyOn(api,"tenancy").mockResolvedValue({...detail,tenancy:{...tenant,status,configuration_issue_count:1,configuration_check_state:"unavailable"}});
 mount(<Tenancies identifier={id} expired={vi.fn()} navigate={vi.fn()}/>);
 await screen.findByText("Checks are available for active managed tenancies.");
 expect(screen.queryByRole("link",{name:"Unable to verify"})).toBeNull();
 expect(screen.queryByRole("link",{name:/configuration issue/})).toBeNull();
});

// The server's contact preview is read-only and never substitutes a testing address for employee identity.
it.each(["create_tenancy","import_tenancy"] as const)("shows effective contacts on %s without changing the person",async(action)=>{
 const route={original_email:employee.email,effective_email:"capture@example.test",environment:"staging" as const,policy_hash:"a".repeat(64),redirected:true};
 dialog({...preview,email_contacts:{activation:{...route,original_email:null},owner:route}});
 await userEvent.selectOptions(await screen.findByLabelText("Action"),action);
 const contacts=screen.getByRole("region",{name:"Tenancy email contacts"});
 expect(contacts).toHaveTextContent("Original contact: "+employee.email);expect(contacts).toHaveTextContent("Test delivery: capture@example.test");
 expect(screen.getByText(employee.email,{selector:"span"})).toBeVisible();expect(within(contacts).queryByRole("textbox")).toBeNull();
 if(action==="create_tenancy")expect(within(contacts).getByText("Activation / bootstrap email")).toBeVisible();else {expect(within(contacts).queryByText("Activation / bootstrap email")).toBeNull();expect(within(contacts).getByText("Bootstrap contact email")).toBeVisible();}
});

// A presence-only pending check refreshes inventory even when lifecycle and cost jobs are idle.
it("refreshes stored required-user summaries while checking and stops when complete",async()=>{
  const read=vi.spyOn(api,"tenancies").mockResolvedValueOnce({...inventory,items:[{...tenant,required_users:{state:"not_checked",checking:true}}]})
    .mockResolvedValue({...inventory,items:[{...tenant,required_users:{state:"present",checking:false,
      automation:{state:"present",checked_at:time,operation_id:op},recovery:{state:"present",checked_at:time,operation_id:op}}}]});
  const c=mount(<Tenancies identifier={null} expired={vi.fn()} navigate={vi.fn()}/>);
  await screen.findByText("Checking…");
  await screen.findByRole("link",{name:`Users: 2/2 present for ${tenant.name}`},{timeout:3500});
  expect(read).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("Checking…")).not.toBeInTheDocument();
  c.unmount();
});

// Revoked directory access hides previously visible user facts while the session is cleared.
it("hides a retained required-user summary after inventory authorization is lost",async()=>{
  const read=vi.spyOn(api,"tenancies").mockResolvedValue({...inventory,items:[{...tenant,required_users:{state:"present",
    automation:{state:"present",checked_at:time,operation_id:op},recovery:{state:"present",checked_at:time,operation_id:op}}}]});
  const expired=vi.fn();mount(<Tenancies identifier={null} expired={expired} navigate={vi.fn()}/>);
  await screen.findByRole("link",{name:`Users: 2/2 present for ${tenant.name}`});
  read.mockRejectedValue(new ApiError(403));
  await userEvent.click(screen.getByRole("button",{name:/^Refresh$/}));
  await screen.findByText("Tenancies could not be loaded. Use Refresh to try again.");
  expect(screen.queryByRole("link",{name:/Users: 2\/2 present/})).not.toBeInTheDocument();
  expect(expired).toHaveBeenCalled();
});


// Explicit consent blocks click, Enter and script-triggered submit before any destructive API call.
it.each(["offboard_person", "delete_tenancy", "remove_member", "transfer_owner", "merge"] as const)(
  "requires independent destructive consent for %s", async action => {
    const c=dialog({...preview,actions:[action], associations:action==="offboard_person"||action==="merge"?[]:[{...association,tenancy_kind:"individual",actions:["delete","remove","transfer","keep"]}]},action);
    const control=await screen.findByLabelText("Action");
    if(action==="offboard_person")await userEvent.click(screen.getByLabelText(/I verified that no tenancy associations/));
    if(["delete_tenancy","remove_member","transfer_owner"].includes(action))await userEvent.selectOptions(screen.getByLabelText("Tenancy"),id);
    if(action==="transfer_owner"){await userEvent.selectOptions(screen.getByLabelText("New owner"),other);await userEvent.selectOptions(screen.getByLabelText("Former owner"),"remove");}
    if(action==="merge")await userEvent.selectOptions(screen.getByLabelText("Matching identity"),other);
    const ack=screen.getByLabelText(/I acknowledge the consequences/);expect(ack).not.toBeChecked();
    const button=control.closest("form")!.querySelector<HTMLButtonElement>('button.danger')!;
    expect(button).toBeDisabled();await userEvent.click(button);await userEvent.keyboard("{Enter}");
    fireEvent.submit(control.closest("form")!);expect(c.submit).not.toHaveBeenCalled();
    await userEvent.click(ack);expect(button).toBeEnabled();fireEvent.submit(control.closest("form")!);
    await waitFor(()=>expect(c.submit).toHaveBeenCalledTimes(1));
    expect(c.submit.mock.calls[0][0].confirm_destructive).toBe(true);
  }
);

// Acknowledgment belongs to the reviewed target/plan and is cleared even on an identical reload.
it("clears destructive consent on action, target, plan and refreshed preview",async()=>{
  const another={...association,id:other,tenancy_id:other,tenancy_name:"Other tenancy",actions:["remove","keep"] as AssociationView["actions"]};
  const c=dialog({...preview,actions:["remove_member","offboard_person"],associations:[{...association,actions:["remove","keep"]},another]},"remove_member");
  const action=await screen.findByLabelText("Action");
  await userEvent.selectOptions(screen.getByLabelText("Tenancy"),id);
  const ack=()=>screen.getByLabelText(/I acknowledge the consequences/);
  await userEvent.click(ack());await userEvent.selectOptions(screen.getByLabelText("Tenancy"),other);expect(ack()).not.toBeChecked();
  await userEvent.click(ack());await userEvent.selectOptions(action,"offboard_person");expect(ack()).not.toBeChecked();
  await userEvent.click(ack());await userEvent.selectOptions(screen.getByLabelText("Action for "+tenant.name),"keep");expect(ack()).not.toBeChecked();
  await userEvent.click(ack());await c.client.invalidateQueries({queryKey:["person-workflow"]});
  await waitFor(()=>expect(ack()).not.toBeChecked());expect(c.submit).not.toHaveBeenCalled();
});


// A simultaneous generic preview failure must not mask authorization loss in compartment discovery.
it("expires when either required query loses authorization", async()=>{
  const c=dialog(preview,"join_shared");
  vi.mocked(api.tenancy).mockRejectedValue(new ApiError(401));
  await userEvent.selectOptions(await screen.findByLabelText("Shared tenancy"),id);
  await waitFor(()=>expect(c.expired).toHaveBeenCalled());
  c.expired.mockClear();vi.mocked(api.personWorkflow).mockRejectedValue(new ApiError(503));
  await c.client.invalidateQueries({queryKey:["person-workflow"]});
  await waitFor(()=>expect(c.expired).toHaveBeenCalled());expect(c.submit).not.toHaveBeenCalled();
});

// Changing the recipient or identity pair always invalidates prior destructive consent.
it.each(["transfer_owner","merge"] as const)("clears consent on %s recipient change", async action=>{
  dialog({...preview,actions:[action],associations:[{...association,actions:["transfer","keep"]}],
    transfer_recipients:[recipient,{id:op,name:"Another owner",email:"another@example.test"}],
    merge_partners:[recipient,{id:op,name:"Another identity",email:"another@example.test"}]},action);
  await screen.findByLabelText("Action");
  if(action==="transfer_owner")await userEvent.selectOptions(screen.getByLabelText("Tenancy"),id);
  const field=screen.getByLabelText(action==="merge"?"Matching identity":"New owner");
  await userEvent.selectOptions(field,other);
  if(action==="transfer_owner")await userEvent.selectOptions(screen.getByLabelText("Former owner"),"remove");
  const ack=screen.getByLabelText(/I acknowledge the consequences/);await userEvent.click(ack);
  await userEvent.selectOptions(field,op);expect(ack).not.toBeChecked();
  await userEvent.selectOptions(field,other);expect(ack).not.toBeChecked();
});

// Keeping an employee closes onboarding without an exemption, cloud job or destructive consent.
it("keeps an employee in the normal directory without provisioning",async()=>{
 const c=dialog({...preview,actions:[...preview.actions,"keep_without_tenancy"]},"keep_without_tenancy");
 c.submit.mockResolvedValue({operation_id:null,state:"succeeded",provider_mode:"application",accepted_at:time});
 await screen.findByRole("button",{name:/^Keep in organization$/});
 expect(screen.queryByRole("checkbox")).toBeNull();
 await userEvent.click(screen.getByRole("button",{name:/^Keep in organization$/}));
 await screen.findByText("Decision saved",{exact:true});
 expect(c.submit).toHaveBeenCalledTimes(1);
 expect(c.submit.mock.calls[0][0].action).toBe("keep_without_tenancy");
 expect(screen.queryByRole("link",{name:"View operation"})).toBeNull();
});

// The tenancy shortcut is available only on active shared tenancies, with busy work protected.
it.each([
 ["shared","active",false,true,false], ["shared","active",true,true,true],
 ["individual","active",false,false,false], ["shared","terminated",false,false,false],
] as const)("gates the add-member shortcut for %s/%s busy=%s",async(kind,status,busy,visible,disabled)=>{
 vi.spyOn(api,"tenancy").mockResolvedValue({...detail,tenancy:{...tenant,kind,status,has_pending_operation:busy}});
 mount(<Tenancies identifier={id} expired={vi.fn()} navigate={vi.fn()}/>);
 await screen.findByText("Accountability & registration");
 const button=screen.queryByRole("button",{name:"Add member"});
 if(visible){expect(button).toBeVisible();expect(button).toHaveClass("secondary");if(disabled)expect(button).toBeDisabled();else expect(button).toBeEnabled();}
 else expect(button).toBeNull();
});

// Retaining an owner is an explicit, neutral mapping choice, never silent privilege reduction.
it("keeps the former owner's identity without destructive consent",async()=>{
 const c=dialog({...preview,actions:["transfer_owner"],associations:[{...association,actions:["transfer","keep"]}]},"transfer_owner");
 await userEvent.selectOptions(await screen.findByLabelText("Tenancy"),id);
 await userEvent.selectOptions(screen.getByLabelText("New owner"),other);
 expect(screen.getByLabelText("Former owner")).toHaveValue("");
 fireEvent.submit(screen.getByLabelText("Action").closest("form")!);expect(c.submit).not.toHaveBeenCalled();
 await userEvent.selectOptions(screen.getByLabelText("Former owner"),"keep_member");
 expect(screen.getByText(/including any administrator access/)).toBeVisible();
 expect(screen.queryByText("Review destructive action")).toBeNull();
 expect(screen.queryByLabelText(/I acknowledge the consequences/)).toBeNull();
 await userEvent.click(screen.getByLabelText(/I reviewed the ownership change and retained access/));
 const submit=screen.getByRole("button",{name:"Transfer tenancy ownership"});expect(submit).toHaveClass("primary");
 await userEvent.click(submit);await screen.findByText("Operation accepted");
 expect(c.submit.mock.calls[0][0]).toMatchObject({action:"transfer_owner",former_owner_disposition:"keep_member",recipient_person_id:other});
 expect(c.submit.mock.calls[0][0].confirm_destructive).toBeUndefined();
});

// Changing retention/removal invalidates both target-specific and destructive acknowledgments.
it("reviews explicit identity removal and makes cleanup instructions optional",async()=>{
 const c=dialog({...preview,actions:["transfer_owner"],associations:[{...association,actions:["transfer","keep"]}]},"transfer_owner");
 await userEvent.selectOptions(await screen.findByLabelText("Tenancy"),id);
 await userEvent.selectOptions(screen.getByLabelText("New owner"),other);
 const choice=screen.getByLabelText("Former owner");await userEvent.selectOptions(choice,"remove");
 expect(screen.getByText(/Confirm former-owner access removal/)).toBeVisible();
 const summary=screen.getByText("Manual cleanup responsibilities",{selector:"summary"});
 expect(summary.closest("details")).not.toHaveAttribute("open");
 await userEvent.click(summary);expect(screen.getByText(/If a dedicated compartment was created/)).toBeVisible();
 expect(screen.getByText(/Review additional users, API keys/)).toBeVisible();
 await userEvent.click(screen.getByLabelText(/I reviewed the shared tenancy impact/));
 await userEvent.click(screen.getByLabelText(/I acknowledge the consequences/));
 await userEvent.selectOptions(choice,"keep_member");
 await userEvent.selectOptions(choice,"remove");
 expect(screen.getByLabelText(/I acknowledge the consequences/)).not.toBeChecked();
 expect(screen.getByLabelText(/I reviewed the shared tenancy impact/)).not.toBeChecked();
 fireEvent.submit(screen.getByLabelText("Action").closest("form")!);expect(c.submit).not.toHaveBeenCalled();
});

// The offboarding variant also fails closed when its exact outgoing identity is unavailable.
it("blocks offboard-transfer removal without a bound identity",async()=>{
 const c=dialog({...preview,source_present:false,actions:["offboard_person"],associations:[{...association,user_ocid:null,actions:["transfer","keep"]}]},"offboard_person");
 await userEvent.selectOptions(await screen.findByLabelText("Action for "+tenant.name),"transfer");
 await userEvent.selectOptions(screen.getByLabelText("New owner for "+tenant.name),other);
 expect(screen.getByText(/Not recorded — automated removal is unavailable/)).toBeVisible();
 await userEvent.click(screen.getByLabelText(/I reviewed the shared tenancy impact/));
 await userEvent.click(screen.getByLabelText(/I acknowledge the consequences/));
 expect(screen.getByRole("button",{name:"Offboard employee"})).toBeDisabled();
 fireEvent.submit(screen.getByLabelText("Action").closest("form")!);expect(c.submit).not.toHaveBeenCalled();
 await userEvent.selectOptions(screen.getByLabelText("Former owner for "+tenant.name),"keep_member");
 expect(screen.getByText(/including any administrator access/)).toBeVisible();
 expect(screen.getByText("Review destructive action")).toBeVisible();
});

// Individual-tenancy removal has the same resource/account cleanup explanation as shared removal.
it("shows cleanup responsibilities for individual owner transfer",async()=>{
 dialog({...preview,actions:["transfer_owner"],associations:[{...association,tenancy_kind:"individual",actions:["transfer","keep"]}]},"transfer_owner");
 await userEvent.selectOptions(await screen.findByLabelText("Tenancy"),id);
 await userEvent.selectOptions(screen.getByLabelText("New owner"),other);
 expect(screen.queryByRole("option",{name:/Keep as a member/})).toBeNull();
 await userEvent.selectOptions(screen.getByLabelText("Former owner"),"remove");
 expect(screen.getByText("Manual cleanup responsibilities",{selector:"summary"})).toBeVisible();
});
