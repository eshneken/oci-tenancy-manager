import {act,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {it,expect,vi} from "vitest";
import {FleetRefresh} from "../src/FleetRefresh";
import {api,ApiError} from "../src/api";
import type {FleetRefreshReceipt} from "../src/contracts";

const ids=["11111111-1111-4111-8111-111111111111","22222222-2222-4222-8222-222222222222","33333333-3333-4333-8333-333333333333"];
const receipt:FleetRefreshReceipt={tenancy_count:2,categories:[{category:"costs",operation_ids:[ids[0]],skipped_count:1,failed_count:0},{category:"users",operation_ids:[ids[1]],skipped_count:1,failed_count:0},{category:"configuration",operation_ids:[ids[2]],skipped_count:1,failed_count:0}]};

// Keep durable provider admission and compact progress independent in a real query-cache mount.
function mount(value=receipt){
 const start=vi.spyOn(api,"refreshAllData").mockResolvedValue(value);
 const progress=vi.spyOn(api,"refreshAllStatus").mockResolvedValue({jobs:ids.map(operation_id=>({operation_id,state:"pending" as const}))});
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}});
 const invalidate=vi.spyOn(client,"invalidateQueries");const expired=vi.fn();
 render(<QueryClientProvider client={client}><FleetRefresh expired={expired}/></QueryClientProvider>);
 return {start,progress,client,invalidate,expired};
}

it("queues once, polls compact progress and retains terminal skipped feedback",async()=>{
 const c=mount();await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));
 expect(await screen.findByText("Refreshing tenancy data")).toBeVisible();
 expect(screen.getByRole("button",{name:"Refreshing data…"})).toBeDisabled();
 await waitFor(()=>expect(c.progress).toHaveBeenCalledWith(ids,expect.any(AbortSignal)));
 expect(c.start.mock.calls[0][0]).toEqual({client_request_key:expect.any(String)});
 expect(screen.getByText(/Includes tenancies outside this page/)).toBeVisible();
 await act(async()=>{c.client.setQueryData(["fleet-refresh-progress",ids],{jobs:ids.map(operation_id=>({operation_id,state:"finished"}))});});
 expect(await screen.findByText("Refresh finished with skipped checks")).toBeVisible();
 expect(screen.getAllByText("1 jobs finished · 0 pending · 0 failed · 1 tenancies skipped")).toHaveLength(3);
 expect(screen.getByText(/Finished jobs can report drift/)).toBeVisible();
 expect(c.invalidate).toHaveBeenCalledWith({queryKey:["configuration-drift"]});
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));expect(c.start).toHaveBeenCalledTimes(2);
 expect(c.start.mock.calls[0][0].client_request_key).not.toBe(c.start.mock.calls[1][0].client_request_key);
});

it("retains command keys after uncertain response and prevents duplicate submission",async()=>{
 const c=mount();c.start.mockRejectedValueOnce(new ApiError(503));
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));await screen.findByRole("alert");
 const key=c.start.mock.calls[0][0].client_request_key;
 await userEvent.click(screen.getByRole("button",{name:"Retry refresh"}));
 expect(c.start.mock.calls[1][0].client_request_key).toBe(key);
});

it("retries failed progress without resubmitting the provider command",async()=>{
 const c=mount();c.progress.mockRejectedValueOnce(new ApiError(503));
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("Refresh was accepted");
 await userEvent.click(screen.getByRole("button",{name:"Retry progress check"}));
 await waitFor(()=>expect(c.progress).toHaveBeenCalledTimes(2));expect(c.start).toHaveBeenCalledTimes(1);
});

it.each([401,403])("expires authorization for queue and progress failures %s",async status=>{
 const c=mount();c.start.mockRejectedValueOnce(new ApiError(status));
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));await waitFor(()=>expect(c.expired).toHaveBeenCalledTimes(1));
 c.progress.mockRejectedValueOnce(new ApiError(status));await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));
 await waitFor(()=>expect(c.expired).toHaveBeenCalledTimes(2));
});

it("handles empty fleet, skipped setup and failed jobs without claiming healthy data",async()=>{
 const c=mount({tenancy_count:0,categories:receipt.categories.map(category=>({...category,operation_ids:[],skipped_count:0,failed_count:0}))});
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));await screen.findByText("No eligible active child tenancies");
 expect(c.progress).not.toHaveBeenCalled();
 c.start.mockResolvedValue({...receipt,categories:receipt.categories.map(category=>({...category,failed_count:1}))});
 c.progress.mockResolvedValue({jobs:ids.map(operation_id=>({operation_id,state:"failed"}))});
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));
 expect(await screen.findByText("Refresh finished with issues")).toBeVisible();
 expect(within(screen.getByRole("region",{name:"Fleet refresh progress"})).getAllByText(/2 failed/)).toHaveLength(3);
});

it("announces finished jobs without skips and clears the prior receipt on a new attempt",async()=>{
 const c=mount({...receipt,categories:receipt.categories.map(category=>({...category,skipped_count:0}))});
 c.progress.mockResolvedValue({jobs:ids.map(operation_id=>({operation_id,state:"finished"}))});
 await userEvent.click(screen.getByRole("button",{name:"Refresh all data"}));await screen.findByText("Refresh finished");
 let finish!:(value:FleetRefreshReceipt)=>void;c.start.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 await userEvent.dblClick(screen.getByRole("button",{name:"Refresh all data"}));
 expect(screen.queryByRole("region",{name:"Fleet refresh progress"})).toBeNull();
 expect(c.start).toHaveBeenCalledTimes(2);
 await act(async()=>finish({...receipt,categories:[]}));
});
