import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { AuditHistory } from "../src/AuditHistory";
import { api, ApiError } from "../src/api";
import type { AuditDirectory } from "../src/contracts";

const directory: AuditDirectory = {
  items: [
    {
      id: "11111111-1111-4111-8111-111111111111",
      at: "2026-10-30T12:00:00Z",
      kind: "audit_export",
      category: "administration",
      actor_name: "Example operator",
      operation_id: null,
      administrator_id: "22222222-2222-4222-8222-222222222222",
      administrator_name: "Example operator",
      safe_code: null,
    },
  ],
  total: 21,
  page: 1,
  pages: 3,
  page_size: 10,
};

// Each scenario has a private query cache; exported bytes never become query data.
function mount(expired = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return {
    ...render(
      <QueryClientProvider client={client}>
        <AuditHistory expired={expired} navigate={vi.fn()} />
      </QueryClientProvider>,
    ),
    client,
    expired,
  };
}

// Model the browser's transient download handle without navigating jsdom to a blob URL.
function downloadSupport() {
  const create = vi.fn().mockReturnValue("blob:synthetic-download");
  const revoke = vi.fn();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: create,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revoke,
  });
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  return { create, revoke, click };
}

describe("Audit UTC range and CSV export", () => {
  // Explicit UTC inputs yield half-open UTC filters; invalid ordering cannot issue a read/export.
  it("applies UTC date filters, holds invalid ranges, and clears the complete filter set", async () => {
    const read = vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
    mount();
    await screen.findByText("Audit export prepared");
    fireEvent.change(screen.getByLabelText("From (UTC)"), {
      target: { value: "2026-10-01T03:30" },
    });
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({
          from_at: "2026-10-01T03:30:00.000Z",
          to_at: null,
          page: 1,
        }),
        expect.any(AbortSignal),
      ),
    );
    fireEvent.change(screen.getByLabelText("Before (UTC)"), {
      target: { value: "2026-11-01T00:00" },
    });
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ to_at: "2026-11-01T00:00:00.000Z" }),
        expect.any(AbortSignal),
      ),
    );
    const count = read.mock.calls.length;
    fireEvent.change(screen.getByLabelText("Before (UTC)"), {
      target: { value: "2026-09-30T00:00" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "From must be earlier than Before",
    );
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
    expect(read).toHaveBeenCalledTimes(count);
    fireEvent.change(screen.getByLabelText("Before (UTC)"), {
      target: { value: "2026-10-01T03:30" },
    });
    expect(screen.getByLabelText("Before (UTC)")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(read).toHaveBeenCalledTimes(count);
    await userEvent.click(
      screen.getByRole("button", { name: "Clear filters" }),
    );
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({
          from_at: null,
          to_at: null,
          query: "",
          category: "",
        }),
        expect.any(AbortSignal),
      ),
    );
    expect(screen.getByLabelText("From (UTC)")).toHaveValue("");
    expect(screen.getByLabelText("Before (UTC)")).toHaveValue("");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // The browser permits five-digit years despite max; invalid typed values retain safe prior results.
  it.each(["From (UTC)", "Before (UTC)"])(
    "handles an out-of-range year in %s without sending it or crashing",
    async (field) => {
      const read = vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
      const exported = vi.spyOn(api, "exportAudit");
      mount();
      await screen.findByText("Audit export prepared");
      const count = read.mock.calls.length;
      const input = screen.getByLabelText(field);
      fireEvent.change(input, { target: { value: "10000-01-01T00:00" } });
      expect(input).toHaveValue("10000-01-01T00:00");
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Enter valid UTC dates between years 0001 and 9999",
      );
      expect(screen.getByText("Audit export prepared")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
      expect(read).toHaveBeenCalledTimes(count);
      expect(exported).not.toHaveBeenCalled();
      await userEvent.click(
        screen.getByRole("button", { name: "Clear filters" }),
      );
      expect(input).toHaveValue("");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "Export CSV" }),
        ).toBeEnabled(),
      );
    },
  );

  // Download all matching records with bounded controls, not only the current table page.
  it("downloads one uncached CSV with current filters and releases its object URL", async () => {
    const read = vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
    const content = new Blob(["id,at\r\nsynthetic,2026-10-30T12:00:00Z\r\n"], {
      type: "text/csv",
    });
    const exported = vi.spyOn(api, "exportAudit").mockResolvedValue(content);
    const browser = downloadSupport();
    const { client } = mount();
    await screen.findByText("Audit export prepared");
    await userEvent.selectOptions(
      screen.getByLabelText("Category"),
      "administration",
    );
    await userEvent.type(screen.getByRole("searchbox"), "Example");
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "Example" }),
        expect.any(AbortSignal),
      ),
    );
    fireEvent.change(screen.getByLabelText("From (UTC)"), {
      target: { value: "2026-10-01T00:00" },
    });
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ from_at: "2026-10-01T00:00:00.000Z" }),
        expect.any(AbortSignal),
      ),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Page 3" }),
    );
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 3 }),
        expect.any(AbortSignal),
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Export CSV" })).toBeEnabled(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(
      await screen.findByText(
        "Export prepared. Your browser download has started.",
      ),
    ).toBeInTheDocument();
    expect(exported).toHaveBeenCalledWith(
      {
        category: "administration",
        query: "Example",
        sort: "at",
        direction: "desc",
        from_at: "2026-10-01T00:00:00.000Z",
        to_at: null,
      },
      expect.any(AbortSignal),
    );
    expect(browser.create).toHaveBeenCalledWith(content);
    expect(browser.click.mock.instances[0]).toHaveProperty(
      "download",
      "audit-history.csv",
    );
    expect(browser.revoke).toHaveBeenCalledWith("blob:synthetic-download");
    expect(document.querySelector("a[download]")).toBeNull();
    expect(
      client
        .getQueryCache()
        .getAll()
        .some((query) => query.state.data instanceof Blob),
    ).toBe(false);
  });

  // Same-tick repeated clicks cannot prepare duplicate downloads or orphan transient URLs.
  it("prevents duplicate preparation and restores controls after a failed browser download", async () => {
    vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
    let resolve!: (blob: Blob) => void;
    const exported = vi.spyOn(api, "exportAudit").mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const browser = downloadSupport();
    browser.click.mockImplementation(() => {
      throw new Error("browser refused");
    });
    mount();
    await screen.findByText("Audit export prepared");
    const button = screen.getByRole("button", { name: "Export CSV" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(exported).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Preparing export…" }),
    ).toBeDisabled();
    await act(async () => resolve(new Blob(["id\r\nsynthetic"])));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to export audit history",
    );
    expect(browser.revoke).toHaveBeenCalledWith("blob:synthetic-download");
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeEnabled();
  });

  // Expiration clears authority; large/service failures stay generic and never create a partial file.
  it.each([401, 403, 413, 503])(
    "handles export status %s without exposing response text",
    async (status) => {
      vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
      vi.spyOn(api, "exportAudit").mockRejectedValue(new ApiError(status));
      const browser = downloadSupport();
      const { expired } = mount();
      await screen.findByText("Audit export prepared");
      await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
      if (status === 401 || status === 403)
        await waitFor(() => expect(expired).toHaveBeenCalled());
      else
        expect(await screen.findByRole("alert")).toHaveTextContent(
          status === 413
            ? "Narrow the date range"
            : "Unable to export audit history",
        );
      expect(browser.create).not.toHaveBeenCalled();
      if (status > 403) expect(expired).not.toHaveBeenCalled();
    },
  );

  // Navigation/logout aborts an in-flight request and refuses even a late resolved or failed download.
  it.each(["resolved", "rejected"])(
    "abandons an export %s after the page unmounts",
    async (outcome) => {
      vi.spyOn(api, "auditHistory").mockResolvedValue(directory);
      let settle!: (value: Blob) => void;
      let reject!: (value: unknown) => void;
      const exported = vi.spyOn(api, "exportAudit").mockImplementation(
        () =>
          new Promise((done, failed) => {
            settle = done;
            reject = failed;
          }),
      );
      const browser = downloadSupport();
      const view = mount();
      await screen.findByText("Audit export prepared");
      await userEvent.click(screen.getByRole("button", { name: "Export CSV" }));
      const signal = exported.mock.calls[0][1]!;
      view.unmount();
      expect(signal.aborted).toBe(true);
      await act(async () => {
        if (outcome === "resolved") settle(new Blob(["synthetic"]));
        else reject(new ApiError(401));
      });
      expect(browser.create).not.toHaveBeenCalled();
      expect(view.expired).not.toHaveBeenCalled();
    },
  );
});
