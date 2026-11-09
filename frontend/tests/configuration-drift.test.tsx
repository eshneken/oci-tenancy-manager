import { act,render,screen,waitFor,within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient,QueryClientProvider } from "@tanstack/react-query";
import { it,expect,vi } from "vitest";
import { ConfigurationDrift } from "../src/ConfigurationDrift";
import { api,ApiError } from "../src/api";
import type { ConfigurationCheckSummary,ConfigurationDriftDirectory,ConfigurationIssue } from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",op="22222222-2222-4222-8222-222222222222",time="2026-11-03T12:00:00Z";
const policy:ConfigurationIssue={category:"policy",state:"different",safe_code:"DIFFERENT",binding_ocid:"ocid1.policy.oc1..example",expected:'{"statements":["Allow expected"]}',observed:'{"statements":["Allow observed"]}',evidence_at:time,retained:false};
const child:ConfigurationCheckSummary={tenancy_id:id,tenancy_name:"Example tenancy",baseline_id:id,baseline_version_number:4,override_categories:["budget"],state:"drifted",checked_at:time,issue_count:1,confirmed_issue_count:1,can_check:true,pending_operation_id:null,last_operation_id:null,stale:false,categories:[policy]};
const directory:ConfigurationDriftDirectory={items:[child],total:1,page:1,pages:1,page_size:10,confirmed_count:1,unavailable_count:0,unchecked_count:0,checking_count:0,provider_mode:"simulated"};

// Exercise real filtering, request admission and evidence rendering without provider or user data.
function mount({identifier=null,data=directory,summary=child,url="/configuration/drift"}:{identifier?:string|null;data?:ConfigurationDriftDirectory;summary?:ConfigurationCheckSummary;url?:string}={}) {
 history.replaceState(null,"",url);
 const read=vi.spyOn(api,"configurationDrift").mockResolvedValue(data);
 const detail=vi.spyOn(api,"configurationCheck").mockResolvedValue(summary);
 const start=vi.spyOn(api,"startConfigurationCheck").mockResolvedValue({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:time});
 const operation=vi.spyOn(api,"operation").mockResolvedValue({operation:{id:op,kind:"configuration_check",state:"queued",stage:"check_assigned_configuration",target_tenancy_ocid:"ocid1.tenancy.oc1..example",accepted_at:time,updated_at:time,completed_at:null,initiated_by:"Example administrator"},steps:[],events:[],events_limited:false});
 const expired=vi.fn(),navigate=vi.fn(),client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}});
 const view=render(<QueryClientProvider client={client}><ConfigurationDrift identifier={identifier} expired={expired} navigate={navigate}/></QueryClientProvider>);
 return {...view,client,read,detail,start,expired,navigate,operation};
}

it("shows confirmed differences separately from all checks and preserves route identity",async()=>{
 const c=mount();await screen.findByRole("link",{name:"Example tenancy"});
 expect(screen.getByRole("button",{name:"Confirmed drift 1"})).toHaveAttribute("aria-pressed","true");
 expect(screen.getByRole("link",{name:"Example tenancy"})).toHaveAttribute("href",`/configuration/drift/${id}?returnTo=%2Fconfiguration%2Fdrift`);
 await userEvent.click(screen.getByRole("link",{name:"Example tenancy"}));expect(c.navigate).toHaveBeenCalled();
 await userEvent.click(screen.getByRole("button",{name:"Checks"}));
 expect(c.navigate).toHaveBeenLastCalledWith("/configuration/drift?tab=checks");
 expect(screen.getByLabelText("Check status")).toBeInTheDocument();
 expect(screen.getByRole("link",{name:"Example tenancy"})).toHaveAttribute("href",`/configuration/drift/${id}?returnTo=%2Fconfiguration%2Fdrift%3Ftab%3Dchecks`);
 await userEvent.click(screen.getByRole("button",{name:"Confirmed drift 1"}));expect(screen.queryByLabelText("Check status")).toBeNull();
});

it("filters, sorts in both directions, pages and clears a tenancy scope",async()=>{
 const c=mount({url:`/configuration/drift?tab=checks&tenancy_id=${id}`,data:{...directory,pages:3}});await screen.findByRole("link",{name:"Example tenancy"});
 await userEvent.type(screen.getByLabelText("Search tenancies"),"Example");
 await userEvent.selectOptions(screen.getByLabelText("Check status"),"unavailable");
 await userEvent.click(screen.getByRole("button",{name:/Last attempt/}));
 await waitFor(()=>expect(c.read).toHaveBeenLastCalledWith(expect.objectContaining({sort:"checked_at",direction:"asc",state:"unavailable",query:"Example",tenancy_id:id}),expect.any(AbortSignal)));
 await userEvent.click(screen.getByRole("button",{name:/Last attempt/}));
 await waitFor(()=>expect(c.read).toHaveBeenLastCalledWith(expect.objectContaining({direction:"desc"}),expect.any(AbortSignal)));
 await userEvent.click(screen.getByRole("button",{name:"Next"}));await waitFor(()=>expect(c.read).toHaveBeenLastCalledWith(expect.objectContaining({page:2}),expect.any(AbortSignal)));
 await userEvent.selectOptions(screen.getByLabelText("Rows per page"),"25");
 await waitFor(()=>expect(c.read).toHaveBeenLastCalledWith(expect.objectContaining({page:1,page_size:25}),expect.any(AbortSignal)));
 await userEvent.click(screen.getByRole("button",{name:"Clear filters"}));expect(screen.getByLabelText("Search tenancies")).toHaveValue("");expect(screen.getByLabelText("Check status")).toHaveValue("all");
});

it("allows previous-page navigation and identifies the active name sort",async()=>{
 const c=mount({data:{...directory,page:2,pages:3}});await screen.findByRole("link",{name:"Example tenancy"});
 await userEvent.click(screen.getByRole("button",{name:"Previous"}));expect(c.read).toHaveBeenLastCalledWith(expect.objectContaining({page:1}),expect.any(AbortSignal));
 await userEvent.click(screen.getByRole("button",{name:/Configuration status/}));await userEvent.click(screen.getByRole("button",{name:/Tenancy ↕/}));
 expect(screen.getByRole("button",{name:/Tenancy ↑/}).closest("th")).toHaveAttribute("aria-sort","ascending");
});

it("queues the exact scope and keeps evidence visible until readback",async()=>{
 const c=mount({identifier:id});await screen.findByRole("heading",{name:"Example tenancy"});
 expect(screen.getByRole("button",{name:"Check now"})).toHaveClass("secondary");
 await userEvent.click(screen.getByRole("button",{name:"Check now"}));
 const message=await screen.findByText(/Check request accepted/);expect(message).toHaveFocus();
 expect(c.start).toHaveBeenCalledWith({client_request_key:expect.any(String),tenancy_id:id},expect.any(AbortSignal));
 expect(screen.getByRole("link",{name:"View operation"})).toHaveAttribute("href","/operations/"+op);
 expect(screen.getByText("Allow observed")).toBeVisible();
 await userEvent.click(screen.getByRole("link",{name:"View operation"}));expect(c.navigate).toHaveBeenLastCalledWith("/operations/"+op);
});

it("queues fleet scope and refreshes rows without an invented healthy result",async()=>{
 const c=mount();await screen.findByRole("link",{name:"Example tenancy"});
 await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));await screen.findByText(/Check request accepted/);
 expect(c.start).toHaveBeenCalledWith(expect.objectContaining({tenancy_id:null}),expect.any(AbortSignal));
 const before=c.read.mock.calls.length;await userEvent.click(screen.getByRole("button",{name:"Refresh"}));await waitFor(()=>expect(c.read.mock.calls.length).toBeGreaterThan(before));
 expect(screen.getByRole("link",{name:"Example tenancy"})).toBeVisible();
});

it.each([400,409,500])("retains safe retry identity after check admission failure %s",async(status)=>{
 const c=mount();c.start.mockRejectedValueOnce(new ApiError(status));await screen.findByRole("link",{name:"Example tenancy"});
 await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));expect(await screen.findByRole("alert")).toHaveTextContent(status===409?"conflicting":status===400?"No eligible":"could not be confirmed");
 const key=c.start.mock.calls[0][0].client_request_key;
 await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));await screen.findByText(/Check request accepted/);
 expect(c.start.mock.calls[1][0].client_request_key).toBe(key);
});

it.each([401,403])("expires authorization on admission failure %s",async(status)=>{
 const c=mount();c.start.mockRejectedValue(new ApiError(status));await screen.findByRole("link",{name:"Example tenancy"});await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));await waitFor(()=>expect(c.expired).toHaveBeenCalled());
});

it("disables duplicate admission while the request is pending",async()=>{
 const c=mount();let complete!:(value:Awaited<ReturnType<typeof api.startConfigurationCheck>>)=>void;c.start.mockReturnValue(new Promise(resolve=>{complete=resolve;}));await screen.findByRole("link",{name:"Example tenancy"});await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));expect(screen.getByRole("button",{name:"Queueing check…"})).toBeDisabled();complete({operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:time});await screen.findByText(/Check request accepted/);
});

it("aborts an unmounted request without publishing a late receipt",async()=>{
 const c=mount();let reject!:(value:unknown)=>void;c.start.mockReturnValue(new Promise((_resolve,no)=>{reject=no;}));await screen.findByRole("link",{name:"Example tenancy"});await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));const signal=c.start.mock.calls[0][1]!;c.unmount();expect(signal.aborted).toBe(true);reject(new Error("aborted"));
});

it.each([404,500,401])("shows bounded directory failure %s and offers retry",async(status)=>{
 const c=mount();c.read.mockRejectedValue(new ApiError(status));await userEvent.click(await screen.findByRole("button",{name:"Refresh"}));expect(await screen.findByRole("alert")).toHaveTextContent(status===404?"could not be found":"could not be loaded");expect(screen.getByRole("link",{name:"Example tenancy"})).toBeVisible();c.read.mockResolvedValue(directory);await userEvent.click(screen.getByRole("button",{name:"Retry"}));await waitFor(()=>expect(screen.queryByRole("alert")).toBeNull());if(status===401)expect(c.expired).toHaveBeenCalled();
});

it.each(["confirmed","checks"] as const)("gives truthful initial empty copy in %s",async(tab)=>{
 const c=mount({data:{...directory,items:[],total:0,confirmed_count:0},url:"/configuration/drift"+(tab==="checks"?"?tab=checks":"")});
 await screen.findByRole("heading",{name:tab==="confirmed"?"No confirmed configuration drift":"No current tenancy checks"});
 if(tab==="confirmed"){await userEvent.click(screen.getByRole("button",{name:"View checks"}));expect(c.navigate).toHaveBeenCalledWith("/configuration/drift?tab=checks");}
});

it("distinguishes a filtered empty result from healthy configuration",async()=>{
 const c=mount();await screen.findByRole("link",{name:"Example tenancy"});c.read.mockResolvedValue({...directory,items:[],total:0});await userEvent.type(screen.getByLabelText("Search tenancies"),"absent");await screen.findByRole("heading",{name:"No checks match these filters"});
});

it("renders old same-context evidence without a healthy full-check claim",async()=>{
 mount({identifier:id,summary:{...child,state:"unavailable",stale:true,categories:[{...policy,retained:true},{...policy,category:"quota",state:"matching",retained:false}],pending_operation_id:op}});
 await screen.findByRole("heading",{name:"Example tenancy"});
 expect(screen.getByText(/Earlier confirmed drift is retained/)).toBeVisible();expect(screen.getAllByText(/Check out of date/).length).toBeGreaterThan(0);expect(screen.getByText("Matching (earlier check)")).not.toHaveClass("active");expect(screen.getByRole("button",{name:"Check now"})).toBeDisabled();
 await userEvent.click(screen.getByRole("link",{name:"View pending operation"}));
});

it("renders matching and unavailable rows with distinct status evidence",async()=>{
 mount({data:{...directory,items:[{...child,state:"matching",stale:false,confirmed_issue_count:0,issue_count:0},{...child,tenancy_id:op,tenancy_name:"Old check",state:"not_checked",stale:true,categories:[{...policy,retained:true}]}]}});
 await screen.findByRole("link",{name:"Old check"});expect(screen.getByText("Check out of date")).toBeVisible();expect(screen.getByText("Matching")).toHaveClass("active");expect(screen.getByText(/earlier evidence/)).toBeVisible();
});

it.each(["/tenancies",`/tenancies/${id}`,"/configuration/drift?tab=checks",`/operations/${op}`,"https://malicious.test"]) ("allowlists contextual return %s",async(returnTo)=>{
 const c=mount({identifier:id,url:`/configuration/drift/${id}?returnTo=${encodeURIComponent(returnTo)}`});await screen.findByRole("heading",{name:"Example tenancy"});const back=screen.getByRole("link",{name:/Back to/});expect(back).toHaveAttribute("href",returnTo.startsWith("https:")?"/configuration/drift":returnTo);await userEvent.click(back);expect(c.navigate).toHaveBeenCalled();
});

it("focuses a requested category and links exact baseline and tenancy",async()=>{
 const c=mount({identifier:id,url:`/configuration/drift/${id}?category=policy`});const heading=await screen.findByRole("heading",{name:"Policy statements"});await waitFor(()=>expect(heading).toHaveFocus());await userEvent.click(screen.getByRole("link",{name:"Open tenancy"}));expect(c.navigate).toHaveBeenLastCalledWith("/tenancies/"+id);await userEvent.click(screen.getByRole("link",{name:"Assigned baseline v4"}));expect(c.navigate).toHaveBeenLastCalledWith(expect.stringContaining("baseline="+id));
});

it("shows no-assignment, no-overrides and disabled-check guidance",async()=>{
 mount({identifier:id,summary:{...child,baseline_id:null,baseline_version_number:null,can_check:false,override_categories:[]}});await screen.findByRole("heading",{name:"Example tenancy"});expect(screen.getByText(/None; all categories inherit/)).toBeVisible();expect(screen.getByText(/check is currently unavailable/)).toBeVisible();expect(screen.queryByRole("link",{name:/Assigned baseline/})).toBeNull();
});

it.each(["missing","unavailable","conflict","not_checked"] as const)("does not invent observation evidence for %s",async(state)=>{
 mount({identifier:id,summary:{...child,checked_at:null,categories:[{...policy,state,expected:null,observed:null,binding_ocid:null,evidence_at:null}]}});await screen.findByRole("heading",{name:"Policy statements"});expect(screen.getByText("Expected configuration is unavailable.")).toBeVisible();expect(screen.getByText(state==="missing"?"Object absent.":"No verified observation.")).toBeVisible();if(state==="missing")expect(screen.getByText(/complete authorized read/)).toBeVisible();
});

it("renders statement, exact budget and tag payloads as readable text",async()=>{
 mount({identifier:id,summary:{...child,state:"matching",categories:[{...policy,state:"matching"},{...policy,category:"budget",expected:'{"monthly_amount":"500.0000","currency":"USD","period":"MONTHLY"}',observed:'{"monthly_amount":"250.0000","currency":"USD","period":"MONTHLY"}'},{...policy,category:"tags",expected:'{"namespace":"OTM","defaults":[]}',observed:'{"namespace":"OTM","defaults":[{"key":"team","value":"Example"}]}'}]}});
 await screen.findByRole("heading",{name:"Tag defaults"});expect(screen.getByText("500")).toBeVisible();expect(screen.getByText("250")).toBeVisible();expect(screen.getByText("No tag defaults")).toBeVisible();expect(screen.getByText("key: team · value: Example")).toBeVisible();expect(screen.getAllByText("Matching").every(item=>item.classList.contains("active"))).toBe(true);
});

it.each(["<script>text</script>","null","[]",'{"extra":{"unexpected":"value"}}','{"defaults":["text"]}'])("retains unknown observed content safely: %s",async(value)=>{
 mount({identifier:id,summary:{...child,categories:[{...policy,observed:value}]}});await screen.findByText(value==='<script>text</script>'?value:value==='null'||value==='[]'?value:value.includes("unexpected")?/unexpected/:"text");expect(document.querySelector("script")).toBeNull();
});

// HTTP adapters preserve bounded query fields and use the same same-origin guarded POST path.
it("uses drift/check endpoints with encoded identities and a guarded JSON body",async()=>{
 const fetch=vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify(directory),{status:200,headers:{"Content-Type":"application/json"}})));vi.stubGlobal("fetch",fetch);
 await api.configurationDrift({tab:"checks",query:"Example & team",tenancy_id:undefined});expect(fetch.mock.calls[0][0]).toBe("/api/configuration/drift?tab=checks&query=Example+%26+team");
 await api.configurationCheck(id);expect(fetch.mock.calls[1][0]).toBe("/api/configuration/drift/"+id);
 await api.startConfigurationCheck({client_request_key:op,tenancy_id:null});expect(fetch.mock.calls[2][0]).toBe("/api/configuration/checks");expect(fetch.mock.calls[2][1]).toMatchObject({method:"POST",credentials:"same-origin",headers:{"X-OTM-Request":"1"},body:JSON.stringify({client_request_key:op,tenancy_id:null})});
});

// Both direct routes live in the real shell and their private evidence is removed on sign-out.
it.each([null,id])("routes a direct drift view and purges its private cache: %s",async(identifier)=>{
 history.replaceState(null,"",identifier?`/configuration/drift/${identifier}?category=policy`:"/configuration/drift?tab=checks");
 vi.spyOn(api,"session").mockResolvedValue({display_name:"Example administrator",workspace_id:"unit",expires_at:""});
 vi.spyOn(api,"branding").mockResolvedValue({display_name:"Atlas",logo_url:null,icon_url:null});
 vi.spyOn(api,"operations").mockRejectedValue(new Error("not requested"));
 vi.spyOn(api,"organizationReviews").mockRejectedValue(new Error("not requested"));
 vi.spyOn(api,"configurationDrift").mockResolvedValue(directory);vi.spyOn(api,"configurationCheck").mockResolvedValue(child);vi.spyOn(api,"logout").mockResolvedValue(undefined);
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}});client.setQueryData(["configuration-drift","private"],directory);client.setQueryData(["configuration-check","private"],child);
 const {App}=await import("../src/App");render(<QueryClientProvider client={client}><App/></QueryClientProvider>);
 await screen.findByRole("heading",{level:1,name:identifier?"Example tenancy":"Configuration drift"});
 if(identifier)await waitFor(()=>expect(screen.getByRole("heading",{name:"Policy statements"})).toHaveFocus());
 expect(screen.getByRole("link",{name:"Configuration drift"})).toHaveAttribute("aria-current","page");expect(screen.getByRole("link",{name:"Administrators"})).not.toHaveAttribute("aria-current");
 await userEvent.click(screen.getByRole("button",{name:"Sign out"}));await screen.findByRole("heading",{name:"Sign in"});expect(client.getQueriesData({queryKey:["configuration-drift"]})).toEqual([]);expect(client.getQueriesData({queryKey:["configuration-check"]})).toEqual([]);
});

// An immutable recipe returns to the check that supplied its context rather than a different tenancy page.
it("retains an exact scoped check return through the baseline recipe",async()=>{
 const {baselineHref,baselineReturn}=await import("../src/baselineNavigation");
 const href=baselineHref(id,"/configuration/drift/"+id);
 expect(baselineReturn(href.slice(href.indexOf("?")))).toEqual({path:"/configuration/drift/"+id,label:"Back to configuration check"});
});

// Only this accepted operation's sealed result ends the acknowledgement; cached older evidence cannot.
it("clears the scoped acceptance only after the exact check completes",async()=>{
 const c=mount({identifier:id,summary:{...child,last_operation_id:id}});
 await screen.findByRole("heading",{name:"Example tenancy"});
 await userEvent.click(screen.getByRole("button",{name:"Check now"}));
 await screen.findByText(/Check request accepted/);
 expect(screen.queryByText(/until verification completes/)).toBeNull();
 c.detail.mockResolvedValue({...child,last_operation_id:op,pending_operation_id:op,state:"checking"});
 await userEvent.click(screen.getByRole("button",{name:"Refresh"}));
 await screen.findByRole("link",{name:"View pending operation"});expect(screen.getByText(/Check request accepted/)).toBeVisible();
 c.detail.mockResolvedValue({...child,last_operation_id:op,pending_operation_id:null,state:"unavailable"});
 await userEvent.click(screen.getByRole("button",{name:"Refresh"}));
 await waitFor(()=>expect(screen.queryByText(/Check request accepted/)).toBeNull());
 expect(screen.getByText(/latest attempt did not verify all four categories/)).toBeVisible();
});

// Both management views expose the same independent labels without counting unverifiable categories as drift.
it.each([
 ["matching",false,0,["Matching"]], ["not_checked",false,0,["Not checked"]],
 ["not_checked",true,0,["Check out of date"]], ["unavailable",false,0,["Unable to verify"]],
 ["checking",false,0,["Checking"]], ["superseded",false,0,["Not checked"]],
 ["drifted",false,2,["Configuration drift · 2 categories"]],
 ["unavailable",true,2,["Configuration drift · 2 categories","Check out of date","Unable to verify"]],
 ["checking",true,1,["Configuration drift · 1 category","Check out of date","Checking"]],
] as const)("keeps check directory labels exact for %s stale=%s confirmed=%s",async(state,stale,confirmed,labels)=>{
 mount({url:"/configuration/drift?tab=checks",data:{...directory,items:[{...child,state,stale,issue_count:confirmed,confirmed_issue_count:confirmed}]}});
 const row=await screen.findByRole("row",{name:new RegExp("Example tenancy")});
 for(const label of labels)expect(within(row).getByText(label)).toBeVisible();
 expect(within(row).queryByText(/4 categories|4 issues/)).toBeNull();expect(within(row).queryByText("Affected categories")).toBeNull();
});

it("keeps retained confirmed drift alongside failed/stale summary on the exact tenancy detail",async()=>{
 mount({identifier:id,summary:{...child,state:"unavailable",stale:true,issue_count:2,confirmed_issue_count:2}});
 const section=(await screen.findByRole("heading",{name:"Assigned configuration"})).closest("section")!;
 for(const label of ["Configuration drift · 2 categories","Check out of date","Unable to verify"])expect(within(section).getByText(label)).toBeVisible();
 expect(within(section).queryByText("Matching")).toBeNull();
});

it("explains aged/unchecked/failed coverage even when the confirmed queue is empty",async()=>{
 const c=mount({data:{...directory,items:[],total:0,confirmed_count:0,stale_count:3,unchecked_count:2,unavailable_count:1}});
 await screen.findByRole("heading",{name:"No confirmed configuration drift"});
 expect(screen.getByText(/Check status: 3 out of date · 2 not checked · 1 unable to verify/)).toBeVisible();
 await userEvent.click(screen.getByRole("button",{name:"View checks"}));expect(c.navigate).toHaveBeenCalledWith("/configuration/drift?tab=checks");
 await userEvent.selectOptions(screen.getByLabelText("Check status"),"stale");await waitFor(()=>expect(c.read).toHaveBeenLastCalledWith(expect.objectContaining({state:"stale",page:1}),expect.any(AbortSignal)));
});

// Native execution completion, rather than queue admission, makes inventory and evidence caches refresh.
it.each(["succeeded","failed"] as const)("refreshes both directories and scoped evidence when accepted work is %s",async(state)=>{
 const c=mount({identifier:id,summary:{...child,confirmed_issue_count:2,issue_count:2}});
 await screen.findByRole("heading",{name:"Example tenancy"});
 c.client.setQueryData(["tenancies","cached"],{old:true});c.client.setQueryData(["configuration-drift","cached"],{old:true});
 c.start.mockImplementation(async()=>{c.detail.mockResolvedValue({...child,state:"checking",pending_operation_id:op,confirmed_issue_count:2,issue_count:2});return{operation_id:op,state:"queued",provider_mode:"simulated",accepted_at:time};});
 await userEvent.click(screen.getByRole("button",{name:"Check now"}));await screen.findByRole("link",{name:"View pending operation"});
 expect(screen.getByText("Configuration drift · 2 categories")).toBeVisible();
 const invalidate=vi.spyOn(c.client,"invalidateQueries");
 c.detail.mockResolvedValue({...child,state:state==="succeeded"?"matching":"unavailable",pending_operation_id:null,last_operation_id:op,confirmed_issue_count:state==="succeeded"?0:2,issue_count:state==="succeeded"?0:2});
 act(()=>c.client.setQueryData(["operations","detail",op],{operation:{id:op,state},steps:[],events:[],events_limited:false}));
 await waitFor(()=>expect(invalidate).toHaveBeenCalledWith({queryKey:["tenancies"]}));expect(invalidate).toHaveBeenCalledWith({queryKey:["configuration-drift"]});expect(invalidate).toHaveBeenCalledWith({queryKey:["configuration-check"]});
 if(state==="failed"){await screen.findByText("Unable to verify");expect(screen.getByText("Configuration drift · 2 categories")).toBeVisible();}else await waitFor(()=>expect(screen.queryByText("Configuration drift · 2 categories")).toBeNull());
});

it("refreshes even a fleet completion that leaves no confirmed queue rows",async()=>{
 const c=mount({data:{...directory,items:[],total:0,confirmed_count:0}});await screen.findByRole("heading",{name:"No confirmed configuration drift"});
 await userEvent.click(screen.getByRole("button",{name:"Check all tenancies"}));await screen.findByText(/Check request accepted/);
 const invalidate=vi.spyOn(c.client,"invalidateQueries");act(()=>c.client.setQueryData(["operations","detail",op],{operation:{id:op,state:"succeeded"}}));
 await waitFor(()=>expect(invalidate).toHaveBeenCalledWith({queryKey:["tenancies"]}));expect(invalidate).toHaveBeenCalledWith({queryKey:["configuration-drift"]});await waitFor(()=>expect(screen.queryByText(/Check request accepted/)).toBeNull());
});

it("refreshes an inactive scoped evidence cache when an externally started fleet check finishes",async()=>{
 const c=mount({url:"/configuration/drift?tab=checks",data:{...directory,checking_count:1}});await screen.findByRole("link",{name:"Example tenancy"});
 c.client.setQueryData(["configuration-check","another-child"],{old:true});c.client.setQueryData(["tenancies","cached"],{old:true});
 c.read.mockResolvedValue({...directory,checking_count:0});await userEvent.click(screen.getByRole("button",{name:"Refresh"}));
 await waitFor(()=>expect(c.client.getQueryState(["configuration-check","another-child"])?.isInvalidated).toBe(true));expect(c.client.getQueryState(["tenancies","cached"])?.isInvalidated).toBe(true);
});

// Age alone is not a failed API read: preserve historical values with an explicit out-of-date label.
it.each([true,false])("describes age-only category evidence without inventing a read failure, prior value=%s",async(observed)=>{
 mount({identifier:id,summary:{...child,state:"not_checked",stale:true,issue_count:0,confirmed_issue_count:0,categories:[{...policy,state:"unavailable",safe_code:"CHECK_STALE",observed:observed?policy.observed:null}]}});
 const category=await screen.findByRole("region",{name:"Policy statements"});
 expect(within(category).getByText("Check out of date")).toBeVisible();expect(within(category).queryByText("Unable to verify")).toBeNull();
 expect(within(category).getByRole("heading",{name:"Observed (earlier check)"})).toBeVisible();
 expect(within(category).queryByText(/check could not verify/)).toBeNull();
 expect(within(category).getByText(observed?"Allow observed":"No earlier verified observation.")).toBeVisible();
});

it("retains aged confirmed findings without falsely claiming the earlier complete read failed",async()=>{
 mount({identifier:id,summary:{...child,state:"drifted",stale:true,categories:[{...policy,retained:true}]}});
 const category=await screen.findByRole("region",{name:"Policy statements"});expect(within(category).getByText(/Its evidence is out of date/)).toBeVisible();expect(within(category).queryByText(/latest check could not verify/)).toBeNull();expect(screen.getByText("Configuration drift · 1 category")).toBeVisible();
});

it("uses out-of-date wording for aged managed-object rows in the checks list",async()=>{
 mount({url:"/configuration/drift?tab=checks",data:{...directory,items:[{...child,state:"not_checked",stale:true,confirmed_issue_count:0,issue_count:0,categories:[{...policy,state:"unavailable",safe_code:"CHECK_STALE"}]}]}});
 const row=await screen.findByRole("row",{name:/Example tenancy/});expect(within(row).getByText("Policy statements: Check out of date")).toBeVisible();expect(within(row).queryByText(/Unable to verify/)).toBeNull();
});

// A service outage on one private read cannot hide authorization loss on the accepted-operation observer.
it.each([null,id])("expires once when evidence is unavailable but operation authorization is denied, scope=%s",async(identifier)=>{
 const c=mount({identifier});await screen.findByRole(identifier?"heading":"link",{name:"Example tenancy"});
 await userEvent.click(screen.getByRole("button",{name:identifier?"Check now":"Check all tenancies"}));await screen.findByText(/Check request accepted/);
 (identifier?c.detail:c.read).mockRejectedValue(new ApiError(500));c.operation.mockRejectedValue(new ApiError(401));
 await act(async()=>{await Promise.all([c.client.refetchQueries({queryKey:[identifier?"configuration-check":"configuration-drift"]}),c.client.refetchQueries({queryKey:["operations","detail",op]})]);});
 await waitFor(()=>expect(c.expired).toHaveBeenCalledTimes(1));
 c.operation.mockRejectedValue(new ApiError(403));await act(async()=>{await c.client.refetchQueries({queryKey:["operations","detail",op]});});expect(c.expired).toHaveBeenCalledTimes(1);
});

// A newly loading tab is not a qualified zero-pending observation and must not announce completion.
it("does not refresh unrelated caches merely because a pending fleet view switches tabs",async()=>{
 const c=mount({data:{...directory,checking_count:1}});await screen.findByRole("link",{name:"Example tenancy"});
 let complete!:(value:ConfigurationDriftDirectory)=>void;c.read.mockReturnValue(new Promise(resolve=>{complete=resolve;}));const invalidate=vi.spyOn(c.client,"invalidateQueries");
 await userEvent.click(screen.getByRole("button",{name:"Checks"}));await screen.findByText("Loading configuration checks…");expect(invalidate).not.toHaveBeenCalled();
 complete({...directory,checking_count:1});await screen.findByRole("link",{name:"Example tenancy"});expect(invalidate).not.toHaveBeenCalled();
});
