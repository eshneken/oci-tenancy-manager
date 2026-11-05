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
import { Organization } from "../src/Organization";
import { App } from "../src/App";
import { api, ApiError, CsvUploadError } from "../src/api";
import type {
  OrganizationDirectory,
  OrganizationQuery,
} from "../src/contracts";

const row = {
  id: "11111111-1111-4111-8111-111111111111",
  full_name: "O'Connor <script>literal</script>",
  email: "engineer@example.test",
  manager_name: "Manager",
  leader_name: "Leader",
  lob_name: "Business Applications",
  absence_review: true,
};
const directory: OrganizationDirectory = {
  configured: true,
  upload_enabled: true,
  server_time: "2026-10-30T12:00:00Z",
  items: [
    row,
    {
      ...row,
      id: "22222222-2222-4222-8222-222222222222",
      full_name: "Other",
      email: "other@example.test",
      manager_name: null,
      leader_name: null,
      lob_name: null,
      absence_review: false,
    },
  ],
  total: 26,
  employee_count: 26,
  absence_count: 1,
  page: 1,
  pages: 3,
  page_size: 10,
  applied_at: "2026-10-30T12:00:00Z",
  source_as_of: "2026-10-30T11:59:00Z",
  absence_eligible: true,
  latest: null,
  findings: [
    {
      category: "actionable",
      code: "PERSON_ABSENCE_REVIEW",
      employee_name: "Employee",
      email: row.email,
      detail: "Review absence",
      at: "2026-10-30T12:00:00Z",
    },
    {
      category: "change",
      code: "METADATA_UPDATED",
      employee_name: "Changed employee",
      email: "changed@example.test",
      detail: "Manager updated automatically.",
      at: "2026-10-30T12:00:00Z",
    },
  ],
};
const outcome = {
  snapshot_id: "33333333-3333-4333-8333-333333333333",
  state: "published" as const,
};

// Every test gets an isolated private query cache; no browser persistence is configured.
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

// Simulate server-owned paging while preserving the actual sort/filter request for assertions.
async function readPage(query: OrganizationQuery) {
  return { ...directory, page: query.page ?? 1 };
}

// Exercise real controls and literal text, without relying on a mocked table implementation.
describe("Organization screens", () => {
  // Directory controls keep the server authoritative and do not render employee strings as HTML.
  it("renders searchable sortable paginated directory and drift navigation", async () => {
    const read = vi.spyOn(api, "organization").mockImplementation(readPage);
    const navigate = vi.fn();
    const { container } = mount(
      <Organization drift={false} expired={vi.fn()} navigate={navigate} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading organization",
    );
    expect(await screen.findByText(row.full_name)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("Unmapped")).toBeInTheDocument();
    expect(screen.getByText(/Complete census qualified/)).toHaveTextContent(
      "UTC",
    );
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /Employee/ }));
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "full_name", direction: "desc" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /Email/ }));
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: "email", direction: "asc" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.type(screen.getByRole("searchbox"), "O'Connor");
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "O'Connor", page: 1 }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Organization rows per page"),
      "25",
    );
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ page_size: 25 }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText(/Page 2 of 3/);
    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await screen.findByText(/Page 1 of 3/);
    await userEvent.click(
      screen.getByRole("link", { name: /View organization drift/ }),
    );
    expect(navigate).toHaveBeenCalledWith("/organization/drift");
  });

  // Tabs separate current actionable issues from source warnings and latest metadata changes.
  it("shows drift tabs and safe intake diagnostics without fake action buttons", async () => {
    vi.spyOn(api, "organization").mockResolvedValue({
      ...directory,
      latest: {
        ...outcome,
        state: "rejected",
        diagnostics: [
          {
            code: "GRAPH_CYCLE",
            affected_email: "source@example.test",
            fatal: true,
          },
        ],
      },
    });
    mount(<Organization drift expired={vi.fn()} navigate={vi.fn()} />);
    expect(await screen.findByText("Review absence")).toBeInTheDocument();
    expect(screen.getByText(/GRAPH CYCLE/)).toBeInTheDocument();
    expect(screen.getByText(/Feed not applied/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Delete|Resolve|Create tenancy/ }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Informational & changes/ }),
    );
    expect(screen.getByText("Changed employee")).toBeInTheDocument();
    expect(screen.queryByText("Review absence")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Actionable/ }));
    expect(screen.getByText("Review absence")).toBeInTheDocument();
  });

  // Empty, unconfigured and filtered results offer accurate guidance without a clean/reset bypass.
  it("distinguishes empty states, no matches, incomplete census and unconfigured source", async () => {
    const read = vi.spyOn(api, "organization").mockResolvedValue({
      ...directory,
      configured: false,
      upload_enabled: false,
      items: [],
      total: 0,
      employee_count: 0,
      findings: [],
      applied_at: null,
    });
    const mounted = mount(
      <Organization drift={false} expired={vi.fn()} navigate={vi.fn()} />,
    );
    expect(
      await screen.findByText("No organization feed loaded"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Upload organization CSV" }),
    ).toBeDisabled();
    await userEvent.type(screen.getByRole("searchbox"), "missing");
    expect(
      await screen.findByText("No employees match your search"),
    ).toBeInTheDocument();
    mounted.unmount();
    read.mockResolvedValue({
      ...directory,
      findings: [],
      absence_eligible: false,
    });
    mount(<Organization drift expired={vi.fn()} navigate={vi.fn()} />);
    expect(
      await screen.findByText("No actionable organization drift"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Absence checks not qualified/),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Informational & changes/ }),
    );
    expect(screen.getByText("No informational changes")).toBeInTheDocument();
  });

  // A failed read remains distinct from an empty organization; current authorization loss ends the view.
  it("recovers read errors and expires denied sessions", async () => {
    const read = vi
      .spyOn(api, "organization")
      .mockRejectedValue(new Error("offline"));
    const expired = vi.fn();
    const mounted = mount(
      <Organization drift={false} expired={expired} navigate={vi.fn()} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Organization could not be loaded",
    );
    read.mockResolvedValue(directory);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText(row.full_name);
    read.mockRejectedValue(new ApiError(403));
    await mounted.client.invalidateQueries({ queryKey: ["organization"] });
    await waitFor(() => expect(expired).toHaveBeenCalled());
  });

  // Every new dialog starts a fresh acquisition and requires a server-defaulted explicit UTC attestation.
  it("uploads a complete feed, resets new upload inputs and permits safe cancel", async () => {
    vi.spyOn(api, "organization").mockResolvedValue(directory);
    const upload = vi
      .spyOn(api, "uploadOrganization")
      .mockResolvedValue(outcome);
    mount(<Organization drift={false} expired={vi.fn()} navigate={vi.fn()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Upload organization CSV" }),
    );
    await screen.findByRole("dialog");
    expect(screen.getByLabelText("Organization data as of (UTC)")).toHaveValue(
      "2026-10-30T12:00",
    );
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose an organization CSV",
    );
    const file = new File(
      ["EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nName,name@example.test,,"],
      "org.csv",
      { type: "text/csv" },
    );
    await userEvent.upload(screen.getByLabelText("Organization CSV"), file);
    await userEvent.click(
      screen.getByLabelText("This file contains the complete organization"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(
      await screen.findByText(/Organization feed processed/),
    ).toBeInTheDocument();
    expect(upload).toHaveBeenCalledWith(
      file,
      "2026-10-30T12:00:00.000Z",
      expect.any(String),
      false,
      expect.any(AbortSignal),
    );
    const firstKey = upload.mock.calls[0][2];
    await userEvent.click(
      screen.getByRole("button", { name: "Upload organization CSV" }),
    );
    await screen.findByRole("dialog");
    expect(
      screen.getByLabelText("This file contains the complete organization"),
    ).toBeChecked();
    await userEvent.upload(screen.getByLabelText("Organization CSV"), file);
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload.mock.calls[1][2]).not.toEqual(firstKey);
    await userEvent.click(
      screen.getByRole("button", { name: "Upload organization CSV" }),
    );
    await screen.findByRole("dialog");
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { cancelable: true }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // File size is checked locally while server checks remain authoritative for content and graph validity.
  it("bounds files, shows safe parser errors and preserves request keys for exact retries", async () => {
    vi.spyOn(api, "organization").mockResolvedValue(directory);
    const upload = vi
      .spyOn(api, "uploadOrganization")
      .mockRejectedValue(
        new CsvUploadError(400, "Duplicate employee email at line 3."),
      );
    mount(<Organization drift={false} expired={vi.fn()} navigate={vi.fn()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Upload organization CSV" }),
    );
    await screen.findByRole("dialog");
    const file = new File(["x"], "org.csv", { type: "text/csv" });
    Object.defineProperty(file, "size", { value: 2 * 1024 * 1024 + 1 });
    fireEvent.change(screen.getByLabelText("Organization CSV"), {
      target: { files: [file] },
    });
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(screen.getByRole("alert")).toHaveTextContent("2 MiB");
    expect(upload).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Organization CSV"), {
      target: { files: [new File(["bad"], "org.csv", { type: "text/csv" })] },
    });
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Duplicate employee",
    );
    upload.mockRejectedValue(new Error("offline"));
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Retry here with unchanged inputs",
    );
    expect(upload.mock.calls[0][2]).toEqual(upload.mock.calls[1][2]);
    fireEvent.change(screen.getByLabelText("Organization data as of (UTC)"), {
      target: { value: "2026-10-30T11:00" },
    });
    upload.mockResolvedValue({ ...outcome, state: "rejected" });
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(await screen.findByText(/Feed was not applied/)).toBeInTheDocument();
    expect(upload.mock.calls[2][2]).not.toEqual(upload.mock.calls[0][2]);
  });

  // Pending uploads cannot masquerade as cancelled work; leaving the route aborts private transport.
  it("blocks dismiss during processing, aborts on unmount and handles auth failure", async () => {
    vi.spyOn(api, "organization").mockResolvedValue(directory);
    let reject!: (value: unknown) => void;
    const upload = vi.spyOn(api, "uploadOrganization").mockImplementation(
      () =>
        new Promise((_resolve, fail) => {
          reject = fail;
        }),
    );
    const expired = vi.fn();
    const mounted = mount(
      <Organization drift={false} expired={expired} navigate={vi.fn()} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Upload organization CSV" }),
    );
    await screen.findByRole("dialog");
    await userEvent.upload(
      screen.getByLabelText("Organization CSV"),
      new File(["x"], "org.csv", { type: "text/csv" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { cancelable: true }),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await act(async () => reject(new ApiError(401)));
    expect(expired).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Process feed" }));
    const signal = upload.mock.calls.at(-1)![4]!;
    mounted.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => reject(new Error("late")));
  });

  // Main navigation enables the production routes and removes their cached data after logout.
  it("routes Organization and drift through the common shell and clears organization data", async () => {
    vi.spyOn(api, "session").mockResolvedValue({
      workspace_id: "test",
      display_name: "Admin",
      expires_at: "2099-01-01",
    });
    vi.spyOn(api, "organization").mockResolvedValue(directory);
    vi.spyOn(api, "logout").mockResolvedValue();
    history.replaceState(null, "", "/organization");
    const mounted = mount(<App />);
    expect(
      await screen.findByRole("heading", { name: "Organization" }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("link", { name: "Organization drift" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Organization drift" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Organization" }));
    expect(
      await screen.findByRole("heading", { name: "Organization" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await screen.findByRole("heading", { name: "Sign in" });
    expect(
      mounted.client.getQueriesData({ queryKey: ["organization"] }),
    ).toEqual([]);
  });
});

// Raw bytes never become JSON or URL arguments, and only known parser failures expose fixed guidance.
describe("Organization transport", () => {
  // Verify literal query encoding, bounded CSV guidance and status-only errors for unexpected failures.
  it("posts CSV headers/body and preserves safe error classification", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => directory,
    });
    vi.stubGlobal("fetch", fetch);
    await api.organization({
      page: 1,
      page_size: 10,
      sort: "full_name",
      direction: "asc",
      query: "' OR 1=1",
    });
    expect(fetch.mock.calls[0][0]).toContain("query=%27+OR+1%3D1");
    const file = new File(["x"], "org.csv");
    await api.uploadOrganization(file, directory.server_time, "delivery", true);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/organization/feeds",
      expect.objectContaining({
        body: file,
        headers: expect.objectContaining({
          "Content-Type": "text/csv",
          "X-OTM-Request": "1",
          "X-OTM-Complete": "true",
        }),
      }),
    );
    for (const status of [400, 413]) {
      fetch.mockResolvedValue({
        ok: false,
        status,
        json: async () => ({
          code: "INVALID_CSV",
          message: "Invalid name or email at line 2.",
        }),
      });
      await expect(
        api.uploadOrganization(file, directory.server_time, "delivery", true),
      ).rejects.toBeInstanceOf(CsvUploadError);
    }
    fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ code: "OTHER", message: "private" }),
    });
    await expect(
      api.uploadOrganization(file, directory.server_time, "delivery", true),
    ).rejects.toBeInstanceOf(ApiError);
    fetch.mockResolvedValue({ ok: false, status: 503 });
    await expect(
      api.uploadOrganization(file, directory.server_time, "delivery", true),
    ).rejects.toMatchObject({ status: 503 });
  });
});

// The development control explains an operator command; it never submits destructive HTTP work.
describe("Local organization reset instructions", () => {
  // Hide by default and allow dismissal/refresh only when the server explicitly enables the control.
  it("shows local reset guidance without executing a reset request", async () => {
    const read = vi
      .spyOn(api, "organization")
      .mockResolvedValue({ ...directory, test_reset_enabled: true });
    mount(<Organization drift={false} expired={vi.fn()} navigate={vi.fn()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Reset test organization" }),
    );
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "--confirm-reset-organization",
    );
    expect(
      screen.getByRole("heading", { name: "Reset test organization" }),
    ).toHaveFocus();
    expect(screen.getByRole("dialog")).toHaveTextContent(
      '--directory "/absolute/path/to/this/installation"',
    );
    expect(
      screen.getByText(/This control does not execute the command/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Reset test organization" }),
    );
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { cancelable: true }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Reset test organization" }),
    );
    const before = read.mock.calls.length;
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh organization" }),
    );
    await waitFor(() => expect(read.mock.calls.length).toBeGreaterThan(before));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
