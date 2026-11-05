import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { Baselines } from "../src/Baselines";
import { BaselineHistory, PublishedBaseline } from "../src/BaselineHistory";
import { api, ApiError } from "../src/api";
import type { BaselineDirectory, BaselineVersion } from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111";
const draft: BaselineVersion={id,version_number:1,edit_revision:1,created_by:"test",created_at:"2026-11-02T12:00:00Z",content_hash:"a".repeat(64),content:{policy_statements:["Allow example"],quota_statements:["Set example quota"],monthly_budget_amount:"250.0000",budget_currency:"USD",tag_defaults:[{key:"Environment",value:"Test"}]}};
const version: BaselineVersion={...draft,edit_revision:2,published_by:"publisher",published_by_name:"Example administrator",published_at:"2026-11-02T12:01:00Z",publication_mode:"simulated"};

// Use a private authenticated cache while isolating only HTTP at the component boundary.
function mount(data:BaselineDirectory={configured:true,draft,publication_available:true}) {
  const read=vi.spyOn(api,"baselines").mockResolvedValue(data);
  const publish=vi.spyOn(api,"publishBaseline").mockResolvedValue(version);
  const save=vi.spyOn(api,"saveBaselineDraft").mockResolvedValue(draft);
  const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
  const navigate=vi.fn(),expired=vi.fn();
  const view=render(<QueryClientProvider client={client}><Baselines expired={expired} navigate={navigate}/></QueryClientProvider>);
  return {...view,client,read,publish,save,navigate,expired};
}

// Publishing freezes the saved revision; the next draft begins from the latest recipe and parent.
it("publishes with confirmation and clones the latest publication into a fresh draft", async()=>{
  const c=mount();
  c.publish.mockImplementation(async()=>{c.read.mockResolvedValue({configured:true,publication_available:true,latest:version,items:[version],total:1});return version;});
  await userEvent.click(await screen.findByRole("button",{name:"Publish"}));
  await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
  expect(c.publish).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Publish"}));
  await userEvent.click(screen.getByRole("button",{name:"Publish baseline"}));
  await screen.findByText("Baseline v1 published with simulated validation.");
  expect(c.publish.mock.calls[0][0]).toEqual({baseline_id:id,expected_revision:1});
  expect(c.navigate).toHaveBeenCalledWith(`/configuration?baseline=${id}`);
  expect(screen.getByText("Latest published")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button",{name:"New baseline"}));
  expect(screen.getByLabelText("Policy statements")).toHaveValue("Allow example");
  expect(screen.getByLabelText("Monthly amount")).toHaveValue("250");
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByText("Baseline draft saved.");
  expect(c.save.mock.calls[0][0]).toMatchObject({baseline_id:null,expected_revision:null,based_on_id:id});
  c.client.clear();
});

// Published links select a specific immutable version; its values are escaped and never editable.
it("reads exact published snapshots without an edit or apply action", async()=>{
  history.replaceState(null,"",`/configuration?baseline=${id}`);
  const selected={...version,based_on_id:"22222222-2222-4222-8222-222222222222",content:{...version.content,tag_defaults:[{key:"Note",value:"<script>literal</script>"}]}};
  const c=mount({configured:true,selected,latest:selected,items:[selected]});
  await screen.findByRole("heading",{name:"Published baseline v1"});
  expect(screen.getByLabelText("Policy statements")).toHaveAttribute("readonly");
  expect(screen.getByText("250 USD / month")).toBeInTheDocument();
  expect(screen.getByText("<script>literal</script>")).toBeInTheDocument();
  expect(c.container.querySelector("script")).toBeNull();
  expect(screen.queryByRole("button",{name:"Save draft"})).toBeNull();
  await userEvent.click(screen.getByRole("link",{name:"previous published version"}));
  expect(c.navigate).toHaveBeenCalledWith(`/configuration?baseline=${selected.based_on_id}`);
  await userEvent.click(screen.getByRole("link",{name:/Back to baselines/}));
  expect(c.navigate).toHaveBeenLastCalledWith("/configuration");
  expect(c.read.mock.calls[0][1]?.baseline_id).toBe(id);
  c.client.clear();
});

// History paging does not reassign or mutate a version and never substitutes the current page's first row.
it("pages publication history and changes page size through the shared select", async()=>{
  const c=mount({configured:true,items:[version],latest:version,total:22,page:1,pages:3,page_size:10});
  await userEvent.click(await screen.findByRole("button",{name:"Next"}));
  await waitFor(()=>expect(c.read.mock.calls.at(-1)?.[1]?.page).toBe(2));
  await userEvent.selectOptions(screen.getByLabelText("Versions per page"),"50");
  await waitFor(()=>expect(c.read.mock.calls.at(-1)?.[1]).toMatchObject({page:1,page_size:50}));
  await userEvent.click(screen.getByRole("button",{name:"Refresh"}));
  expect(c.read).toHaveBeenCalled();
  c.client.clear();
});

// Publication failure preserves the saved draft and exact revision; outages never imply publication.
it.each([409,400,503])("retains a failed publication for safe recovery (%s)", async status=>{
  const c=mount();c.publish.mockRejectedValue(new ApiError(status));
  await userEvent.click(await screen.findByRole("button",{name:"Publish"}));
  await userEvent.click(screen.getByRole("button",{name:"Publish baseline"}));
  expect(await screen.findByRole("alert")).toHaveTextContent(status===409?"draft changed":status===400?"Local validation failed":"could not be confirmed");
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button",{name:"Open draft"})).toBeInTheDocument();
  c.client.clear();
});

// Busy publication traps modal dismissal and denied access returns to the common session boundary.
it.each([401,403])("blocks double-submit/cancel and expires denied publication %s",async status=>{
  const c=mount();let reject!:(error:ApiError)=>void;
  c.publish.mockReturnValue(new Promise((_,failed)=>{reject=failed;}));
  await userEvent.click(await screen.findByRole("button",{name:"Publish"}));
  await userEvent.click(screen.getByRole("button",{name:"Publish baseline"}));
  expect(screen.getByRole("button",{name:"Cancel"})).toBeDisabled();
  fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await act(async()=>reject(new ApiError(status)));
  await waitFor(()=>expect(c.expired).toHaveBeenCalled());
  c.client.clear();
});

// A successful explicit reload cannot silently keep editing a draft somebody else published.
it("closes a stale editor after publication and retains immutable versions without tags",async()=>{
  const c=mount();c.save.mockRejectedValue(new ApiError(409));
  await userEvent.click(await screen.findByRole("button",{name:"Edit draft"}));
  await userEvent.click(screen.getByRole("button",{name:"Save draft"}));
  await screen.findByRole("alert");c.read.mockResolvedValue({configured:true,latest:version,items:[version]});
  await userEvent.click(screen.getByRole("button",{name:"Reload saved draft"}));
  await screen.findByText(/no longer editable/);
  expect(c.navigate).toHaveBeenCalledWith("/configuration");
  c.client.clear();c.unmount();
  render(<PublishedBaseline version={{...version,content:{...version.content,tag_defaults:[]}}} navigate={vi.fn()}/>);
  expect(screen.getByText("No tag defaults.")).toBeInTheDocument();
});

// Missing host qualification leaves draft editing available without an actionable publish control.
it("disables publishing without a configured qualifier",async()=>{
  const c=mount({configured:true,draft});
  expect(await screen.findByRole("button",{name:"Publish"})).toBeDisabled();
  expect(screen.getByText(/no baseline validator/)).toBeInTheDocument();
  c.client.clear();c.unmount();
  const previous=vi.fn();
  render(<BaselineHistory data={{configured:true,items:[version],page:2,pages:2}} openDraft={vi.fn()} navigate={vi.fn()} expired={vi.fn()} published={vi.fn()} pageChanged={previous} sizeChanged={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button",{name:"Previous"}));
  expect(previous).toHaveBeenCalledWith(1);
});

