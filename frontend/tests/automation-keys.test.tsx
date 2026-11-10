import {render,screen,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {AutomationKeys} from "../src/AutomationKeys";
import type {AutomationKeysView} from "../src/contracts";
import {operationDestination} from "../src/operationNavigation";

const operation="11111111-1111-4111-8111-111111111111";
const created="2026-11-01T00:00:00Z";
const inventory:AutomationKeysView={state:"known",checked_at:"2026-11-03T12:30:00Z",age_as_of:"2026-11-03T12:30:00Z",operation_id:operation,keys:[{provider_key_id:"synthetic-public-key-id",fingerprint:Array(16).fill("ab").join(":"),created_at:created,key_state:"active",age_state:"within_limit",age_days:2,retirement_due_at:"2026-12-01T00:00:00Z"}]};

// Legacy absence, unavailable enumeration and complete empty inventories remain distinct.
it("separates unavailable and known empty inventory without inventing key rows",()=>{
  const view=render(<AutomationKeys navigate={vi.fn()}/>);
  expect(screen.getByText(/has not been checked/)).toBeVisible();
  view.rerender(<AutomationKeys inventory={{state:"unavailable"}} navigate={vi.fn()}/>);
  expect(screen.getByText(/Refresh does not create or enroll keys/)).toBeVisible();
  expect(screen.queryByText(/No signing keys were found/)).not.toBeInTheDocument();
  view.rerender(<AutomationKeys inventory={{...inventory,keys:[]}} navigate={vi.fn()}/>);
  expect(screen.getByText(/complete authorized inventory/)).toBeVisible();
  expect(screen.queryByText("Fingerprint")).not.toBeInTheDocument();
});

// Dated public metadata has a contextual operation link and no custody/rotation action.
it("shows compact public facts and links to the exact recorded check",async()=>{
  history.replaceState(null,"","/tenancies/"+operation);
  const navigate=vi.fn();render(<AutomationKeys inventory={inventory} navigate={navigate}/>);
  const region=screen.getByRole("region",{name:"Automation signing keys"});
  expect(within(region).getByText(inventory.keys![0]!.fingerprint)).toHaveAttribute("title","synthetic-public-key-id");
  expect(within(region).getByText("Under 30 days")).toBeVisible();
  expect(within(region).getByText(/2 days/)).toBeVisible();
  expect(within(region).getByText("Nov 1, 2026")).toHaveAttribute("datetime",created);
  const link=within(region).getByRole("link",{name:"View automation signing-key inventory check, Nov 3, 2026"});
  expect(link).toHaveAttribute("title",expect.stringContaining("UTC"));
  expect(link.getAttribute("href")).toContain("#automation-keys");
  expect(operationDestination(link.getAttribute("href")!)).toBe(link.getAttribute("href"));
  await userEvent.click(link);expect(navigate).toHaveBeenCalledWith(link.getAttribute("href"));
  expect(within(region).queryByRole("button")).not.toBeInTheDocument();
  expect(within(region).getByText(/Rotation and credential custody are not verified/)).toBeVisible();
  history.replaceState(null,"","/");
});

// Per-key age uncertainty and staleness cannot turn into positive readiness labels.
it.each(["due_soon","overdue","unknown","inactive"] as const)("shows %s independently of inventory availability",state=>{
  render(<AutomationKeys inventory={{...inventory,state:"stale",keys:[{...inventory.keys![0]!,age_state:state,created_at:state==="unknown"?null:created,retirement_due_at:null,age_days:null}]}} navigate={vi.fn()}/>);
  expect(screen.getByText(/Inventory is out of date/)).toBeVisible();
  expect(screen.getByText({due_soon:"Due within 1 day",overdue:"30 days or older",unknown:"Age unknown",inactive:"Inactive"}[state])).toBeVisible();
  expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
});

// History displays capture-time age and avoids linking an operation back to itself.
it("renders a dated historical observation without a refresh instruction",()=>{
  render(<AutomationKeys inventory={inventory} historical navigate={vi.fn()}/>);
  expect(screen.getByText(/Age at observation/)).toBeVisible();
  expect(screen.queryByText(/Refresh user data above/)).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.getByRole("region")).toHaveAttribute("id","automation-keys");
});
