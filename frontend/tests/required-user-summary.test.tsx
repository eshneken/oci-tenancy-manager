import { render,screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect,it,vi } from "vitest";
import { RequiredUserSummary } from "../src/RequiredUserSummary";
import type {RequiredUsersSummary} from "../src/contracts";

const id="11111111-1111-4111-8111-111111111111";

// Compact labels never substitute recorded identities, unknown reads or stale facts for presence.
it.each([
  ["not_checked","Not checked"],["present","2/2 present"],["missing","Missing"],
  ["unavailable","Unable to verify"],["stale","Check out of date"],
] as const)("renders the scoped %s summary",async(state,label)=>{
  const navigate=vi.fn();
  const summary:RequiredUsersSummary={state,automation:{state:"present",checked_at:"2026-11-06T12:00:00Z",operation_id:id},recovery:{state:state==="missing"?"missing":state==="present"?"present":"unknown",checked_at:"2026-11-06T12:00:00Z",operation_id:id,stale:state==="stale"},checking:true};
  render(<RequiredUserSummary id={id} name="Example child" status="active" summary={summary} navigate={navigate}/>);
  const link=screen.getByRole("link",{name:`Users: ${label} for Example child`});
  expect(link).toHaveAttribute("href",`/tenancies/${id}#required-users`);
  expect(link).toHaveAccessibleDescription(/Permissions are not checked/);
  expect(link).toHaveAttribute("title",expect.stringContaining("UTC"));
  if(state==="stale") expect(link).toHaveAttribute("title",expect.stringContaining("last result: Unable to verify"));
  expect(screen.getByText("Checking…")).toBeVisible();
  await userEvent.click(link);
  expect(navigate).toHaveBeenCalledWith(`/tenancies/${id}#required-users`);
});

// Legacy records stay neutral and retirement does not advertise a new active-user health state.
it("handles older payloads and omits inactive children",()=>{
  const c=render(<RequiredUserSummary id={id} name="Example child" status="active" navigate={vi.fn()}/>);
  expect(screen.getByRole("link")).toHaveTextContent("Users: Not checked");
  expect(screen.queryByText("Checking…")).not.toBeInTheDocument();
  c.rerender(<RequiredUserSummary id={id} name="Example child" status="terminated" navigate={vi.fn()}/>);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

// A coarse positive status without individual dated observations remains visibly unverified.
it.each(["present","missing"] as const)("rejects incomplete %s wire summaries",state=>{
  render(<RequiredUserSummary id={id} name="Example" status="active" summary={{state}} navigate={vi.fn()}/>);
  expect(screen.getByRole("link")).toHaveTextContent("Users: Unable to verify");
});
