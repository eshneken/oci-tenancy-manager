import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { it, expect, vi } from "vitest";
import { NavigationCount } from "../src/NavigationCount";
import { api, ApiError } from "../src/api";

const operations = { items: [], total: 0, page: 1, page_size: 10, pages: 1, attention_count: 2 };
const reviews = { items: [], total: 4, page: 1, page_size: 10, pages: 1, actionable_count: 4, history_count: 200 };

// Render only the authenticated navigation child with a private cache that real invalidations affect.
function mount(kind: "operations" | "organization", expired = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const view = render(<QueryClientProvider client={client}><NavigationCount kind={kind} expired={expired} /></QueryClientProvider>);
  return { ...view, client, expired };
}

// The operation count comes from global action-needed states, not this list's page or total.
it("shows operation attention count and updates after an operation invalidation", async () => {
  const read = vi.spyOn(api, "operations").mockResolvedValue(operations);
  const c = mount("operations");
  await screen.findByText("2");
  expect(screen.getByText("2")).toHaveAttribute("title", "2 operations requiring administrator action");
  read.mockResolvedValue({ ...operations, attention_count: 0 });
  await act(async () => { await c.client.invalidateQueries({ queryKey: ["operations"] }); });
  await waitFor(() => expect(c.container.querySelector(".nav-count")).toBeNull());
  expect(screen.getByText("0 operations requiring administrator action")).toHaveClass("sr-only");
  c.client.clear();
});

// An old history count must never inflate the current organizational work badge.
it("counts actionable reviews only and refreshes after organization changes", async () => {
  const read = vi.spyOn(api, "organizationReviews").mockResolvedValue(reviews);
  const c = mount("organization");
  await screen.findByText("4");
  expect(screen.queryByText("200")).toBeNull();
  read.mockResolvedValue({ ...reviews, actionable_count: 1 });
  await act(async () => { await c.client.invalidateQueries({ queryKey: ["organization-reviews"] }); });
  await screen.findByText("1");
  c.client.clear();
});

// No unavailable count is presented as zero, and stale positive evidence is clearly described.
it("hides an unavailable initial count and identifies stale retained data", async () => {
  const read = vi.spyOn(api, "operations").mockRejectedValue(new ApiError(503));
  const c = mount("operations");
  await screen.findByText("Count unavailable");
  expect(c.container.querySelector(".nav-count")).toBeNull();
  read.mockResolvedValue(operations);
  await act(async () => { await c.client.invalidateQueries({ queryKey: ["operations"] }); });
  await screen.findByText("2");
  read.mockRejectedValue(new ApiError(503));
  await act(async () => { await c.client.invalidateQueries({ queryKey: ["operations"] }); });
  await screen.findByText("2 operations requiring administrator action (last known count)");
  expect(c.expired).not.toHaveBeenCalled();
  c.client.clear();
});

// Denied reads end the privileged view through the existing application session boundary.
it.each([401, 403])("expires the private badge after denied read %s", async (status) => {
  vi.spyOn(api, "organizationReviews").mockRejectedValue(new ApiError(status));
  const c = mount("organization");
  await waitFor(() => expect(c.expired).toHaveBeenCalled());
  c.client.clear();
});

// Switching pages must observe a worker transition without opening Operations or waiting for polling.
it("refreshes operation counts immediately when the route changes", async () => {
  const read = vi.spyOn(api, "operations").mockResolvedValue({ ...operations, attention_count: 0 });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const expired = vi.fn();
  const view = render(<QueryClientProvider client={client}><NavigationCount kind="operations" navigationRevision={0} expired={expired} /></QueryClientProvider>);
  await screen.findByText("0 operations requiring administrator action");
  read.mockResolvedValue({ ...operations, attention_count: 3 });
  view.rerender(<QueryClientProvider client={client}><NavigationCount kind="operations" navigationRevision={1} expired={expired} /></QueryClientProvider>);
  await screen.findByText("3");
  expect(read).toHaveBeenCalledTimes(2);
  client.clear();
});

// Worker progress must also appear while an administrator stays on a different page.
it("observes a later worker state on the five-second fallback without navigation", async () => {
  vi.useFakeTimers();
  const read = vi.spyOn(api, "operations").mockResolvedValue({ ...operations, attention_count: 0 });
  const c = mount("operations");
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(screen.getByText("0 operations requiring administrator action")).toBeInTheDocument();
  read.mockResolvedValue({ ...operations, attention_count: 2 });
  await act(async () => { await vi.advanceTimersByTimeAsync(5_001); });
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(read).toHaveBeenCalledTimes(2);
  c.client.clear();
});
