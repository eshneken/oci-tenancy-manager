import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {it,expect,vi} from "vitest";
import {RecoveryNetworkRepair} from "../src/RecoveryNetworkRepair";
import {api,ApiError} from "../src/api";
import type {RecoveryConsoleView,RecoveryNetworkPreview,OperationDetail} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",op="22222222-2222-4222-8222-222222222222";
const policy:RecoveryConsoleView={state:"drift",mfa_exemption:"verified",network_boundary:"drift",desired_fingerprint:"a".repeat(64),observed_fingerprint:"b".repeat(64),checked_at:"2026-11-09T00:00:00Z",operation_id:op};
const preview:RecoveryNetworkPreview={tenancy_id:id,tenancy_name:"Example shared tenancy",preview_hash:"c".repeat(64),desired_fingerprint:"a".repeat(64),observed_fingerprint:"b".repeat(64),current_network_count:2,desired_network_count:1,expires_at:"2026-11-10T00:00:00Z",provider_mode:"simulated"};

// Exercise the real modal with an isolated cache and independently controlled admission/progress.
function mount(eligible=true){
 const read=vi.spyOn(api,"previewRecoveryNetworks").mockResolvedValue(preview);
 const write=vi.spyOn(api,"repairRecoveryNetworks").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:"2026-11-09T00:00:00Z"});
 const progress=vi.spyOn(api,"operation").mockResolvedValue({operation:{state:"queued"}} as OperationDetail);
 const refresh=vi.spyOn(api,"checkRequiredUsers").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:"2026-11-09T00:00:00Z"});
 const expired=vi.fn(),navigate=vi.fn(),client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
 const invalidate=vi.spyOn(client,"invalidateQueries");
 const props={tenancyId:id,eligible,policy,expired,navigate};
 const view=render(<QueryClientProvider client={client}><h2 id="required-users-title" tabIndex={-1}>Required users</h2><RecoveryNetworkRepair {...props}/></QueryClientProvider>);
 return {read,write,progress,refresh,expired,navigate,client,invalidate,view,props};
}

it("requires unchecked consent for click, Enter and programmatic submit",async()=>{
 const c=mount();const user=userEvent.setup();
 await user.click(screen.getByRole("button",{name:"Repair approved networks"}));
 await screen.findByText("Example shared tenancy");
 const submit=screen.getByRole("button",{name:"Confirm network repair"});
 expect(submit).toBeDisabled();expect(screen.getByRole("checkbox")).not.toBeChecked();
 fireEvent.submit(submit.closest("form")!);await user.keyboard("{Enter}");expect(c.write).not.toHaveBeenCalled();
 await user.click(screen.getByRole("checkbox"));await user.click(submit);
 expect(c.write).toHaveBeenCalledWith(id,expect.objectContaining({preview_hash:preview.preview_hash,acknowledged:true}),expect.any(AbortSignal));
 expect(await screen.findByText(/Approved-network repair queued/)).toBeVisible();
 expect(c.invalidate).toHaveBeenCalled();
 await user.click(screen.getByRole("link",{name:"View operation"}));expect(c.navigate).toHaveBeenCalledWith(`/operations/${op}`);
});

it("hides repair without eligible current network-only drift",()=>{mount(false);expect(screen.queryByRole("button",{name:"Repair approved networks"})).not.toBeInTheDocument();});

it("clears consent and preview when reviewed evidence changes",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));
 await screen.findByText("Example shared tenancy");await userEvent.click(screen.getByRole("checkbox"));
 c.view.rerender(<QueryClientProvider client={c.client}><h2 id="required-users-title" tabIndex={-1}>Required users</h2><RecoveryNetworkRepair {...c.props} policy={{...policy,desired_fingerprint:"d".repeat(64)}}/></QueryClientProvider>);
 await waitFor(()=>expect(screen.queryByRole("checkbox")).not.toBeInTheDocument());
 expect(screen.getByRole("button",{name:"Confirm network repair"})).toBeDisabled();
});

it.each([409,404,500,401,403])("handles preview failure %s safely",async(status)=>{
 const c=mount();c.read.mockRejectedValue(new ApiError(status));
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));
 if([401,403].includes(status))await waitFor(()=>expect(c.expired).toHaveBeenCalled());
 else expect(await screen.findByRole("alert")).toHaveTextContent("Repair is unavailable");
 expect(c.write).not.toHaveBeenCalled();
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
});

it.each([400,409,404,401,403])("handles admission failure %s without blind retries",async(status)=>{
 const c=mount();c.write.mockRejectedValue(new ApiError(status));
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));
 await screen.findByText("Example shared tenancy");await userEvent.click(screen.getByRole("checkbox"));
 fireEvent.submit(screen.getByRole("button",{name:"Confirm network repair"}).closest("form")!);
 if([401,403].includes(status))await waitFor(()=>expect(c.expired).toHaveBeenCalled());
 else {expect(await screen.findByRole("alert")).toHaveTextContent("preview changed");expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();}
 expect(c.write).toHaveBeenCalledTimes(1);
});

it("retries an uncertain response with the same request and retained reviewed target",async()=>{
 const c=mount();c.write.mockRejectedValueOnce(new Error("transport"));
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));
 await screen.findByText("Example shared tenancy");await userEvent.click(screen.getByRole("checkbox"));
 fireEvent.submit(screen.getByRole("button",{name:"Confirm network repair"}).closest("form")!);
 expect(await screen.findByRole("alert")).toHaveTextContent("request result is unknown");
 await userEvent.click(screen.getByRole("button",{name:"Retry same request"}));
 await waitFor(()=>expect(c.write).toHaveBeenCalledTimes(2));
 expect(c.write.mock.calls[0][1]).toEqual(c.write.mock.calls[1][1]);
});

it.each(["succeeded","failed","needs_attention"])("shows terminal %s progress without claiming unsent checks",async(state)=>{
 const c=mount();c.progress.mockResolvedValue({operation:{state}} as OperationDetail);
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));
 await screen.findByText("Example shared tenancy");await userEvent.click(screen.getByRole("checkbox"));
 fireEvent.submit(screen.getByRole("button",{name:"Confirm network repair"}).closest("form")!);
 await waitFor(()=>expect(c.progress).toHaveBeenCalled());
 if(state==="succeeded")await waitFor(()=>expect(c.refresh).toHaveBeenCalledTimes(1));
 else expect(c.refresh).not.toHaveBeenCalled();
});

it("retains successful repair when starting the separate check fails",async()=>{
 const c=mount();c.progress.mockResolvedValue({operation:{state:"succeeded"}} as OperationDetail);c.refresh.mockRejectedValue(new Error("unavailable"));
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));await screen.findByText("Example shared tenancy");
 await userEvent.click(screen.getByRole("checkbox"));fireEvent.submit(screen.getByRole("button",{name:"Confirm network repair"}).closest("form")!);
 expect(await screen.findByRole("alert")).toHaveTextContent("a user-data refresh could not be started");
});

it("rejects another tenancy's preview",async()=>{
 const c=mount();c.read.mockResolvedValue({...preview,tenancy_id:op});
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));expect(await screen.findByRole("alert")).toHaveTextContent("Repair is unavailable");expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

it("cancels a pending preview and restores launcher focus after it is enabled",async()=>{
 const c=mount();c.read.mockImplementation(()=>new Promise(()=>{}));
 const launch=screen.getByRole("button",{name:"Repair approved networks"});
 await userEvent.click(launch);expect(launch).toBeDisabled();
 const signal=c.read.mock.calls[0][1]!;
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
 expect(signal.aborted).toBe(true);await waitFor(()=>expect(launch).toHaveFocus());
 expect(launch).toBeEnabled();
});

it("rejects a late GET after the reviewed context changes",async()=>{
 const c=mount();let resolve!:(value:RecoveryNetworkPreview)=>void;
 c.read.mockImplementation(()=>new Promise(done=>{resolve=done;}));
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));
 c.view.rerender(<QueryClientProvider client={c.client}><h2 id="required-users-title" tabIndex={-1}>Required users</h2><RecoveryNetworkRepair {...c.props} policy={{...policy,observed_fingerprint:"e".repeat(64)}}/></QueryClientProvider>);
 resolve(preview);
 expect(await screen.findByRole("alert")).toHaveTextContent(/Repair is unavailable|preview is out of date/);
 expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();expect(c.write).not.toHaveBeenCalled();
});

it("cannot submit after eligibility is lost",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));await screen.findByText("Example shared tenancy");
 await userEvent.click(screen.getByRole("checkbox"));
 c.view.rerender(<QueryClientProvider client={c.client}><h2 id="required-users-title" tabIndex={-1}>Required users</h2><RecoveryNetworkRepair {...c.props} eligible={false}/></QueryClientProvider>);
 const submit=screen.getByRole("button",{name:"Confirm network repair"});
 expect(submit).toBeDisabled();fireEvent.submit(submit.closest("form")!);expect(c.write).not.toHaveBeenCalled();
 await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
 await waitFor(()=>expect(screen.getByRole("heading",{name:"Required users"})).toHaveFocus());
});

it("retains uncertain replay across close/reopen and a changed context",async()=>{
 const c=mount();c.write.mockRejectedValueOnce(new Error("transport"));
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));await screen.findByText("Example shared tenancy");
 await userEvent.click(screen.getByRole("checkbox"));fireEvent.submit(screen.getByRole("button",{name:"Confirm network repair"}).closest("form")!);
 await screen.findByRole("alert");await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
 c.view.rerender(<QueryClientProvider client={c.client}><h2 id="required-users-title" tabIndex={-1}>Required users</h2><RecoveryNetworkRepair {...c.props} eligible={false} policy={{...policy,desired_fingerprint:"d".repeat(64)}}/></QueryClientProvider>);
 await userEvent.click(screen.getByRole("button",{name:"Recover repair request"}));
 expect(screen.getByRole("checkbox")).not.toBeChecked();expect(screen.getByRole("button",{name:"Retry same request"})).toBeDisabled();
 await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Retry same request"}));
 await waitFor(()=>expect(c.write).toHaveBeenCalledTimes(2));expect(c.write.mock.calls[0][1]).toEqual(c.write.mock.calls[1][1]);
});

it.each(["queued","needs_attention"])("blocks a new launch for accepted %s work",async(state)=>{
 const c=mount();c.progress.mockResolvedValue({operation:{state}} as OperationDetail);
 await userEvent.click(screen.getByRole("button",{name:"Repair approved networks"}));await screen.findByText("Example shared tenancy");
 await userEvent.click(screen.getByRole("checkbox"));fireEvent.submit(screen.getByRole("button",{name:"Confirm network repair"}).closest("form")!);
 await waitFor(()=>expect(c.progress).toHaveBeenCalled());
 expect(screen.getByRole("button",{name:"Repair approved networks"})).toBeDisabled();
 expect(screen.getByRole("status")).toHaveFocus();
});
