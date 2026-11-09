import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import { Select } from "./Select";

// Choose an employee before entering the existing authoritative shared-membership preview.
export function AddSharedMember({ tenancyName, memberIds, expired, onChoose, onClose }: {
  tenancyName: string; memberIds: string[]; expired: () => void;
  onChoose: (personId: string) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [search, setSearch] = useState("");
  const [person, setPerson] = useState("");
  const result = useQuery({
    queryKey: ["organization", "add-shared-member", search],
    queryFn: ({ signal }) => api.organization({page:1,page_size:25,query:search,
      sort:"full_name",direction:"asc"}, signal),
    enabled: search.trim().length >= 2,
    retry: false,
  });
  const unauthorized = result.error instanceof ApiError && [401,403].includes(result.error.status);
  useEffect(() => { if (unauthorized) expired(); }, [unauthorized, expired]);
  useEffect(() => {
    dialog.current?.showModal();
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, []);
  const people = unauthorized ? [] : (result.data?.items ?? []).filter(employee =>
    !memberIds.includes(employee.id) && !employee.absence_review &&
    !employee.pending_operation_id && (employee.directory_status ?? "included") === "included");
  // Release native modal focus/inert state before closing or opening the membership preview.
  function close() { dialog.current?.close(); onClose(); }
  const valid = !unauthorized && !result.isFetching && !result.isError &&
    people.some(employee => employee.id === person);
  return <dialog ref={dialog} className="workflow-dialog" aria-labelledby="add-member-title"
    onCancel={event => {event.preventDefault();close();}}>
    <h2 id="add-member-title">Add member</h2>
    <p className="workflow-person"><strong>{tenancyName}</strong></p>
    <p>Choose an employee, then review their compartment and access before adding them.</p>
    <form onSubmit={event => {event.preventDefault();if(valid) {dialog.current?.close();onChoose(person);}}}>
      <label>Find employee<input value={search} maxLength={128} autoComplete="off"
        placeholder="Search by name or email" onChange={event => {setSearch(event.target.value);setPerson("");}}/></label>
      {search.trim().length < 2 ? <p className="muted">Enter at least two characters to find an employee.</p> : <>
        {result.isFetching && <p role="status">Finding employees…</p>}
        {result.isError && <p className="alert" role="alert">Unable to load employees. <button type="button" className="text-link" onClick={() => void result.refetch()}>Retry</button></p>}
        {!result.isFetching && !result.isError && result.data && <>
          <label>Employee<Select required value={person} onChange={event => setPerson(event.target.value)}>
            <option value="">Choose an employee</option>
            {people.map(employee => <option key={employee.id} value={employee.id}>{employee.full_name} · {employee.email}</option>)}
          </Select></label>
          <p className="muted">{people.length ? "Current members and unavailable profiles are omitted. Refine your search if needed; up to 25 matches are loaded." : "No available employees in these results. Refine your search by name or email."}</p>
        </>}
      </>}
      <div className="dialog-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button>
        <button type="submit" className="button primary" disabled={!valid}>Continue</button></div>
    </form>
  </dialog>;
}
