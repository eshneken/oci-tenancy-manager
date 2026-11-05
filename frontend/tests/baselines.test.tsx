import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { Baselines } from "../src/Baselines";
import { api, ApiError } from "../src/api";
import type { BaselineDraft, BaselineDirectory } from "../src/contracts";

const draft: BaselineDraft = { id:"11111111-1111-4111-8111-111111111111", version_number:1, edit_revision:1, created_by:"test-actor", created_at:"2026-11-02T12:00:00Z", content_hash:"a".repeat(64), content:{ policy_statements:["Allow example"], quota_statements:["set example quota"], monthly_budget_amount:"200.0000", budget_currency:"USD", budget_period:"MONTHLY", tag_namespace:"OTM", tag_defaults:[{key:"Environment", value:"Test"}] } };

// Render with a private real query cache while replacing only authenticated HTTP calls.
function mount(value: BaselineDirectory = { configured:true }, failure?: ApiError) {
  const read = vi.spyOn(api,"baselines").mockResolvedValue(value);
  if (failure) read.mockRejectedValue(failure);
  const write = vi.spyOn(api,"saveBaselineDraft").mockResolvedValue(draft);
  const expired = vi.fn(), navigate = vi.fn();
  const client = new QueryClient({ defaultOptions:{queries:{retry:false,gcTime:0}} });
  const view=render(<QueryClientProvider client={client}><Baselines expired={expired} navigate={navigate}/></QueryClientProvider>);
  return { ...view,read,write,expired,navigate,client };
}

// Saving preserves the administrator's complete statement boundaries and exact decimal input.
it("creates and reopens newline-separated blocks and static tags", async () => {
  const c=mount();
  await userEvent.click(await screen.findByRole("button",{name:"New baseline"}));
  expect(screen.getByRole("heading",{name:"New baseline draft"})).toHaveFocus();
  fireEvent.change(screen.getByLabelText("Policy statements"),{target:{value:"Allow Example\n\nSecond complete statement\n"}});
  fireEvent.change(screen.getByLabelText("Quota statements"),{target:{value:"set example quota\nsecond quota"}});
  expect(screen.queryByRole("button", {name:"Add policy statement"})).toBeNull();
  fireEvent.change(screen.getByLabelText("Monthly amount"),{target:{value:"500"}});
  fireEvent.change(screen.getByLabelText("Currency code"),{target:{value:"usd"}});
  await userEvent.click(screen.getByRole("button",{name:"Add tag default"}));
  fireEvent.change(screen.getByLabelText("Tag key 1"),{target:{value:"Environment"}});
  fireEvent.change(screen.getByLabelText("Static value 1"),{target:{value:"Test"}});
  await userEvent.click(screen.getByRole("button",{name:"Add tag default"}));
  await userEvent.click(screen.getByRole("button",{name:"Remove tag 2"}));
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText("Baseline draft saved.");
  expect(c.write.mock.calls[0][0]).toMatchObject({ baseline_id:null, expected_revision:null, content:{ monthly_budget_amount:"500",budget_currency:"USD",policy_statements:["Allow Example", "Second complete statement"],quota_statements:["set example quota", "second quota"],tag_namespace:"OTM" } });
  expect(screen.getByRole("heading",{name:"Configuration"})).toHaveFocus();
  await userEvent.click(screen.getByRole("button",{name:"Open draft"}));
  expect(screen.getByRole("textbox", { name: "Policy statements" })).toHaveAttribute("aria-labelledby", "policy_statements-label");
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("200");
  await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
  expect(screen.getByText("Version 1")).toBeInTheDocument();
  c.client.clear();
});

// A stale draft cannot overwrite another administrator's save, and reload is an explicit decision.
it("retains local edits on conflict and blocks editing while reloading", async () => {
  const c=mount({configured:true,draft});
  c.write.mockRejectedValue(new ApiError(409));
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  fireEvent.change(screen.getByLabelText("Monthly amount"),{target:{value:"700"}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText(/This draft changed/);
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("700");
  let finish!: (value: BaselineDirectory)=>void;
  c.read.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  await userEvent.click(screen.getByRole("button",{name:"Reload saved draft"}));
  expect(screen.getByLabelText("Monthly amount")).toBeDisabled();
  expect(screen.getByRole("button",{name:"Saving…"})).toBeDisabled();
  await act(async()=>finish({configured:true,draft:{...draft,edit_revision:2}}));
  await waitFor(()=>expect(screen.getByLabelText("Monthly amount")).toBeEnabled());
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("200");
  c.client.clear();
});

// Failed refreshes keep the local form visible instead of replacing it with an empty successful state.
it("preserves edits when an explicit reload fails and permits a safe retry", async () => {
  const c=mount({configured:true,draft});
  c.write.mockRejectedValue(new ApiError(503));
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  fireEvent.change(screen.getByLabelText("Monthly amount"),{target:{value:"900"}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText(/draft could not be saved/);
  c.read.mockRejectedValue(new ApiError(503));
  await userEvent.click(screen.getByRole("button",{name:"Reload saved draft"}));
  await screen.findByText(/Your edits are retained/);
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("900");
  c.client.clear();
});

// Initial loading/errors and absent setup have concrete recoveries rather than invented recipes.
it("handles failed reads and directs unconfigured workspaces to Organization Mapping", async () => {
  const c=mount({configured:false});
  await userEvent.click(await screen.findByRole("link",{name:"Organization Mapping"}));
  expect(c.navigate).toHaveBeenCalledWith("/organization-mapping");
  c.client.clear(); c.unmount();
  const d=mount({configured:true}, new ApiError(503));
  await screen.findByRole("button",{name:"Retry"});
  d.read.mockResolvedValue({configured:true});
  await userEvent.click(screen.getByRole("button",{name:"Retry"}));
  await screen.findByText("No baseline draft yet");
  expect(d.read).toHaveBeenCalled(); d.client.clear();
});

// Unknown baseline links never edit the workspace's first draft as a substitute.
it("shows unavailable targets and keeps explicit navigation safe", async () => {
  history.replaceState(null,"","/configuration?baseline=unknown");
  const c=mount({configured:true,draft});
  await userEvent.click(await screen.findByRole("link",{name:"Return to Configuration"}));
  expect(c.navigate).toHaveBeenCalledWith("/configuration");
  expect(screen.queryByRole("button",{name:"Edit draft"})).toBeNull();
  c.client.clear();
});

// A denied save/read leaves the common privileged session boundary authoritative.
it.each([401,403])("expires authoring after denied access %s", async status => {
  const c=mount({configured:true,draft}); c.write.mockRejectedValue(new ApiError(status));
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await waitFor(()=>expect(c.expired).toHaveBeenCalled());
  c.read.mockRejectedValue(new ApiError(status));
  await c.client.invalidateQueries({queryKey:["baselines"]});
  await waitFor(()=>expect(c.expired).toHaveBeenCalledTimes(2));
  c.client.clear();
});


// Desktop paste formats normalize to the same ordered arrays while nonblank text stays literal.
it.each(["\n", "\r\n", "\r"])("converts pasted block separators %j at save", async separator => {
  const c=mount({configured:true,draft});
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  fireEvent.change(screen.getByLabelText("Policy statements"),{target:{value:["Allow <literal>", " ", "  Second statement  ", ""].join(separator)}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText("Baseline draft saved.");
  expect(c.write.mock.calls[0][0].content.policy_statements).toEqual(["Allow <literal>", "  Second statement  "]);
  c.client.clear();
});

// Oversized or empty blocks stay visible with actionable feedback and never reach the save API.
it.each(["   ", Array(51).fill("One statement").join("\n"), "x".repeat(2001)])("rejects invalid block limits without discarding edits", async block => {
  const c=mount({configured:true,draft});
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  fireEvent.change(screen.getByLabelText("Policy statements"),{target:{value:block}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter 1–50 statements");
  expect(screen.getByLabelText("Policy statements")).toHaveValue(block);
  expect(c.write).not.toHaveBeenCalled();
  c.client.clear();
});


// Whole stored budgets display without decimal padding; fractional input never rounds on save.
it("displays whole amounts and rejects fractional budget authoring", async () => {
  const c=mount({configured:true,draft});
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("200");
  expect(screen.getByLabelText("Monthly amount")).toHaveAttribute("inputmode", "numeric");
  fireEvent.change(screen.getByLabelText("Monthly amount"), {target:{value:"250.50"}});
  fireEvent.submit(screen.getByRole("button",{name:"Save draft"}).closest("form")!);
  expect(await screen.findByRole("alert")).toHaveTextContent("without cents");
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("250.50");
  expect(c.write).not.toHaveBeenCalled();
  c.client.clear();
});

// Legacy fractional drafts stay readable until an explicit whole-value correction is saved.
it("retains a legacy fractional value without silently rounding it", async () => {
  const c=mount({configured:true,draft:{...draft,content:{...draft.content,monthly_budget_amount:"250.5000"}}});
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("250.5000");
  fireEvent.change(screen.getByLabelText("Monthly amount"), {target:{value:"251"}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText("Baseline draft saved.");
  expect(c.write.mock.calls[0][0].content.monthly_budget_amount).toBe("251");
  c.client.clear();
});


// Both complete blocks accept the new boundary without changing line order or truncating entries.
it("saves fifty policy and fifty quota statements", async () => {
  const c=mount({configured:true,draft});
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  const policies=Array.from({length:50},(_,i)=>`Allow statement ${i+1}`);
  const quotas=Array.from({length:50},(_,i)=>`Set quota ${i+1}`);
  fireEvent.change(screen.getByLabelText("Policy statements"),{target:{value:policies.join("\n")}});
  fireEvent.change(screen.getByLabelText("Quota statements"),{target:{value:quotas.join("\n")}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText("Baseline draft saved.");
  expect(c.write.mock.calls[0][0].content.policy_statements).toEqual(policies);
  expect(c.write.mock.calls[0][0].content.quota_statements).toEqual(quotas);
  c.client.clear();
});


// Quota overflow receives the same visible guard as policy overflow and never sends a request.
it("rejects fifty-one quota statements", async () => {
  const c=mount({configured:true,draft});
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  fireEvent.change(screen.getByLabelText("Quota statements"),{target:{value:Array(51).fill("Set quota").join("\n")}});
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter 1–50 statements");
  expect(c.write).not.toHaveBeenCalled();
  c.client.clear();
});
