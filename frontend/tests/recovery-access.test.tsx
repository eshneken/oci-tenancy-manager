import {act,fireEvent,render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {it,expect,vi} from "vitest";
import {RecoveryAccess} from "../src/RecoveryAccess";
import {api,ApiError} from "../src/api";
import type {RecoveryPasswordView} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",op="22222222-2222-4222-8222-222222222222";
const ready:RecoveryPasswordView={tenancy_id:id,tenancy_name:"Example tenancy",state:"ready",user_name:"otm-recovery",available:true,preview_hash:"a".repeat(64),provider_mode:"simulated"};
const response={request_id:op,user_name:"otm-recovery",password:"synthetic-not-a-real-credential-value",first_disclosure_at:new Date().toISOString(),rotation_due_at:new Date(Date.now()+14400000).toISOString(),operation_id:op,provider_mode:"simulated" as const};

// Isolate only HTTP and browser clipboard; never place a secret response in Query state.
function mount(data:RecoveryPasswordView=ready){
 const read=vi.spyOn(api,"administratorAccess").mockResolvedValue(data);
 const write=vi.spyOn(api,"recoveryPassword").mockResolvedValue(response);
 const expired=vi.fn(),navigate=vi.fn(),client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
 const props={tenancyId:id,checksRevision:1,expired,navigate};
 const view=render(<QueryClientProvider client={client}><RecoveryAccess {...props}/></QueryClientProvider>);
 return {read,write,expired,navigate,client,view,props};
}

// Open an enabled ready dialog and leave its universal consent unchecked.
async function open(){await userEvent.click(await screen.findByRole("button",{name:"Request password"}));await screen.findByRole("checkbox");}
// An explicit operator request is the only route to the last-mile value.
async function disclose(){await open();await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Get password"}));await screen.findByLabelText("Recovery password");}

it("blocks click, Enter and programmatic submit without explicit consent",async()=>{
 const c=mount();await open();const button=screen.getByRole("button",{name:"Get password"});
 expect(button).toBeDisabled();fireEvent.submit(button.closest("form")!);await userEvent.keyboard("{Enter}");expect(c.write).not.toHaveBeenCalled();
 await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(button);
 const input=await screen.findByLabelText("Recovery password");expect(input).toHaveAttribute("type","password");
 expect(c.write).toHaveBeenCalledWith(id,expect.objectContaining({acknowledged:true,preview_hash:ready.preview_hash}),expect.any(AbortSignal));
 expect(JSON.stringify(c.client.getQueryCache().getAll().map(q=>q.state.data))).not.toContain(response.password);
});

it("reveals/hides/copies explicitly and clears on close while preserving original due",async()=>{
 const c=mount();const copy=vi.fn().mockResolvedValue(undefined);Object.defineProperty(navigator,"clipboard",{value:{writeText:copy},configurable:true});
 await disclose();await userEvent.click(screen.getByRole("button",{name:"Show password"}));expect(screen.getByLabelText("Recovery password")).toHaveAttribute("type","text");
 await userEvent.click(screen.getByRole("button",{name:"Hide password"}));await userEvent.click(screen.getByRole("button",{name:"Copy password"}));await screen.findByRole("button",{name:"Copied"});expect(copy).toHaveBeenCalledTimes(1);
 await userEvent.click(screen.getByRole("button",{name:"Close"}));expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument();
 c.read.mockResolvedValue({...ready,state:"exposed",rotation_due_at:response.rotation_due_at,first_disclosure_at:response.first_disclosure_at,operation_id:op});
 await open();expect(screen.getByText(/does not extend/)).toBeVisible();expect(screen.getByRole("checkbox")).not.toBeChecked();
 await userEvent.click(screen.getByRole("link",{name:"View password operation"}));expect(c.navigate).toHaveBeenCalledWith(`/operations/${op}`);
});

it("clears disclosed material when the page becomes hidden",async()=>{
 mount();await disclose();Object.defineProperty(document,"visibilityState",{value:"hidden",configurable:true});fireEvent(document,new Event("visibilitychange"));await waitFor(()=>expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument());Object.defineProperty(document,"visibilityState",{value:"visible",configurable:true});
});

it("clears consent and secrets on target/check context changes",async()=>{
 const c=mount();await open();await userEvent.click(screen.getByRole("checkbox"));
 c.view.rerender(<QueryClientProvider client={c.client}><RecoveryAccess {...c.props} checksRevision={2}/></QueryClientProvider>);
 await waitFor(()=>expect(screen.getByRole("checkbox")).not.toBeChecked());
 c.view.rerender(<QueryClientProvider client={c.client}><RecoveryAccess {...c.props} tenancyId={op}/></QueryClientProvider>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Get password"})).toBeDisabled());
 fireEvent.submit(screen.getByRole("button",{name:"Get password"}).closest("form")!);expect(c.write).not.toHaveBeenCalled();
});

it.each(["not_prepared","unavailable","overdue","attention","preparing","rotating"] as const)("shows %s without fetching password",async(state)=>{
 const c=mount({...ready,state,available:false,preview_hash:null});await open();expect(screen.getByRole("button",{name:"Get password"})).toBeDisabled();expect(screen.getByRole("checkbox")).toBeDisabled();expect(c.write).not.toHaveBeenCalled();
});

it("does not allow inactive access",async()=>{mount({...ready,state:"inactive",available:false});await waitFor(()=>expect(screen.getByRole("button",{name:"Request password"})).toBeDisabled());});

it.each([401,403,500])("handles metadata failure %s",async(status)=>{
 const c=mount();await screen.findByText("Ready");c.read.mockRejectedValue(new ApiError(status));await c.client.invalidateQueries();
 if(status===500){await screen.findByRole("alert");c.read.mockResolvedValue(ready);await userEvent.click(screen.getByRole("button",{name:"Retry access state"}));await screen.findByText("Ready");}
 else await waitFor(()=>expect(c.expired).toHaveBeenCalled());
});

it.each([400,404,409,422,401,403])("handles refused disclosure %s without revealing a value",async(status)=>{
 const c=mount();c.write.mockRejectedValue(new ApiError(status));await open();await userEvent.click(screen.getByRole("checkbox"));fireEvent.submit(screen.getByRole("button",{name:"Get password"}).closest("form")!);
 if([401,403].includes(status))await waitFor(()=>expect(c.expired).toHaveBeenCalled());else await screen.findByRole("alert");expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument();
});

it("retries a lost response using the exact original request",async()=>{
 const c=mount();c.write.mockRejectedValueOnce(new Error("transport"));await open();await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Get password"}));await screen.findByRole("alert");
 await userEvent.click(screen.getByRole("button",{name:"Retry same request"}));await screen.findByLabelText("Recovery password");expect(c.write.mock.calls[0][1]).toEqual(c.write.mock.calls[1][1]);
});

it("ignores a late response after closing and restores launch focus",async()=>{
 const c=mount();let resolve!:(value:typeof response)=>void;c.write.mockImplementation(()=>new Promise(done=>{resolve=done;}));await open();await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Get password"}));
 await userEvent.click(screen.getByRole("button",{name:"Close"}));resolve(response);await waitFor(()=>expect(screen.getByRole("button",{name:"Request password"})).toHaveFocus());expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument();
});

it("reports clipboard denial without sending another password request",async()=>{
 const c=mount();Object.defineProperty(navigator,"clipboard",{value:{writeText:vi.fn().mockRejectedValue(new Error("denied"))},configurable:true});await disclose();await userEvent.click(screen.getByRole("button",{name:"Copy password"}));expect(await screen.findByRole("alert")).toHaveTextContent("Clipboard access is unavailable");expect(c.write).toHaveBeenCalledTimes(1);
});

it.each(["checks","metadata"])("rejects a late disclosure after %s changes",async(kind)=>{
 const c=mount();let resolve!:(value:typeof response)=>void;c.write.mockImplementation(()=>new Promise(done=>{resolve=done;}));
 await open();await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Get password"}));
 if(kind==="checks")c.view.rerender(<QueryClientProvider client={c.client}><RecoveryAccess {...c.props} checksRevision={2}/></QueryClientProvider>);
 else c.client.setQueryData(["tenancies","administrator-access",id],{...ready,available:false,state:"attention",preview_hash:null});
 await waitFor(()=>expect(c.write.mock.calls[0][2]?.aborted).toBe(true));resolve(response);
 await waitFor(()=>expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument());expect(screen.getByRole("checkbox")).not.toBeChecked();
});

it.each([new Date(Date.now()-1).toISOString(),"invalid"])("never renders a value with an expired/invalid deadline %s",async(due)=>{
 const c=mount();let resolve!:(value:typeof response)=>void;c.write.mockImplementation(()=>new Promise(done=>{resolve=done;}));
 await open();await userEvent.click(screen.getByRole("checkbox"));await userEvent.click(screen.getByRole("button",{name:"Get password"}));
 const observed:boolean[]=[];const observer=new MutationObserver(()=>observed.push(Boolean(document.querySelector("#recovery-password"))));observer.observe(document.body,{childList:true,subtree:true});
 resolve({...response,rotation_due_at:due});await screen.findByRole("alert");observer.disconnect();
 expect(observed.every(value=>!value)).toBe(true);expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument();
});

it("keeps the retrieved value across unchanged required-user record refreshes",async()=>{
 const {RequiredUsers}=await import("../src/RequiredUsers");
 const c=mount();c.view.unmount();
 const users={tenancy_id:id,tenancy_status:"active" as const,provider_mode:"simulated" as const,check_available:true,users:(["automation","recovery"] as const).map(purpose=>({purpose,identity_state:"recorded" as const,presence:{state:"present" as const,stale:false}}))};
 vi.spyOn(api,"requiredUsers").mockResolvedValue(users as Awaited<ReturnType<typeof api.requiredUsers>>);
 render(<QueryClientProvider client={c.client}><RequiredUsers tenancyId={id} expired={c.expired} navigate={c.navigate}/></QueryClientProvider>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Request password"})).toBeEnabled());await disclose();
 await c.client.invalidateQueries({queryKey:["tenancies","required-users",id]});
 await waitFor(()=>expect(screen.getByLabelText("Recovery password")).toBeInTheDocument());
 expect(JSON.stringify(c.client.getQueryCache().getAll().map(q=>q.state.data))).not.toContain(response.password);
});

it("clears a currently displayed value when its scheduled deadline fires",async()=>{
 const c=mount();const timer=vi.spyOn(globalThis,"setTimeout");await disclose();
 const callback=timer.mock.calls.find(call=>Number(call[1])>60*60*1000)?.[0];expect(typeof callback).toBe("function");
 await act(async()=>{if(typeof callback==="function")callback();});
 expect(screen.queryByLabelText("Recovery password")).not.toBeInTheDocument();expect(c.read.mock.calls.length).toBeGreaterThan(1);
});
