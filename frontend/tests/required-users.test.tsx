import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { RequiredUsers } from "../src/RequiredUsers";
import { api, ApiError } from "../src/api";
import type { RequiredUsersDirectory } from "../src/contracts";

const id = "11111111-1111-4111-8111-111111111111";
const directory: RequiredUsersDirectory = {
  tenancy_id: id, tenancy_status: "active", provider_mode: "simulated",
  users: ["automation", "recovery"].map(purpose => ({
    purpose, identity_state: "recorded", identity: {
      user_name: "otm-" + purpose, user_ocid: "ocid1.user.oc1..otmsim" + purpose,
      scim_resource_id: purpose + "-scim", domain_ocid: "ocid1.domain.oc1..otmsimdomain",
      recorded_at: "2026-11-06T12:00:00Z", retired_at: null, source_operation_id: id,
    },
  })) as RequiredUsersDirectory["users"],
};

// Each case owns its cache; no data is borrowed from the operator's saved workspace.
function mount(value: RequiredUsersDirectory | Promise<RequiredUsersDirectory> = directory) {
  vi.spyOn(api,"administratorAccess").mockResolvedValue({tenancy_id:id,tenancy_name:"Example tenancy",state:"not_prepared",available:false,provider_mode:"simulated"});
  const read = vi.spyOn(api, "requiredUsers").mockImplementation(() => Promise.resolve(value));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const expired = vi.fn(), navigate = vi.fn();
  const result = render(<QueryClientProvider client={client}><RequiredUsers tenancyId={id} expired={expired} navigate={navigate}/></QueryClientProvider>);
  return { ...result, client, read, expired, navigate };
}

// Identity details remain collapsed, neutral and useful without asserting live access health.
it("shows both identities and contextual setup links", async () => {
  const c = mount();
  await screen.findByText("otm-automation");
  const access=screen.getByRole("region",{name:"Administrator access"});
  expect(within(access).getByRole("button",{name:"Request password"})).toBeInTheDocument();
  expect(access.closest("li")).toBe(screen.getByRole("heading",{name:"Automation user"}).closest("li"));
  expect(screen.getAllByText("Recorded", { exact: true })).toHaveLength(2);
  expect(screen.getAllByText("Not checked", { exact: true })).toHaveLength(9);
  expect(screen.queryByText(/healthy|verified|missing/i)).not.toBeInTheDocument();
  const card = screen.getByRole("heading", { name: "Automation user" }).closest("li")!;
  const details = card.querySelector("details")!;
  expect(details.open).toBe(false);
  await userEvent.click(within(card).getByText("Identity details"));
  expect(details.open).toBe(true);
  expect(within(card).getByText("automation-scim")).toBeVisible();
  expect(within(card).getByText(/11\/6\/2026/)).toBeVisible();
  await userEvent.click(within(card).getByRole("link", { name: "View setup operation" }));
  expect(c.navigate).toHaveBeenCalledWith("/operations/" + id);
  c.client.clear();
});

// A successful absent registry result does not fabricate a missing OCI user or display fake details.
it("shows genuine unbound records and explicit pending context", async () => {
  const c = mount({ ...directory, tenancy_status: "pending", users: directory.users.map(u => ({...u, identity: null, identity_state: "not_recorded"})) as RequiredUsersDirectory["users"] });
  await screen.findByText(/Setup is still in progress/);
  expect(screen.getAllByText("Not recorded")).toHaveLength(4);
  expect(screen.queryByText("Identity details")).not.toBeInTheDocument();
  expect(screen.queryByText(/missing/i)).not.toBeInTheDocument();
  c.client.clear();
});

// Termination retains account evidence without claiming OCI deletion, and timestamps remain inspectable.
it("shows retired records as retained history", async () => {
  const c = mount({ ...directory, tenancy_status: "terminated", users: directory.users.map(u => ({...u, identity_state: "retired", identity: {...u.identity!, retired_at: "2026-11-06T16:00:00Z"}})) as RequiredUsersDirectory["users"] });
  await screen.findByText(/retained for tenancy history/);
  expect(screen.getAllByText("Retired record")).toHaveLength(2);
  await userEvent.click(screen.getAllByText("Identity details")[0]);
  expect(within(screen.getByRole("heading", { name: "Automation user" }).closest("li")!).getByText("Record retired (UTC)")).toBeVisible();
  c.client.clear();
});

// Loading never becomes an empty success; busy refresh preserves the existing records.
it("keeps loading and refresh states honest", async () => {
  let complete!: (value: RequiredUsersDirectory) => void;
  const c = mount(new Promise(resolve => { complete = resolve; }));
  expect(screen.getByRole("status")).toHaveTextContent("Loading required user records");
  expect(screen.queryByText("Not recorded")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Refresh user data" })).toBeDisabled();
  complete(directory); await screen.findByText("otm-recovery");
  let refresh!: (value: RequiredUsersDirectory) => void;
  c.read.mockReturnValueOnce(new Promise(resolve => { refresh = resolve; }));
  void c.client.invalidateQueries({queryKey:["tenancies","required-users",id]});
  await waitFor(()=>expect(screen.getByRole("region",{name:"Required users"})).toHaveAttribute("aria-busy","true"));
  expect(screen.getByText("otm-recovery")).toBeVisible();
  refresh(directory); await waitFor(()=>expect(screen.getByRole("region",{name:"Required users"})).toHaveAttribute("aria-busy","false")); c.client.clear();
});

// A failed read offers retry and never synthesizes unregistered accounts from a network error.
it("distinguishes initial failure and a failed refresh of retained records", async () => {
  const c = mount(Promise.reject(new Error("private")));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load");
  expect(screen.queryByText("Not recorded")).not.toBeInTheDocument();
  c.read.mockResolvedValue(directory);
  await userEvent.click(screen.getByRole("button", { name: "Retry loading users" }));
  await screen.findByText("otm-automation");
  c.read.mockRejectedValueOnce(new Error("private"));
  await c.client.invalidateQueries({queryKey:["tenancies","required-users",id]});
  expect(await screen.findByRole("alert")).toHaveTextContent("Previously loaded records are shown");
  expect(screen.getByText("otm-automation")).toBeVisible();
  expect(screen.queryByText("private")).not.toBeInTheDocument(); c.client.clear();
});

// Revoked or expired sessions leave authorization handling to the application's existing boundary.
it.each([401, 403])("expires access after %s", async status => {
  const c = mount(Promise.reject(new ApiError(status)));
  await waitFor(() => expect(c.expired).toHaveBeenCalled()); c.client.clear();
});

// Switching children never displays another tenant's retained identity record while the new GET waits.
it("isolates each tenancy's query cache", async () => {
  const c = mount(); await screen.findByText("otm-automation");
  c.read.mockReturnValueOnce(new Promise(() => {}));
  c.rerender(<QueryClientProvider client={c.client}><RequiredUsers tenancyId="22222222-2222-4222-8222-222222222222" expired={c.expired} navigate={c.navigate}/></QueryClientProvider>);
  expect(screen.queryByText("otm-automation")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Loading"); c.client.clear();
});


// Expired authority hides retained facts immediately while the parent closes the private session.
it("does not retain visible records after a denied refresh", async () => {
  const c = mount(); await screen.findByText("otm-automation");
  c.read.mockRejectedValueOnce(new ApiError(403));
  await c.client.invalidateQueries({queryKey:["tenancies","required-users",id]});
  await waitFor(() => expect(c.expired).toHaveBeenCalled());
  expect(screen.queryByText("otm-automation")).not.toBeInTheDocument(); c.client.clear();
});


const configured:RequiredUsersDirectory = {...directory,check_available:true,check_unavailable_reason:null};
const checkId="33333333-3333-4333-8333-333333333333";
const receipt={operation_id:checkId,state:"queued" as const,provider_mode:"simulated" as const,accepted_at:"2026-11-06T12:00:00Z"};

// Account presence, permissions and recorded identity stay distinct; failed latest reads replace old facts.
it("shows independent current and failed account observations", async()=>{
  const present:RequiredUsersDirectory={...configured,users:configured.users.map((u,i)=>({...u,presence:{state:i?"missing":"present",checked_at:"2026-11-06T12:00:00Z",stale:false,operation_id:checkId}})) as RequiredUsersDirectory["users"]};
  const c=mount(present);
  expect(await screen.findByText("Present",{exact:true})).toBeVisible();
  expect(screen.getByText("Missing",{exact:true})).toBeVisible();
  expect(screen.getAllByText("Permissions")).toHaveLength(1);
  expect(screen.getAllByText("Not checked",{exact:true})).toHaveLength(7);
  await userEvent.click(screen.getAllByRole("link",{name:/^View presence check, /})[0]);
  expect(c.navigate).toHaveBeenCalledWith("/operations/"+checkId+"#automation-presence");
  c.read.mockResolvedValue({...present,users:present.users.map(u=>({...u,presence:{...u.presence!,state:"unknown"}})) as RequiredUsersDirectory["users"]});
  await c.client.invalidateQueries({queryKey:["tenancies","required-users",id]});
  await waitFor(()=>expect(screen.getAllByText("Unable to verify")).toHaveLength(2));
  expect(screen.queryByText("Present",{exact:true})).not.toBeInTheDocument();
  expect(screen.getAllByText("Presence last attempt (UTC)")).toHaveLength(2);c.client.clear();
});

// An old positive result is labeled out of date and never retains current green styling.
it("neutralizes stale presence evidence",async()=>{
  const c=mount({...configured,users:configured.users.map(u=>({...u,presence:{state:"present",checked_at:"2026-11-06T12:00:00Z",stale:true,operation_id:checkId}})) as RequiredUsersDirectory["users"]});
  await screen.findByText("otm-automation");
  expect(screen.getAllByText("Check out of date")).toHaveLength(2);
  expect(screen.getAllByText(/Last result: Present/)).toHaveLength(2);
  expect(document.querySelectorAll(".required-users .badge.active")).toHaveLength(0);c.client.clear();
});

// Disabled states explain actual server availability visibly, rather than implying a missing account.
it.each(["not_configured","tenancy_inactive","tenancy_busy","provider_unavailable"] as const)("explains %s",async reason=>{
  const c=mount({...directory,check_available:false,check_unavailable_reason:reason});
  await screen.findByText("otm-automation");
  expect(screen.getByRole("button",{name:"Refresh user data"})).toBeDisabled();
  expect(screen.getByText(reason==="not_configured"?/Presence checks require a registered automation connection/:reason==="tenancy_inactive"?/active tenancies/:reason==="tenancy_busy"?/operation is in progress/:/provider is currently unavailable/)).toBeVisible();c.client.clear();
});

// Acceptance is only progress; poll the exact child until its dated results are published.
it("queues once and displays background completion",async()=>{
  let server:RequiredUsersDirectory=configured;
  const start=vi.spyOn(api,"checkRequiredUsers").mockImplementation(async()=>{server={...configured,pending_operation_id:checkId};return receipt;});
  const c=mount(configured);c.read.mockImplementation(()=>Promise.resolve(server));
  await screen.findByText("otm-automation");
  expect(screen.getByRole("button",{name:"Refresh user data"})).toHaveClass("secondary");
  await userEvent.click(screen.getByRole("button",{name:"Refresh user data"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Refreshing user data…"})).toBeDisabled());
  expect(start).toHaveBeenCalledTimes(1);
  expect(start.mock.calls[0][0]).toBe(id);
  const first=start.mock.calls[0][1].client_request_key;
  expect(first).toMatch(/^[0-9a-f-]{36}$/);
  server={...configured,pending_operation_id:null,users:configured.users.map(u=>({...u,presence:{state:"present",checked_at:"2026-11-06T12:00:00Z",stale:false,operation_id:checkId}})) as RequiredUsersDirectory["users"]};
  await waitFor(()=>expect(screen.getAllByText("Present",{exact:true})).toHaveLength(2),{timeout:3000});
  expect(screen.getByRole("button",{name:"Refresh user data"})).toBeEnabled();
  await userEvent.click(screen.getByRole("button",{name:"Refresh user data"}));
  await waitFor(()=>expect(start).toHaveBeenCalledTimes(2));
  expect(start.mock.calls[1][1].client_request_key).not.toBe(first);c.client.clear();
});

// Losing the HTTP response preserves its command key; retry never creates duplicate work.
it("retries an uncertain request with the original key",async()=>{
  const start=vi.spyOn(api,"checkRequiredUsers").mockRejectedValueOnce(new ApiError(503)).mockResolvedValue(receipt);
  const c=mount(configured);await screen.findByText("otm-automation");
  await userEvent.click(screen.getByRole("button",{name:"Refresh user data"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to confirm");
  await userEvent.click(screen.getByRole("button",{name:"Retry user refresh"}));
  await waitFor(()=>expect(start).toHaveBeenCalledTimes(2));
  expect(start.mock.calls[1][1]).toEqual(start.mock.calls[0][1]);c.client.clear();
});

// Mutation authorization failure hides all cached identities even if the concurrent GET still succeeds.
it.each([401,403])("hides cached data after denied check %s",async status=>{
  vi.spyOn(api,"checkRequiredUsers").mockRejectedValue(new ApiError(status));
  const c=mount(configured);await screen.findByText("otm-automation");
  await userEvent.click(screen.getByRole("button",{name:"Refresh user data"}));
  await waitFor(()=>expect(c.expired).toHaveBeenCalled());
  expect(screen.queryByText("otm-automation")).not.toBeInTheDocument();c.client.clear();
});

// A response arriving after navigation updates only its originating tenancy's private cache.
it("does not apply a late command receipt to another tenancy",async()=>{
  let resolve!:(value:typeof receipt)=>void;
  vi.spyOn(api,"checkRequiredUsers").mockReturnValue(new Promise(done=>{resolve=done;}));
  const c=mount(configured);await screen.findByText("otm-automation");
  await userEvent.click(screen.getByRole("button",{name:"Refresh user data"}));
  const other="22222222-2222-4222-8222-222222222222";
  c.read.mockResolvedValue({...directory,tenancy_id:other,users:directory.users.map(u=>({...u,identity:{...u.identity!,user_name:"other-"+u.purpose}})) as RequiredUsersDirectory["users"]});
  c.rerender(<QueryClientProvider client={c.client}><RequiredUsers tenancyId={other} expired={c.expired} navigate={c.navigate}/></QueryClientProvider>);
  await screen.findByText("other-automation");resolve(receipt);
  await waitFor(()=>expect(c.client.getQueryData<RequiredUsersDirectory>(["tenancies","required-users",id])?.pending_operation_id).toBe(checkId));
  expect(screen.queryByRole("button",{name:"Refreshing user data…"})).not.toBeInTheDocument();
  expect(screen.getByText("other-automation")).toBeVisible();c.client.clear();
});

// A malformed acceptance does not produce a false completed check or arbitrary navigation target.
it("rejects a receipt without an operation reference",async()=>{
  vi.spyOn(api,"checkRequiredUsers").mockResolvedValue({...receipt,operation_id:null});
  const c=mount(configured);await screen.findByText("otm-automation");
  await userEvent.click(screen.getByRole("button",{name:"Refresh user data"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to confirm");
  expect(screen.queryByText("Present",{exact:true})).not.toBeInTheDocument();c.client.clear();
});

// Inventory links land keyboard users on the requested facts after the async record load.
it("focuses the required-users heading for its deep link and refreshes inventory caches",async()=>{
  history.replaceState(null,"",`/tenancies/${id}#required-users`);
  const c=mount();
  const invalidate=vi.spyOn(c.client,"invalidateQueries");
  await screen.findByText("otm-automation");
  await waitFor(()=>expect(screen.getByRole("heading",{name:"Required users"})).toHaveFocus());
  expect(invalidate).toHaveBeenCalledWith({queryKey:["tenancies","list"]});
  expect(invalidate).toHaveBeenCalledWith({queryKey:["tenancies","detail",id]});
  history.replaceState(null,"","/");
  c.client.clear();
});


// An unavailable record read still lands on the requested section rather than stranding navigation.
it("focuses an unavailable section without revealing retained identity facts",async()=>{
  history.replaceState(null,"",`/tenancies/${id}#required-users`);
  const c=mount(Promise.reject(new ApiError(503)));
  await screen.findByText("Unable to load required user records. Try again.");
  await waitFor(()=>expect(screen.getByRole("heading",{name:"Required users"})).toHaveFocus());
  expect(screen.getByRole("region",{name:"Required users"})).toHaveAttribute("id","required-users");
  expect(screen.queryByText("otm-automation")).not.toBeInTheDocument();
  history.replaceState(null,"","/");c.client.clear();
});


// Unqualified accounts cannot force refresh; stored facts are revalidated without another UI action.
it("explains unavailable refresh and exposes no duplicate saved-record action",async()=>{
  const check=vi.spyOn(api,"checkRequiredUsers");
  const c=mount({...directory,check_available:false,check_unavailable_reason:"not_configured"});
  await screen.findByText(/Presence checks require a registered automation connection/);
  const action=screen.getByRole("button",{name:"Refresh user data"});
  expect(action).toBeDisabled();
  expect(action).toHaveAccessibleDescription(/Existing tenancies are not enrolled automatically/);
  expect(screen.getByText(/For local testing, complete setup/)).toBeVisible();
  expect(screen.queryByRole("button",{name:"Refresh required users"})).toBeNull();
  c.read.mockResolvedValue({...directory,check_available:true,check_unavailable_reason:null});
  await c.client.invalidateQueries({queryKey:["tenancies","required-users",id]});
  await waitFor(()=>expect(action).toBeEnabled());
  expect(action).not.toHaveAttribute("aria-describedby");
  expect(screen.queryByText(/Existing tenancies are not enrolled automatically/)).not.toBeInTheDocument();
  expect(check).not.toHaveBeenCalled();c.client.clear();
});


// Policy drift remains separate from a present identity and never exposes configured networks.
it("shows recovery MFA drift beside verified network controls and present users", async()=>{
  const c=mount({...configured, recovery_console:{state:"drift",mfa_exemption:"drift",network_boundary:"verified",checked_at:"2026-11-07T12:00:00Z",operation_id:checkId},
    users:configured.users.map(u=>({...u,presence:{state:"present",checked_at:"2026-11-07T12:00:00Z",operation_id:checkId}})) as RequiredUsersDirectory["users"]});
  await screen.findByText("Policy drift");
  const card=screen.getByRole("heading",{name:"Recovery user"}).closest("li")!;
  expect(within(card).getByText("Present",{exact:true})).toBeVisible();
  expect(within(card).getByText("Console MFA exemption")).toBeVisible();
  expect(within(card).getByText("Approved-network restriction")).toBeVisible();
  expect(within(card).getByText("Verified in simulation")).toBeVisible();
  await userEvent.click(within(card).getByRole("link",{name:/^View policy check, /}));
  expect(c.navigate).toHaveBeenCalledWith("/operations/"+checkId+"#recovery-policy");
  c.client.clear();
});

// Stale policy evidence cannot retain a positive current label after desired settings change.
it("shows stale policy controls without asserting verified readiness", async()=>{
  const c=mount({...configured,recovery_console:{state:"stale",mfa_exemption:"verified",network_boundary:"verified",checked_at:"2026-11-07T12:00:00Z",operation_id:checkId}});
  await screen.findAllByText("Check out of date");
  expect(screen.queryByText("Verified in simulation")).not.toBeInTheDocument();
  c.client.clear();
});

// Unverified policy does not create a fake missing-user signal.
it("keeps incomplete policy evidence visibly unverified", async()=>{
  const c=mount({...configured,recovery_console:{state:"unknown",mfa_exemption:"unknown",network_boundary:"unknown"}});
  await screen.findByText("Console MFA exemption");
  expect(screen.getAllByText("Unable to verify")).toHaveLength(2);
  c.client.clear();
});

// Presence never substitutes for required assignments; each read retains its own provenance.
it.each(["verified","missing","unknown"] as const)("shows automation assignment result %s separately from presence", async state => {
  const value = {...directory,users:directory.users.map(user => user.purpose === "automation" ? {...user,administrator_access:{group:state,domain_role:state,stale:false,checked_at:"2026-11-09T12:00:00Z",operation_id:id}} : user)} as RequiredUsersDirectory;
  mount(value);
  const heading=await screen.findByRole("heading",{name:"Automation user"});
  const card=within(heading.closest("li")!);
  expect(card.getByText("Administrators group")).toBeInTheDocument();
  expect(card.getByText("Domain administrator role")).toBeInTheDocument();
  expect(card.getAllByText(state === "verified" ? "Verified in simulation" : state === "missing" ? "Missing or disabled" : "Unable to verify")).toHaveLength(2);
  expect(card.getByRole("link",{name:/^View assignment check, /})).toHaveAttribute("href","/operations/"+id+"#automation-assignment");
});

// Expired assignment evidence remains dated and neutral even when the last observation passed.
it("marks retained assignment results out of date", async () => {
  mount({...directory,users:directory.users.map(user=>user.purpose === "automation" ? {...user,administrator_access:{group:"verified",domain_role:"verified",stale:true,checked_at:"2026-11-09T12:00:00Z",operation_id:id}} : user)} as RequiredUsersDirectory);
  await screen.findByText("otm-automation");
  expect(screen.getAllByText("Check out of date")).toHaveLength(2);
  expect(screen.queryByText("Verified in simulation")).not.toBeInTheDocument();
});

// Compact UTC dates keep distinct check destinations even across local-time date boundaries.
it("groups date-only provenance below badges with the exact check links", async () => {
  const assignment="22222222-2222-4222-8222-222222222222",policy="33333333-3333-4333-8333-333333333333";
  const c=mount({...directory,users:directory.users.map(user=>({...user,presence:{state:"present",checked_at:"2026-11-09T00:10:00Z",stale:false,operation_id:id},...(user.purpose==="automation"?{administrator_access:{group:"verified",domain_role:"verified",stale:false,checked_at:"2026-11-10T00:10:00Z",operation_id:assignment}}:{})})),recovery_console:{state:"verified",mfa_exemption:"verified",network_boundary:"verified",checked_at:"2026-11-11T00:10:00Z",operation_id:policy}} as RequiredUsersDirectory);
  const presence=await screen.findAllByRole("link",{name:"View presence check, Nov 9, 2026"});
  expect(presence).toHaveLength(2);
  const assignmentLink=screen.getByRole("link",{name:"View assignment check, Nov 10, 2026"});
  const policyLink=screen.getByRole("link",{name:"View policy check, Nov 11, 2026"});
  expect(assignmentLink).toHaveTextContent(/^Nov 10, 2026$/);
  expect(assignmentLink.querySelector("time")).toHaveAttribute("datetime","2026-11-10T00:10:00Z");
  expect(assignmentLink).toHaveAttribute("title",expect.stringContaining("UTC"));
  expect(assignmentLink).toHaveAttribute("href","/operations/"+assignment+"#automation-assignment");
  expect(policyLink).toHaveAttribute("href","/operations/"+policy+"#recovery-policy");
  for(const link of [...presence,assignmentLink,policyLink]){
    const card=link.closest("li")!,footer=card.querySelector(".required-user-checks")!,facts=card.querySelector(".required-user-facts")!;
    expect(facts.compareDocumentPosition(footer)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(footer.textContent).not.toMatch(/\d+:\d+/);
  }
  await userEvent.click(assignmentLink);
  expect(c.navigate).toHaveBeenCalledWith("/operations/"+assignment+"#automation-assignment");
});

// A legacy dated result without a check reference remains readable without inventing a destination.
it("shows a date without a link when operation provenance is absent", async () => {
  mount({...directory,users:directory.users.map(user=>({...user,presence:{state:"unknown",checked_at:"2026-11-09T00:10:00Z",operation_id:null}}))} as RequiredUsersDirectory);
  await screen.findAllByText("Presence last attempt (UTC)");
  expect(screen.getAllByText("Nov 9, 2026")).toHaveLength(2);
  expect(screen.queryByRole("link",{name:/^View presence check/})).not.toBeInTheDocument();
});

// The compact recovery row reports only assignments, with the individual facts behind disclosure.
it.each([
  ["verified","verified",false,"Assigned"],
  ["missing","verified",false,"Missing"],
  ["verified","missing",false,"Missing"],
  ["unknown","verified",false,"Unverified"],
  ["not_checked","not_checked",false,"Not checked"],
  ["verified","verified",true,"Out of date"],
] as const)("summarizes recovery assignments %s/%s stale=%s",async(group,domain_role,stale,label)=>{
  const c=mount({...directory,users:directory.users.map(user=>user.purpose==="recovery"?{...user,administrator_access:{group,domain_role,stale,checked_at:group==="not_checked"?null:"2026-11-09T12:00:00Z",operation_id:group==="not_checked"?null:id}}:user)} as RequiredUsersDirectory);
  const heading=await screen.findByRole("heading",{name:"Recovery user"});
  const card=within(heading.closest("li")!);
  const summary=card.getByLabelText(`Administrator assignments: ${label} (simulation)`);
  expect(summary).toBeVisible();
  expect(summary).toHaveAttribute("title",expect.stringContaining("does not establish password readiness"));
  const disclosure=card.getByText("Identity details");
  await userEvent.click(disclosure);
  expect(card.getByText("Administrators group")).toBeVisible();
  expect(card.getByText("Domain administrator role")).toBeVisible();
  if(group!=="not_checked")expect(card.getByRole("link",{name:/^View assignment check, /})).toHaveAttribute("href","/operations/"+id+"#recovery-assignment");
  c.client.clear();
});
