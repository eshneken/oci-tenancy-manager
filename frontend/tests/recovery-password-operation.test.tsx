import {act,render,screen,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {RecoveryPasswordOperation} from "../src/RecoveryPasswordOperation";
import type {OperationSummary,RecoveryPasswordProgress} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111";
const first="2026-11-09T12:00:00Z",due="2026-11-09T16:00:00Z";
const operation:OperationSummary={id,kind:"recovery_password",state:"waiting",stage:"Rotate recovery password",accepted_at:first,updated_at:first,completed_at:null,initiated_by:"Test admin",target_tenancy_ocid:"ocid1.tenancy.oc1..otmsimtest",provider_mode:"simulated"};
const progress:RecoveryPasswordProgress={phase:"rotation",tenancy_id:id,user_name:"otm-recovery",first_request_at:first,rotation_due_at:due,request_count:2};

// Scheduled, running, overdue and terminal records retain their own original-window meaning.
it.each([
 ["waiting",false,"Scheduled"],["queued",true,"Rotation overdue"],["running",false,"Rotating"],
 ["needs_attention",false,"Reconciliation required"],["failed",true,"Reconciliation required"],
 ["cancelled",false,"Reconciliation required"],["succeeded",true,"Rotated in simulation"],
] as const)("describes rotation %s overdue=%s",(state,overdue,label)=>{
 vi.spyOn(Date,"now").mockReturnValue(Date.parse(overdue?due:first));
 render(<RecoveryPasswordOperation operation={{...operation,state,completed_at:state==="succeeded"?due:null}} progress={progress} navigate={vi.fn()}/>);
 expect(screen.getByText(label,{exact:true})).toBeVisible();
 expect(screen.getByText("Original rotation deadline (UTC)").nextElementSibling?.querySelector("time")).toHaveAttribute("datetime",due);
 expect(screen.getByText("Authorized requests").nextElementSibling).toHaveTextContent("2");
 expect(screen.queryByRole("button")).not.toBeInTheDocument();
 expect(screen.queryByText(/Inspection completed/)).not.toBeInTheDocument();
});

// Setup has no invented exposure dates, while successful setup/rotation use different labels.
it.each(["queued","running","succeeded"] as const)("describes %s password preparation",state=>{
 render(<RecoveryPasswordOperation operation={{...operation,state,completed_at:state==="succeeded"?first:null}} progress={{...progress,phase:"setup",first_request_at:null,rotation_due_at:null,request_count:0}} navigate={vi.fn()}/>);
 expect(screen.getByRole("heading",{name:"Password preparation"})).toBeVisible();
 expect(screen.getByText(state==="succeeded"?"Prepared in simulation":state==="running"?"Preparing":"Preparation pending",{exact:true})).toBeVisible();
 expect(screen.queryByText("Original rotation deadline (UTC)")).not.toBeInTheDocument();
 expect(screen.queryByText("Authorized requests")).not.toBeInTheDocument();
});

// Help stays optional and the safe tenancy link follows normal same-app navigation.
it("explains the original deadline and links back without exposing credentials",async()=>{
 const navigate=vi.fn();render(<RecoveryPasswordOperation operation={operation} progress={progress} navigate={navigate}/>);
 const help=screen.getByText("How the access window works").closest("details")!;
 expect(help.open).toBe(false);await userEvent.click(within(help).getByText("How the access window works"));
 expect(help.open).toBe(true);expect(help).toHaveTextContent("Further requests join that window");
 await userEvent.click(screen.getByRole("link",{name:"Open tenancy"}));expect(navigate).toHaveBeenCalledWith("/tenancies/"+id);
 expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

// Crossing the due instant changes display even when the server returns the same waiting record.
it("marks an unchanged scheduled operation overdue at its original deadline",()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date(first));
 render(<RecoveryPasswordOperation operation={operation} progress={progress} navigate={vi.fn()}/>);
 expect(screen.getByText("Scheduled",{exact:true})).toBeVisible();
 act(()=>vi.advanceTimersByTime(4*60*60*1000));
 expect(screen.getByText("Rotation overdue",{exact:true})).toBeVisible();
});

// A setup failure has no exposure window and cannot claim a pending rotation obligation.
it.each(["failed","needs_attention","cancelled"] as const)("explains %s setup without inventing a window",state=>{
 render(<RecoveryPasswordOperation operation={{...operation,state}} progress={{...progress,phase:"setup",first_request_at:null,rotation_due_at:null,request_count:0}} navigate={vi.fn()}/>);
 expect(screen.getByRole("alert")).toHaveTextContent("Password custody has not been verified");
 expect(screen.getByRole("alert")).not.toHaveTextContent("rotation obligation");
});
