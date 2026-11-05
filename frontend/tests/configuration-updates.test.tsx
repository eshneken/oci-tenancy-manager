import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect,it,vi } from "vitest";
import { ConfigurationRollout } from "../src/ConfigurationRollout";
import { PublishedBaseline } from "../src/BaselineHistory";
import { baselineHref,baselineReturn } from "../src/baselineNavigation";
import { api,ApiError } from "../src/api";
import type {BaselineVersion,ConfigurationPreview,ConfigurationProgress,ConfigurationPlanView,OverrideConflict} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",tenant="22222222-2222-4222-8222-222222222222",op="33333333-3333-4333-8333-333333333333";
const time="2026-11-03T12:00:00Z";
const version:BaselineVersion={id,version_number:2,edit_revision:2,created_by:"test",created_at:time,published_by:"test",published_by_name:"Example administrator",published_at:time,publication_mode:"simulated",content_hash:"a".repeat(64),content:{policy_statements:["Allow example"],quota_statements:["Set example"],monthly_budget_amount:"250.0000",budget_currency:"USD"}};
const preview:ConfigurationPreview={baseline:version,tenancy_id:null,ready_count:2,pending_count:1,blockers:[],preview_hash:"b".repeat(64)};
const progress:ConfigurationProgress={operation_id:op,state:"needs_attention",baseline:version,can_retry:true,targets:[{tenancy_id:tenant,name:"Test child",state:"needs_attention",safe_code:"CONFIGURATION_UNVERIFIED"}]};

// Render real query/form behavior while only the authenticated HTTP boundary is substituted.
function mount(data:ConfigurationPreview=preview,props:{tenancyId?:string;selectedId?:string;initialOperationId?:string}={},initialProgress?:ConfigurationProgress,initialPlan?:ConfigurationPlanView){
 const read=vi.spyOn(api,"configurationPreview").mockResolvedValue(data);
 const create=vi.spyOn(api,"createConfigurationPlan").mockResolvedValue({id:tenant,revision:1,state:"draft",preview:data});
 const load=vi.spyOn(api,"configurationPlan").mockResolvedValue(initialPlan??{id:tenant,revision:1,state:"draft",preview:data});
 const stage=vi.spyOn(api,"reviewConfigurationPlan").mockResolvedValue({id:tenant,revision:2,state:"draft",preview:data});
 const start=vi.spyOn(api,"startConfigurationUpdate").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:time});
 const status=vi.spyOn(api,"configurationProgress").mockResolvedValue(initialProgress??{...progress,state:"succeeded",can_retry:false,targets:[{tenancy_id:tenant,name:"Test child",state:"verified",verified_at:time}]});
 const retry=vi.spyOn(api,"retryConfigurationUpdate").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:time});
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
 const expired=vi.fn(),navigate=vi.fn();
 const view=render(<QueryClientProvider client={client}><ConfigurationRollout {...props} expired={expired} navigate={navigate}/></QueryClientProvider>);
 return {...view,client,read,start,status,retry,expired,navigate,create,load,stage};
}

// Bulk start requires an explicit frozen preview; browsing its recipe never mutates assignments.
it("previews the complete batch, returns from recipe with focus and starts async work",async()=>{
 const c=mount();
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));
 const dialog=screen.getByRole("dialog",{name:"Update existing tenancies"});
 expect(within(dialog).getByText("2")).toBeVisible();
 expect(dialog).toHaveTextContent("pending tenancies keep their original setup version");
 await userEvent.click(within(dialog).getByRole("link",{name:"Baseline v2"}));
 expect(screen.getByRole("dialog",{name:"Published baseline v2"})).toBeInTheDocument();
 expect(screen.getByRole("heading",{name:"Published baseline v2"})).toHaveFocus();
 await userEvent.click(screen.getByRole("link",{name:/Back to baseline update/}));
 expect(within(dialog).getByRole("link",{name:"Baseline v2"})).toHaveFocus();
 await userEvent.click(within(dialog).getByRole("button",{name:"Start update"}));
 expect(c.start.mock.calls[0][0]).toMatchObject({tenancy_id:null,preview_hash:preview.preview_hash});
 await screen.findByText(/Verified in simulation/);
 expect(screen.queryByRole("button",{name:"Refresh progress"})).toBeNull();
 expect(screen.getByRole("link",{name:"View operation history"})).toHaveAttribute("href","/operations/"+op);
 await userEvent.click(screen.getByRole("button",{name:"Acknowledge"}));
 expect(screen.queryByRole("region",{name:"Baseline update progress"})).toBeNull();
 expect(c.navigate).toHaveBeenLastCalledWith("/configuration");
 expect(c.navigate).toHaveBeenCalledWith("/configuration?update="+op);
 c.client.clear();
});

// One exception blocks the whole set; this screen never silently starts only the ready subset.
it("blocks the whole batch and permits closing without effects",async()=>{
 const c=mount({...preview,blockers:[{tenancy_id:tenant,name:"Busy child",code:"TENANCY_BUSY",operation_id:op}]});
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));
 expect(screen.getByRole("button",{name:"Start update"})).toBeDisabled();
 expect(screen.getByRole("region",{name:"Update exceptions"})).toHaveTextContent("Busy child");
 fireEvent(screen.getByRole("dialog"),new Event("cancel",{bubbles:true,cancelable:true}));
 expect(screen.queryByRole("dialog")).toBeNull();expect(c.start).not.toHaveBeenCalled();c.client.clear();
});

// Single-tenancy actions identify the new version, preserve scope and leave success to the worker.
it("applies a selected but unverified baseline to exactly one tenancy",async()=>{
 const c=mount({...preview,tenancy_id:tenant,ready_count:1,pending_count:0},{tenancyId:tenant,selectedId:id});
 await userEvent.click(await screen.findByRole("button",{name:"Apply baseline v2"}));
 await userEvent.click(screen.getByRole("button",{name:"Start update"}));
 await waitFor(()=>expect(screen.queryByRole("region",{name:"Tenancy baseline update"})).toBeNull());
 expect(c.start.mock.calls[0][0].tenancy_id).toBe(tenant);expect(c.navigate).not.toHaveBeenCalledWith("/configuration?update="+op);c.client.clear();
});

// A stale context requires explicit re-preview; a transport failure keeps the same idempotency key.
it.each([409,503])("retains preview after start failure %s",async status=>{
 const c=mount();c.start.mockRejectedValue(new ApiError(status));
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));
 await userEvent.click(screen.getByRole("button",{name:"Start update"}));
 expect(await screen.findByRole("alert")).toHaveTextContent(status===409?"set changed":"could not be confirmed");
 const key=c.start.mock.calls[0][0].client_request_key;
 await userEvent.click(screen.getByRole("button",{name:"Start update"}));
 await waitFor(()=>expect(c.start).toHaveBeenCalledTimes(2));
 expect(c.start.mock.calls[1][0].client_request_key).toBe(key);
 await userEvent.click(screen.getByRole("button",{name:"Reload preview"}));
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));c.client.clear();
});

// Progress retains failed targets and offers retry only when the server authorizes the fixed batch.
it("shows failed and pending targets and retries without changing version or targets",async()=>{
 const c=mount(preview,{initialOperationId:op},{...progress,targets:[...progress.targets,{tenancy_id:id,name:"Waiting child",state:"pending"}]});
 await userEvent.click(await screen.findByRole("button",{name:"Retry incomplete updates"}));
 expect(c.retry.mock.calls[0][0]).toBe(op);
 await userEvent.click(screen.getByRole("button",{name:"Refresh progress"}));
 expect(screen.getByText("Pending")).toBeInTheDocument();
 c.retry.mockRejectedValue(new ApiError(503));await userEvent.click(screen.getByRole("button",{name:"Retry incomplete updates"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("Retry could not be confirmed");c.client.clear();
});

// Read failures are truthful, retryable views rather than empty-success states.
it("handles missing baseline, up-to-date scope and unavailable reads",async()=>{
 const c=mount({...preview,baseline:null,ready_count:0});
 await screen.findByText("Publish a baseline to enable updates.");
 c.read.mockResolvedValue({...preview,ready_count:0});await act(async()=>{await c.client.invalidateQueries({queryKey:["configuration-preview"]});});
 await screen.findByText("No active tenancies need updating.");
 c.read.mockRejectedValue(new ApiError(503));await act(async()=>{await c.client.invalidateQueries({queryKey:["configuration-preview"]});});
 await waitFor(()=>expect(screen.queryByText("No active tenancies need updating.")).toBeNull());
 await userEvent.click(await screen.findByRole("button",{name:"Refresh eligibility"}));c.client.clear();
});

// Explicit auth denial expires the privileged view for both read and mutation boundaries.
it("expires authorization on preview and start denial",async()=>{
 const c=mount();c.start.mockRejectedValue(new ApiError(403));
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));
 await userEvent.click(screen.getByRole("button",{name:"Start update"}));
 await waitFor(()=>expect(c.expired).toHaveBeenCalled());
 c.read.mockRejectedValue(new ApiError(401));await act(async()=>{await c.client.invalidateQueries({queryKey:["configuration-preview"]});});c.client.clear();
});

// Return routes are explicit allowlisted local pages; malformed and external destinations are ignored.
it("labels safe contextual returns and rejects external or malformed destinations",async()=>{
 for(const [path,label] of [["/tenancies","Back to tenancies"],["/tenancies/"+tenant,"Back to tenancy"],["/operations/"+op,"Back to operation"],["/audit-history","Back to audit history"],["/organization","Back to Organization"],["/organization/drift","Back to Organization drift"]]){
  expect(baselineReturn("?returnTo="+encodeURIComponent(path))).toEqual({path,label});
 }
 for(const path of ["https://evil.test","//evil.test","/tenancies/not-uuid","javascript:alert(1)","/configuration?external=evil"]){expect(baselineReturn("?returnTo="+encodeURIComponent(path)).path).toBe("/configuration");}
 history.replaceState(null,"",baselineHref(id,"/tenancies/"+tenant));
 const navigate=vi.fn();render(<PublishedBaseline version={{...version,based_on_id:tenant}} navigate={navigate}/>);
 const back=screen.getByRole("link",{name:/Back to tenancy/});expect(back).toHaveAttribute("href","/tenancies/"+tenant);
 await userEvent.click(back);expect(navigate).toHaveBeenCalledWith("/tenancies/"+tenant);
 expect(screen.getByRole("link",{name:"previous published version"})).toHaveAttribute("href",baselineHref(tenant,"/tenancies/"+tenant));
});

// A verified individual has no duplicate receipt, refresh control or already-current update panel.
it("hides completed individual updates and styles the idle fleet status",async()=>{
 const c=mount({...preview,tenancy_id:tenant,ready_count:0},{tenancyId:tenant,selectedId:id,initialOperationId:op});
 await waitFor(()=>expect(c.status).toHaveBeenCalled());
 await waitFor(()=>expect(screen.queryByRole("region",{name:"Tenancy baseline update"})).toBeNull());c.unmount();c.client.clear();
 const fleet=mount({...preview,ready_count:0});
 expect(await screen.findByRole("status")).toHaveClass("configuration-current");
 expect(screen.queryByRole("button",{name:"Acknowledge"})).toBeNull();fleet.client.clear();
});

// Changed overridden categories need explicit independent decisions before the complete batch starts.
it("stages full-list conflict choices and starts only after every required category is reviewed",async()=>{
 const conflict:OverrideConflict={tenancy_id:tenant,tenancy_name:"Special child",old_baseline:{...version,version_number:1},overrides:{policy_override_statements:["Existing special policy"],quota_override_statements:["Existing special quota"],monthly_budget_override_amount:"500.0000"},policy_review:true,quota_review:true};
 const blocked={...preview,ready_count:1,conflicts:[conflict],blockers:[{tenancy_id:tenant,name:"Special child",code:"OVERRIDE_REVIEW_REQUIRED" as const}]};
 const c=mount(blocked);
 c.stage.mockResolvedValue({id:tenant,revision:2,state:"draft",preview:{...preview,ready_count:2,preview_hash:"c".repeat(64),conflicts:[{...conflict,policy_choice:"use_new_baseline",quota_choice:"keep_override"}]}});
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));
 expect(screen.getByRole("button",{name:"Start update"})).toBeDisabled();
 await userEvent.click(screen.getByRole("button",{name:"Review override"}));
 expect(screen.getByRole("dialog",{name:"Review overrides · Special child"})).toBeInTheDocument();
 expect(screen.getByRole("heading",{name:"Review overrides · Special child"})).toHaveFocus();
 expect(screen.getAllByText("Old baseline v1")).toHaveLength(2);expect(screen.getAllByText("New baseline v2")).toHaveLength(2);
 expect(screen.getByRole("button",{name:"Save review"})).toBeDisabled();
 await userEvent.click(within(screen.getByRole("group",{name:"Choose policy content for this update"})).getByRole("radio",{name:"Use new baseline"}));
 expect(screen.getByRole("button",{name:"Save review"})).toBeDisabled();
 await userEvent.click(within(screen.getByRole("group",{name:"Choose quota content for this update"})).getByRole("radio",{name:"Keep override"}));
 await userEvent.click(screen.getByRole("button",{name:"Save review"}));
 await screen.findByText("Reviewed · staged");expect(c.start).not.toHaveBeenCalled();
 expect(c.stage.mock.calls[0]).toEqual([tenant,{expected_revision:1,tenancy_id:tenant,policy_choice:"use_new_baseline",quota_choice:"keep_override"},expect.any(AbortSignal)]);
 expect(screen.getByRole("button",{name:"Start update"})).toBeEnabled();
 await userEvent.click(screen.getByText("Reviewed · staged"));await userEvent.click(screen.getByRole("button",{name:"Review decisions"}));
 await userEvent.click(screen.getByRole("button",{name:"Back"}));
 await userEvent.click(screen.getByRole("button",{name:"Start update"}));
 await screen.findByText(/Verified in simulation/);expect(c.start.mock.calls[0][0]).toMatchObject({plan_id:tenant,preview_hash:"c".repeat(64)});c.client.clear();
});

// Lost staged-save responses can be read back; no error recovery silently applies or merges content.
it("reloads a saved conflict review and handles denial without changing live configuration",async()=>{
 const conflict:OverrideConflict={tenancy_id:tenant,tenancy_name:"Special child",old_baseline:version,overrides:{policy_override_statements:["Special policy"]},policy_review:true,quota_review:false};
 const data={...preview,ready_count:0,conflicts:[conflict],blockers:[{tenancy_id:tenant,name:"Special child",code:"OVERRIDE_REVIEW_REQUIRED" as const}]};
 const c=mount(data);c.stage.mockRejectedValue(new ApiError(503));
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));await userEvent.click(screen.getByRole("button",{name:"Review override"}));
 await userEvent.click(screen.getByRole("radio",{name:"Keep override"}));await userEvent.click(screen.getByRole("button",{name:"Save review"}));
 await screen.findByRole("alert");c.load.mockRejectedValue(new ApiError(503));await userEvent.click(screen.getByRole("button",{name:"Reload saved review"}));
 await waitFor(()=>expect(screen.getByRole("alert")).toHaveTextContent("Saved review could not be loaded"));
 c.load.mockResolvedValue({id:tenant,revision:2,state:"draft",preview:{...preview,conflicts:[{...conflict,policy_choice:"keep_override"}]}});
 await userEvent.click(screen.getByRole("button",{name:"Reload saved review"}));await screen.findByText("Reviewed · staged");expect(c.start).not.toHaveBeenCalled();
 await userEvent.click(screen.getByText("Reviewed · staged"));await userEvent.click(screen.getByRole("button",{name:"Review decisions"}));
 c.stage.mockRejectedValue(new ApiError(403));await userEvent.click(screen.getByRole("button",{name:"Save review"}));await waitFor(()=>expect(c.expired).toHaveBeenCalled());c.client.clear();
});

// Durable plan URLs restore staged state; stale/unknown contexts cannot quietly become empty success.
it("reloads a stale saved plan and requires an explicit new preview",async()=>{
 history.replaceState(null,"","/configuration?plan="+tenant);
 const c=mount(preview,{},undefined,{id:tenant,revision:3,state:"stale",preview:{...preview,ready_count:0}});
 expect(await screen.findByRole("alert")).toHaveTextContent("plan is stale");expect(screen.getByRole("button",{name:"Start update"})).toBeDisabled();
 await userEvent.click(screen.getByRole("button",{name:"Reload preview"}));await waitFor(()=>expect(c.create).toHaveBeenCalled());
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));c.client.clear();
});

// Creating a local preview still needs current authorization; outages never produce a hidden plan.
it.each([403,503])("handles plan creation failure %s",async status=>{
 const c=mount();c.create.mockRejectedValue(new ApiError(status));
 await userEvent.click(await screen.findByRole("button",{name:"Update existing tenancies"}));
 if(status===403)await waitFor(()=>expect(c.expired).toHaveBeenCalled());else expect(await screen.findByRole("alert")).toHaveTextContent("could not be created");
 expect(c.start).not.toHaveBeenCalled();c.client.clear();
});
