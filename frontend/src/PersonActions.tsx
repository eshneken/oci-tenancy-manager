import { CleanupResponsibilities } from "./CleanupResponsibilities";
import { EmailContactSummary } from "./EmailContacts";
import { baselineHref } from "./baselineNavigation";
import { PublishedBaseline } from "./BaselineHistory";
import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, WorkflowError } from "./api";
import type {
  ActionReceipt,
  OrganizationAction,
  PersonWorkflow,
} from "./contracts";
import { followLink } from "./navigation";

type Action = OrganizationAction["action"];
const destructiveActions = new Set<Action>(["offboard_person", "delete_tenancy", "remove_member", "transfer_owner", "merge"]);
const labels: Record<Action, string> = {
  create_tenancy: "Create tenancy",
  import_tenancy: "Import tenancy",
  join_shared: "Add to shared tenancy",
  offboard_person: "Offboard employee",
  delete_tenancy: "Initiate tenancy termination",
  remove_member: "Remove shared member",
  transfer_owner: "Transfer tenancy ownership",
  no_tenancy_required: "No tenancy required",
  keep_without_tenancy: "Keep in organization without a tenancy",
  ignore: "Ignore permanently",
  resolve: "Complete review",
  merge: "Merge employee identity",
  reonboard: "Re-onboard employee",
  mark_returned: "Mark employee returned",
  cancel_simulation: "Cancel local simulation",
};
const guidance: Record<string, string> = {
  RECOVERY_PASSWORD_ROTATION_REQUIRED:"Termination is blocked while recovery access or password reconciliation is outstanding. Review Administrator access on the tenancy and its password operation before retrying.",
  DESTRUCTIVE_CONFIRMATION_REQUIRED: "Review the action and acknowledge its consequences before continuing.",
  SIMULATION_ALREADY_FINISHED:
    "This simulation has already finished or changed. Reload the preview before making another decision.",
  SHARED_COMPARTMENT_NAME_REQUIRED:
    "Enter a name for the employee compartment.",
  ORGANIZATION_PREVIEW_CHANGED:
    "The organization or associations changed. Reload this preview and review your choices again.",
  ORGANIZATION_REVIEW_CHANGED:
    "This review has changed or is already closed. Refresh the list.",
  VALID_CREATE_NAME_REQUIRED:
    "Enter a tenancy name using only lowercase letters and numbers.",
  PARENT_SUBSCRIBED_REGION_REQUIRED:
    "Choose a home region from the parent subscription list. Reload the preview if the list changed.",
  DISTINCT_TENANCY_NAME_REQUIRED:
    "That tenancy name is already registered in OTM. Choose another name and try again; your other choices are kept.",
  TENANCY_ALREADY_REGISTERED: "That tenancy is already registered.",
  SIMULATED_CHILD_REQUIRED:
    "For local testing, use an OCID beginning ocid1.tenancy.oc1..otmsim. The parent cannot be imported as a child.",
  EXACT_IMPORT_TARGET_REQUIRED:
    "Import requires an exact simulated tenancy OCID.",
  PUBLISHED_BASELINE_REQUIRED:
    "Publish a baseline in Configuration before creating or importing a tenancy.",
  EMAIL_ROUTE_BLOCKED: "Configure an approved delivery contact or a non-production test destination before provisioning.",
  EMAIL_CONTEXT_CHANGED: "Email routing changed. Reload this preview before starting the operation.",
  ACCOUNTABILITY_MAPPING_REQUIRED:
    "Correct this employee's industry segment/reporting mapping before provisioning access.",
  IDENTITY_HAS_PENDING_WORK:
    "An affected identity or tenancy has pending work. Finish that work before merging identities.",
  IDENTITY_MERGE_PAIR_INVALID:
    "Choose an absent identity and a new source-present identity. The organization root is protected.",
  REVIEW_ALL_ASSOCIATIONS:
    "Review every current association before starting offboarding.",
  CURRENT_TRANSFER_RECIPIENT_REQUIRED:
    "Choose a different, currently present managed employee as the new owner.",
  LIFECYCLE_PROVIDER_UNAVAILABLE:
    "Lifecycle simulation is unavailable or paused. Application-only decisions are still available.",
  MERGE_OVERRIDE_CONFLICT:
    "These identities have conflicting organization overrides. Resolve those before merging.",
  ORGANIZATION_ROOT_PROTECTED:
    "The configured organization root cannot be removed from the managed directory.",
  PERSON_NOT_ABSENT: "This employee is present in the current feed and cannot be offboarded. Reload the preview.",
};

// Invalidate every related read model after an application decision or durable operation acceptance.
export async function refreshOrganization(
  client: ReturnType<typeof useQueryClient>,
) {
  await Promise.all(
    [
      "organization",
      "organization-mapping",
      "organization-reviews",
      "tenancies",
      "operations",
      "audit-history",
      "person-workflow",
    ].map((key) =>
      client.invalidateQueries({
        queryKey: [key],
        // Saved mapping context must be current even while its settings page is closed.
        refetchType: key === "organization-mapping" ? "all" : key === "person-workflow" ? "none" : "active",
      }),
    ),
  );
}

// Model real admin choices while clearly separating local provider simulation from app-only decisions.
export function PersonActions({
  personId,
  reviewId = null,
  initialAction,
  tenancyId,
  expired,
  navigate,
  onClose,
}: {
  personId: string;
  reviewId?: string | null;
  initialAction?: Action;
  tenancyId?: string;
  expired: () => void;
  navigate: (path: string) => void;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const requestKey = useRef(crypto.randomUUID());
  const [action, setAction] = useState<Action | "">(initialAction ?? "");
  const [name, setName] = useState("");
  const [region, setRegion] = useState("");
  const [kind, setKind] = useState<"individual" | "shared">("individual");
  const [importOcid, setImportOcid] = useState(
    "ocid1.tenancy.oc1..otmsim" + crypto.randomUUID().replaceAll("-", ""),
  );
  const [selectedTenancy, setSelectedTenancy] = useState(tenancyId ?? "");
  const [parent, setParent] = useState("");
  const [compartment, setCompartment] = useState("");
  const [compartmentMode,setCompartmentMode]=useState<"create"|"existing">("create");
  const [recipient, setRecipient] = useState("");
  const [formerOwner, setFormerOwner] = useState<""|"keep_member"|"remove">("");
  const [partner, setPartner] = useState("");
  const [plan, setPlan] = useState<
    Record<
      string,
      {
        action: "" | "delete" | "transfer" | "remove" | "keep";
        recipient: string;
        formerOwner: ""|"keep_member"|"remove";
      }
    >
  >({});
  const [consent, setConsent] = useState<string | null>(null);
  const [confirmEmpty, setConfirmEmpty] = useState(false);
  const [confirmManager, setConfirmManager] = useState(false);
  const [confirmShared, setConfirmShared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [viewBaseline,setViewBaseline]=useState(false);
  const baselineLink=useRef<HTMLAnchorElement>(null);
  useEffect(()=>{
    // Inline detail owns a history entry so browser Back/Forward also retain controlled form values.
    function popBaseline(){setViewBaseline(history.state?.otmBaselinePreview===personId);}
    window.addEventListener("popstate",popBaseline);
    return()=>window.removeEventListener("popstate",popBaseline);
  },[personId]);
  useEffect(()=>{
    if(viewBaseline) dialog.current?.querySelector<HTMLAnchorElement>(".baseline-backlink")?.focus();
    else baselineLink.current?.focus();
  },[viewBaseline]);

  // Returning from the recipe restores the same mounted form's name, region and other choices.
  function closeBaseline(){
    setViewBaseline(false);
    if(history.state?.otmBaselinePreview===personId) history.back();
  }
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<ActionReceipt | null>(null);
  const preview = useQuery({
    queryKey: ["person-workflow", personId, reviewId],
    queryFn: ({ signal }) => api.personWorkflow(personId, reviewId, signal),
    retry: false,
    enabled: receipt === null,
    refetchOnWindowFocus: false,
  });
  const data = preview.data;
  const selectedDetail = useQuery({
    queryKey: ["tenancies", "parents", selectedTenancy],
    queryFn: ({ signal }) => api.tenancy(selectedTenancy, signal),
    enabled: action === "join_shared" && Boolean(selectedTenancy),
    retry: false,
    refetchOnWindowFocus: false,
  });
  useEffect(() => {
    dialog.current?.showModal();
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    if ([preview.error, selectedDetail.error].some(
      failure => failure instanceof ApiError && [401, 403].includes(failure.status)))
      expired();
  }, [preview.error, selectedDetail.error, expired]);
  useEffect(() => {
    if (!data) return;
    // General entry requires a choice; only explicit eligible task links may preselect.
    setAction(
      initialAction && data.actions.includes(initialAction)
        ? initialAction
        : "",
    );
    setCompartment(data.person.email.split("@")[0].replaceAll(".", "-"));
    setPlan(
      Object.fromEntries(
        data.associations.map((a) => [a.id, { action: "", recipient: "", formerOwner: "remove" }]),
      ),
    );
    setConfirmEmpty(false);
    setFormerOwner("");
    setConfirmManager(false);
    setConfirmShared(false);
    requestKey.current = crypto.randomUUID();
  }, [data, initialAction]);
  const target = data?.associations.find(
    (a) => a.tenancy_id === selectedTenancy,
  );
  const managerWarning = Boolean(
    data?.is_manager &&
    (action === "delete_tenancy" ||
      (action === "offboard_person" &&
        Object.values(plan).some((p) => p.action === "delete"))),
  );
  const sharedWarning = Boolean(
    data &&
    (action === "offboard_person"
      ? data.associations.some(
          (a) =>
            a.tenancy_kind === "shared" &&
            plan[a.id]?.action &&
            plan[a.id].action !== "keep",
        )
      : ["remove_member", "transfer_owner", "delete_tenancy"].includes(
          action,
        ) && target?.tenancy_kind === "shared"),
  );
  const destructive = action !== "" && destructiveActions.has(action) &&
    (action !== "transfer_owner" || formerOwner === "remove");
  const cleanupRequired = action === "remove_member" ||
    (action === "transfer_owner" && formerOwner === "remove") ||
    (action === "offboard_person" && data?.associations.some(a =>
      plan[a.id]?.action === "remove" || (plan[a.id]?.action === "transfer" && plan[a.id]?.formerOwner === "remove")));
  const validTransfer = action !== "transfer_owner" || Boolean(recipient && formerOwner &&
    (formerOwner !== "keep_member" || target?.tenancy_kind === "shared") &&
    (formerOwner !== "remove" || target?.user_ocid));
  const validPlan = action !== "offboard_person" || Boolean(data?.associations.every(a =>
    plan[a.id]?.action !== "transfer" || (plan[a.id]?.recipient && plan[a.id]?.formerOwner &&
      (plan[a.id].formerOwner !== "keep_member" || a.tenancy_kind === "shared") &&
      (plan[a.id].formerOwner !== "remove" || a.user_ocid))));
  // Consent is specific to the whole displayed review, not merely to a button or employee.
  const consentContext = JSON.stringify({personId, reviewId, action, selectedTenancy, recipient,
    partner, plan, formerOwner, context:data?.context, associations:data?.associations, previewAt:preview.dataUpdatedAt});
  const acknowledged = consent === consentContext;
  useEffect(() => { setConsent(null); setConfirmShared(false); }, [consentContext]);
  const provisioning = action === "create_tenancy" || action === "import_tenancy";
  const controls = action !== "" && Boolean(data?.actions.includes(action)) && (!provisioning || Boolean(data?.current_baseline));

  const validCreation =
    action !== "create_tenancy" ||
    (/^[a-z0-9]{1,200}$/.test(name) &&
      Boolean(
        data?.creation_regions?.some((item) => item.identifier === region),
      ));

  // Wait until submission releases the input before focusing a rejected name for correction.
  useEffect(() => {
    if (!busy && error === guidance.DISTINCT_TENANCY_NAME_REQUIRED)
      nameInput.current?.focus();
  }, [busy, error]);

  useEffect(() => { setFormerOwner(""); }, [selectedTenancy]);

  // Any edit starts a different bounded request; unchanged retries preserve the original identity.
  function edited() {
    requestKey.current = crypto.randomUUID();
    setError("");
  }

  // Close through the browser so focus returns to the employee/review/tenancy trigger.
  function close() {
    if (!busy) {
      dialog.current?.close();
      onClose();
    }
  }

  // Re-fetch an expired preview instead of applying choices to a newer organization implicitly.
  async function reload() {
    setConsent(null);
    setError("");
    setReceipt(null);
    await preview.refetch();
  }

  // Build only action-relevant fields; stale values from another form cannot retarget the operation.
  function command(current: PersonWorkflow): OrganizationAction {
    if (!action) throw new Error("Choose an action.");
    const body: OrganizationAction = {
      client_request_key: requestKey.current,
      context: current.context,
      person_id: personId,
      review_id: reviewId,
      action,
    };
    if (action === "create_tenancy" || action === "import_tenancy") {
      body.tenancy_kind = kind;
      if (action === "import_tenancy") body.import_ocid = importOcid;
    }
    if (action === "create_tenancy") {
      if (!validCreation)
        throw new Error(
          "Enter a valid requested name and choose a home region.",
        );
      body.name = name;
      body.home_region = region;
    }
    if (action === "join_shared") {
      body.tenancy_id = selectedTenancy;
      if(compartmentMode==="existing") body.existing_compartment_ocid=parent;
      else {body.parent_compartment_ocid=parent;body.compartment_name=compartment;}
    }
    if (["delete_tenancy", "remove_member", "transfer_owner"].includes(action))
      body.tenancy_id = selectedTenancy;
    if (action === "transfer_owner") {
      if (!validTransfer) throw new Error("Choose the new owner and former-owner disposition.");
      body.recipient_person_id = recipient;
      body.former_owner_disposition = formerOwner as "keep_member"|"remove";
    }
    if (action === "merge") body.partner_person_id = partner;
    if (action === "cancel_simulation")
      body.operation_id = current.pending_operation_id;
    if (action === "offboard_person") {
      if (current.associations.some((a) => !plan[a.id]?.action))
        throw new Error("Choose an action for every association.");
      body.plan = current.associations.map((a) => ({
        association_id: a.id,
        action: plan[a.id].action as "delete" | "transfer" | "remove" | "keep",
        recipient_person_id:
          plan[a.id].action === "transfer" ? plan[a.id].recipient : null,
        ...(plan[a.id].action === "transfer" ? {former_owner_disposition:plan[a.id].formerOwner as "keep_member"|"remove"} : {}),
      }));
      body.confirm_no_associations = confirmEmpty;
    }
    if (destructive) body.confirm_destructive = acknowledged;
    body.confirm_manager = confirmManager;
    body.confirm_shared = confirmShared;
    return body;
  }

  // An accepted workflow is tracked elsewhere; only application-only receipts claim immediate completion.
  async function submit() {
    if (!data || !controls || !validTransfer || !validPlan || busy || preview.isError || preview.isFetching
      || (destructive && !acknowledged)
      || (managerWarning && !confirmManager) || (sharedWarning && !confirmShared)
      || (action === "offboard_person" && data.associations.length === 0 && !confirmEmpty)) return;
    let body: OrganizationAction;
    try {
      body = command(data);
    } catch (failure) {
      setError((failure as Error).message);
      return;
    }
    setBusy(true);
    setError("");
    controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      const saved = await api.organizationAction(body, signal);
      if (signal.aborted) return;
      // Finish dependent refreshes before the success dialog offers onward navigation.
      await refreshOrganization(client);
      if (!signal.aborted) setReceipt(saved);
    } catch (failure) {
      if (signal.aborted) return;
      if (failure instanceof ApiError && [401, 403].includes(failure.status))
        expired();
      else
        setError(
          failure instanceof WorkflowError
            ? (guidance[failure.code] ??
                "This action is no longer available with the displayed preview. Reload the preview and review your choices.")
            : "The action could not be confirmed. Retry with unchanged choices to reuse this request, or refresh the list before starting a new action.",
        );
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="workflow-dialog"
      aria-labelledby="workflow-title"
      onCancel={(event) => {
        event.preventDefault();
        if(viewBaseline) closeBaseline(); else close();
      }}
    >
      <h2 id="workflow-title">
        {data?.review
          ? "Organization review"
          : "Employee & tenancy associations"}
      </h2>
      {viewBaseline && data?.current_baseline ? <PublishedBaseline version={data.current_baseline} navigate={navigate} back={{path:location.pathname,label:`Back to ${action==="import_tenancy"?"import":"create"} tenancy`,close:closeBaseline}}/> : receipt && data ? (
        <>
          <p className="workflow-person">
            <strong>{data.person.name}</strong>
            <span>{data.person.email}</span>
          </p>
          <div className="workflow-result" role="status">
            <h3>
              {receipt.state === "cancelled"
                ? "Simulation cancelled"
                : receipt.operation_id
                  ? "Operation accepted"
                  : "Decision saved"}
            </h3>
            <p>
              {receipt.state === "cancelled"
                ? "No further local execution will run. Unresolved organization work is available for review again."
                : receipt.operation_id
                  ? "The review handoff is complete. Tenancy and access changes remain pending until the worker verifies them."
                  : "The organization decision has been recorded."}
            </p>
            {receipt.operation_id && (
              <a
                href={"/operations/" + receipt.operation_id}
                onClick={(event) => {
                  close();
                  followLink(
                    event,
                    "/operations/" + receipt.operation_id,
                    navigate,
                  );
                }}
              >
                View operation
              </a>
            )}
          </div>
        </>
      ) : preview.isPending ? (
        <p role="status">Loading current preview…</p>
      ) : preview.isError ? (
        <div role="alert">
          <p>
            This employee or review could not be loaded. Refresh the current
            organization before trying again.
          </p>
          <button className="button secondary" onClick={() => void reload()}>
            Reload preview
          </button>
        </div>
      ) : (
        data && (
          <>
            <p className="workflow-person">
              <strong>{data.person.name}</strong>
              <span>{data.person.email}</span>
            </p>
            {
              <>
                {data.provider_mode === "simulated" && (
                  <p className="notice">
                    OCI operations are simulated locally. No cloud resources or
                    accounts will be changed.
                  </p>
                )}
                {data.mapping_required && (
                  <p className="notice" role="status">
                    Organization mapping must be corrected before creating or
                    importing a tenancy, or adding this employee to a shared
                    tenancy. Cleanup and other available decisions remain
                    separate.{" "}
                    <a
                      href="/organization-mapping"
                      onClick={(event) => {
                        close();
                        followLink(event, "/organization-mapping", navigate);
                      }}
                    >
                      Repair Organization Mapping
                    </a>
                  </p>
                )}
                {data.pending_operation_id && (
                  <p className="notice">
                    This employee has pending work.{" "}
                    <a
                      href={"/operations/" + data.pending_operation_id}
                      onClick={(event) => {
                        close();
                        followLink(
                          event,
                          "/operations/" + data.pending_operation_id,
                          navigate,
                        );
                      }}
                    >
                      View operation
                    </a>
                  </p>
                )}
                {data.associations.length > 0 && (
                  <div className="workflow-associations">
                    <h3>Current associations ({data.associations.length})</h3>
                    <ul>
                      {data.associations.map((a) => (
                        <li key={a.id}>
                          <a
                            href={"/tenancies/" + a.tenancy_id}
                            onClick={(event) => {
                              close();
                              followLink(
                                event,
                                "/tenancies/" + a.tenancy_id,
                                navigate,
                              );
                            }}
                          >
                            {a.tenancy_name}
                          </a>
                          <span>
                            {a.tenancy_kind} · {a.role} · {a.status}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {data.actions.length === 0 ? (
                  <p>
                    No action is currently available. Complete pending work or
                    correct the source data first.
                  </p>
                ) : (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void submit();
                    }}
                  >
                    <label>
                      Action
                      <Select
                        disabled={busy}
                        value={action}
                        required
                        onChange={(event) => {
                          setAction(event.target.value as Action);
                          edited();
                          setConfirmManager(false);
                          setConfirmShared(false);
                        }}
                      >
                        <option value="">Choose an action</option>
                        {data.actions.map((name) => (
                          <option key={name} value={name}>
                            {labels[name]}
                          </option>
                        ))}
                      </Select>
                    </label>
                    {(action === "create_tenancy" ||
                      action === "import_tenancy") && (
                      <div className="workflow-fields">
                        <p className="notice full-field">{data.current_baseline ? <>Selected baseline: <a ref={baselineLink} href={baselineHref(data.current_baseline.id,location.pathname)} onClick={event=>{if(!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey&&!event.button){event.preventDefault();history.pushState({otmBaselinePreview:personId},"",location.href);setViewBaseline(true);}}}>Version {data.current_baseline.version_number}</a> · simulated. This version stays with the operation.</> : <>No published baseline. <a href="/configuration" onClick={event=>{followLink(event,"/configuration",navigate);if(event.defaultPrevented) close();}}>Publish a baseline</a> before creating or importing a tenancy.</>}</p>
                        <EmailContactSummary contacts={data.email_contacts} activation={action==="create_tenancy"}/>
                        {action === "create_tenancy" && (
                          <>
                            <label>
                              Requested tenancy name
                              <input
                                required
                                ref={nameInput}
                                pattern="[a-z0-9]+"
                                maxLength={200}
                                value={name}
                                disabled={busy}
                                onChange={(event) => {
                                  setName(event.target.value);
                                  edited();
                                }}
                                aria-describedby="create-name-help"
                              />
                            </label>
                            <label>
                              Home region
                              <Select
                                required
                                value={region}
                                disabled={busy}
                                onChange={(event) => {
                                  setRegion(event.target.value);
                                  edited();
                                }}
                              >
                                <option value="">Choose a home region</option>
                                {(data.creation_regions ?? []).map((item) => (
                                  <option
                                    key={item.identifier}
                                    value={item.identifier}
                                  >
                                    {item.name} · {item.identifier}
                                  </option>
                                ))}
                              </Select>
                            </label>
                            <p
                              className="field-help full-field"
                              id="create-name-help"
                            >
                              Use lowercase letters and numbers. OCI checks
                              global name availability. Region choices simulate
                              the parent's subscriptions in this local
                              environment.
                            </p>
                          </>
                        )}
                        <label>
                          Tenancy type
                          <Select
                            value={kind}
                            disabled={busy}
                            onChange={(event) => {
                              setKind(
                                event.target.value as "individual" | "shared",
                              );
                              edited();
                            }}
                          >
                            <option value="individual">Individual</option>
                            <option value="shared">Shared</option>
                          </Select>
                        </label>
                        {action === "import_tenancy" && (
                          <label className="full-field">
                            Simulated tenancy OCID
                            <input
                              required
                              maxLength={256}
                              value={importOcid}
                              disabled={busy}
                              onChange={(event) => {
                                setImportOcid(event.target.value);
                                edited();
                              }}
                            />
                          </label>
                        )}
                      </div>
                    )}
                    {action === "join_shared" && (
                      <>
                        <label>
                          Shared tenancy
                          <Select
                            required
                            disabled={busy}
                            value={selectedTenancy}
                            onChange={(event) => {
                              setSelectedTenancy(event.target.value);
                              setParent("");
                              edited();
                            }}
                          >
                            <option value="">Choose a shared tenancy</option>
                            {data.shared_tenancies.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.name} · owner {t.owner_name}
                              </option>
                            ))}
                          </Select>
                        </label>
                        {selectedDetail.isPending && selectedTenancy ? (
                          <p role="status">Loading existing compartments…</p>
                        ) : selectedDetail.isError ? (
                          <div role="alert">
                            <p>Compartment choices could not be loaded.</p>
                            <button
                              type="button"
                              className="button secondary"
                              disabled={selectedDetail.isFetching}
                              onClick={() => void selectedDetail.refetch()}
                            >
                              Retry compartments
                            </button>
                          </div>
                        ) : null}
                        <label>Compartment assignment<Select value={compartmentMode} disabled={busy} onChange={event=>{setCompartmentMode(event.target.value as "create"|"existing");setParent("");edited();}}><option value="create">Create a compartment under an existing parent</option><option value="existing">Use an existing compartment</option></Select></label>
                        <label>
                          {compartmentMode==="create"?"Existing parent compartment":"Existing compartment"}
                          <Select
                            key={compartmentMode}
                            required
                            disabled={busy || !selectedDetail.data}
                            value={parent}
                            onChange={(event) => {
                              setParent(event.target.value);
                              edited();
                            }}
                          >
                            <option value="">{compartmentMode==="create"?"Choose an existing parent":"Choose an existing compartment"}</option>
                            {selectedDetail.data?.compartment_parents.filter(p=>compartmentMode==="create"||p.ocid!==selectedDetail.data?.tenancy.tenancy_ocid).map(
                              (p) => (
                                <option key={p.ocid} value={p.ocid}>
                                  {p.name} · {p.ocid.slice(-10)}
                                </option>
                              ),
                            )}
                          </Select>
                        </label>
                        {parent && (
                          <p className="technical-id">
                            {compartmentMode==="create"?"Selected parent":"Selected compartment"}: {parent}
                          </p>
                        )}
                        {compartmentMode==="create"&&<label>
                          Employee compartment name
                          <input
                            required
                            maxLength={100}
                            value={compartment}
                            disabled={busy}
                            onChange={(event) => {
                              setCompartment(event.target.value);
                              edited();
                            }}
                          />
                        </label>}
                        {compartmentMode==="existing"&&<p className="notice">The user will be assigned to this existing compartment. Its resources and compartment structure will remain in place.</p>}
                      </>
                    )}
                    {[
                      "delete_tenancy",
                      "remove_member",
                      "transfer_owner",
                    ].includes(action) && (
                      <label>
                        Tenancy
                        <Select
                          required
                          disabled={busy}
                          value={selectedTenancy}
                          onChange={(event) => {
                            setSelectedTenancy(event.target.value);
                            edited();
                          }}
                        >
                          <option value="">Choose a tenancy</option>
                          {data.associations
                            .filter((a) =>
                              a.actions.includes(
                                action === "delete_tenancy"
                                  ? "delete"
                                  : action === "remove_member"
                                    ? "remove"
                                    : "transfer",
                              ),
                            )
                            .map((a) => (
                              <option key={a.id} value={a.tenancy_id}>
                                {a.tenancy_name} · {a.role}
                              </option>
                            ))}
                        </Select>
                      </label>
                    )}
                    {action === "transfer_owner" && (
                      <>
                      <label>
                        New owner
                        <Select
                          required
                          disabled={busy}
                          value={recipient}
                          onChange={(event) => {
                            setRecipient(event.target.value);
                            edited();
                          }}
                        >
                          <option value="">Choose a current employee</option>
                          {data.transfer_recipients.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name} · {p.email}
                            </option>
                          ))}
                        </Select>
                      </label>
                      <label>Former owner
                        <Select required disabled={busy} value={formerOwner} onChange={event => {setFormerOwner(event.target.value as "keep_member"|"remove");edited();}}>
                          <option value="">Choose what happens to the former owner</option>
                          {target?.tenancy_kind === "shared" && <option value="keep_member">Keep as a member — retain existing access</option>}
                          <option value="remove">Remove from tenancy — delete their recorded user</option>
                        </Select>
                      </label>
                      {formerOwner === "keep_member" && <p className="notice">Only accountability changes for the former owner. Their user ID, group memberships, existing permissions (including any administrator access) and compartment mappings remain unchanged. They remain a member of this tenancy.</p>}
                      {formerOwner === "remove" && <p className="notice">The transfer operation removes the former owner's recorded user and group memberships. Identity to remove: <code className="technical-id">{target?.user_ocid ?? "Not recorded — automated removal is unavailable"}</code>. Resources, compartments and additional accounts are left for manual cleanup.</p>}
                      </>
                    )}
                    {action === "offboard_person" && (
                      <>
                        <h3>Review every association</h3>
                        {data.associations.map((a) => (
                          <fieldset className="association-choice" key={a.id}>
                            <legend>
                              {a.tenancy_name} · {a.role}
                            </legend>
                            <label>
                              {"Action for " + a.tenancy_name}
                              <Select
                                required
                                disabled={busy}
                                value={plan[a.id]?.action ?? ""}
                                onChange={(event) => {
                                  setPlan({
                                    ...plan,
                                    [a.id]: {
                                      action: event.target.value as
                                        | "delete"
                                        | "transfer"
                                        | "remove"
                                        | "keep",
                                      recipient: "",
                                      formerOwner: "remove",
                                    },
                                  });
                                  edited();
                                }}
                              >
                                <option value="">Choose an action</option>
                                {a.actions.map((choice) => (
                                  <option key={choice} value={choice}>
                                    {
                                      {
                                        delete: "Initiate termination",
                                        transfer: "Transfer ownership",
                                        remove: "Remove membership",
                                        keep: "Keep association",
                                      }[choice]
                                    }
                                  </option>
                                ))}
                              </Select>
                            </label>
                            {plan[a.id]?.action === "transfer" && (
                              <>
                              <label>
                                {"New owner for " + a.tenancy_name}
                                <Select
                                  required
                                  disabled={busy}
                                  value={plan[a.id].recipient}
                                  onChange={(event) => {
                                    setPlan({
                                      ...plan,
                                      [a.id]: {
                                        ...plan[a.id],
                                        recipient: event.target.value,
                                      },
                                    });
                                    edited();
                                  }}
                                >
                                  <option value="">
                                    Choose a current employee
                                  </option>
                                  {data.transfer_recipients.map((p) => (
                                    <option key={p.id} value={p.id}>
                                      {p.name} · {p.email}
                                    </option>
                                  ))}
                                </Select>
                              </label>
                              <label>{"Former owner for " + a.tenancy_name}
                                <Select required disabled={busy} value={plan[a.id].formerOwner} onChange={event=>{setPlan({...plan,[a.id]:{...plan[a.id],formerOwner:event.target.value as "keep_member"|"remove"}});edited();}}>
                                  <option value="remove">Remove from tenancy — delete their recorded user</option>
                                  {a.tenancy_kind === "shared" && <option value="keep_member">Keep as a member — retain existing access</option>}
                                </Select>
                              </label>
                              {plan[a.id].formerOwner === "keep_member" && <p className="notice">The former owner's identity, group memberships, permissions (including any administrator access) and compartment mappings remain unchanged. They stay tracked as a member.</p>}
                              {plan[a.id].formerOwner === "remove" && <p className="notice">Identity to remove: <code className="technical-id">{a.user_ocid ?? "Not recorded — automated removal is unavailable"}</code>. Resources, compartments and additional accounts remain for manual cleanup.</p>}
                              </>
                            )}
                            {a.compartment_ocid && (
                              <p className="muted">
                                Compartment:{" "}
                                {a.compartment_name ?? a.compartment_ocid}
                              </p>
                            )}
                          </fieldset>
                        ))}
                        {data.associations.length === 0 && (
                          <label className="workflow-check">
                            <input
                              type="checkbox"
                              required
                              disabled={busy}
                              checked={confirmEmpty}
                              onChange={(event) => {
                                setConfirmEmpty(event.target.checked);
                                edited();
                              }}
                            />
                            I verified that no tenancy associations need to be
                            retained or handled outside this registry.
                          </label>
                        )}
                        <p className="notice">
                          This explicitly offboards the employee. After the selected work
                          completes, they leave the managed directory if no associations
                          remain; kept associations stay mapped outside the organization.
                          A later fresh feed containing their employee row can restore
                          directory presence, but never deleted tenancies, accounts or access.
                          The tenancy owner reviews the departing user's resources
                          manually. Shared compartments and other members' resources
                          are retained.
                        </p>
                      </>
                    )}
                    {action === "merge" && (
                      <>
                        <p>
                          Keep the absent employee's stable identity and tenancy
                          associations, and apply the new employee's name, email
                          and reporting metadata. This does not rename corporate
                          or OCI identities.
                        </p>
                        <label>
                          Matching identity
                          <Select
                            required
                            disabled={busy}
                            value={partner}
                            onChange={(event) => {
                              setPartner(event.target.value);
                              edited();
                            }}
                          >
                            <option value="">
                              Choose the confirmed matching employee
                            </option>
                            {data.merge_partners.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name} · {p.email}
                              </option>
                            ))}
                          </Select>
                        </label>
                      </>
                    )}
                    {action === "cancel_simulation" && (
                      <p className="notice">
                        Cancel pending local simulation without undoing verified
                        changes. Current source reviews and associations remain
                        available for a new decision.
                      </p>
                    )}
                    {action === "ignore" && (
                      <p className="notice">
                        Ignore this employee's Industry segment mapping review
                        permanently. This does not assign an industry segment or
                        suppress other kinds of review.
                      </p>
                    )}
                    {action === "resolve" && (
                      <p className="notice">
                        Record completion of this reviewed condition. This does
                        not repair source data. A changed condition can open
                        another review.
                      </p>
                    )}
                    {action === "keep_without_tenancy" && (
                      <p className="notice">
                        Keep this employee in the organization with no tenancy and close
                        this onboarding review. You can create or import a tenancy, or add
                        this employee to a shared tenancy later from their employee record. Routine feed updates
                        will not reopen this same onboarding review.
                      </p>
                    )}
                    {action === "no_tenancy_required" && (
                      <p className="notice">
                        Record that this employee needs no tenancy and close
                        onboarding reviews until an administrator re-onboards
                        them. Their source profile and reporting relationships
                        are retained. They remain visible with Include excluded profiles.
                      </p>
                    )}
                    {action === "remove_member" && (
                      <p className="notice">
                        OTM removes group memberships and deletes this user's account.
                        Ask the tenancy owner to review and clean only this user's
                        resources in the assigned compartment. The compartment and
                        other members' resources remain.
                      </p>
                    )}
                    {managerWarning && (
                      <label className="workflow-check">
                        <input
                          type="checkbox"
                          required
                          disabled={busy}
                          checked={confirmManager}
                          onChange={(event) => {
                            setConfirmManager(event.target.checked);
                            edited();
                          }}
                        />
                        This employee is a manager. I have reviewed the tenancy
                        termination impact.
                      </label>
                    )}
                    {cleanupRequired && <><p className="notice">User removal does not clean resources, compartments or additional accounts. Coordinate manual cleanup with the current tenancy owner.</p><CleanupResponsibilities/></>}
                    {sharedWarning && (
                      <>
                      <label className="workflow-check">
                        <input
                          type="checkbox"
                          required
                          disabled={busy}
                          checked={confirmShared}
                          onChange={(event) => {
                            setConfirmShared(event.target.checked);
                            edited();
                          }}
                        />
                        {cleanupRequired ? "I reviewed the shared tenancy impact and manual cleanup responsibilities." : action === "transfer_owner" ? "I reviewed the ownership change and retained access for this shared tenancy." : "I reviewed the shared tenancy impact."}
                      </label>
                      </>
                    )}
                    {destructive && (
                      <div className="alert destructive-confirmation">
                        <p><strong>{action === "transfer_owner" ? "Confirm former-owner access removal" : "Review destructive action"}</strong></p>
                        <p id="workflow-destructive-consequences">
                          {action === "offboard_person" && <>Offboard {data.person.name} ({data.person.email}) using every association choice shown above. Kept associations remain tracked outside the organization.</>}
                          {action === "delete_tenancy" && <>Initiate termination of {target?.tenancy_name ?? "the selected tenancy"} and its resources. Remove this tenancy association for {data.person.name} ({data.person.email}); employee directory status is unchanged.</>}
                          {action === "remove_member" && <>Remove {data.person.name} ({data.person.email}) from {target?.tenancy_name ?? "the selected tenancy"}, including their user account and group access. Resources and compartments remain for manual cleanup. Employee directory status is unchanged.</>}
                          {action === "transfer_owner" && <>Transfer {target?.tenancy_name ?? "the selected tenancy"} from {data.person.name} ({data.person.email}) to {data.transfer_recipients.find(p=>p.id===recipient)?.name ?? "the selected new owner"} ({data.transfer_recipients.find(p=>p.id===recipient)?.email ?? "choose a recipient"}). Remove the former owner's recorded user and group memberships after establishing the replacement owner. Resources, compartments and additional accounts remain for manual cleanup.</>}
                          {action === "merge" && <>Merge {data.person.name} ({data.person.email}) with {data.merge_partners.find(p=>p.id===partner)?.name ?? "the selected identity"} ({data.merge_partners.find(p=>p.id===partner)?.email ?? "choose an identity"}). This is a one-way identity remap: the absent identity survives and keeps its tenancy associations.</>}
                        </p>
                        <label className="workflow-check">
                          <input type="checkbox" required disabled={busy || preview.isFetching}
                            aria-describedby="workflow-destructive-consequences" checked={acknowledged}
                            onChange={event=>{setConsent(event.target.checked ? consentContext : null);setError("");}} />
                          <span>I acknowledge the consequences of this action for the identified employee and tenancies.</span>
                        </label>
                      </div>
                    )}
                    {error && (
                      <div className="alert" role="alert">
                        <p>{error}</p>
                        <button
                          type="button"
                          className="button secondary"
                          disabled={busy}
                          onClick={() => void reload()}
                        >
                          Reload preview
                        </button>
                      </div>
                    )}
                    <div className="dialog-actions">
                      <button
                        type="button"
                        className="button secondary"
                        disabled={busy}
                        onClick={close}
                      >
                        Cancel
                      </button>
                      <button
                        className={destructive ? "button danger" : "button primary"}
                        disabled={busy || !controls || !validCreation || !validTransfer || !validPlan || preview.isFetching
                          || (destructive && !acknowledged)
                          || (managerWarning && !confirmManager) || (sharedWarning && !confirmShared)
                          || (action === "offboard_person" && data.associations.length === 0 && !confirmEmpty)}
                      >
                        {busy
                          ? "Saving…"
                          : action
                            ? action === "keep_without_tenancy" ? "Keep in organization" : labels[action]
                            : "Continue"}
                      </button>
                    </div>
                  </form>
                )}
              </>
            }
          </>
        )
      )}
      {(receipt ||
        preview.isPending ||
        preview.isError ||
        data?.actions.length === 0) && (
        <div className="dialog-actions">
          <button className="button secondary" disabled={busy} onClick={close}>
            {receipt ? "Done" : "Close"}
          </button>
        </div>
      )}
    </dialog>
  );
}
