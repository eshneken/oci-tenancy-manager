import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {expect,it,vi} from "vitest";
import {TenancyOverride} from "../src/TenancyOverride";
import {OverrideChooser} from "../src/OverrideChooser";
import {api,ApiError} from "../src/api";
import type {OverrideEditor,ConfigurationPreview,TenancyDirectory} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",op="22222222-2222-4222-8222-222222222222",baseline="33333333-3333-4333-8333-333333333333",time="2026-11-03T12:00:00Z";
const editor:OverrideEditor={tenancy_id:id,tenancy_name:"Example shared child",tenancy_revision:3,configuration:null,can_edit:true,values:{policy_override_statements:null,quota_override_statements:null,monthly_budget_override_amount:null},baseline:{id:baseline,version_number:1,edit_revision:2,created_by:"test",created_at:time,published_at:time,published_by:"test",published_by_name:"Example administrator",publication_mode:"simulated",content_hash:"a".repeat(64),content:{policy_statements:["Old baseline policy"],quota_statements:["Old baseline quota"],monthly_budget_amount:"200.0000",budget_currency:"USD"}}};
const preview:ConfigurationPreview={tenancy_id:id,baseline:editor.baseline,ready_count:1,pending_count:0,blockers:[],preview_hash:"b".repeat(64)};

// Exercise real forms/query behavior with only the authenticated transport boundary substituted.
function mount(data:OverrideEditor=editor,chooser=false){
 const read=vi.spyOn(api,"overrideEditor").mockResolvedValue(data),inspect=vi.spyOn(api,"previewOverride").mockResolvedValue(preview),apply=vi.spyOn(api,"applyOverride").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:time});
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}}),navigate=vi.fn(),expired=vi.fn();
 const view=render(<QueryClientProvider client={client}>{chooser?<OverrideChooser expired={expired} navigate={navigate}/>:<TenancyOverride tenancyId={id} expired={expired} navigate={navigate}/>}</QueryClientProvider>);
 return {...view,read,inspect,apply,client,navigate,expired};
}

// Independent replacements retain the assigned version and preview exactly what the admin entered.
it("copies assigned blocks and previews independent replacement values before queuing",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));
 await screen.findByText("Example shared child");
 expect(screen.getByRole("link",{name:"baseline v1"})).toHaveAttribute("target","_blank");
 await userEvent.click(screen.getByRole("checkbox",{name:"Override policy statements"}));
 expect(screen.getByRole("textbox",{name:"Policy statement override"})).toHaveValue("Old baseline policy");
 fireEvent.change(screen.getByRole("textbox",{name:"Policy statement override"}),{target:{value:"Allow replacement one\n\nAllow replacement two"}});
 await userEvent.click(screen.getByRole("checkbox",{name:"Override monthly budget"}));
 expect(screen.getByRole("textbox",{name:"Monthly budget override (USD)"})).toHaveValue("200");
 fireEvent.change(screen.getByRole("textbox",{name:"Monthly budget override (USD)"}),{target:{value:"500"}});
 await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));
 await screen.findByRole("heading",{name:"Review override changes"});
 expect(c.inspect.mock.calls[0][0]).toMatchObject({tenancy_id:id,context:{tenancy_revision:3,baseline_version_id:baseline,configuration_id:null},values:{policy_override_statements:["Allow replacement one","Allow replacement two"],quota_override_statements:null,monthly_budget_override_amount:"500"}});
 expect(c.apply).not.toHaveBeenCalled();
 await userEvent.click(screen.getByRole("button",{name:"Back to editing"}));
 expect(screen.getByRole("textbox",{name:"Monthly budget override (USD)"})).toHaveValue("500");
 await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));
 await userEvent.click(await screen.findByRole("button",{name:"Apply overrides"}));
 await waitFor(()=>expect(c.navigate).toHaveBeenCalledWith("/tenancies/"+id));
 expect(c.apply.mock.calls[0][0]).toMatchObject({override_mode:true,tenancy_id:id,override_context:{baseline_version_id:baseline,tenancy_revision:3},preview_hash:preview.preview_hash});
 expect(screen.queryByRole("dialog")).toBeNull();c.client.clear();
});

// Disabling existing overrides inherits the assigned baseline; it never submits an empty statement list.
it("clears all three overrides to null without deleting managed objects",async()=>{
 const data={...editor,values:{policy_override_statements:["Existing policy"],quota_override_statements:["Existing quota"],monthly_budget_override_amount:"750.0000"}} as OverrideEditor;
 const c=mount(data);await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));await screen.findByText("Example shared child");
 for(const name of ["Override policy statements","Override quota statements","Override monthly budget"]){const checkbox=screen.getByRole("checkbox",{name});expect(checkbox).toBeChecked();await userEvent.click(checkbox);}
 await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));
 await screen.findByRole("button",{name:"Apply overrides"});
 expect(c.inspect.mock.calls[0][0].values).toEqual({policy_override_statements:null,quota_override_statements:null,monthly_budget_override_amount:null});
 expect(screen.getByText("200 USD · Inherited")).toBeVisible();
 fireEvent(screen.getByRole("dialog"),new Event("cancel",{bubbles:true,cancelable:true}));
 expect(c.apply).not.toHaveBeenCalled();c.client.clear();
});

// Boundary validation blocks fractional/zero budgets and oversized statement lists before admission.
it("rejects invalid amounts and statement counts while retaining editable input",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));await screen.findByText("Example shared child");
 await userEvent.click(screen.getByRole("checkbox",{name:"Override monthly budget"}));
 for(const amount of ["0","12.5"]){fireEvent.change(screen.getByRole("textbox",{name:"Monthly budget override (USD)"}),{target:{value:amount}});await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));expect(screen.getByRole("alert")).toHaveTextContent("positive whole");}
 await userEvent.click(screen.getByRole("checkbox",{name:"Override monthly budget"}));
 await userEvent.click(screen.getByRole("checkbox",{name:"Override quota statements"}));
 for(const text of [Array(51).fill("Quota").join("\n"),"x".repeat(2001),"   "]){fireEvent.change(screen.getByRole("textbox",{name:"Quota statement override"}),{target:{value:text}});await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));expect(screen.getByRole("alert")).toHaveTextContent("1–50 complete statements");}
 expect(c.inspect).not.toHaveBeenCalled();await userEvent.click(screen.getByRole("button",{name:"Cancel"}));c.client.clear();
});

// A failed read can be retried, while ineligible registrations expose no enabled mutation control.
it("recovers unavailable reads and blocks an ineligible editor",async()=>{
 const c=mount();c.read.mockRejectedValue(new ApiError(503));await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));
 await screen.findByRole("alert");c.read.mockResolvedValue({...editor,can_edit:false});await userEvent.click(screen.getByRole("button",{name:"Retry"}));
 await screen.findByText("Example shared child");expect(screen.getByRole("button",{name:"Preview changes"})).toBeDisabled();expect(screen.getByRole("checkbox",{name:"Override monthly budget"})).toBeDisabled();
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));c.client.clear();
});

// A stale editor requires explicit reload; a lost acceptance response reuses the same request key.
it("retains failed previews, reloads explicitly and retries an uncertain apply safely",async()=>{
 const c=mount();c.inspect.mockRejectedValue(new ApiError(409));await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));await screen.findByText("Example shared child");
 await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));await screen.findByRole("alert");
 c.read.mockResolvedValue({...editor,tenancy_revision:5});c.inspect.mockResolvedValue(preview);await userEvent.click(screen.getByRole("button",{name:"Reload configuration"}));await screen.findByText("Example shared child");
 await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));c.apply.mockRejectedValue(new ApiError(503));
 await userEvent.click(await screen.findByRole("button",{name:"Apply overrides"}));expect(await screen.findByRole("alert")).toHaveTextContent("could not be confirmed");
 const key=c.apply.mock.calls[0][0].client_request_key;
 c.apply.mockRejectedValue(new ApiError(409));await userEvent.click(screen.getByRole("button",{name:"Apply overrides"}));await waitFor(()=>expect(c.apply).toHaveBeenCalledTimes(2));expect(c.apply.mock.calls[1][0].client_request_key).toBe(key);
 expect(screen.getByRole("alert")).toHaveTextContent("assigned configuration changed");await userEvent.click(screen.getByRole("button",{name:"Cancel"}));c.client.clear();
});

// Denied reads or commands expire privilege rather than converting to a successful empty editor.
it.each(["read","preview","apply"])("expires on %s authorization denial",async phase=>{
 const c=mount();if(phase==="read")c.read.mockRejectedValue(new ApiError(403));if(phase==="preview")c.inspect.mockRejectedValue(new ApiError(403));if(phase==="apply")c.apply.mockRejectedValue(new ApiError(403));
 await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));
 if(phase!=="read"){await screen.findByText("Example shared child");await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));if(phase==="apply")await userEvent.click(await screen.findByRole("button",{name:"Apply overrides"}));}
 await waitFor(()=>expect(c.expired).toHaveBeenCalled());c.client.clear();
});

// Saved child URLs open the editor directly; busy previews cannot be accepted or silently cleared.
it("opens a saved override URL and blocks a busy preview",async()=>{
 history.replaceState(null,"","/tenancies/"+id+"?override=1");
 const c=mount();c.inspect.mockResolvedValue({...preview,ready_count:0,blockers:[{tenancy_id:id,name:editor.tenancy_name,code:"TENANCY_BUSY",operation_id:op}]});
 await screen.findByText("Example shared child");await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));
 expect(await screen.findByRole("button",{name:"Apply overrides"})).toBeDisabled();
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));expect(c.navigate).toHaveBeenCalledWith("/tenancies/"+id);c.client.clear();
});

// The configuration entry uses bounded paging/search and excludes unavailable active-work targets.
it("chooses a child from the configuration dashboard and preserves route identity",async()=>{
 const row={id,name:"Selectable child",owner_name:"Example owner",kind:"shared",status:"active",baseline_version_id:baseline,has_pending_operation:false};
 const data={items:[row],total:1,page:1,pages:2,page_size:10,total_tenancies:1,individual_count:0,shared_count:1,pending_count:0,issue_count:0} as TenancyDirectory;
 const read=vi.spyOn(api,"tenancies").mockImplementation(async query=>({...data,page:query.page??1}));
 const c=mount(editor,true);await userEvent.click(screen.getByRole("button",{name:"Create tenancy override"}));await screen.findByText("Selectable child");
 await userEvent.type(screen.getByRole("searchbox",{name:"Search tenancies"}),"child");await userEvent.click(screen.getByRole("button",{name:"Next"}));await screen.findByText("Page 2 of 2");
 await userEvent.click(screen.getByRole("button",{name:"Previous"}));await screen.findByText("Page 1 of 2");
 await userEvent.click(screen.getByRole("button",{name:"Choose"}));expect(c.navigate).toHaveBeenCalledWith("/tenancies/"+id+"?override=1");
 expect(read).toHaveBeenCalledWith(expect.objectContaining({query:"child"}),expect.any(AbortSignal));c.client.clear();
});

// Empty/error/denied chooser states provide recovery instead of selecting another arbitrary child.
it("handles chooser errors, ineligible records and cancellation",async()=>{
 const read=vi.spyOn(api,"tenancies").mockRejectedValue(new ApiError(503));const c=mount(editor,true);
 await userEvent.click(screen.getByRole("button",{name:"Create tenancy override"}));await screen.findByRole("alert");
 read.mockResolvedValue({items:[],total:0,page:1,pages:1,page_size:10,total_tenancies:0,individual_count:0,shared_count:0,pending_count:0,issue_count:0});await userEvent.click(screen.getByRole("button",{name:"Retry"}));await screen.findByText("No tenancies match this search.");
 read.mockRejectedValue(new ApiError(403));await act(async()=>{await c.client.invalidateQueries({queryKey:["tenancies"]});});await waitFor(()=>expect(c.expired).toHaveBeenCalled());
 fireEvent(screen.getByRole("dialog"),new Event("cancel",{bubbles:true,cancelable:true}));expect(c.navigate).not.toHaveBeenCalled();c.client.clear();
});

// Browser route changes reopen and close explicit editor links without remounting the tenancy.
it("synchronizes explicit override links across browser history changes",async()=>{
 history.replaceState(null,"","/tenancies/"+id+"?override=1");
 const c=mount();await screen.findByText("Example shared child");
 const draw=()=>c.rerender(<QueryClientProvider client={c.client}><TenancyOverride tenancyId={id} expired={c.expired} navigate={c.navigate}/></QueryClientProvider>);
 history.replaceState(null,"","/tenancies/"+id);draw();
 await waitFor(()=>expect(screen.getByRole("dialog",{hidden:true})).not.toHaveAttribute("open"));
 history.replaceState(null,"","/tenancies/"+id+"?override=1");draw();
 await waitFor(()=>expect(screen.getByRole("dialog")).toHaveAttribute("open"));
 await screen.findByText("Example shared child");
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
 expect(c.navigate).toHaveBeenCalledWith("/tenancies/"+id);c.client.clear();
});

// Final review exposes exact resolved statement blocks and inherited tags before any apply call.
it("shows resolved effective blocks and provenance in the confirmation",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Manage overrides"}));await screen.findByText("Example shared child");
 await userEvent.click(screen.getByRole("button",{name:"Preview changes"}));
 await screen.findByRole("heading",{name:"Review override changes"});
 await userEvent.click(screen.getByText("Effective policy statements · Assigned baseline"));
 expect(screen.getByText("Old baseline policy",{exact:true})).toBeVisible();
 await userEvent.click(screen.getByText("Tag defaults · Assigned baseline"));
 expect(screen.getByText("No tag defaults.",{exact:true})).toBeVisible();expect(c.apply).not.toHaveBeenCalled();c.client.clear();
});
