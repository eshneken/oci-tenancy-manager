import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { Tenancies } from "../src/Tenancies";
import { DeleteTenancy } from "../src/DeleteTenancy";
import { api, ApiError } from "../src/api";
import type { TenancyDeletionPreview } from "../src/contracts";

const id = "11111111-1111-4111-8111-111111111111";
const preview: TenancyDeletionPreview = {
  context: {
    applied_version_id: id,
    proposed_version_id: id,
    configuration_id: id,
    registry_revision: 1,
  },
  tenancy: {
    id,
    name: "Shared sandbox",
    tenancy_ocid: "ocid1.tenancy.oc1..otmsimchild",
    parent_tenancy_ocid: "ocid1.tenancy.oc1..otmsimparent",
    home_region: "us-ashburn-1",
    kind: "shared",
    status: "active",
    origin: "create",
    provider_mode: "simulated",
    owner_person_id: id,
    owner_name: "Owner",
    owner_email: "owner@example.test",
    manager_name: "Manager",
    leader_name: "Leader",
    lob_name: "Example",
    member_count: 2,
    operation_id: null,
    operation_state: null,
    verified_at: null,
    created_at: "2026-10-31T12:00:00Z",
    cleanup_count: 0,
  },
  people: [
    {
      person_id: id,
      name: "Owner",
      email: "owner@example.test",
      role: "owner",
      is_manager: true,
      other_tenancy_count: 0,
      leaves_directory: true,
    },
    {
      person_id: "22222222-2222-4222-8222-222222222222",
      name: "Member",
      email: "member@example.test",
      role: "member",
      is_manager: false,
      other_tenancy_count: 1,
      leaves_directory: false,
    },
  ],
  manager_warning: true,
  shared_warning: true,
};

// Every test owns an isolated cache and API stubs; no operator session or database is used.
function mount() {
  const read = vi.spyOn(api, "deletionPreview").mockResolvedValue(preview);
  const write = vi.spyOn(api, "deleteTenancy").mockResolvedValue({
    operation_id: id,
    state: "queued",
    provider_mode: "simulated",
    accepted_at: "2026-10-31T12:00:00Z",
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const expired = vi.fn(),
    navigate = vi.fn(),
    onClose = vi.fn();
  const rendered = render(
    <QueryClientProvider client={client}>
      <DeleteTenancy
        tenancyId={id}
        expired={expired}
        navigate={navigate}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { ...rendered, client, read, write, expired, navigate, onClose };
}

describe("Whole-tenancy deletion preview", () => {
  // The affected set and separate other-tenancy/directory consequences are visible before consent.
  it("lists all affected people, requires consent and submits a bounded command", async () => {
    const c = mount();
    await screen.findByText("Owner", { selector: "strong" });
    expect(
      screen.getByText("Member", { selector: "strong" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Tenancy deletion never removes an employee/)).toBeInTheDocument();
    expect(screen.getAllByText(/Employee directory status is unchanged/)).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Initiate termination" }),
    ).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(
      screen.getByRole("button", { name: "Initiate termination" }),
    );
    expect(
      await screen.findByText("Termination requested"),
    ).toBeInTheDocument();
    expect(c.write).toHaveBeenCalledWith(
      expect.objectContaining({
        tenancy_id: id,
        confirm_deletion: true,
        confirm_manager: true,
        confirm_shared: true,
      }),
      expect.any(AbortSignal),
    );
    await userEvent.click(screen.getByRole("link", { name: "View operation" }));
    expect(c.navigate).toHaveBeenCalledWith("/operations/" + id);
    expect(c.onClose).toHaveBeenCalled();
  });

  // Read failures discard actionable affordances and fresh previews always clear previous consent.
  it.each([401, 403, 503])(
    "handles denied or unavailable previews (%s)",
    async (status) => {
      const c = mount();
      await screen.findByRole("checkbox");
      c.read.mockRejectedValueOnce(new ApiError(status));
      await userEvent.click(
        screen.getByRole("button", { name: "Reload preview" }),
      );
      await screen.findByText(/This tenancy cannot currently be deleted/);
      expect(
        screen.getByRole("button", { name: "Initiate termination" }),
      ).toBeDisabled();
      if (status !== 503) expect(c.expired).toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
      expect(c.onClose).toHaveBeenCalled();
    },
  );

  // Unchanged retries use the same UUID and never echo provider/database failure details.
  it("preserves request identity after uncertainty and clears consent on reload", async () => {
    const c = mount();
    c.write.mockRejectedValue(new Error("private failure"));
    await userEvent.click(await screen.findByRole("checkbox"));
    await userEvent.click(
      screen.getByRole("button", { name: "Initiate termination" }),
    );
    await screen.findByText(/Termination could not be confirmed/);
    await userEvent.click(
      screen.getByRole("button", { name: "Initiate termination" }),
    );
    await waitFor(() => expect(c.write).toHaveBeenCalledTimes(2));
    expect(c.write.mock.calls[0][0].client_request_key).toBe(
      c.write.mock.calls[1][0].client_request_key,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Reload preview" }),
    );
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    c.write.mockRejectedValueOnce(new ApiError(403));
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(
      screen.getByRole("button", { name: "Initiate termination" }),
    );
    await waitFor(() => expect(c.expired).toHaveBeenCalled());
  });
});

// A background affected-set refresh cannot reuse consent given to a different preview context.
it("requires fresh confirmation when the preview context changes", async () => {
  const c = mount();
  await userEvent.click(await screen.findByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "Initiate termination" }),
  ).toBeEnabled();
  c.client.setQueryData(["tenancy-deletion", id], {
    ...preview,
    context: { ...preview.context, registry_revision: 2 },
  });
  await waitFor(() => expect(screen.getByRole("checkbox")).not.toBeChecked());
  expect(
    screen.getByRole("button", { name: "Initiate termination" }),
  ).toBeDisabled();
});

// Browser Back and a different tenancy require a fresh explicit Delete click, never a carried modal.
it("closes deletion on inventory navigation and does not open it for the next tenancy", async () => {
  vi.spyOn(api, "deletionPreview").mockResolvedValue(preview);
  vi.spyOn(api, "tenancy").mockImplementation(async (identifier) => ({
    tenancy: { ...preview.tenancy, id: identifier },
    people: [],
    memberships: [],
    compartment_parents: [],
  }));
  vi.spyOn(api, "tenancies").mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pages: 1,
    page_size: 10,
    total_tenancies: 0,
    individual_count: 0,
    shared_count: 0,
    pending_count: 0,
    issue_count: 0,
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const expired = vi.fn(),
    navigate = vi.fn();
  const wrap = (identifier: string | null) => (
    <QueryClientProvider client={client}>
      <Tenancies
        identifier={identifier}
        expired={expired}
        navigate={navigate}
      />
    </QueryClientProvider>
  );
  const page = render(wrap(id));
  await userEvent.click(
    await screen.findByRole("button", { name: "Delete tenancy" }),
  );
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  page.rerender(wrap(null));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  page.rerender(wrap("22222222-2222-4222-8222-222222222222"));
  await screen.findByRole("button", { name: "Delete tenancy" });
  expect(screen.queryByRole("dialog")).toBeNull();
});
