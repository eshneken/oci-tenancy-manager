import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {it,expect,vi} from "vitest";
import {ConfigurationRepair} from "../src/ConfigurationRepair";
import {api,ApiError} from "../src/api";
import type {ConfigurationCheckSummary,ConfigurationPreview,ConfigurationProgress} from "../src/contracts";
const id="11111111-1111-4111-8111-111111111111", op="22222222-2222-4222-8222-222222222222";
const summary:ConfigurationCheckSummary={tenancy_id:id,tenancy_name:"Example tenancy",baseline_id:id,baseline_version_number:3,override_categories:[],state:"drifted",checked_at:"2026-11-06T00:00:00Z",issue_count:2,confirmed_issue_count:2,stale:false,can_check:true,pending_operation_id:null,last_operation_id:null,categories:[{category:"policy",state:"different",safe_code:"DIFFERENT",binding_ocid:null,expected:null,observed:null,evidence_at:null},{category:"quota",state:"missing",safe_code:"MISSING",binding_ocid:null,expected:null,observed:null,evidence_at:null}]};
const preview:ConfigurationPreview={baseline:{id,version_number:3} as NonNullable<ConfigurationPreview["baseline"]>,tenancy_id:id,ready_count:1,pending_count:0,blockers:[],conflicts:[],repair_expected:{policy:'{"statements":["Allow expected"]}',quota:'{"statements":["set quota"]}'},repair_observed:{policy:'{"statements":["Allow previous"]}',quota:null},preview_hash:"1".repeat(64)};
// Render the real modal with isolated request/cache state and synthetic display values.
function mount(value=summary){
 const read=vi.spyOn(api,"previewConfigurationRepair").mockResolvedValue(preview);
 const start=vi.spyOn(api,"startConfigurationUpdate").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:"2026-11-06T00:00:00Z"});
 const progress=vi.spyOn(api,"configurationProgress").mockResolvedValue({state:"succeeded",change_kind:"repair",operation_id:op,targets:[],baseline:{} as ConfigurationProgress["baseline"],can_retry:false});
 const expired=vi.fn(),navigate=vi.fn();
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
 const invalidate=vi.spyOn(client,"invalidateQueries");
 render(<QueryClientProvider client={client}><ConfigurationRepair summary={value} expired={expired} navigate={navigate}/></QueryClientProvider>);
 return {read,start,progress,expired,navigate,invalidate};
}
it("previews exact selected categories, confirms and refreshes consistent views",async()=>{
 const c=mount(),user=userEvent.setup();
 await user.click(screen.getByRole("button",{name:"Repair configuration"}));
 expect(screen.getByRole("dialog")).toHaveAttribute("open");
 await user.click(screen.getByRole("checkbox",{name:/Quota statements/}));
 await user.click(screen.getByRole("button",{name:"Preview repair"}));
 expect(c.read.mock.calls[0][0]).toEqual({tenancy_id:id,categories:["policy"]});
 await screen.findByRole("heading",{name:"Confirm configuration repair"});
 await user.click(screen.getByRole("button",{name:"Repair selected objects"}));
 expect(c.start.mock.calls[0][0]).toMatchObject({tenancy_id:id,repair_categories:["policy"],preview_hash:preview.preview_hash});
 await screen.findByText(/Selected objects verified/);
 expect(c.invalidate).toHaveBeenCalledWith({queryKey:["tenancies"]});
 await user.click(screen.getByRole("link",{name:"View operation"}));expect(c.navigate).toHaveBeenCalledWith("/operations/"+op);
});
it("supports empty selection, back, cancel and focus restoration",async()=>{
 mount();const user=userEvent.setup();const launch=screen.getByRole("button",{name:"Repair configuration"});await user.click(launch);
 for(const checkbox of screen.getAllByRole("checkbox"))await user.click(checkbox);
 expect(screen.getByRole("button",{name:"Preview repair"})).toBeDisabled();
 await user.click(screen.getByRole("checkbox",{name:/Policy statements/}));
 await user.click(screen.getByRole("button",{name:"Preview repair"}));await screen.findByRole("heading",{name:"Confirm configuration repair"});
 await user.click(screen.getByRole("button",{name:"Change selection"}));expect(screen.getByRole("checkbox",{name:/Policy statements/})).toBeEnabled();
 await user.click(screen.getByRole("button",{name:"Cancel"}));expect(screen.getByRole("dialog",{hidden:true})).not.toBeVisible();expect(launch).toHaveFocus();
});
it.each([401,403,409,503])("handles guarded preview failure %s without admitting work",async status=>{
 const c=mount();c.read.mockRejectedValue(new ApiError(status));const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Repair configuration"}));await user.click(screen.getByRole("button",{name:"Preview repair"}));
 if(status===401||status===403)await waitFor(()=>expect(c.expired).toHaveBeenCalled());else await screen.findByRole("alert");expect(c.start).not.toHaveBeenCalled();
});
it("retains the exact command on an uncertain response and retries safely",async()=>{
 const c=mount();c.start.mockRejectedValueOnce(new Error("network"));const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Repair configuration"}));await user.click(screen.getByRole("button",{name:"Preview repair"}));await user.click(await screen.findByRole("button",{name:"Repair selected objects"}));await screen.findByRole("alert");await user.click(screen.getByRole("button",{name:"Cancel"}));await user.click(screen.getByRole("button",{name:"Recover repair request"}));expect(screen.queryByRole("button",{name:"Change selection"})).not.toBeInTheDocument();await user.click(screen.getByRole("button",{name:"Retry same request"}));expect(c.start.mock.calls[0][0]).toEqual(c.start.mock.calls[1][0]);
});
it("refreshes failed progress without presenting a completed repair",async()=>{
 const c=mount();c.progress.mockRejectedValueOnce(new Error("network")).mockResolvedValue({state:"needs_attention",change_kind:"repair",operation_id:op,targets:[],baseline:{} as ConfigurationProgress["baseline"],can_retry:false});const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Repair configuration"}));await user.click(screen.getByRole("button",{name:"Preview repair"}));await user.click(await screen.findByRole("button",{name:"Repair selected objects"}));await user.click(await screen.findByRole("button",{name:"Refresh progress"}));await screen.findByText(/Repair could not be verified/);
});
it.each([{...summary,stale:true},{...summary,state:"unavailable" as const},{...summary,can_check:false}])("hides repair without fresh complete available evidence",value=>{mount(value);expect(screen.queryByRole("button",{name:"Repair configuration"})).not.toBeInTheDocument();});

it("blocks a stale or nonready preview instead of presenting a confirm action",async()=>{
 const c=mount();c.read.mockResolvedValue({...preview,ready_count:0});const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Repair configuration"}));await user.click(screen.getByRole("button",{name:"Preview repair"}));await screen.findByRole("heading",{name:"Confirm configuration repair"});expect(screen.getByRole("button",{name:"Repair selected objects"})).toBeDisabled();expect(screen.getByRole("heading",{name:"Confirm configuration repair"})).toHaveFocus();expect(c.start).not.toHaveBeenCalled();
});

// Verify fresh budget/tag evidence, whole-dollar display and escaped text before selected-only admission.
it.each(["budget","tags"] as const)("previews and submits %s values from fresh server evidence",async category=>{
 const issue:ConfigurationCheckSummary["categories"][number]={...summary.categories[0],category};
 const c=mount({...summary,categories:[issue],issue_count:1,confirmed_issue_count:1});
 const expected=category==="budget"?{monthly_amount:"650.0000",currency:"USD",period:"MONTHLY"}:{namespace:"OTM",defaults:[{key:"Environment",value:"Test"}]};
 const observed=category==="budget"?{monthly_amount:"25.0000",currency:"USD",period:"MONTHLY"}:{namespace:"OTM",defaults:[{key:"Environment",value:"Changed <script>unsafe()</script>"}]};
 c.read.mockResolvedValue({...preview,repair_expected:{[category]:JSON.stringify(expected)},repair_observed:{[category]:JSON.stringify(observed)}});
 const user=userEvent.setup();await user.click(screen.getByRole("button",{name:"Repair configuration"}));await user.click(screen.getByRole("button",{name:"Preview repair"}));
 await screen.findByRole("heading",{name:"Confirm configuration repair"});
 const intended=screen.getByRole("heading",{name:"Expected after repair"}).parentElement!.querySelector("pre")!;
 expect(JSON.parse(intended.textContent!)).toEqual({...expected,...(category==="budget"?{monthly_amount:"650"}:{})});
 expect(screen.getByRole("dialog").querySelector("script")).toBeNull();
 await user.click(screen.getByRole("button",{name:"Repair selected objects"}));
 expect(c.start.mock.calls[0][0]).toMatchObject({repair_categories:[category]});expect(c.start.mock.calls[0][0]).not.toHaveProperty("overrides");
});
