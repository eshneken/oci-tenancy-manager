import { Select } from "./Select";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";

const scenarioNames = {
  healthy: "Healthy",
  access_denied: "Access denied",
  timeout: "Timeout",
  unsupported: "Unsupported",
  unobservable: "Unobservable",
};

// Admit only an explicitly chosen configured simulation target, retaining each target's request identity.
export function SimulationInspection({
  expired,
  navigate,
}: {
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const client = useQueryClient();
  const catalog = useQuery({
    queryKey: ["operations", "sandbox"],
    queryFn: ({ signal }) => api.inspectionSandbox(signal),
    retry: false,
  });
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const requestKeys = useRef(new Map<string, string>());
  const submitting = useRef(false);
  const [target, setTarget] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false);
  useEffect(() => {
    if (
      catalog.error instanceof ApiError &&
      (catalog.error.status === 401 || catalog.error.status === 403)
    )
      expired();
  }, [catalog.error, expired]);
  const selected = catalog.data?.targets.find(
    (item) => item.tenancy_ocid === target,
  );
  // Generate a new identity only for a newly selected target; uncertain retries reuse the exact same key.
  function choose(value: string) {
    setTarget(value);
    if (!requestKeys.current.has(value))
      requestKeys.current.set(value, crypto.randomUUID());
    setMessage("");
    setUncertain(false);
  }
  // Put the safe action first in keyboard focus each time the native confirmation is opened.
  function open() {
    dialog.current?.showModal();
    cancelButton.current?.focus();
  }
  // Native cancellation must not conceal a submission while its acceptance is still pending.
  function close() {
    if (!submitting.current) dialog.current?.close();
  }
  // Accepting the request records work; only the detail view can later report its inspection outcome.
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || !selected || catalog.data?.execution_paused)
      return;
    submitting.current = true;
    setPending(true);
    setMessage("");
    try {
      const accepted = await api.inspect({
        client_request_key: requestKeys.current.get(target)!,
        tenancy_ocid: target,
      });
      void client.invalidateQueries({ queryKey: ["operations", "list"] });
      dialog.current?.close();
      navigate("/operations/" + accepted.operation_id);
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403)
      )
        expired();
      else if (error instanceof ApiError && error.status === 400) {
        setUncertain(false);
        setMessage(
          "This inspection request could not be accepted. Review the configured target before trying again.",
        );
      } else if (error instanceof ApiError && error.status === 409) {
        setUncertain(false);
        setMessage(
          "This request conflicts with recorded work. Check Operations before starting another request.",
        );
      } else {
        setUncertain(true);
        setMessage(
          "Unable to confirm submission. Check Operations before starting another request.",
        );
      }
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }
  // Feature absence is intentionally quiet; availability failures must not block recorded-operation reads.
  if (
    catalog.isPending ||
    (catalog.error instanceof ApiError && catalog.error.status === 404)
  )
    return null;
  if (catalog.isError)
    return (
      <div className="simulation-availability">
        <p className="muted" role="status">
          Simulated inspection availability could not be checked.
        </p>
        <button
          className="button secondary"
          disabled={catalog.isFetching}
          onClick={() => void catalog.refetch()}
        >
          Retry availability
        </button>
      </div>
    );
  return (
    <div className="simulation-control">
      <button
        className="button primary"
        disabled={catalog.data.execution_paused || !catalog.data.targets.length}
        onClick={open}
      >
        Run simulated inspection
      </button>
      {catalog.data.execution_paused && (
        <p className="field-help">Simulated inspection execution is paused.</p>
      )}
      {!catalog.data.targets.length && (
        <p className="field-help">No simulated targets are configured.</p>
      )}
      <dialog
        ref={dialog}
        className="simulation-dialog"
        aria-labelledby="simulation-title"
        aria-describedby="simulation-consequence"
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        <h2 id="simulation-title">Run simulated inspection?</h2>
        <p id="simulation-consequence">
          Inspect a configured synthetic target using the simulated provider.
          This read-only inspection makes no OCI calls, changes no OCI resources
          and does not adopt a tenancy.
        </p>
        <form onSubmit={submit}>
          <label htmlFor="simulation-target">Synthetic target</label>
          <Select
            id="simulation-target"
            required
            disabled={pending}
            value={target}
            onChange={(event) => choose(event.target.value)}
          >
            <option value="" disabled>
              Choose a configured target
            </option>
            {catalog.data.targets.map((item) => (
              <option key={item.tenancy_ocid} value={item.tenancy_ocid}>
                {item.name} · {scenarioNames[item.scenario]}
              </option>
            ))}
          </Select>
          {selected && (
            <div className="simulation-target-summary">
              <p className="technical-id">{selected.tenancy_ocid}</p>
              <p>Scenario: {scenarioNames[selected.scenario]}</p>
            </div>
          )}
          {message && (
            <p className="alert" role="alert">
              {message}
            </p>
          )}
          {uncertain && (
            <p className="field-help">
              Checking submission again uses the same request identity. Closing
              this dialog does not cancel an accepted inspection.
            </p>
          )}
          <div className="dialog-actions">
            <button
              type="button"
              className="button secondary"
              ref={cancelButton}
              autoFocus
              disabled={pending}
              onClick={close}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={pending || !selected || catalog.data.execution_paused}
            >
              {pending
                ? "Submitting…"
                : uncertain
                  ? "Check submission again"
                  : "Run simulated inspection"}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
