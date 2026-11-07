import {act,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {expect,it,vi} from "vitest";
import {EmailContactSummary} from "../src/EmailContacts";
import {EmailNotifications} from "../src/EmailNotifications";
import {Operations} from "../src/Operations";
import {App} from "../src/App";
import {api,ApiError} from "../src/api";
import type {EmailContacts,EmailPolicyView,NotificationSummary,OperationDetail} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",time="2026-11-04T12:00:00Z",testEmail="capture@example.test";
const route={original_email:"owner@example.test",effective_email:testEmail,environment:"staging" as const,policy_hash:"a".repeat(64),redirected:true};
const contacts:EmailContacts={activation:{...route,original_email:null},owner:route};
const notice:NotificationSummary={id,state:"sent",event:"action_required",recipient:testEmail,original_recipient:null,created_at:time,updated_at:time,last_attempt_at:time,redirected:true,attempts:1,safe_code:"SMTP_ACCEPTED"};
const operation:OperationDetail={operation:{id,kind:"inspect_import",state:"failed",stage:"inspect_target",target_tenancy_ocid:"ocid1.tenancy.oc1..synthetic",accepted_at:time,updated_at:time,completed_at:time,initiated_by:"Original administrator"},steps:[],events:[],events_limited:false,notifications:[notice]};

// Reuse the real authenticated shell without reaching an installation or corporate identity service.
function shell(policy:EmailPolicyView={environment:"staging",redirected:true,effective_test_email:testEmail},session=true){
 history.replaceState(null,"","/operations/"+id);
 vi.spyOn(api,"session").mockResolvedValue(session?{display_name:"Recovery administrator",workspace_id:"synthetic",expires_at:""}:null);
 vi.spyOn(api,"branding").mockResolvedValue({display_name:"Atlas",icon_url:null,logo_url:null});
 vi.spyOn(api,"operations").mockRejectedValue(new Error("count unavailable"));vi.spyOn(api,"organizationReviews").mockRejectedValue(new Error("count unavailable"));vi.spyOn(api,"operation").mockResolvedValue(operation);vi.spyOn(api,"logout").mockResolvedValue(undefined);
 const read=vi.spyOn(api,"emailPolicy").mockResolvedValue(policy),client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}});
 render(<QueryClientProvider client={client}><App/></QueryClientProvider>);return {read,client};
}

it("shows separate original identities and effective test destinations without editable contact fields",()=>{
 render(<EmailContactSummary contacts={contacts} activation/>);const section=screen.getByRole("region",{name:"Tenancy email contacts"});expect(section).toHaveTextContent("Original contact: Not configured");expect(section).toHaveTextContent("Original contact: owner@example.test");expect(screen.getAllByText("Test delivery: "+testEmail)).toHaveLength(2);expect(screen.queryByRole("textbox")).toBeNull();expect(section).toHaveTextContent("identities remain unchanged");
});

it("labels import bootstrap contacts without implying a new activation",()=>{
 render(<EmailContactSummary contacts={{activation:{...contacts.activation,redirected:false,effective_email:"administrator@example.test",environment:"production"},owner:{...route,redirected:false,effective_email:route.original_email,environment:"production"}}} activation={false}/>);expect(screen.queryByText("Activation / bootstrap email")).toBeNull();expect(screen.getByText("owner@example.test")).toBeVisible();expect(screen.getByText("Bootstrap contact email")).toBeVisible();expect(screen.queryByText(/Test delivery/)).toBeNull();expect(screen.queryByText(/Non-production delivery/)).toBeNull();
});

it("keeps legacy and missing contacts truthful without inventing a mailbox",()=>{
 const view=render(<EmailContactSummary contacts={null} activation/>);expect(screen.queryByRole("region")).toBeNull();view.rerender(<EmailContactSummary contacts={{activation:{...contacts.activation,redirected:false,effective_email:null},owner:{...route,redirected:false,effective_email:null}}} activation/>);expect(screen.getAllByText("Not configured")).toHaveLength(2);expect(screen.queryByText(testEmail)).toBeNull();
});

it.each([
 ["pending","Pending"],["blocked","Delivery blocked"],["sending","Submitting to mail server"],["sent","Accepted by mail server"],["failed","Delivery failed"],["unknown","Delivery not confirmed"],["superseded","Superseded"],
] as const)("reports %s without claiming inbox delivery or exposing action controls",(state,label)=>{
 render(<EmailNotifications notifications={[{...notice,state,event:state==="failed"?"terminal_failure":"action_required"}]}/>);expect(screen.getByText(label)).toBeVisible();expect(screen.getByText(testEmail)).toBeVisible();expect(screen.getByText("Original contact: Not configured")).toBeVisible();expect(screen.queryByRole("button")).toBeNull();expect(screen.queryByText("Delivered")).toBeNull();if(state==="unknown")expect(screen.getByText(/will not be resent automatically/)).toBeVisible();if(state==="superseded")expect(screen.getByText(/superseded before sending/)).toBeVisible();
});

it("does not imply a pending message when no lifecycle notice was recorded",()=>{
 render(<EmailNotifications notifications={[]}/>);expect(screen.getByText("No email notice recorded for this operation.")).toBeVisible();expect(screen.queryByText("Pending")).toBeNull();
});

it("distinguishes unattempted messages from historical attempts with missing timestamps",()=>{
 render(<EmailNotifications notifications={[{...notice,id:"first",state:"pending",redirected:false,recipient:null,attempts:0,last_attempt_at:null},{...notice,id:"second",last_attempt_at:null,attempts:1}]}/>);expect(screen.getByText("Not configured")).toBeVisible();expect(screen.getByText("Not attempted")).toBeVisible();expect(screen.getByText("Not recorded")).toBeVisible();expect(screen.getByText("Delivery recipient")).toBeVisible();expect(screen.getByText("Test recipient")).toBeVisible();
});

it.each([
 ["EMAIL_RESPONSIBLE_ADMIN_UNAVAILABLE","does not have an available delivery contact"],["EMAIL_ROUTE_BLOCKED","does not satisfy"],["EMAIL_CONTEXT_CHANGED","cannot use a different recipient"],["EMAIL_RETRIES_EXHAUSTED","attempts have ended"],["SMTP_REJECTED","rejected this submission"],["SMTP_UNAVAILABLE","could not be reached"],
])("maps only fixed guidance for %s",(safe_code,part)=>{
 render(<EmailNotifications notifications={[{...notice,state:"blocked",safe_code}]}/>);expect(screen.getByText(new RegExp(part))).toBeVisible();expect(screen.queryByText(safe_code)).toBeNull();
});

it("never renders arbitrary delivery diagnostics or unsafe addresses as markup",()=>{
 render(<EmailNotifications notifications={[{...notice,state:"failed",recipient:"<script>recipient</script>",safe_code:"password=private-provider-error"}]}/>);expect(screen.getByText("<script>recipient</script>")).toBeVisible();expect(document.querySelector("script")).toBeNull();expect(screen.queryByText(/private-provider-error/)).toBeNull();expect(screen.getByText(/Review the recorded contact/)).toBeVisible();
});

it("loads non-production routing only after authentication and purges it on logout",async()=>{
 const c=shell();await screen.findByText(/Non-production email routing/);expect(screen.getByText("Recovery administrator")).toBeVisible();expect(screen.getByText(/previously recorded activation contacts remain unchanged/)).toBeVisible();expect(c.read).toHaveBeenCalledWith(expect.any(AbortSignal));expect(c.client.getQueryData(["email-policy"])).toBeDefined();await userEvent.click(screen.getByRole("button",{name:"Sign out"}));await screen.findByRole("heading",{name:"Sign in"});expect(c.client.getQueryData(["email-policy"])).toBeUndefined();expect(screen.queryByText(testEmail)).toBeNull();
});

it("keeps policy contacts out of the public sign-in screen",async()=>{
 const c=shell(undefined,false);await screen.findByRole("heading",{name:"Sign in"});expect(c.read).not.toHaveBeenCalled();expect(screen.queryByText(/Non-production email routing/)).toBeNull();
});

it("does not display a redirect banner in a production profile",async()=>{
 shell({environment:"production",redirected:false,effective_test_email:null});await screen.findByRole("heading",{name:"Import inspection"});expect(screen.queryByText(/Non-production email routing/)).toBeNull();
});

it.each([401,403])("ends the privileged view when email-policy access is denied: %s",async(status)=>{
 const c=shell();c.read.mockRejectedValue(new ApiError(status));await c.client.invalidateQueries({queryKey:["email-policy"]});await screen.findByRole("heading",{name:"Sign in"});expect(c.client.getQueryData(["email-policy"])).toBeUndefined();
});

it("does not reveal raw policy failures in the application",async()=>{
 const c=shell();c.read.mockRejectedValue(new Error("private SMTP password"));await c.client.invalidateQueries({queryKey:["email-policy"]});await screen.findByRole("heading",{name:"Import inspection"});expect(screen.queryByText(/private SMTP/)).toBeNull();
});

it("shows an operation's recorded notification without adding resend or mailbox controls",async()=>{
 vi.spyOn(api,"operation").mockResolvedValue(operation);render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})}><Operations operationId={id} expired={vi.fn()} navigate={vi.fn()}/></QueryClientProvider>);const panel=await screen.findByRole("region",{name:"Email notifications"});expect(within(panel).getByText("Accepted by mail server")).toBeVisible();expect(within(panel).queryByRole("button")).toBeNull();expect(within(panel).queryByRole("link")).toBeNull();
});

// Terminal operation history still observes its pending transport until a bounded delivery result exists.
it("polls pending mail on a terminal operation and stops after server acceptance",async()=>{
 vi.useFakeTimers();const read=vi.spyOn(api,"operation").mockResolvedValue({...operation,notifications:[{...notice,state:"pending"}]});render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})}><Operations operationId={id} expired={vi.fn()} navigate={vi.fn()}/></QueryClientProvider>);
 await act(async()=>{await vi.advanceTimersByTimeAsync(1);});expect(read).toHaveBeenCalledTimes(1);read.mockResolvedValue(operation);await act(async()=>{await vi.advanceTimersByTimeAsync(5001);});expect(read).toHaveBeenCalledTimes(2);expect(screen.getByText("Accepted by mail server")).toBeVisible();await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});expect(read).toHaveBeenCalledTimes(2);
});

it("reads deployment routing through the guarded same-origin HTTP adapter",async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({environment:"staging",redirected:true,effective_test_email:testEmail}),{status:200}));vi.stubGlobal("fetch",fetch);const controller=new AbortController();expect(await api.emailPolicy(controller.signal)).toMatchObject({redirected:true});expect(fetch).toHaveBeenCalledWith("/api/email-policy",expect.objectContaining({method:"GET",credentials:"same-origin",cache:"no-store",signal:controller.signal}));
});

it.each(["automation","recovery"] as const)("shows %s missing notices with frozen role and routing explanations",purpose=>{
 render(<EmailNotifications notifications={[{...notice,event:"required_user_missing",required_user_purpose:purpose,recipient_roles:["owner","manager","designee","administrator"],routing_issues:["owner_unavailable","manager_unavailable","designee_unavailable","administrator_unavailable"]}]}/>);
 expect(screen.getByRole("heading",{name:`${purpose==="automation"?"Automation":"Recovery"} user missing`})).toBeVisible();
 expect(screen.getByText("Owner, Manager, Designee, Administrator")).toBeVisible();
 expect(screen.getByText(/Review the recorded recipients and delivery status/)).toBeVisible();
 expect(screen.getByText(/Owner contact unavailable/)).toBeVisible();
 expect(screen.queryByText("Terminal operation failure")).toBeNull();
 expect(screen.queryByRole("button")).toBeNull();
});

it.each([
 ["required_user_missing","Required user missing"],["cost_read_failed","Cost collection failure"],
] as const)("labels %s independently from lifecycle failures",(event,label)=>{
 render(<EmailNotifications notifications={[{...notice,event}]}/>);
 expect(screen.getByRole("heading",{name:label})).toBeVisible();
});

it.each([
 ["EMAIL_RECIPIENT_UNAVAILABLE","No currently authorized delivery contact"],
 ["EMAIL_RECIPIENT_CHANGED","no longer holds a notified role"],
] as const)("gives role-safe guidance for %s",(safe_code,message)=>{
 render(<EmailNotifications notifications={[{...notice,event:"required_user_missing",state:"blocked",safe_code}]}/>);
 expect(screen.getByText(new RegExp(message))).toBeVisible();
 expect(screen.queryByText(safe_code)).toBeNull();
});
