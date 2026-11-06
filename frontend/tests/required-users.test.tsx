import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { RequiredUsers } from "../src/RequiredUsers";
import { api, ApiError } from "../src/api";
import type { RequiredUsersDirectory } from "../src/contracts";

const id = "11111111-1111-4111-8111-111111111111";
const directory: RequiredUsersDirectory = {
  tenancy_id: id, tenancy_status: "active", provider_mode: "simulated",
  users: ["automation", "recovery"].map(purpose => ({
    purpose, identity_state: "recorded", identity: {
      user_name: "otm-" + purpose, user_ocid: "ocid1.user.oc1..otmsim" + purpose,
      scim_resource_id: purpose + "-scim", domain_ocid: "ocid1.domain.oc1..otmsimdomain",
      recorded_at: "2026-11-06T12:00:00Z", retired_at: null, source_operation_id: id,
    },
  })) as RequiredUsersDirectory["users"],
};

// Each case owns its cache; no data is borrowed from the operator's saved workspace.
function mount(value: RequiredUsersDirectory | Promise<RequiredUsersDirectory> = directory) {
  const read = vi.spyOn(api, "requiredUsers").mockImplementation(() => Promise.resolve(value));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const expired = vi.fn(), navigate = vi.fn();
  const result = render(<QueryClientProvider client={client}><RequiredUsers tenancyId={id} expired={expired} navigate={navigate}/></QueryClientProvider>);
  return { ...result, client, read, expired, navigate };
}

// Identity details remain collapsed, neutral and useful without asserting live access health.
it("shows both identities and contextual setup links", async () => {
  const c = mount();
  await screen.findByText("otm-automation");
  expect(screen.getAllByText("Recorded", { exact: true })).toHaveLength(2);
  expect(screen.getAllByText("Not checked", { exact: true })).toHaveLength(2);
  expect(screen.queryByText(/healthy|verified|missing/i)).not.toBeInTheDocument();
  const card = screen.getByRole("heading", { name: "Automation user" }).closest("li")!;
  const details = card.querySelector("details")!;
  expect(details.open).toBe(false);
  await userEvent.click(within(card).getByText("Identity details"));
  expect(details.open).toBe(true);
  expect(within(card).getByText("automation-scim")).toBeVisible();
  expect(within(card).getByText(/11\/6\/2026/)).toBeVisible();
  await userEvent.click(within(card).getByRole("link", { name: "View setup operation" }));
  expect(c.navigate).toHaveBeenCalledWith("/operations/" + id);
  c.client.clear();
});

// A successful absent registry result does not fabricate a missing OCI user or display fake details.
it("shows genuine unbound records and explicit pending context", async () => {
  const c = mount({ ...directory, tenancy_status: "pending", users: directory.users.map(u => ({...u, identity: null, identity_state: "not_recorded"})) as RequiredUsersDirectory["users"] });
  await screen.findByText(/Setup is still in progress/);
  expect(screen.getAllByText("Not recorded")).toHaveLength(4);
  expect(screen.queryByText("Identity details")).not.toBeInTheDocument();
  expect(screen.queryByText(/missing/i)).not.toBeInTheDocument();
  c.client.clear();
});

// Termination retains account evidence without claiming OCI deletion, and timestamps remain inspectable.
it("shows retired records as retained history", async () => {
  const c = mount({ ...directory, tenancy_status: "terminated", users: directory.users.map(u => ({...u, identity_state: "retired", identity: {...u.identity!, retired_at: "2026-11-06T16:00:00Z"}})) as RequiredUsersDirectory["users"] });
  await screen.findByText(/retained for tenancy history/);
  expect(screen.getAllByText("Retired record")).toHaveLength(2);
  await userEvent.click(screen.getAllByText("Identity details")[0]);
  expect(within(screen.getByRole("heading", { name: "Automation user" }).closest("li")!).getByText("Record retired (UTC)")).toBeVisible();
  c.client.clear();
});

// Loading never becomes an empty success; busy refresh preserves the existing records.
it("keeps loading and refresh states honest", async () => {
  let complete!: (value: RequiredUsersDirectory) => void;
  const c = mount(new Promise(resolve => { complete = resolve; }));
  expect(screen.getByRole("status")).toHaveTextContent("Loading required user records");
  expect(screen.queryByText("Not recorded")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Loading records…" })).toBeDisabled();
  complete(directory); await screen.findByText("otm-recovery");
  let refresh!: (value: RequiredUsersDirectory) => void;
  c.read.mockReturnValueOnce(new Promise(resolve => { refresh = resolve; }));
  await userEvent.click(screen.getByRole("button", { name: "Refresh records" }));
  expect(screen.getByRole("button", { name: "Refreshing records…" })).toBeDisabled();
  expect(screen.getByText("otm-recovery")).toBeVisible();
  refresh(directory); await screen.findByRole("button", { name: "Refresh records" }); c.client.clear();
});

// A failed read offers retry and never synthesizes unregistered accounts from a network error.
it("distinguishes initial failure and a failed refresh of retained records", async () => {
  const c = mount(Promise.reject(new Error("private")));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load");
  expect(screen.queryByText("Not recorded")).not.toBeInTheDocument();
  c.read.mockResolvedValue(directory);
  await userEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("otm-automation");
  c.read.mockRejectedValueOnce(new Error("private"));
  await userEvent.click(screen.getByRole("button", { name: "Refresh records" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Previously loaded records are shown");
  expect(screen.getByText("otm-automation")).toBeVisible();
  expect(screen.queryByText("private")).not.toBeInTheDocument(); c.client.clear();
});

// Revoked or expired sessions leave authorization handling to the application's existing boundary.
it.each([401, 403])("expires access after %s", async status => {
  const c = mount(Promise.reject(new ApiError(status)));
  await waitFor(() => expect(c.expired).toHaveBeenCalled()); c.client.clear();
});

// Switching children never displays another tenant's retained identity record while the new GET waits.
it("isolates each tenancy's query cache", async () => {
  const c = mount(); await screen.findByText("otm-automation");
  c.read.mockReturnValueOnce(new Promise(() => {}));
  c.rerender(<QueryClientProvider client={c.client}><RequiredUsers tenancyId="22222222-2222-4222-8222-222222222222" expired={c.expired} navigate={c.navigate}/></QueryClientProvider>);
  expect(screen.queryByText("otm-automation")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Loading"); c.client.clear();
});


// Expired authority hides retained facts immediately while the parent closes the private session.
it("does not retain visible records after a denied refresh", async () => {
  const c = mount(); await screen.findByText("otm-automation");
  c.read.mockRejectedValueOnce(new ApiError(403));
  await userEvent.click(screen.getByRole("button", { name: "Refresh records" }));
  await waitFor(() => expect(c.expired).toHaveBeenCalled());
  expect(screen.queryByText("otm-automation")).not.toBeInTheDocument(); c.client.clear();
});
