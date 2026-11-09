import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { it, expect, vi } from "vitest";
import { AddSharedMember } from "../src/AddSharedMember";
import { api, ApiError } from "../src/api";

const person={id:"candidate",full_name:"Test Engineer",email:"engineer@example.test",absence_review:false,
  directory_status:"included" as const,manager_name:null,leader_name:null,lob_name:null};
const directory={items:[person],page:1,pages:1,page_size:25,total:1,employee_count:1,absence_count:0,
  absence_eligible:true,configured:true,upload_enabled:true,findings:[],latest:null,applied_at:null,source_as_of:null,server_time:"2026-11-07T12:00:00Z"};

// Isolate directory search from operator data and preserve the real picker form and query behavior.
function mount(){
 const read=vi.spyOn(api,"organization").mockResolvedValue(directory);
 const choose=vi.fn(),close=vi.fn(),expired=vi.fn();
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
 const view=render(<QueryClientProvider client={client}><AddSharedMember tenancyName="Shared lab" memberIds={["member"]} expired={expired} onChoose={choose} onClose={close}/></QueryClientProvider>);
 return {...view,read,choose,close,expired};
}

// Selection only opens the existing membership preview; script/Enter cannot skip the employee choice.
it("requires a fresh selection and hands off the stable employee id",async()=>{
 const c=mount();const button=screen.getByRole("button",{name:"Continue"});
 expect(button).toBeDisabled();fireEvent.submit(button.closest("form")!);expect(c.choose).not.toHaveBeenCalled();
 expect(c.read).not.toHaveBeenCalled();await userEvent.type(screen.getByLabelText("Find employee"),"Test");
 await userEvent.selectOptions(await screen.findByLabelText("Employee"),person.id);
 await userEvent.type(screen.getByLabelText("Find employee"),"x");expect(button).toBeDisabled();
 await userEvent.selectOptions(await screen.findByLabelText("Employee"),person.id);
 await userEvent.click(button);expect(c.choose).toHaveBeenCalledWith(person.id);
});

// Already associated, absent, excluded and pending people cannot be picked through this shortcut.
it("omits current members and unavailable profiles",async()=>{
 const c=mount();c.read.mockResolvedValue({...directory,items:[
  {...person,id:"member"},{...person,id:"absent",absence_review:true},
  {...person,id:"pending",pending_operation_id:"pending"},{...person,id:"exempt",directory_status:"exempt"},
 ]});
 await userEvent.type(screen.getByLabelText("Find employee"),"Test");
 await screen.findByText(/No available employees in these results/);
 expect(screen.queryByRole("option",{name:/Test Engineer/})).toBeNull();
 fireEvent.submit(screen.getByRole("button",{name:"Continue"}).closest("form")!);expect(c.choose).not.toHaveBeenCalled();
});

// Failed searches remain retryable while authentication loss also clears usable private choices.
it.each([401,403,503])("handles directory failure %s",async status=>{
 const c=mount();c.read.mockRejectedValue(new ApiError(status));
 await userEvent.type(screen.getByLabelText("Find employee"),"Test");
 await screen.findByText(/Unable to load employees/);
 if(status!==503)await waitFor(()=>expect(c.expired).toHaveBeenCalled());
 expect(screen.getByRole("button",{name:"Continue"})).toBeDisabled();
 c.read.mockResolvedValue(directory);await userEvent.click(screen.getByRole("button",{name:"Retry"}));
 await screen.findByLabelText("Employee");
});

// Escape closes without any membership command or employee mutation.
it("cancels with Escape",()=>{
 const c=mount();fireEvent(screen.getByRole("dialog"),new Event("cancel",{cancelable:true}));
 expect(c.close).toHaveBeenCalled();expect(c.choose).not.toHaveBeenCalled();
});

// Explicit cancellation closes the native modal without advancing to a workflow.
it("cancels without selecting a member",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
 expect(c.close).toHaveBeenCalled();expect(c.choose).not.toHaveBeenCalled();
});
