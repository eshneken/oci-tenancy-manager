import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { refreshOrganization } from "./PersonActions";
import { followLink } from "./navigation";
import type { ActionReceipt } from "./contracts";

// Preview the whole child and every affected person before accepting its asynchronous termination.
export function DeleteTenancy({
  tenancyId,
  expired,
  navigate,
  onClose,
}: {
  tenancyId: string;
  expired: () => void;
  navigate: (path: string) => void;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const controller = useRef<AbortController | null>(null);
  const key = useRef(crypto.randomUUID());
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<ActionReceipt | null>(null);
  const preview = useQuery({
    queryKey: ["tenancy-deletion", tenancyId],
    queryFn: ({ signal }) => api.deletionPreview(tenancyId, signal),
    retry: false,
    refetchOnWindowFocus: false,
    enabled: receipt === null,
  });
  const data = preview.data;
  useEffect(() => {
    dialog.current?.showModal();
    dialog.current?.querySelector<HTMLElement>("h2")?.focus();
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    if (
      preview.error instanceof ApiError &&
      [401, 403].includes(preview.error.status)
    )
      expired();
  }, [preview.error, expired]);

  // A new affected-set context always requires fresh consent, including background reconnection.
  useEffect(() => {
    setConfirmed(false);
    key.current = crypto.randomUUID();
  }, [data?.context]);

  // A fresh preview invalidates previous consent; uncertainty retries retain the original request UUID.
  async function reload() {
    setConfirmed(false);
    setError("");
    key.current = crypto.randomUUID();
    await preview.refetch();
  }

  // The server freezes the affected set and commits reservations/audit/job before returning acceptance.
  async function submit() {
    if (!data || !confirmed || preview.isError || preview.isFetching) return;
    setBusy(true);
    setError("");
    controller.current = new AbortController();
    const signal = controller.current.signal;
    try {
      const result = await api.deleteTenancy(
        {
          client_request_key: key.current,
          tenancy_id: tenancyId,
          context: data.context,
          confirm_deletion: confirmed,
          confirm_shared: data.shared_warning && confirmed,
          confirm_manager: data.manager_warning && confirmed,
        },
        signal,
      );
      if (signal.aborted) return;
      setReceipt(result);
      await refreshOrganization(client);
    } catch (failure) {
      if (signal.aborted) return;
      if (failure instanceof ApiError && [401, 403].includes(failure.status))
        expired();
      else
        setError(
          "Termination could not be confirmed. Retry with unchanged confirmation to recover this request, or reload the preview to review current memberships.",
        );
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  // An in-flight acceptance must finish before dismissing; dismissal never cancels accepted work.
  function close() {
    if (!busy) {
      dialog.current?.close();
      if (receipt) document.querySelector<HTMLElement>("main h1")?.focus();
      onClose();
    }
  }

  return (
    <dialog
      ref={dialog}
      className="workflow-dialog tenancy-delete-dialog"
      aria-labelledby="delete-tenancy-title"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <h2 id="delete-tenancy-title" tabIndex={-1}>
        Delete tenancy
      </h2>
      {receipt ? (
        <div className="workflow-result" role="status">
          <h3>Termination requested</h3>
          <p>
            Removal is pending. All mappings remain tracked until termination
            initiation is verified. Other tenancy associations are preserved.
          </p>
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
        </div>
      ) : preview.isPending ? (
        <p role="status">Loading deletion preview…</p>
      ) : preview.isError || !data ? (
        <p role="alert">
          This tenancy cannot currently be deleted. It may have pending work or
          its registration has changed. Reload the preview or return to the
          tenancy.
        </p>
      ) : (
        <>
          <p className="notice">
            <strong>Local simulation.</strong> No OCI resources or accounts will
            be changed.
          </p>
          <h3>{data.tenancy.name}</h3>
          <dl className="deletion-target">
            <div>
              <dt>Tenancy OCID</dt>
              <dd>{data.tenancy.tenancy_ocid}</dd>
            </div>
            <div>
              <dt>Parent tenancy</dt>
              <dd>{data.tenancy.parent_tenancy_ocid}</dd>
            </div>
          </dl>
          <p>
            This initiates termination of the entire tenancy and all resources
            in it. Once initiation is verified, all {data.people.length}{" "}
            owner/member associations below will be removed from this tenancy.
          </p>
          {data.shared_warning && (
            <p className="notice">
              <strong>Shared tenancy.</strong> Every listed member is affected,
              not just its owner.
            </p>
          )}
          {data.manager_warning && (
            <p className="notice">
              <strong>Manager impact.</strong> This tenancy is associated with
              one or more managers. Review their scope before continuing.
            </p>
          )}
          <h3>Tracked people affected · {data.people.length}</h3>
          <p className="muted">
            This lists registered owners and members. Untracked users and all
            resources in the tenancy are also affected.
          </p>
          <ul className="deletion-people">
            {data.people.map((person) => (
              <li key={person.person_id}>
                <div>
                  <strong>{person.name}</strong>
                  <span className="cell-secondary">
                    {person.email} · {person.role}
                    {person.is_manager ? " · Manager" : ""}
                  </span>
                </div>
                <p>
                  {person.other_tenancy_count} other tenancy association
                  {person.other_tenancy_count === 1 ? "" : "s"}.{" "}
                  {person.leaves_directory
                    ? "Will leave the managed directory; source and audit history remain."
                    : "Will remain in the managed directory."}
                </p>
              </li>
            ))}
          </ul>
          <label className="workflow-check">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy || preview.isFetching}
              onChange={(event) => {
                setConfirmed(event.target.checked);
                key.current = crypto.randomUUID();
                setError("");
              }}
            />
            <span>
              I have reviewed the affected people and confirm termination of
              this entire tenancy.
            </span>
          </label>
        </>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        {!receipt && (
          <button
            className="button secondary"
            disabled={busy || preview.isFetching}
            onClick={() => void reload()}
          >
            Reload preview
          </button>
        )}
        <button className="button secondary" disabled={busy} onClick={close}>
          {receipt ? "Close" : "Cancel"}
        </button>
        {!receipt && (
          <button
            className="button danger"
            disabled={
              !confirmed ||
              busy ||
              preview.isError ||
              preview.isFetching ||
              !data
            }
            onClick={() => void submit()}
          >
            {busy ? "Submitting…" : "Initiate termination"}
          </button>
        )}
      </div>
    </dialog>
  );
}
