import { EmailContactSummary } from "./EmailContacts";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { refreshOrganization } from "./PersonActions";
import { baselineHref } from "./baselineNavigation";
import { followLink } from "./navigation";
import type { OnboardingCommand, OnboardingHandoff } from "./contracts";

const phaseLabels = {
  preparing: "Preparing setup",
  handoff: "Administrator action required",
  review: "Ready for your review",
  configuring: "Setting up access",
  complete: "Local setup verified",
  blocked: "Setup needs attention",
  cancelled: "Setup cancelled",
};

// Keep onboarding's current action near the tenancy while Operations retains its durable history.
export function Onboarding({
  operationId,
  expired,
  navigate,
  showTenancyLink = true,
}: {
  showTenancyLink?: boolean;
  operationId: string;
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const result = useQuery({
    queryKey: ["onboarding", operationId],
    queryFn: ({ signal }) => api.onboarding(operationId, signal),
    retry: false,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.state ?? "")
        ? 1500
        : false,
  });
  const data = result.data;
  const [handoff, setHandoff] = useState<OnboardingHandoff>({
    tenancy_ocid: "",
    bootstrap_user_ocid: "",
    activation_user_ocid: null,
  });
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef(crypto.randomUUID());
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (
      result.error instanceof ApiError &&
      [401, 403].includes(result.error.status)
    )
      expired();
  }, [result.error, expired]);
  useEffect(() => {
    if (!data) return;
    setHandoff(
      data.submitted_handoff ?? {
        tenancy_ocid: data.origin === "import" ? data.suggested_handoff.tenancy_ocid : "",
        bootstrap_user_ocid: "",
        activation_user_ocid: null,
      },
    );
    setConfirmed(false);
    key.current = crypto.randomUUID();
  }, [operationId, data?.revision]);

  // Phase transitions refresh the related record once; polling the same phase does not fan out reads.
  useEffect(() => {
    if (!data) return;
    void client.invalidateQueries({
      queryKey: ["operations", "detail", operationId],
    });
    if (data.phase === "complete") void refreshOrganization(client);
    else void client.invalidateQueries({ queryKey: ["operations", "list"] });
  }, [client, operationId, data?.state, data?.phase]);

  // A changed form starts a new command; an unchanged transport retry reuses its request key.
  function edited() {
    key.current = crypto.randomUUID();
    setError("");
  }

  // Server revision and available actions guard double clicks and stale handoff/cleanup previews.
  async function submit(action: OnboardingCommand["action"]) {
    if (!data) return;
    setBusy(true);
    setError("");
    controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      await api.onboardingAction(
        operationId,
        {
          client_request_key: key.current,
          revision: data.revision,
          action,
          ...(action === "verify_handoff"
            ? { handoff: data.origin === "import"
                ? { ...handoff, tenancy_ocid: data.suggested_handoff.tenancy_ocid, activation_user_ocid: null }
                : handoff }
            : { confirm_cleanup: confirmed }),
        },
        signal,
      );
      if (signal.aborted) return;
      await result.refetch();
      await refreshOrganization(client);
    } catch (failure) {
      if (signal.aborted) return;
      if (failure instanceof ApiError && [401, 403].includes(failure.status))
        expired();
      else
        setError(
          "Setup could not be confirmed. Retry unchanged inputs to recover this request, or refresh the setup before making a new choice.",
        );
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  if (result.isPending) return <p role="status">Loading tenancy setup…</p>;
  if (!data || result.isError)
    return (
      <section className="operation-panel">
        <p role="alert">Unable to load tenancy setup.</p>
        <button
          className="button secondary"
          onClick={() => void result.refetch()}
        >
          Refresh setup
        </button>
      </section>
    );
  const verifying = data.available_actions.includes("verify_handoff");
  const reviewing = data.available_actions.includes("start_setup");
  return (
    <section
      className="operation-panel onboarding-panel"
      aria-labelledby="onboarding-title"
    >
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            {data.origin === "create" ? "NEW TENANCY" : "IMPORT TENANCY"}
          </span>
          <h2 id="onboarding-title" aria-live="polite" aria-atomic="true">
            {phaseLabels[data.phase]}
          </h2>
          <p>
            Owner: {data.owner_name} · Initiated by:{" "}
            {data.administrator_name}
          </p>
        </div>
        <button
          className="button secondary"
          disabled={busy || result.isFetching}
          onClick={() => void result.refetch()}
        >
          Refresh setup
        </button>
      </div>
      <p className="notice">{data.baseline ? <>Selected baseline: <a href={baselineHref(data.baseline.id,location.pathname+(location.pathname.startsWith("/operations/")?location.search:""))} onClick={event=>followLink(event,baselineHref(data.baseline!.id,location.pathname+(location.pathname.startsWith("/operations/")?location.search:"")),navigate)}>Version {data.baseline.version_number}</a> · simulated. Retained through activation and retries.</> : "This older operation has no selected baseline. No version has been attached retroactively."}</p>
      <p className="notice">
        <strong>Local simulation.</strong> No OCI activation email is sent, no key is issued
        and no OCI accounts are changed. The selected baseline is recorded;
        this simulator does not apply OCI configuration. Use simulated handoff below; do not create real OCI users or keys.
      </p>
      <EmailContactSummary contacts={data.email_contacts} activation={data.origin==="create"}/>
      {data.can_act === false && (
        <p className="notice">
          The responsible administrator must complete the next setup action.
        </p>
      )}
      {data.issue_code && (
        <p className="alert" role="alert">
          A required check did not pass. Temporary-account cleanup is not
          verified. Review the failed check below; previous verified steps are
          preserved.
        </p>
      )}
      {verifying && (
        <>
          <p>
            Configured parent{" "}
            <code className="technical-id">
              {data.expected_parent_tenancy_ocid}
            </code>
          </p>
          {data.origin === "create" && (
            <dl className="operation-facts">
              <div>
                <dt>Requested tenancy name</dt>
                <dd>{data.requested_name ?? "Not recorded"}</dd>
              </div>
              <div>
                <dt>Requested home region</dt>
                <dd>{data.requested_home_region ?? "Not recorded"}</dd>
              </div>
            </dl>
          )}
          <details className="operator-instructions">
            <summary>OCI administrator checklist</summary>
            <div className="operator-instructions-body">
              <p className="muted">
                For this local simulation, select “Use simulated handoff” below; do not
                create real OCI users or keys. The checklist describes the OCI
                handoff for the live integration.
              </p>
              <ol className="onboarding-instructions">
                <li>
                  {data.origin === "create" ? (
                    <>
                      <strong>Activate the requested child.</strong> Open the OCI
                      email sent to the {data.email_contacts?"activation delivery address":"activation mailbox"} below. Follow its
                      activation link, set your password and enroll MFA, then sign
                      in to the child tenancy. The name and home region were
                      supplied with this request; do not create another tenancy.{" "}
                      <a href="https://docs.oracle.com/en-us/iaas/Content/General/organization/child-tenancy-create.htm" target="_blank" rel="noopener noreferrer">Oracle activation guide</a>.
                    </>
                  ) : (
                    <>
                      <strong>Confirm the manual transfer is complete.</strong>{" "}
                      In the configured parent, open Governance &amp; Administration
                      → Organization Management → Tenancies and confirm this
                      tenancy is listed as a child. A tenancy created under another
                      parent needs transfer approval; an invited tenancy has a
                      different removal procedure. Follow the applicable Oracle
                      procedure before continuing.
                      <details>
                        <summary>Oracle transfer procedures</summary>
                        <ul>
                          <li><a href="https://docs.oracle.com/en-us/iaas/Content/General/organization/approve-createdchildtenancy-for-transfer.htm" target="_blank" rel="noopener noreferrer">Transfer a created child (approval uses the CLI)</a></li>
                          <li><a href="https://docs.oracle.com/en-us/iaas/Content/General/organization/link-delete.htm" target="_blank" rel="noopener noreferrer">Remove an invited child from its previous organization</a></li>
                          <li><a href="https://docs.oracle.com/en-us/iaas/Content/General/organization/sender-invitation-create.htm" target="_blank" rel="noopener noreferrer">Invite the tenancy from the new parent</a></li>
                          <li><a href="https://docs.oracle.com/en-us/iaas/Content/General/organization/recipient-invitation-accept.htm" target="_blank" rel="noopener noreferrer">Accept the invitation in the child</a></li>
                        </ul>
                      </details>
                    </>
                  )}
                </li>
                <li>
                  <strong>{data.origin === "import" ? "Confirm the selected child tenancy." : "Copy the child tenancy OCID."}</strong> In the child's
                  profile menu, select Tenancy, then copy the OCID under Tenancy
                  Information. A work-request ID is not a tenancy OCID.{" "}
                  <a href="https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/contactingsupport_topic-Locating_Oracle_Cloud_Infrastructure_IDs.htm" target="_blank" rel="noopener noreferrer">Find the tenancy OCID</a>.
                  {data.origin === "create" && (
                    <> Also open the activation administrator's User settings and
                      copy that user's OCID for the separate field below.</>
                  )}
                </li>
                <li>
                  <strong>Create the temporary bootstrap user in the child.</strong>{" "}
                  Open Identity &amp; Security → Domains → Default → Users → Create
                  user. Turn off Use the email address as the username, enter the
                  bootstrap username below, {data.email_contacts?.activation.effective_email ? <>complete the required name fields using your administrator details and use the recorded bootstrap contact <strong className="email-address">{data.email_contacts.activation.effective_email}</strong> for the email field</> : <>complete the required name/email fields using your administrator contact details</>}, and assign the
                  Administrators group. Copy the new user's OCID from its details.{" "}
                  <a href="https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/addingusers.htm" target="_blank" rel="noopener noreferrer">Create an administrator user</a>.
                </li>
                <li>
                  <strong>Grant identity-domain administration.</strong> In the
                  Default domain, open Administrators (or Security → Administrators),
                  find Identity domain administrator and add the bootstrap user.
                  Domain roles and the OCI Administrators group are separate grants.{" "}
                  <a href="https://docs.oracle.com/en-us/iaas/Content/Identity/users/assign-users-roles.htm" target="_blank" rel="noopener noreferrer">Assign the domain role</a>.
                </li>
                <li>
                  <strong>Attach the app-provided public key.</strong> Open the
                  bootstrap user's details → API keys → Add API Key. Choose Paste
                  a public key, paste the public PEM supplied by the app, and add
                  it. Do not generate a different key pair or upload a private key.{" "}
                  <a href="https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm" target="_blank" rel="noopener noreferrer">Upload an API public key</a>.{" "}
                  <strong>This simulator provides no usable key.</strong>
                </li>
                <li>
                  <strong>Return here and verify.</strong> Paste the matching OCIDs
                  below and select Verify handoff. For import, the tenancy OCID is
                  carried over from your original selection and cannot be edited here.
                  Keep the temporary accounts until
                  setup verifies replacement access and presents the cleanup review.
                  Do not paste passwords, MFA codes or private keys into this form.
                </li>
              </ol>
            </div>
          </details>
          <p className="muted">
            {data.origin === "create" && (
              <>
                {data.email_contacts ? <>Activation delivery: {data.email_contacts.activation.effective_email??"Not configured"} · Original administrator contact: {data.administrator_email??"Not configured"}</> : <>Activation mailbox: {data.administrator_email??"Not configured for this local administrator"}</>}{" "}·{" "}
              </>
            )}
            Bootstrap username: <code>{data.bootstrap_username}</code>
          </p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => {
              setHandoff(data.suggested_handoff);
              edited();
            }}
          >
            Use simulated handoff
          </button>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit("verify_handoff");
            }}
          >
            <div className="workflow-fields">
              <label className="full-field">
                Tenancy OCID
                <input
                  required
                  value={data.origin === "import" ? data.suggested_handoff.tenancy_ocid : handoff.tenancy_ocid}
                  readOnly={data.origin === "import"}
                  aria-describedby={data.origin === "import" ? "import-target-help" : undefined}
                  maxLength={256}
                  disabled={busy}
                  onChange={(event) => {
                    setHandoff({
                      ...handoff,
                      tenancy_ocid: event.target.value,
                    });
                    edited();
                  }}
                />
              </label>
              {data.origin === "import" && (
                <p id="import-target-help" className="muted full-field">
                  Selected when this import started. Only the bootstrap user OCID is needed below.
                </p>
              )}
              <label className="full-field">
                Bootstrap user OCID
                <input
                  required
                  value={handoff.bootstrap_user_ocid}
                  maxLength={256}
                  disabled={busy}
                  onChange={(event) => {
                    setHandoff({
                      ...handoff,
                      bootstrap_user_ocid: event.target.value,
                    });
                    edited();
                  }}
                />
              </label>
              {data.origin === "create" && (
                <label className="full-field">
                  Activation administrator user OCID
                  <input
                    required
                    value={handoff.activation_user_ocid ?? ""}
                    maxLength={256}
                    disabled={busy}
                    onChange={(event) => {
                      setHandoff({
                        ...handoff,
                        activation_user_ocid: event.target.value,
                      });
                      edited();
                    }}
                  />
                </label>
              )}
            </div>
            <button className="button primary" disabled={busy}>
              {busy ? "Submitting…" : "Verify handoff"}
            </button>
          </form>
        </>
      )}
      {reviewing && data.discovery && (
        <>
          <dl className="operation-facts">
            <div>
              <dt>Discovered tenancy</dt>
              <dd>
                {data.discovery.name}
                <span className="technical-id">
                  {data.discovery.tenancy_ocid}
                </span>
              </dd>
            </div>
            <div>
              <dt>Home region</dt>
              <dd>{data.discovery.home_region}</dd>
            </div>
            <div>
              <dt>Parent tenancy</dt>
              <dd className="technical-id">
                {data.discovery.parent_tenancy_ocid}
              </dd>
            </div>
            <div>
              <dt>Identity domain</dt>
              <dd className="technical-id">{data.discovery.domain_ocid}</dd>
            </div>
          </dl>
          <h3>Temporary access to retire</h3>
          <p>
            After permanent automation and owner/recovery access are verified,
            setup will remove:
          </p>
          <ul className="onboarding-targets">
            <li>
              Bootstrap user <code>{data.discovery.bootstrap_user_ocid}</code>
            </li>
            {data.origin === "create" && (
              <li>
                Activation administrator{" "}
                <code>{data.discovery.activation_user_ocid}</code>
              </li>
            )}
          </ul>
          {data.origin === "import" && (
            <p>Existing human administrators are preserved.</p>
          )}
          <label className="workflow-check">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(event) => {
                setConfirmed(event.target.checked);
                edited();
              }}
            />
            <span>
              I confirm the exact temporary accounts above may be removed after
              replacement access is verified.
            </span>
          </label>
          <button
            className="button primary"
            disabled={!confirmed || busy}
            onClick={() => void submit("start_setup")}
          >
            {busy
              ? "Submitting…"
              : data.phase === "blocked"
                ? "Retry setup"
                : "Start setup"}
          </button>
        </>
      )}
      {["preparing", "configuring"].includes(data.phase) && (
        <p role="status">
          The worker is processing this setup. You can leave this page and
          return later.
        </p>
      )}
      {data.phase === "complete" && (
        <p role="status">
          All local setup and temporary-account cleanup checks passed. Owner
          first sign-in remains unconfirmed.{" "}
          {showTenancyLink && (
            <a
              href={"/tenancies/" + data.tenancy_id}
              onClick={(event) =>
                followLink(event, "/tenancies/" + data.tenancy_id, navigate)
              }
            >
              Open tenancy
            </a>
          )}
        </p>
      )}
      {data.phase === "cancelled" && (
        <p>This local setup was cancelled. No OCI resources were changed.</p>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <h3>Setup checks · simulated</h3>
      <ol className="onboarding-checks">
        {data.checks.map((check) => (
          <li key={check.key}>
            <span>{check.label}</span>
            <span
              className={
                "badge " + (check.state === "verified" ? "succeeded" : "")
              }
            >
              {check.state === "verified"
                ? "Verified"
                : check.state === "needs_attention"
                  ? "Needs attention"
                  : "Pending"}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
