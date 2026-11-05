import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { OrganizationMapping } from "../src/OrganizationMapping";
import { api, ApiError } from "../src/api";
import type {
  MappingSettings,
  MappingPreview,
  OrganizationDirectory,
} from "../src/contracts";

const id = "11111111-1111-4111-8111-111111111111";
const saved: MappingSettings = {
  configured: true,
  available: true,
  root_editable: false,
  has_feed: true,
  blockers: [],
  context: {
    configuration_id: id,
    applied_version_id: id,
    proposed_version_id: id,
    registry_revision: 1,
  },
  candidate: {
    root_email: "root@example.test",
    root_name: null,
    segments: [
      {
        id: "one",
        label: "Industry One",
        leader_email: "one@example.test",
        designee_emails: ["delegate@example.test"],
      },
    ],
  },
  roles: [],
};
const checked: MappingPreview = {
  root_before: "root@example.test",
  root_name_before: null,
  root_present: true,
  unresolved_count: 0,
  context: saved.context,
  candidate: saved.candidate!,
  preview_token: "a".repeat(64),
  changes: [
    {
      segment_id: "one",
      before: saved.candidate!.segments[0],
      after: saved.candidate!.segments[0],
    },
  ],
  roles: [],
  affected_count: 1,
  unassigned_count: 0,
  items: [
    {
      person_id: id,
      name: "Engineer",
      email: "engineer@example.test",
      before_ancestry: "resolved",
      after_ancestry: "resolved",
      before_segment: "Industry One",
      after_segment: "Changed",
      before_leader: null,
      after_leader: "one@example.test",
      before_designees: [],
      after_designees: ["delegate@example.test"],
    },
  ],
  page: 1,
  pages: 2,
  blockers: [],
  has_feed: true,
};

// Render real controls and query lifecycles while isolating only the authenticated HTTP boundary.
function mount(settings = saved, segmentId?: string) {
  const read = vi.spyOn(api, "mapping").mockResolvedValue(settings);
  const preview = vi
    .spyOn(api, "previewMapping")
    .mockImplementation(async (body, page) => ({
      ...checked,
      context: body.context,
      candidate: body.candidate,
      page: page ?? 1,
    }));
  const apply = vi.spyOn(api, "applyMapping").mockResolvedValue(saved);
  vi.spyOn(api, "organization").mockResolvedValue({
    items: [{ id, full_name: "Engineer", email: "engineer@example.test" }],
  } as OrganizationDirectory);
  const expired = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const rendered = render(
    <QueryClientProvider client={client}>
      <OrganizationMapping expired={expired} segmentId={segmentId} />
    </QueryClientProvider>,
  );
  return { read, preview, apply, expired, client, ...rendered };
}

describe("Organization Mapping", () => {
  // Every edit invalidates the previous preview; cancel reloads saved values without a write.
  it("previews normalized editable fields and applies only the exact server candidate", async () => {
    const c = mount(saved, "one");
    const name = await screen.findByLabelText("Segment name");
    await waitFor(() => expect(name).toHaveFocus());
    expect(screen.getByLabelText("Root manager email")).toHaveAttribute(
      "readonly",
    );
    fireEvent.change(name, { target: { value: "Changed" } });
    fireEvent.change(screen.getByLabelText("Find designee for segment 1"), {
      target: { value: "suggested@example.test" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Add designee" }));
    expect(screen.getByLabelText("Designee emails (optional)")).toHaveValue(
      "delegate@example.test\nsuggested@example.test",
    );
    fireEvent.change(screen.getByLabelText("Designee emails (optional)"), {
      target: { value: "delegate@example.test\nother@example.test" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Preview changes" }),
    );
    await screen.findByRole("dialog", { name: "Mapping change preview" });
    expect(
      c.preview.mock.calls[0][0].candidate.segments[0].designee_emails,
    ).toEqual(["delegate@example.test", "other@example.test"]);
    await userEvent.click(
      screen.getByRole("button", { name: "Back to editing" }),
    );
    fireEvent.change(name, { target: { value: "Edited again" } });
    expect(screen.queryByRole("button", { name: "Apply changes" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Cancel edits" }));
    expect(name).toHaveValue("Industry One");
    await userEvent.click(
      screen.getByRole("button", { name: "Preview changes" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Next impact page" }),
    );
    await screen.findByText("Page 2 of 2");
    await userEvent.click(
      screen.getByRole("button", { name: "Previous impact page" }),
    );
    await screen.findByText("Page 1 of 2");
    await userEvent.click(
      screen.getByRole("button", { name: "Apply changes" }),
    );
    await screen.findByText(/Organization mapping applied/);
    expect(c.apply).toHaveBeenCalledWith(
      expect.objectContaining({
        candidate: saved.candidate,
        preview_token: checked.preview_token,
      }),
      expect.any(AbortSignal),
    );
  });

  // Pre-feed setup uses typed emails and permits optional empty designees, but requires a segment.
  it("supports typed initial setup and editing segment rows without auto-saving", async () => {
    const c = mount({
      ...saved,
      configured: false,
      candidate: null,
      has_feed: false,
      root_editable: true,
      roles: [],
    });
    await userEvent.type(
      await screen.findByLabelText("Root manager email"),
      "root@example.test",
    );
    await userEvent.type(screen.getByLabelText("Segment name"), "First");
    await userEvent.type(
      screen.getByLabelText("Leader email"),
      "one@example.test",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Add industry segment" }),
    );
    fireEvent.change(screen.getAllByLabelText("Segment name")[1], {
      target: { value: "Second" },
    });
    fireEvent.change(screen.getAllByLabelText("Leader email")[1], {
      target: { value: "two@example.test" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Remove segment 2" }),
    );
    expect(
      screen.getByRole("button", { name: "Remove segment 1" }),
    ).toBeDisabled();
    c.preview.mockImplementationOnce(async (body) => ({
      ...checked,
      candidate: body.candidate,
      has_feed: false,
      changes: [
        {
          segment_id: "new",
          before: null,
          after: {
            id: "new",
            label: "New",
            leader_email: "new@example.test",
            designee_emails: [],
          },
        },
      ],
      items: [],
    }));
    await userEvent.click(
      screen.getByRole("button", { name: "Preview changes" }),
    );
    await screen.findByText(
      "Employee impact cannot be calculated until the first feed.",
    );
    expect(c.apply).not.toHaveBeenCalled();
  });

  // A request finishing after an edit cannot enable Apply for now-different values.
  it("discards an in-flight stale preview", async () => {
    const c = mount();
    let finish!: (value: MappingPreview) => void;
    c.preview.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Preview changes" }),
    );
    fireEvent.change(screen.getByLabelText("Segment name"), {
      target: { value: "New edit" },
    });
    finish(checked);
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Apply changes" }),
      ).toBeNull(),
    );
  });

  // Failed/uncertain writes retain edited values and require a fresh read before another preview.
  it("preserves edits and refreshes after an uncertain Apply", async () => {
    const c = mount();
    c.apply.mockRejectedValueOnce(new ApiError(503));
    fireEvent.change(await screen.findByLabelText("Segment name"), {
      target: { value: "Keep me" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Preview changes" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Apply changes" }),
    );
    await screen.findByText(/Your edits are retained/);
    expect(screen.getByLabelText("Segment name")).toHaveValue("Keep me");
    expect(
      screen.getByRole("button", { name: "Preview changes" }),
    ).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh saved settings" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Preview changes" }),
      ).toBeEnabled(),
    );
  });

  // Role warnings are separate per segment/role and include absent/no-tenancy/excluded profiles.
  it("shows all role health causes and blocks Apply for pending work", async () => {
    const roles: MappingSettings["roles"] = [
      "departed",
      "excluded",
      "profile_missing",
      "ancestry_incomplete",
      "branch_changed",
      "not_verified",
    ].map((status, i) => ({
      segment_id: "one",
      segment_name: "Industry One",
      role: i % 2 ? "designee" : "leader",
      email: `person${i}@example.test`,
      status: status as MappingSettings["roles"][number]["status"],
    }));
    const c = mount({ ...saved, roles });
    c.preview.mockResolvedValueOnce({
      ...checked,
      blockers: ["PENDING_LIFECYCLE"],
      changes: [
        {
          segment_id: "one",
          before: saved.candidate!.segments[0],
          after: null,
        },
      ],
      items: [
        {
          ...checked.items[0],
          after_segment: null,
          after_leader: null,
          after_designees: [],
        },
      ],
    });
    await screen.findAllByText("Industry One: Leader needs attention");
    await userEvent.click(
      screen.getByRole("button", { name: "Preview changes" }),
    );
    expect(
      await screen.findByRole("button", { name: "Apply changes" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/A tenancy workflow is unsettled/),
    ).toBeInTheDocument();
  });

  // Read and command authorization failures close the privileged screen without echoing diagnostics.
  it.each([401, 403, 400, 409])(
    "handles a rejected preview safely (%s)",
    async (status) => {
      const c = mount();
      c.preview.mockRejectedValueOnce(new ApiError(status));
      await userEvent.click(
        await screen.findByRole("button", { name: "Preview changes" }),
      );
      if (status === 401 || status === 403)
        await waitFor(() => expect(c.expired).toHaveBeenCalled());
      else await screen.findByRole("alert");
    },
  );

  // Missing operator policy and read failures retain an explicit retry with no implicit seeding.
  it("shows unavailable setup and retries failed reads", async () => {
    const c = mount({ ...saved, available: false });
    expect(
      await screen.findByRole("button", { name: "Preview changes" }),
    ).toBeDisabled();
    c.read.mockRejectedValueOnce(new ApiError(503));
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh saved settings" }),
    );
    await screen.findByText("Unable to load saved settings.");
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh saved settings" }),
    );
    await screen.findByRole("button", { name: "Preview changes" });
  });
});

// Uncommitted name searches never invalidate native form submission or migrate to another row.
it("keeps partial designee searches out of the candidate and clears them on cancel/removal", async () => {
  const c = mount();
  const search = await screen.findByLabelText("Find designee for segment 1");
  await userEvent.type(search, "Partial employee name");
  await userEvent.click(
    screen.getByRole("button", { name: "Preview changes" }),
  );
  await screen.findByRole("button", { name: "Apply changes" });
  expect(
    c.preview.mock.calls[0][0].candidate.segments[0].designee_emails,
  ).toEqual(["delegate@example.test"]);
  await userEvent.click(
    screen.getByRole("button", { name: "Back to editing" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Cancel edits" }));
  expect(search).toHaveValue("");
  await userEvent.click(
    screen.getByRole("button", { name: "Add industry segment" }),
  );
  fireEvent.change(screen.getAllByLabelText("Segment name")[1], {
    target: { value: "Second" },
  });
  await userEvent.type(search, "Removed row draft");
  await userEvent.click(
    screen.getByRole("button", { name: "Remove segment 1" }),
  );
  expect(screen.getByLabelText("Find designee for segment 1")).toHaveValue("");
  expect(screen.getByLabelText("Segment name")).toHaveValue("Second");
});

// Review is an isolated dialog; Escape retains the draft and a second preview is required.
it("puts health first and closes preview without discarding edits", async () => {
  mount();
  const leader = await screen.findByLabelText("Leader email");
  expect(leader).not.toHaveAttribute("list");
  const health = screen.getByRole("region", {
    name: "Organization role health",
  });
  expect(
    health.compareDocumentPosition(
      screen.getByRole("heading", { name: "Edit saved mappings" }),
    ) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Segment name"), {
    target: { value: "Retain this draft" },
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Preview changes" }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Mapping change preview",
  });
  expect(dialog).toHaveAttribute("open");
  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByLabelText("Segment name")).toHaveValue(
    "Retain this draft",
  );
  expect(screen.queryByRole("button", { name: "Apply changes" })).toBeNull();
});

// Closing during a write would conceal its outcome; Escape remains disabled until it settles.
it("keeps the preview visible during Apply", async () => {
  const c = mount();
  let finish!: (value: MappingSettings) => void;
  c.apply.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Preview changes" }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Apply changes" }),
  );
  const dialog = screen.getByRole("dialog");
  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(dialog).toHaveAttribute("open");
  expect(
    screen.getByRole("button", { name: "Back to editing" }),
  ).toBeDisabled();
  finish(saved);
  await screen.findByText(/Organization mapping applied/);
  expect(screen.queryByRole("dialog")).toBeNull();
});

// Replacing a saved leader is deliberate and requires review of the boundary change before Apply.
it("changes the organization leader with explicit intent, confirmation and retained drafts", async () => {
  const c = mount();
  const root = await screen.findByLabelText("Root manager email");
  expect(root).toHaveAttribute("readonly");
  await userEvent.click(
    screen.getByRole("button", { name: "Change organization leader" }),
  );
  expect(root).not.toHaveAttribute("readonly");
  expect(root).toHaveFocus();
  fireEvent.change(root, { target: { value: "successor@example.test" } });
  c.preview.mockImplementationOnce(async (body) => ({
    ...checked,
    candidate: body.candidate,
    root_present: false,
    unresolved_count: 5,
    items: [{ ...checked.items[0], after_ancestry: "incomplete" }],
  }));
  c.apply.mockImplementationOnce(async () => {
    const updated = {
      ...saved,
      candidate: { ...saved.candidate!, root_email: "successor@example.test" },
    };
    // A successful server Apply also changes subsequent reads of saved settings.
    c.read.mockResolvedValue(updated);
    return updated;
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Preview changes" }),
  );
  await screen.findByRole("dialog");
  expect(
    screen.getByText(/new leader is not in the latest feed/),
  ).toBeInTheDocument();
  expect(screen.getByText(/5 employees have unresolved/)).toBeInTheDocument();
  expect(
    screen.getByText(
      /Reporting chain: Within organization → Reporting chain incomplete/,
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();
  await userEvent.click(
    screen.getByRole("checkbox", {
      name: /I reviewed this leader replacement/,
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Apply changes" }));
  await screen.findByText(/Organization mapping applied/);
  expect(c.apply.mock.calls[0][0]).toMatchObject({
    change_root: true,
    candidate: { root_email: "successor@example.test" },
  });
  expect(root).toHaveAttribute("readonly");
  expect(root).toHaveValue("successor@example.test");
  await userEvent.click(
    screen.getByRole("button", { name: "Change organization leader" }),
  );
  fireEvent.change(root, { target: { value: "discard@example.test" } });
  await userEvent.click(screen.getByRole("button", { name: "Cancel edits" }));
  expect(root).toHaveAttribute("readonly");
  expect(root).toHaveValue("successor@example.test");
});


// A single deliberate edit control unlocks both root fields and binds name-only changes to preview.
it("edits and previews the root name alongside its email", async () => {
  const c = mount();
  const name = await screen.findByLabelText("Root manager name");
  expect(name).toHaveAttribute("readonly");
  await userEvent.click(screen.getByRole("button", { name: "Change organization leader" }));
  expect(name).not.toHaveAttribute("readonly");
  fireEvent.change(name, { target: { value: "Organization Director" } });
  await userEvent.click(screen.getByRole("button", { name: "Preview changes" }));
  await screen.findByRole("dialog");
  expect(screen.getByLabelText("Organization leader name change")).toHaveTextContent("Organization Director");
  expect(screen.queryByRole("checkbox", {name: /I reviewed this leader replacement/})).toBeNull();
  expect(c.preview).toHaveBeenCalledWith(expect.objectContaining({change_root: true, candidate: expect.objectContaining({root_name: "Organization Director", root_email: "root@example.test"})}), 1, expect.anything());
  await userEvent.click(screen.getByRole("button", { name: "Apply changes" }));
  await waitFor(() => expect(c.apply).toHaveBeenCalledWith(expect.objectContaining({candidate: expect.objectContaining({root_name: "Organization Director"})}), expect.any(AbortSignal)));
});
