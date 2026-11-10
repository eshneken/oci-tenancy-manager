import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {expect,it,vi} from "vitest";
import {SigningKeyRotation} from "../src/SigningKeyRotation";
import {api,ApiError} from "../src/api";
import type {SigningKeyView} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111",operation="22222222-2222-4222-8222-222222222222";
const scheduled:SigningKeyView={tenancy_id:id,tenancy_name:"Synthetic child",provider_mode:"simulated",state:"scheduled",generation:1,available:true,preview_hash:"a".repeat(64),operation_id:operation,starts_at:"2026-12-08T12:00:00Z",retire_at:"2026-12-09T12:00:00Z"};

// Each case owns a query cache and synthetic endpoint; no saved app or live provider is contacted.
function mount(value:SigningKeyView=scheduled){
  const read=vi.spyOn(api,"signingKeyRotation").mockResolvedValue(value);
  const request=vi.spyOn(api,"requestSigningKeyRotation").mockResolvedValue({operation_id:operation,state:"queued",provider_mode:"simulated",accepted_at:"2026-11-10T12:00:00Z"});
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}}),expired=vi.fn(),navigate=vi.fn();
  const view=render(<QueryClientProvider client={client}><SigningKeyRotation tenancyId={id} expired={expired} navigate={navigate}/></QueryClientProvider>);
  return {...view,read,request,client,expired,navigate};
}

// Scheduled status stays compact and metadata-only; no material or mutation enters a read.
it("shows the original retirement deadline and contextual operation links",async()=>{
  history.replaceState(null,"","/tenancies/"+id);
  const c=mount({...scheduled,generation:2,last_rotation_operation_id:operation,last_rotated_at:"2026-11-09T12:00:00Z"});
  expect(await screen.findByText("Next rotation scheduled")).toBeVisible();
  expect(screen.getByText("Dec 9, 2026")).toHaveAttribute("title",expect.stringContaining("UTC"));
  expect(screen.getByText(/Current key: generation 2/)).toBeVisible();
  await userEvent.click(screen.getByRole("link",{name:"View last completed key rotation"}));
  expect(c.navigate).toHaveBeenCalledWith(expect.stringContaining("returnTo="));
  expect(c.request).not.toHaveBeenCalled();c.client.clear();history.replaceState(null,"","/");
});

// All submit paths share explicit unchecked consent and fresh preview checks.
it("requires consent for click, Enter and programmatic submit then starts one exact request",async()=>{
  const c=mount();await screen.findByText("Next rotation scheduled");
  await userEvent.click(screen.getByRole("button",{name:"Rotate key"}));
  const dialog=screen.getByRole("dialog"),form=dialog.querySelector("form")!;
  const confirm=within(dialog).getByRole("button",{name:"Rotate now"});
  expect(confirm).toBeDisabled();
  fireEvent.submit(form);await userEvent.keyboard("{Enter}");expect(c.request).not.toHaveBeenCalled();
  expect(within(dialog).getByText("Rotation steps").closest("details")).not.toHaveAttribute("open");
  await userEvent.click(within(dialog).getByRole("checkbox"));
  c.read.mockResolvedValue({...scheduled,state:"rotating",available:false});
  await userEvent.click(confirm);
  await waitFor(()=>expect(c.request).toHaveBeenCalledTimes(1));
  expect(c.request.mock.calls[0][1]).toMatchObject({acknowledged:true,preview_hash:scheduled.preview_hash,action:"rotate"});
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("region",{name:"Automatic key rotation"})).toHaveFocus();c.client.clear();
});

// Unknown response retains a replay path after the server advances and stops offering a new preview.
it("reopens an uncertain request and retries identical UUID/body against rotating status",async()=>{
  const c=mount();await screen.findByText("Next rotation scheduled");
  await userEvent.click(screen.getByRole("button",{name:"Rotate key"}));
  await userEvent.click(screen.getByRole("checkbox"));
  c.request.mockRejectedValueOnce(new Error("synthetic transport"));
  await userEvent.click(screen.getByRole("button",{name:"Rotate now"}));
  await screen.findByText(/request may have been accepted/);
  const original=c.request.mock.calls[0][1];
  await userEvent.click(screen.getByRole("button",{name:"Cancel"}));
  c.read.mockResolvedValue({...scheduled,state:"rotating",available:false,preview_hash:null});
  await act(()=>c.client.invalidateQueries({queryKey:["tenancies","signing-key-rotation",id]}));
  await userEvent.click(screen.getByRole("button",{name:"Recover request"}));
  expect(screen.getByRole("checkbox")).not.toBeChecked();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button",{name:"Retry same request"}));
  await waitFor(()=>expect(c.request).toHaveBeenCalledTimes(2));
  expect(c.request.mock.calls[1][1]).toEqual(original);c.client.clear();
});

// Known stale-preview conflicts discard consent and request identity before a new decision.
it("clears consent when a reviewed preview changes or the server rejects it",async()=>{
  const c=mount();await screen.findByText("Next rotation scheduled");
  await userEvent.click(screen.getByRole("button",{name:"Rotate key"}));
  await userEvent.click(screen.getByRole("checkbox"));
  c.read.mockResolvedValue({...scheduled,preview_hash:"b".repeat(64)});
  await act(()=>c.client.invalidateQueries({queryKey:["tenancies","signing-key-rotation",id]}));
  await waitFor(()=>expect(screen.getByRole("checkbox")).not.toBeChecked());
  c.request.mockRejectedValueOnce(new ApiError(409));
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button",{name:"Rotate now"}));
  await screen.findByText(/preview changed or rotation is unavailable/);
  expect(screen.getByRole("checkbox")).not.toBeChecked();c.client.clear();
});

// Human-held work advertises resume only when the current server context permits it.
it.each([true,false])("honors attention availability %s",async available=>{
  const c=mount({...scheduled,state:"attention",available});
  await screen.findByText("Rotation needs attention");
  if(available){
    await userEvent.click(screen.getByRole("button",{name:"Resume rotation"}));
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button",{name:"Resume rotation"}));
    await waitFor(()=>expect(c.request).toHaveBeenCalled());
    expect(c.request.mock.calls[0][1].action).toBe("resume");
  }else{
    expect(screen.queryByRole("button",{name:"Resume rotation"})).not.toBeInTheDocument();
    expect(screen.getByText(/restore the required context/)).toBeVisible();
  }c.client.clear();
});

// Status failures remain retryable and denied reads end the privileged view.
it.each([401,403,500])("handles metadata error %s safely",async status=>{
  const c=mount();await screen.findByText("Next rotation scheduled");c.read.mockRejectedValue(new ApiError(status));
  await act(()=>c.client.invalidateQueries({queryKey:["tenancies","signing-key-rotation",id]}));
  await screen.findByRole("alert");
  if(status!==500)await waitFor(()=>expect(c.expired).toHaveBeenCalled());
  expect(screen.queryByText("private")).not.toBeInTheDocument();c.client.clear();
});

// Nonactionable states offer honest guidance and never a new rotation button.
it.each(["not_prepared","preparing","overdue","inactive","unavailable"] as const)("shows %s without inventing an action",async state=>{
  const c=mount({...scheduled,state,available:false});
  await screen.findByRole("region",{name:"Automatic key rotation"});
  expect(screen.queryByRole("button",{name:"Rotate key"})).not.toBeInTheDocument();c.client.clear();
});
