import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {expect,it,vi} from "vitest";
import {Operations} from "../src/Operations";
import {api,ApiError} from "../src/api";
import type {OperationDetail} from "../src/contracts";

vi.mock("../src/Onboarding",()=>({Onboarding:()=> <p>Existing onboarding controls</p>}));
const id="11111111-1111-4111-8111-111111111111",admin="22222222-2222-4222-8222-222222222222",time="2026-11-04T12:00:00Z";
const detail:OperationDetail={operation:{id,kind:"organization_action",state:"waiting",stage:"handoff",accepted_at:time,updated_at:time,completed_at:null,target_tenancy_ocid:"ocid1.tenancy.oc1..synthetic",initiated_by:"Original initiator",title:"Create tenancy",guided_onboarding:true,responsible_administrator_name:"Previous administrator",responsible_administrator_id:admin,responsibility_revision:3,can_take_responsibility:true},steps:[],events:[],events_limited:false};

// Exercise the real operation panel and native confirmation while isolating existing onboarding internals.
function mount(data:OperationDetail=detail){
 const read=vi.spyOn(api,"operation").mockResolvedValue(data),take=vi.spyOn(api,"takeResponsibility").mockResolvedValue({operation_id:id,state:"waiting",accepted_at:time,provider_mode:"simulated"});
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}}),expired=vi.fn();
 const view=render(<QueryClientProvider client={client}><Operations operationId={id} expired={expired} navigate={vi.fn()}/></QueryClientProvider>);
 return {...view,client,read,take,expired};
}

// A concise named panel keeps the active administrator visible before any technical-history disclosure.
it("shows responsible and original administrators separately with no reason field",async()=>{
 mount();const panel=await screen.findByRole("region",{name:"Administrator responsibility"});expect(panel).toHaveTextContent("Original initiator");expect(panel).toHaveTextContent("Previous administrator");expect(screen.getAllByText("Original initiator")).toHaveLength(1);expect(screen.queryByLabelText("Reason")).toBeNull();
});

it.each([false,true])("respects the backend handoff capability and available revision: flag=%s",async(flag)=>{
 mount({...detail,operation:{...detail.operation,can_take_responsibility:flag,responsibility_revision:flag?null:3}});await screen.findByRole("region",{name:"Administrator responsibility"});expect(screen.queryByRole("button",{name:"Take responsibility"})).toBeNull();
});

it("omits the guided responsibility panel on unrelated operations",async()=>{
 mount({...detail,operation:{...detail.operation,guided_onboarding:false,kind:"inspect_import"}});await screen.findByRole("heading",{name:"Create tenancy"});expect(screen.queryByRole("region",{name:"Administrator responsibility"})).toBeNull();expect(screen.getByText("Original initiator")).toBeInTheDocument();
});

it("explains limited responsibility, focuses the heading and cancels without mutation",async()=>{
 const c=mount();const launch=await screen.findByRole("button",{name:"Take responsibility"});await userEvent.click(launch);const modal=screen.getByRole("dialog",{name:"Take responsibility?"});expect(within(modal).getByRole("heading")).toHaveFocus();expect(modal).toHaveTextContent("activation email address and tenancy owner remain unchanged");await userEvent.click(within(modal).getByRole("button",{name:"Cancel"}));expect(modal).not.toHaveAttribute("open");expect(launch).toHaveFocus();expect(c.take).not.toHaveBeenCalled();await userEvent.click(launch);fireEvent(screen.getByRole("dialog"),new Event("cancel",{cancelable:true}));expect(launch).toHaveFocus();expect(c.take).not.toHaveBeenCalled();
});

it("records exact reviewed revision, refreshes private workflow data and announces success",async()=>{
 const c=mount();c.client.setQueryData(["onboarding",id],{existing:true});await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));
 c.take.mockImplementation(async()=>{c.read.mockResolvedValue({...detail,operation:{...detail.operation,responsible_administrator_name:"Current administrator",responsibility_revision:4,can_take_responsibility:false}});return{operation_id:id,state:"waiting",accepted_at:time,provider_mode:"simulated"};});
 await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Take responsibility"}));
 const notice=await screen.findByText("Responsibility change recorded.");expect(notice).toHaveFocus();expect(c.take).toHaveBeenCalledWith(id,{client_request_key:expect.any(String),expected_revision:3},expect.any(AbortSignal));expect(c.client.getQueryState(["onboarding",id])?.isInvalidated).toBe(true);expect(screen.getByText("Current administrator")).toBeVisible();expect(screen.getByText("Original initiator")).toBeVisible();expect(screen.queryByRole("button",{name:"Take responsibility"})).toBeNull();
});

it("never rebases a modal's reviewed revision on a background responsibility change",async()=>{
 const c=mount();await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));act(()=>c.client.setQueryData(["operations","detail",id],{...detail,operation:{...detail.operation,responsibility_revision:9,responsible_administrator_name:"Another administrator"}}));const modal=screen.getByRole("dialog");expect(modal).toHaveTextContent("Previous administrator");c.take.mockRejectedValue(new ApiError(409));await userEvent.click(within(modal).getByRole("button",{name:"Take responsibility"}));await screen.findByRole("alert");expect(c.take).toHaveBeenCalledWith(id,expect.objectContaining({expected_revision:3}),expect.any(AbortSignal));expect(screen.getByRole("alert")).toHaveTextContent("eligibility changed");
});

it("retries an unknown response with the same command identity",async()=>{
 const c=mount();c.take.mockRejectedValueOnce(new ApiError(503));await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Take responsibility"}));expect(await screen.findByRole("alert")).toHaveTextContent("could not be confirmed");const first=c.take.mock.calls[0][1];await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Take responsibility"}));await screen.findByText("Responsibility change recorded.");expect(c.take.mock.calls[1][1]).toEqual(first);
});

it.each([401,403])("ends the privileged view for denied responsibility changes: %s",async(status)=>{
 const c=mount();c.take.mockRejectedValue(new ApiError(status));await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Take responsibility"}));await waitFor(()=>expect(c.expired).toHaveBeenCalled());
});

it("blocks duplicate dispatch and native cancellation while a response is pending",async()=>{
 const c=mount();let complete!:(value:Awaited<ReturnType<typeof api.takeResponsibility>>)=>void;c.take.mockReturnValue(new Promise(resolve=>{complete=resolve;}));await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));const modal=screen.getByRole("dialog");await userEvent.click(within(modal).getByRole("button",{name:"Take responsibility"}));expect(within(modal).getByRole("button",{name:"Updating responsibility…"})).toBeDisabled();expect(within(modal).getByRole("button",{name:"Cancel"})).toBeDisabled();fireEvent(modal,new Event("cancel",{cancelable:true}));expect(modal).toHaveAttribute("open");complete({operation_id:id,state:"waiting",accepted_at:time,provider_mode:"simulated"});await screen.findByText("Responsibility change recorded.");expect(c.take).toHaveBeenCalledTimes(1);
});

it("aborts its pending view on unmount without publishing a late success",async()=>{
 const c=mount();let complete!:(value:Awaited<ReturnType<typeof api.takeResponsibility>>)=>void;c.take.mockReturnValue(new Promise(resolve=>{complete=resolve;}));await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Take responsibility"}));const signal=c.take.mock.calls[0][2]!;c.unmount();expect(signal.aborted).toBe(true);complete({operation_id:id,state:"waiting",accepted_at:time,provider_mode:"simulated"});
});

it("does not display names as executable markup and handles historical missing attribution",async()=>{
 mount({...detail,operation:{...detail.operation,initiated_by:null,responsible_administrator_name:"<script>name</script>"}});await screen.findByText("<script>name</script>");expect(document.querySelector("script")).toBeNull();expect(within(screen.getByRole("region",{name:"Administrator responsibility"})).getByText("Not recorded")).toBeVisible();await userEvent.click(screen.getByRole("button",{name:"Take responsibility"}));expect(screen.getByRole("dialog")).toHaveTextContent("<script>name</script>");
});

// The command uses the guarded same-origin POST and never carries a new owner, mailbox or arbitrary administrator.
it("posts only request identity and expected responsibility revision",async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({operation_id:id,state:"waiting",accepted_at:time,provider_mode:"simulated"}),{status:202}));vi.stubGlobal("fetch",fetch);await api.takeResponsibility(id,{client_request_key:admin,expected_revision:3});expect(fetch.mock.calls[0][0]).toBe(`/api/operations/${id}/responsibility`);expect(fetch.mock.calls[0][1]).toMatchObject({method:"POST",credentials:"same-origin",headers:{"X-OTM-Request":"1"},body:JSON.stringify({client_request_key:admin,expected_revision:3})});
});

// Responsibility changes remain readable immutable history rather than implying a new tenancy owner.
it("labels responsibility changes consistently in operation and audit history",async()=>{
 const c=mount({...detail,events:[{kind:"operation_responsibility_changed",at:time,safe_code:null}]});
 await userEvent.click(await screen.findByText("Operation details and history"));
 expect(screen.getByText("Operation responsibility changed")).toBeVisible();c.unmount();
 vi.spyOn(api,"auditHistory").mockResolvedValue({items:[{id:admin,at:time,kind:"operation_responsibility_changed",category:"operations",actor_name:"Current administrator",operation_id:id,administrator_id:null,administrator_name:null,safe_code:null}],total:1,page:1,pages:1,page_size:10});
 const {AuditHistory}=await import("../src/AuditHistory");
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})}><AuditHistory expired={vi.fn()} navigate={vi.fn()}/></QueryClientProvider>);
 expect(await screen.findByText("Operation responsibility changed")).toBeVisible();
});

// Background handoff may remove the launch button; dismissal still restores a meaningful focus target.
it("returns focus to the responsibility heading if handoff eligibility disappears",async()=>{
 const c=mount();await userEvent.click(await screen.findByRole("button",{name:"Take responsibility"}));
 act(()=>c.client.setQueryData(["operations","detail",id],{...detail,operation:{...detail.operation,can_take_responsibility:false,responsibility_revision:4}}));
 await waitFor(()=>expect(screen.getAllByRole("button",{name:"Take responsibility"})).toHaveLength(1));
 await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Cancel"}));
 expect(screen.getByRole("heading",{name:"Administrator responsibility"})).toHaveFocus();
});
