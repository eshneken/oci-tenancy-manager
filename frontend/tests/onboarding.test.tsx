import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { Onboarding } from "../src/Onboarding";
import { Operations } from "../src/Operations";
import { api, ApiError } from "../src/api";
import type { OnboardingView } from "../src/contracts";

const identifier = "11111111-1111-4111-8111-111111111111";
const handoff = {
  tenancy_ocid: "ocid1.tenancy.oc1..otmsimchild",
  bootstrap_user_ocid: "ocid1.user.oc1..otmsimbootstrap",
  activation_user_ocid: "ocid1.user.oc1..otmsimactivation",
};
const base: OnboardingView = {
  operation_id: identifier,
  tenancy_id: identifier,
  revision: 2,
  state: "waiting",
  phase: "handoff",
  origin: "create",
  expected_parent_tenancy_ocid: "ocid1.tenancy.oc1..otmsimparent",
  owner_name: "Synthetic owner",
  administrator_name: "Local administrator",
  administrator_email: null,
  suggested_handoff: handoff,
  submitted_handoff: null,
  discovery: null,
  bootstrap_username: "otm-bootstrap-fixture",
  public_key: null,
  checks: [
    {
      key: "inspect_bootstrap",
      label: "Verify bootstrap",
      state: "pending",
      verified_at: null,
    },
  ],
  available_actions: ["verify_handoff"],
  issue_code: null,
};
const verified: OnboardingView = {
  ...base,
  revision: 4,
  phase: "review",
  submitted_handoff: handoff,
  discovery: {
    ...handoff,
    name: "Discovered sandbox",
    home_region: "us-ashburn-1",
    domain_ocid: "ocid1.domain.oc1..otmsimdomain",
    parent_tenancy_ocid: "ocid1.tenancy.oc1..otmsimparent",
    organization_id: "synthetic-org",
    bootstrap_scim_id: "bootstrap",
    activation_scim_id: "activation",
  },
  available_actions: ["start_setup"],
  checks: [
    {
      key: "inspect_bootstrap",
      label: "Verify bootstrap",
      state: "verified",
      verified_at: "2026-10-31T12:00:00Z",
    },
  ],
};

// Query and command boundaries are isolated; these tests cannot reach the operator's installation.
function mount(view = base) {
  const read = vi.spyOn(api, "onboarding").mockResolvedValue(view);
  const write = vi.spyOn(api, "onboardingAction").mockResolvedValue({
    operation_id: identifier,
    state: "queued",
    provider_mode: "simulated",
    accepted_at: "2026-10-31T12:00:00Z",
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const expired = vi.fn(),
    navigate = vi.fn();
  const rendered = render(
    <QueryClientProvider client={client}>
      <Onboarding
        operationId={identifier}
        expired={expired}
        navigate={navigate}
      />
    </QueryClientProvider>,
  );
  return { read, write, expired, navigate, ...rendered };
}

describe("Guided tenancy setup", () => {
  // Manual inputs carry exact synthetic IDs and leave the browser only in a protected command body.
  it("fills synthetic handoff, permits edits and submits without collecting credentials", async () => {
    const c = mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "Use simulated handoff" }),
    );
    for (const [label, value] of [
      ["Tenancy OCID", handoff.tenancy_ocid],
      ["Bootstrap user OCID", handoff.bootstrap_user_ocid],
      ["Activation administrator user OCID", handoff.activation_user_ocid],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    await userEvent.click(
      screen.getByRole("button", { name: "Verify handoff" }),
    );
    expect(c.write).toHaveBeenCalledWith(
      identifier,
      expect.objectContaining({
        revision: 2,
        action: "verify_handoff",
        handoff,
      }),
      expect.any(AbortSignal),
    );
    expect(screen.getByLabelText("Tenancy OCID")).not.toHaveAttribute("readonly");
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    await userEvent.click(screen.getByText("Delivery and administrator contacts"));
    expect(screen.getByText("Original administrator contact",{exact:true}).nextElementSibling).toHaveTextContent("Not configured");
  });

  // OCI guidance distinguishes request/tenancy IDs and public-key upload from key generation.
  it("provides optional child-console steps without hiding handoff controls", async () => {
    const c=mount();
    const checklist=await screen.findByText("OCI administrator checklist",{selector:"summary"});
    expect(checklist.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText(/A work-request ID is not a tenancy OCID/)).not.toBeVisible();
    expect(screen.getByLabelText("Tenancy OCID")).toBeVisible();
    await userEvent.click(checklist);
    expect(screen.getByText(/A work-request ID is not a tenancy OCID/)).toBeInTheDocument();
    expect(screen.getByText(/Domain roles and the OCI Administrators group are separate grants/)).toBeInTheDocument();
    expect(screen.getByText(/Do not generate a different key pair/)).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(5);
    for (const link of links) {
      expect(new URL(link.getAttribute("href")!).hostname).toBe("docs.oracle.com");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    expect(screen.getByRole("link", { name: "Assign the domain role" })).toHaveAttribute("href", "https://docs.oracle.com/en-us/iaas/Content/Identity/users/assign-users-roles.htm");
    expect(screen.queryByLabelText(/password|private key|MFA code/i)).toBeNull();
    await userEvent.click(checklist);
    expect(checklist.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByLabelText("Tenancy OCID")).toBeVisible();
    expect(screen.getByRole("button",{name:"Use simulated handoff"})).toBeVisible();
    expect(c.write).not.toHaveBeenCalled();
  });

  // Start requires explicit consent to the exact verified cleanup targets after a reload-safe preview.
  it("reviews exact accounts and starts setup only after explicit confirmation", async () => {
    const c = mount(verified);
    expect(
      await screen.findByRole("button", { name: "Start setup" }),
    ).toBeDisabled();
    expect(
      screen.getByText(handoff.activation_user_ocid, { selector: "code" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Start setup" }));
    expect(c.write).toHaveBeenCalledWith(
      identifier,
      expect.objectContaining({ action: "start_setup", confirm_cleanup: true }),
      expect.any(AbortSignal),
    );
  });

  // Import has no initial-human cleanup and cannot accidentally send an activation target.
  it("omits activation-user input and preserves imported human administrators", async () => {
    const c = mount({
      ...base,
      origin: "import",
      suggested_handoff: { ...handoff, activation_user_ocid: null },
    });
    await userEvent.click(
      await screen.findByRole("button", { name: "Use simulated handoff" }),
    );
    expect(
      screen.queryByLabelText("Activation administrator user OCID"),
    ).toBeNull();
    const target = screen.getByLabelText("Tenancy OCID");
    expect(target).toHaveValue(handoff.tenancy_ocid);
    expect(target).toHaveAttribute("readonly");
    await userEvent.click(screen.getByRole("button", { name: "Verify handoff" }));
    expect(c.write).toHaveBeenCalledWith(identifier, expect.objectContaining({
      handoff: { ...handoff, activation_user_ocid: null },
    }), expect.any(AbortSignal));
    await userEvent.click(screen.getByText("OCI administrator checklist",{selector:"summary"}));
    await userEvent.click(screen.getByText("Oracle transfer procedures"));
    expect(screen.getByRole("link", { name: "Transfer a created child (approval uses the CLI)" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Oracle activation guide" })).toBeNull();
    c.read.mockResolvedValue({
      ...verified,
      origin: "import",
      administrator_email: "admin@example.test",
      discovery: {
        ...verified.discovery!,
        activation_user_ocid: null,
        activation_scim_id: null,
      },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Refresh setup" }),
    );
    expect(
      await screen.findByText("Existing human administrators are preserved."),
    ).toBeInTheDocument();
  });

  // The frozen import target is prefilled on reload while only bootstrap identity is entered.
  it("carries the import target into an otherwise blank handoff", async () => {
    const c = mount({ ...base, origin: "import", suggested_handoff: { ...handoff, activation_user_ocid: null } });
    const target = await screen.findByLabelText("Tenancy OCID");
    expect(target).toHaveValue(handoff.tenancy_ocid);
    expect(target).toHaveAttribute("readonly");
    await userEvent.type(target, "different");
    expect(target).toHaveValue(handoff.tenancy_ocid);
    await userEvent.type(screen.getByLabelText("Bootstrap user OCID"), handoff.bootstrap_user_ocid);
    await userEvent.click(screen.getByRole("button", { name: "Verify handoff" }));
    expect(c.write).toHaveBeenCalledWith(identifier, expect.objectContaining({
      handoff: { ...handoff, activation_user_ocid: null },
    }), expect.any(AbortSignal));
  });

  // A denied read ends the privileged view; service outages retain an explicit refresh action.
  it.each([401, 403, 503])(
    "handles a failed read without reflecting response details (%s)",
    async (status) => {
      const c = mount();
      c.read.mockRejectedValue(new ApiError(status));
      await userEvent.click(
        await screen.findByRole("button", { name: "Refresh setup" }),
      );
      await screen.findByText("Unable to load tenancy setup.");
      if (status === 503) expect(c.expired).not.toHaveBeenCalled();
      else await waitFor(() => expect(c.expired).toHaveBeenCalled());
    },
  );

  // Unchanged retries recover the same command while a denied mutation ends access.
  it("shows safe command errors and retains the retry identity", async () => {
    const c = mount();
    c.write.mockRejectedValueOnce(new Error("private failure"));
    await userEvent.click(
      await screen.findByRole("button", { name: "Use simulated handoff" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Verify handoff" }),
    );
    expect(
      await screen.findByText(/Setup could not be confirmed/),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Verify handoff" }),
    );
    expect(c.write.mock.calls[0][1].client_request_key).toBe(
      c.write.mock.calls[1][1].client_request_key,
    );
    c.write.mockRejectedValueOnce(new ApiError(403));
    await userEvent.click(
      screen.getByRole("button", { name: "Verify handoff" }),
    );
    await waitFor(() => expect(c.expired).toHaveBeenCalled());
  });

  // Failed setup retains verified facts and offers a scoped retry, never a second create operation.
  it("shows blocked checks and retries the incomplete setup", async () => {
    const c = mount({
      ...verified,
      phase: "blocked",
      state: "needs_attention",
      issue_code: "CLEANUP_UNVERIFIED",
      checks: [
        {
          key: "retire_temporary",
          label: "Temporary cleanup",
          state: "needs_attention",
          verified_at: null,
        },
      ],
    });
    await screen.findByText(/Temporary-account cleanup is not verified/);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Retry setup" }));
    expect(c.write).toHaveBeenCalledTimes(1);
  });

  // Terminal and queued panels communicate their real scope without prompting another workflow.
  it.each(["preparing", "configuring", "complete", "cancelled"] as const)(
    "renders the %s state",
    async (phase) => {
      const c = mount({
        ...verified,
        phase,
        available_actions: [],
        state:
          phase === "complete"
            ? "succeeded"
            : phase === "cancelled"
              ? "cancelled"
              : "queued",
      });
      await screen.findByRole("heading", { level: 2 });
      if (phase === "complete") {
        await userEvent.click(
          screen.getByRole("link", { name: "Open tenancy" }),
        );
        expect(c.navigate).toHaveBeenCalledWith("/tenancies/" + identifier);
      } else if (phase === "cancelled")
        expect(
          screen.getByText(/local setup was cancelled/),
        ).toBeInTheDocument();
      else expect(screen.getByText(/worker is processing/)).toBeInTheDocument();
    },
  );
});

// Same-revision navigation must require fresh consent and exact IDs for the newly selected operation.
it("clears cleanup confirmation when navigating to another cached operation", async () => {
  vi.spyOn(api, "onboarding").mockImplementation(async (id) => ({
    ...verified,
    operation_id: id,
    tenancy_id: id,
  }));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const expired = vi.fn(),
    navigate = vi.fn();
  const view = render(
    <QueryClientProvider client={client}>
      <Onboarding
        operationId={identifier}
        expired={expired}
        navigate={navigate}
      />
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByRole("checkbox"));
  expect(screen.getByRole("button", { name: "Start setup" })).toBeEnabled();
  const next = "22222222-2222-4222-8222-222222222222";
  client.setQueryData(["onboarding", next], {
    ...verified,
    operation_id: next,
    tenancy_id: next,
  });
  view.rerender(
    <QueryClientProvider client={client}>
      <Onboarding operationId={next} expired={expired} navigate={navigate} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByRole("checkbox")).not.toBeChecked());
  expect(screen.getByRole("button", { name: "Start setup" })).toBeDisabled();
});

// The live operation summary owns current responsibility; frozen onboarding attribution remains the initiator.
it.each(["create","import"] as const)("keeps original %s attribution distinct after responsibility changes",async(origin)=>{
 const creator="Original creator",responsible="Current administrator",at="2026-11-04T12:00:00Z";
 vi.spyOn(api,"operation").mockResolvedValue({operation:{id:identifier,kind:"organization_action",title:origin==="create"?"Create tenancy":"Import tenancy",state:"waiting",stage:"handoff",accepted_at:at,updated_at:at,completed_at:null,target_tenancy_ocid:handoff.tenancy_ocid,initiated_by:creator,guided_onboarding:true,responsible_administrator_name:responsible,responsibility_revision:2,can_take_responsibility:false},steps:[],events:[],events_limited:false});
 vi.spyOn(api,"onboarding").mockResolvedValue({...base,origin,administrator_name:creator,administrator_email:"creator@example.test",can_act:true});
 render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})}><Operations operationId={identifier} expired={vi.fn()} navigate={vi.fn()}/></QueryClientProvider>);
 const panel=await screen.findByRole("region",{name:"Administrator responsibility"});expect(within(panel).getByText(creator)).toBeVisible();expect(within(panel).getByText(responsible)).toBeVisible();
 expect(await screen.findByText(`Owner: ${base.owner_name} · Initiated by: ${creator}`)).toBeVisible();
 expect(screen.queryByText(`Owner: ${base.owner_name} · Responsible administrator: ${creator}`)).toBeNull();
 await userEvent.click(screen.getByText("Delivery and administrator contacts"));
 if(origin==="create")expect(screen.getByText("Activation delivery",{exact:true})).toBeVisible();else expect(screen.queryByText("Activation delivery",{exact:true})).toBeNull();
});

// Frozen external delivery is explicit while the initiating administrator's original mailbox remains intact.
it("shows recorded testing contacts without relabeling the original activation mailbox",async()=>{
 const route={original_email:"owner@example.test",effective_email:"capture@example.test",environment:"staging" as const,policy_hash:"a".repeat(64),redirected:true};
 mount({...base,administrator_email:"creator@example.test",email_contacts:{activation:{...route,original_email:"creator@example.test"},owner:route}});
 await userEvent.click(await screen.findByText("Delivery and administrator contacts"));
 const contacts=await screen.findByRole("region",{name:"Tenancy email contacts"});
 expect(contacts).toHaveTextContent("Original contact: creator@example.test");expect(contacts).toHaveTextContent("Test delivery: capture@example.test");expect(screen.getByText("Activation delivery",{exact:true}).nextElementSibling).toHaveTextContent("capture@example.test");expect(screen.getByText("Original administrator contact",{exact:true}).nextElementSibling).toHaveTextContent("creator@example.test");
});

// Manual OCI setup must use the frozen effective bootstrap contact, not the administrator's original identity.
it.each(["create","import"] as const)("guides %s bootstrap email to the recorded testing destination",async(origin)=>{
 const route={original_email:"creator@example.test",effective_email:"capture@example.test",environment:"staging" as const,policy_hash:"a".repeat(64),redirected:true};
 mount({...base,origin,administrator_email:"creator@example.test",email_contacts:{activation:route,owner:{...route,original_email:"owner@example.test"}}});
 await userEvent.click(await screen.findByText("Delivery and administrator contacts"));
 const contacts=await screen.findByRole("region",{name:"Tenancy email contacts"});expect(within(contacts).getByText(origin==="create"?"Activation / bootstrap email":"Bootstrap contact email")).toBeVisible();
 await userEvent.click(screen.getByText("OCI administrator checklist"));
 const instruction=screen.getByText(/use the recorded bootstrap contact/,{selector:"li"});expect(instruction).toHaveTextContent("capture@example.test");expect(instruction).not.toHaveTextContent("creator@example.test");
 if(origin==="import")expect(screen.queryByText(/Activation delivery:/)).toBeNull();
});


// Background password preparation is a machine wait, so polling must continue until setup completes.
it("continues polling while configuring waits on its password worker",async()=>{
  const c=mount({...verified,state:"waiting",phase:"configuring",available_actions:[]});
  c.read.mockResolvedValue({...verified,state:"succeeded",phase:"complete",available_actions:[]});
  await screen.findByText(/worker is processing/);
  await screen.findByRole("heading",{name:"Local setup verified"},{timeout:4000});
  expect(c.read).toHaveBeenCalledTimes(2);
});


// Legacy in-flight create/import operations prepare a public key without dropping entered OCIDs.
it.each(["create","import"] as const)("prepares %s bootstrap inputs without resetting the handoff",async origin=>{
 const c=mount({...base,origin,available_actions:["verify_handoff","prepare_bootstrap_key"]});
 await screen.findByRole("region",{name:"Enter in OCI"});
 await userEvent.type(screen.getByLabelText("Bootstrap user OCID"),"ocid1.user.oc1..otmsimtyped");
 c.read.mockResolvedValue({...base,origin,public_key:"public demonstration",available_actions:["verify_handoff"]});
 await userEvent.click(screen.getByRole("button",{name:"Generate bootstrap key"}));
 await screen.findByLabelText("Public API key (PEM)");
 expect(c.write).toHaveBeenCalledWith(identifier,expect.objectContaining({action:"prepare_bootstrap_key",revision:2}),expect.any(AbortSignal));
 expect(screen.getByLabelText("Bootstrap user OCID")).toHaveValue("ocid1.user.oc1..otmsimtyped");
 expect((screen.getByText("OCI administrator checklist") as HTMLElement).closest("details")).not.toHaveAttribute("open");
});
