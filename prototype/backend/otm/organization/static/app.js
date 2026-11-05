/* Shared local organization and tenancy client. Source values enter the DOM through textContent, never HTML. */
/** Look up a stable shell element without querying or interpreting source content. */
const $ = (id) => document.getElementById(id);
const isExceptions = location.pathname === "/exceptions";
const isTenancies = location.pathname === "/tenancies";
const isEmployees = !isExceptions && !isTenancies;
const state = {tab: new URLSearchParams(location.search).get("tab") === "informational" ? "informational" : "actionable", page: 1, size: 25, sort: isTenancies ? "name" : "full_name", direction: "asc", query: "", filter: new URLSearchParams(location.search).get(isExceptions ? "kind" : "lob") || "", total: 0, summary: null, request: 0};
const columns = isTenancies ? [["name", "Tenancy"], ["kind", "Type"], ["owner_name", "Owner"], ["owner_email", "Owner email"], ["lob_name", "Line of business"], ["member_count", "Members"]] : isExceptions ? (state.tab === "actionable" ? [["name", "Employee"], ["email", "Email"], ["title", "Review required"], ["status", "Status"], ["dates", "Dates"], ["actions", "Actions"]] : [["name", "Employee"], ["email", "Email"], ["title", "Information / changes"], ["status", "Status"], ["dates", "Dates"]]) : [["full_name", "Employee name"], ["email", "Email"], ["manager_name", "Manager"], ["top_manager_name", "Top-level manager"], ["lob_name", "Line of business"], ["association_count", "Tenancies"]];

/** Construct text-only DOM to keep uploaded names and emails inert. */
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = text;
  if (className) element.className = className;
  return element;
}
/** Fetch JSON with readable network/validation errors; never hide a failed upload. */
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : Array.isArray(value.detail) ? value.detail.map(item => item.msg).join("; ") : `Request failed (${response.status}).`);
  return value;
}
/** Show safe, persistent processing feedback outside the upload dialog. */
function notice(message, bad = false) {
  $("notice").textContent = message;
  $("notice").className = bad ? "notice bad" : "notice";
  $("notice").hidden = false;
}
/** Populate overview counts from the database, including the initial empty state. */
async function summary() {
  state.summary = await api("/api/local/summary");
  $("open-clean").hidden = !state.summary.can_clean_workspace;
  const s = state.summary;
  $("stat-employees").textContent = s.employees;
  $("stat-lobs").textContent = s.lobs.length;
  $("stat-new").textContent = s.new_employees;
  $("stat-absent").textContent = s.absences;
  $("stat-tenancies-total").textContent = s.tenancies?.total ?? "—";
  $("stat-tenancies-individual").textContent = s.tenancies?.individual ?? "—";
  $("stat-tenancies-shared").textContent = s.tenancies?.shared ?? "—";
  $("stat-tenancies-unassigned").textContent = s.tenancies?.unassigned_owner ?? "—";
  $("nav-count").textContent = s.exceptions;
  $("actionable-count").textContent = s.exceptions;
  $("informational-count").textContent = s.informational || 0;
  $("feed-summary").textContent = s.published_at ? `${s.input_rows} source rows · Last organization update ${new Date(s.published_at).toLocaleString()}` : "No organization feed loaded";
  $("feed-coverage").textContent = s.published_at ? (s.absence_eligible ? "Full snapshot · absence review enabled" : "Partial / incomplete coverage · no new absence inference") : isTenancies ? "Manage organization feeds from Employees" : "Upload your first CSV to begin";
  if (!isExceptions) setFilter(s.lobs.map(value => ({value, label: value})), "All lines of business");
  await refreshRegistry();
}
/** Replace filter options while preserving the selected branch/review category. */
function setFilter(items, allLabel) {
  $("filter").replaceChildren(new Option(allLabel, ""));
  for (const item of items) $("filter").add(new Option(item.label, item.value));
  $("filter").value = state.filter;
}
/** Build keyboard-accessible sort controls and communicate their current direction. */
function headers() {
  const tr = node("tr");
  for (const [key, label] of columns) {
    const th = node("th");
    th.scope = "col";
    if (isExceptions) th.textContent = label;
    else {
      const active = state.sort === key;
      th.setAttribute("aria-sort", active ? (state.direction === "asc" ? "ascending" : "descending") : "none");
      const button = node("button", label);
      button.type = "button";
      button.append(node("span", active ? (state.direction === "asc" ? "↑" : "↓") : "↕"));
      button.addEventListener("click", () => {
        state.direction = active && state.direction === "asc" ? "desc" : "asc";
        state.sort = key; state.page = 1; load();
      });
      th.append(button);
    }
    tr.append(th);
  }
  $("table-head").replaceChildren(tr);
}
/** Render active registry tenancies with independent links to tenancy and owner details. */
function renderTenancyRows(rows) {
  $("table-body").replaceChildren();
  for (const row of rows) {
    const tr = node("tr");
    tr.dataset.tenancyId = row.id;
    for (const [key] of columns) {
      const td = node("td");
      if (key === "name") {
        const button = associationButton(row.name, () => openTenancy(row.id), "entity-link");
        button.setAttribute("aria-label", `Manage tenancy ${row.name}`); td.append(button);
      } else if (key === "kind") td.append(node("span", row.kind === "shared" ? "Shared" : "Individual", "lob-pill"));
      else if (key === "owner_name") {
        if (row.owner_person_id) td.append(associationButton(row.owner_name || row.owner_email || "Owner", () => openPerson(row.owner_person_id), "entity-link"));
        else td.textContent = "Unassigned";
      } else if (key === "owner_email") td.textContent = row.owner_email || "—";
      else if (key === "lob_name") td.append(node("span", row.lob_name || "Unmapped", "lob-pill"));
      else if (key === "member_count") td.textContent = String(row.member_count ?? 0);
      tr.append(td);
    }
    $("table-body").append(tr);
  }
}

/** Render table cells, with an explicit marker for retained absence-review employees. */
function renderRows(rows) {
  $("table-body").replaceChildren();
  for (const row of rows) {
    const tr = node("tr");
    tr.dataset.email = row.email;
    tr.dataset.kind = row.kind || "employee";
    if (row.absence_review || row.retained_absence) tr.className = "retained";
    for (const [key] of columns) {
      const td = node("td");
      if (key === "full_name" || key === "name") {
        const person = node("div", null, "person-name");
        const initials = (row[key] || row.email).split(/\s+/).filter(Boolean).slice(0, 2).map(x => x[0]).join("").toUpperCase();
        const name = row.person_id ? associationButton(row[key] || row.email, () => openPerson(row.person_id), "entity-link") : node("span", row[key] || row.email);
        person.append(node("span", initials, "avatar"), name);
        if (row.absence_review || row.tenancy_setup_review) {
          const mark = node("span", "", "status-dot");
          mark.title = row.absence_review ? "Absence review required" : "New employee: tenancy setup review";
          mark.setAttribute("aria-label", mark.title); person.append(mark);
        }
        td.append(person);
        if (isEmployees && (row.retained_absence || row.management_status?.startsWith("Outside organization"))) {
          const retained = node("div", null, "retained-actions");
          retained.append(node("span", row.management_status?.startsWith("Outside organization") ? "Outside organization · retained" : "Absent · retained", "retained-label"));
          const remove = node("button", "Review associations", "secondary compact");
          remove.type = "button";
          remove.setAttribute("aria-label", `Review tenancy associations for ${row.full_name || row.email}`);
          remove.addEventListener("click", () => openRetainedCleanup(row));
          retained.append(remove); td.append(retained);
        }
      } else if (key === "title") {
        td.append(node("span", row.title, "review-title"));
        if (row.changes) {
          const details = node("details", null, "change-details");
          details.append(node("summary", `${row.changes.length} ${row.changes.length === 1 ? "field" : "fields"} changed`));
          for (const change of row.changes) details.append(node("p", `${fieldLabels[change.field] || change.field}: ${formatValue(change.before)} → ${formatValue(change.after)}`));
          td.append(details);
        } else td.append(node("span", row.detail, "review-detail"));
        if (row.last_action) td.append(node("small", `Last acknowledgment: ${actionLabels[row.last_action]}`, "review-detail"));
      } else if (key === "dates") {
        td.append(node("span", dateLabel(row.first_seen), "review-detail"));
        if (row.resolved_at) td.append(node("span", `Resolved ${dateLabel(row.resolved_at)}`, "review-detail"));
        else if (row.last_seen) td.append(node("span", `Last seen ${dateLabel(row.last_seen)}`, "review-detail"));
      } else if (key === "actions") {
        const button = node("button", "Review", "secondary compact");
        button.type = "button"; button.addEventListener("click", () => openReview(row)); td.append(button);
      } else if (key === "lob_name") td.append(node("span", row[key] || "Unmapped", "lob-pill"));
      else if (key === "association_count") td.textContent = String(row.association_count ?? 0);
      else if (key === "status") td.append(node("span", statusLabel(row), row.status === "simulated_success" ? "badge simulated-success" : "badge"));
      else td.textContent = (key === "email" && !row[key]) ? "—" : row[key] || (key === "manager_name" ? row.manager_email : key === "accountable_leader_name" ? row.accountable_leader_email : null) || "Not established";
      tr.append(td);
    }
    $("table-body").append(tr);
  }
}
/** Page with numbered controls; collapse distant pages without losing first/last navigation. */
function pagination() {
  const count = Math.max(1, Math.ceil(state.total / state.size));
  const start = state.total ? (state.page - 1) * state.size + 1 : 0;
  $("range").textContent = `${start}–${Math.min(state.page * state.size, state.total)} of ${state.total} ${isExceptions ? "reviews" : isTenancies ? "tenancies" : "employees"}`;
  $("pages").replaceChildren();
  const entries = [1, ...Array.from({length: 5}, (_, i) => state.page - 2 + i), count].filter(n => n > 0 && n <= count);
  const numbers = [...new Set(entries)].sort((a, b) => a - b);
  const controls = [["‹", state.page - 1], ...numbers.map(n => [String(n), n]), ["›", state.page + 1]];
  let previous = 0;
  for (const [label, page] of controls) {
    if (label !== "‹" && label !== "›" && previous && page - previous > 1) $("pages").append(node("span", "…"));
    const button = node("button", label, page === state.page && /^\d+$/.test(label) ? "active" : "");
    button.type = "button";
    button.disabled = page < 1 || page > count;
    button.setAttribute("aria-label", label === "‹" ? "Previous page" : label === "›" ? "Next page" : `Page ${page}`);
    if (page === state.page && /^\d+$/.test(label)) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => {state.page = page; load();});
    $("pages").append(button);
    if (/^\d+$/.test(label)) previous = page;
  }
}
/** Load the active screen; ignore stale responses when search or sorting changes quickly. */
async function load() {
  const request = ++state.request;
  const params = new URLSearchParams({page: state.page, page_size: state.size, query: state.query});
  if (isExceptions) {params.set("kind", state.filter); params.set("tab", state.tab);}
  else {params.set("sort", state.sort); params.set("direction", state.direction); params.set("lob", state.filter);}
  try {
    const response = await api(`/api/local/${isExceptions ? "exceptions" : isTenancies ? "tenancies" : "employees"}?${params}`);
    if (request !== state.request) return;
    state.total = response.total;
    if (state.page > 1 && (state.page - 1) * state.size >= state.total) {state.page = 1; return load();}
    if (isExceptions) setFilter(response.kinds, "All review types");
    headers(); if (isTenancies) renderTenancyRows(response.data); else renderRows(response.data); pagination();
    $("table-count").textContent = response.total;
    $("empty").hidden = response.data.length > 0;
    $("empty-upload").hidden = !isEmployees || !!state.summary?.employees;
    $("empty-employees").hidden = !isTenancies || response.data.length > 0;
    if (!response.data.length) {
      const isInitial = !state.summary?.employees;
      $("empty-title").textContent = isTenancies ? (state.query || state.filter ? "No matching tenancies" : "No active tenancies") : isExceptions ? "No review items" : isInitial ? "Start with your organization" : "No matching employees";
      $("empty-description").textContent = isTenancies ? (state.query || state.filter ? "Try another search or line of business." : "Create or import a tenancy from an employee’s associations. Uploading an organization CSV updates employee profiles; it does not create tenancies.") : isExceptions ? (state.tab === "actionable" ? "No administrator decisions are pending. Resolved and ignored items stay in informational history." : "Warnings, feed failures and dated employee changes will appear here. The first census is recorded as one baseline event.") : isInitial ? "Upload a CSV to build the directory and identify review items." : "Try another search or line of business.";
    }
  } catch (error) {if (request === state.request) notice(error.message, true);}
}
/** Clear previous validation errors before opening the accessible native modal. */
function openUpload() {$("notice").hidden = true; $("upload-error").hidden = true; $("upload-dialog").showModal();}
/** Submit a fresh CSV observation, report validation failures, and refresh both read models. */
async function upload(event) {
  event.preventDefault();
  const file = $("csv-file").files[0];
  if (!file) return;
  $("open-clean").disabled = true;
  $("submit-upload").disabled = true; $("submit-upload").textContent = "Processing…";
  $("cancel-upload").disabled = true; $("close-upload").disabled = true;
  $("upload-error").hidden = true;
  try {
    if (file.size > 2 * 1024 * 1024) throw new Error("CSV exceeds the 2 MiB upload limit.");
    const value = await api(`/api/local/feeds?complete=${$("complete").checked}`, {method: "POST", headers: {"Content-Type": "text/csv", "X-OTM-Local": "csv-upload", "X-OTM-Workspace": state.summary.workspace_id}, body: file});
    const result = value.outcome;
    const successful = result.state === "published";
    if (!successful) throw new Error(`Feed ${result.state}. ${result.diagnostics.map(d => `${d.code}${d.affected_email ? ": " + d.affected_email : ""}`).join("; ")} Current organization was preserved.`);
    $("upload-dialog").close();
    state.page = 1; state.query = ""; state.filter = ""; $("search").value = "";
    await summary(); await load();
    notice(`${file.name}: ${value.input_rows} rows processed as a new snapshot. Organization updated; ${state.summary.exceptions} review ${state.summary.exceptions === 1 ? "item" : "items"} available on the Exceptions page.`);
  } catch (error) {$("upload-error").textContent = error.message; $("upload-error").hidden = false;}
  finally {$("open-clean").disabled = false; $("submit-upload").disabled = false; $("submit-upload").textContent = "Process CSV"; $("cancel-upload").disabled = false; $("close-upload").disabled = false;}
}
let cleanExpected = null;
/** Capture the exact visible run before asking to archive its test data. */
function openClean() {
  const s = state.summary;
  cleanExpected = {
    workspace_id: s.workspace_id,
    applied_version_id: s.context.applied_version_id,
    proposed_version_id: s.context.proposed_version_id,
    configuration_id: s.context.configuration_id,
  };
  const tenancyCount = registryData?.tenancies.length || 0;
  $("clean-counts").textContent = `This run will be archived: ${s.employees} employee ${s.employees === 1 ? "profile" : "profiles"}, ${tenancyCount} active ${tenancyCount === 1 ? "tenancy" : "tenancies"} and ${s.exceptions} review ${s.exceptions === 1 ? "item" : "items"}. They will no longer appear in the new workspace.`;
  $("clean-dialog").showModal();
  $("cancel-clean").focus();
}
/** Start a version-checked empty run; retained history and settings stay on the server. */
async function cleanWorkspace(event) {
  event.preventDefault();
  for (const id of ["confirm-clean", "cancel-clean", "close-clean", "open-upload", "open-clean"]) $(id).disabled = true;
  $("confirm-clean").textContent = "Cleaning…";
  // Invalidate older table requests before replacing the directory with the fresh run.
  state.request++;
  try {
    await api("/api/local/workspace/clean", {method: "POST", headers: {"Content-Type": "application/json", "X-OTM-Local": "csv-upload"}, body: JSON.stringify(cleanExpected)});
    $("clean-dialog").close();
    state.page = 1; state.query = ""; state.filter = "";
    $("search").value = ""; $("upload-form").reset();
    await summary(); await load();
    notice("Workspace cleaned. Upload an initial CSV to start again. Your LOB configuration was kept and previous test history was archived.");
  } catch (error) {
    $("clean-dialog").close();
    await summary(); await load();
    notice(error.message, true);
  } finally {
    for (const id of ["confirm-clean", "cancel-clean", "close-clean", "open-upload", "open-clean"]) $(id).disabled = false;
    $("confirm-clean").textContent = "Clean workspace";
  }
}
const fieldLabels = {full_name:"Name",email:"Email",manager_email:"Manager",lob_id:"LOB",accountable_leader_email:"Accountable leader",designee_emails:"Designees"};
const actionLabels = {create_tenancy:"Create tenancy", import_tenancy:"Import tenancy", shared_membership:"Add to shared tenancy", delete_tenancy:"Delete tenancy", keep_tenancy:"Keep tenancy", resolve:"Resolve review", ignore:"Always exempt from LOB mapping", offboard_person:"Offboard employee", no_tenancy_required:"No tenancy required", remove_user:"Remove from organization", keep_returned:"Resolve / keep returned employee", merge:"Merge name / email change"};
let activeReview = null;
let reviewOperation = null;
let reviewContext = null;
let reviewBusy = false;
/** Format values without treating employee/source strings as markup. */
function formatValue(value) {return value === null || value === undefined ? "—" : Array.isArray(value) ? value.join(", ") : String(value);}
/** Keep dates visible in the administrator's browser locale. */
function dateLabel(value) {return value ? new Date(value).toLocaleString() : "—";}
/** Separate open work from active source warnings and dated closure history. */
function statusLabel(row) {
  const labels = {simulated_success:"Simulated success", acknowledged:"Acknowledged", applied:"Applied", ignored:"Ignored", merged:"Merged", blocked:"Rejected"};
  if (row.status === "resolved") return row.kind === "REVIEW_DECISION" ? "Resolved" : "Auto-resolved";
  return labels[row.status] || (state.tab === "informational" ? "Active warning" : "Needs review");
}
/** Name condition-specific LOB dismissal explicitly without changing its stored operation. */
function reviewActionLabel(operation, kind) {
  return operation === "resolve" && kind === "LOB_MAPPING_REVIEW" ? "Dismiss current condition" : actionLabels[operation];
}
/** Offer later directory cleanup without reopening an already completed absence review. */
function openRetainedCleanup(row) {openOffboarding(row.person_id);}
/** Capture the visible revision before presenting a case's allowed operations. */
async function openReview(row) {
  $("notice").hidden = true;
  activeReview = row;
  const context = state.summary.context;
  reviewContext = Object.fromEntries(["workspace_id", "applied_version_id", "proposed_version_id", "configuration_id"].map(key => [key, context[key]]));
  $("review-dialog-title").textContent = row.title;
  $("review-person").textContent = `${row.name} · ${row.email}`;
  $("review-explanation").textContent = row.detail;
  $("review-error").hidden = true;
  $("review-actions").replaceChildren();
  $("review-actions").hidden = row.actions.length === 1;
  for (const operation of row.actions) {
    const button = node("button", reviewActionLabel(operation, row.kind), "secondary");
    button.type = "button"; button.dataset.operation = operation;
    button.addEventListener("click", () => chooseOperation(operation));
    $("review-actions").append(button);
  }
  $("review-dialog").showModal();
  chooseOperation(row.actions.includes("resolve") ? "resolve" : row.actions[0]);
}
/** Make simulated OCI actions visually distinct from real local model mutations. */
async function chooseOperation(operation) {
  reviewOperation = operation;
  $("review-error").hidden = true;
  for (const button of $("review-actions").children) {
    const selected = button.dataset.operation === operation;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  const guided = operation === "offboard_person" || (activeReview.kind === "TENANCY_SETUP_REVIEW" && ["create_tenancy", "import_tenancy", "shared_membership"].includes(operation));
  if (guided) {
    $("merge-choice").hidden = true; $("merge-preview").hidden = true;
    $("operation-description").textContent = operation === "offboard_person" ? "Review every tenancy owned by this employee and every shared membership. Choose deletion, membership removal, ownership transfer or retention before confirming offboarding. No OCI resources or access are changed." : "Continue to choose the tenancy name, type or shared target. The review closes only after the association is recorded successfully. No OCI resources or access are changed.";
    $("confirm-review").textContent = operation === "offboard_person" ? "Review tenancy associations" : "Continue to tenancy setup";
    $("confirm-review").disabled = false; return;
  }
  const simulated = ["create_tenancy","import_tenancy","shared_membership","delete_tenancy","keep_tenancy"].includes(operation);
  const simulationLabels = {create_tenancy:"Simulate tenancy creation", import_tenancy:"Simulate tenancy import", shared_membership:"Simulate adding to shared tenancy", delete_tenancy:"Simulate tenancy deletion", keep_tenancy:"Simulate keeping tenancy"};
  const retainedAfterSimulation = activeReview.kind === "PERSON_ABSENCE_REVIEW" ? " The employee remains in the directory. You can remove them later from the employee directory." : "";
  $("operation-description").textContent = simulated ? "Simulate a successful outcome and close this review. No OCI resources, users or memberships will be changed. The simulated result is recorded in informational history." + retainedAfterSimulation : operation === "no_tenancy_required" ? "Record that this employee does not need a tenancy and close the new employee review. If no active tenancy associations remain, the employee leaves the managed directory; source and reporting records are retained. No OCI resources or memberships are changed." : operation === "remove_user" ? "Remove this employee from the current organization. Future feeds will not re-add this excluded identity. Historical records are retained; OCI resources and users are unchanged." : operation === "merge" ? "Retain the absent employee’s stable identity and tenancy ownership and memberships. Adopt the new employee’s name, email and current reporting metadata. Both reviews close. This merge is one way." : operation === "ignore" ? "Exempt this employee from LOB mapping reviews, including after future organizational changes. Other review types remain enabled. The employee stays in the directory; no LOB is assigned." : activeReview.kind === "LOB_MAPPING_REVIEW" ? "Dismiss this LOB mapping condition. Identical future feeds keep it closed, but changes to the employee’s manager or organizational mapping may trigger another review. The employee stays in the directory; no LOB is assigned." : "Close this review with an audited administrator decision. Repeated feeds will not reopen the same resolved condition.";
  $("confirm-review").textContent = simulated ? simulationLabels[operation] : reviewActionLabel(operation, activeReview.kind);
  $("merge-choice").hidden = operation !== "merge"; $("merge-preview").hidden = operation !== "merge";
  $("confirm-review").disabled = false;
  if (operation === "merge") {
    $("confirm-review").disabled = true; $("merge-partner").replaceChildren(new Option("Choose a record…", ""));
    try {
      const candidates = await api(`/api/local/reviews/merge-candidates?case_id=${encodeURIComponent(activeReview.id)}`);
      if (reviewOperation !== "merge") return;
      for (const person of candidates) $("merge-partner").add(new Option(`${person.name} · ${person.email}`, person.email));
      $("merge-preview").textContent = candidates.length ? "Select the matching record. No automatic name matching is performed." : "No eligible absent/new employee pair is available.";
    } catch (error) {$("review-error").textContent = error.message; $("review-error").hidden = false;}
  }
}
/** Show the one-way survivor/destination mapping before an identity merge is confirmed. */
function mergePreview() {
  const partner = $("merge-partner").value;
  $("confirm-review").disabled = !partner;
  const oldEmail = activeReview.kind === "PERSON_ABSENCE_REVIEW" ? activeReview.email : partner;
  const newEmail = activeReview.kind === "PERSON_ABSENCE_REVIEW" ? partner : activeReview.email;
  $("merge-preview").textContent = partner ? `Keep stable identity for tenancy associations: ${oldEmail}. Adopt new metadata: ${newEmail}.` : "Choose the matching record.";
}
/** Apply the expected-context command and refresh queue/counts without clearing prior audit history. */
async function submitReview(event) {
  event.preventDefault();
  if (reviewBusy) return;
  if (reviewOperation === "offboard_person" || (activeReview.kind === "TENANCY_SETUP_REVIEW" && ["create_tenancy", "import_tenancy", "shared_membership"].includes(reviewOperation))) return continueRegistryReview();
  reviewBusy = true;
  // Keep the visible operation and dialog stable until the server outcome is known.
  const controls = [...$("review-form").querySelectorAll("button,input,select,textarea")];
  const disabledBefore = controls.map(control => control.disabled);
  const confirmLabel = $("confirm-review").textContent;
  // Refreshing after the modal closes must still report the decision just submitted.
  const submittedKind = activeReview.kind;
  const submittedOperation = reviewOperation;
  for (const control of controls) control.disabled = true;
  $("review-form").setAttribute("aria-busy", "true");
  $("confirm-review").textContent = "Saving…";
  try {
    const result = await api("/api/local/reviews/operate", {method:"POST", headers:{"Content-Type":"application/json","X-OTM-Local":"csv-upload"}, body:JSON.stringify({context:reviewContext,case_id:activeReview.id,operation:reviewOperation,partner_email:reviewOperation === "merge" ? $("merge-partner").value : null})});
    $("review-dialog").close(); state.page = 1;
    await summary(); await load();
    const retainedMessage = submittedKind === "PERSON_ABSENCE_REVIEW" ? " The employee remains in the directory for separate cleanup." : "";
    notice(result.simulated ? "Simulated success. The review is closed and the result is recorded in informational history. No OCI resources, users or memberships were changed." + retainedMessage : result.acknowledged ? "Historical prototype action acknowledged. No OCI operation occurred; the review remains open." : submittedOperation === "no_tenancy_required" ? "No tenancy required. The review is closed and the employee is outside the managed directory; source and reporting records are retained. The decision is recorded in informational history." : "Decision applied. Current organization and review queue updated; the decision is retained in informational history.");
  } catch (error) {$("review-error").textContent = error.message; $("review-error").hidden = false;}
  finally {
    controls.forEach((control, index) => {control.disabled = disabledBefore[index];});
    $("confirm-review").textContent = confirmLabel;
    $("review-form").removeAttribute("aria-busy");
    reviewBusy = false;
  }
}
let registryData = null;
let registryCommand = null;
let tenancyEdit = null;
let tenancyOriginal = null;
let offboardPerson = null;
const busyRegistryDialogs = new Set();
const registryContextKeys = ["workspace_id", "applied_version_id", "proposed_version_id", "configuration_id"];
/** Refresh association inventory without creating or reconciling any tenancy records. */
async function refreshRegistry() {
  registryData = await api("/api/local/tenancy-registry");
  const warnings = registryData.warnings || [];
  $("registry-warnings").textContent = warnings.join(" ");
  $("registry-warnings").hidden = !warnings.length;
  const former = (registryData.unmanaged_people || []).filter(person => person.source_present);
  $("offboarded-panel").hidden = !isEmployees || !former.length;
  $("offboarded-count").textContent = former.length;
  $("offboarded-people").replaceChildren();
  for (const person of former) {
    const item = node("div", null, "offboarded-person");
    const identity = node("div");
    identity.append(node("strong", person.name || person.email), node("span", person.email, "review-detail"));
    const action = node("button", "Re-onboard", "secondary compact");
    action.type = "button";
    action.setAttribute("aria-label", `Re-onboard ${person.name || person.email}`);
    action.addEventListener("click", () => openRegistryOperation("reonboard", person.id));
    item.append(identity, action); $("offboarded-people").append(item);
  }
}
/** Freeze only the fields accepted by guarded association commands. */
function registryContext() {return Object.fromEntries(registryContextKeys.map(key => [key, registryData.context[key]]));}
/** Resolve stable identities across managed and previously offboarded registry projections. */
function registryPerson(personId) {return [...registryData.people, ...(registryData.unmanaged_people || [])].find(person => person.id === personId);}
/** Build a text-only, consistently sized action without interpreting uploaded names as markup. */
function associationButton(label, handler, className = "secondary compact") {
  const button = node("button", label, className);
  button.type = "button"; button.addEventListener("click", handler); return button;
}
/** Explain source presence separately from managed-directory and association state. */
function personStateLabel(person) {
  const source = person.source_present ? "Present in the latest organization feed" : "Missing from the latest organization feed";
  const managed = person.status || (person.managed ? "Managed directory profile" : "Outside the managed directory");
  return `${managed} · ${source} · ${person.association_count || 0} active tenancy ${person.association_count === 1 ? "association" : "associations"}`;
}
/** Open one person's inventory while retaining stable identity across name and email changes. */
async function openPerson(personId) {
  try {
    await refreshRegistry();
    const person = registryPerson(personId);
    if (!person) throw new Error("This employee is no longer available. Refresh the directory.");
    $("person-title").textContent = person.name || person.email;
    $("person-identity").textContent = person.email;
    $("person-status").textContent = personStateLabel(person);
    $("person-error").hidden = true;
    $("person-associations").replaceChildren(); $("person-commands").replaceChildren();
    if (!person.associations.length) $("person-associations").append(node("p", "No active tenancy associations are recorded."));
    for (const association of person.associations) {
      const item = node("div", null, "association-card");
      const title = associationButton(association.tenancy_name, () => openTenancy(association.tenancy_id), "entity-link");
      item.append(title, node("p", `${association.kind === "shared" ? "Shared" : "Individual"} tenancy · ${association.role === "owner" ? "Owner" : "Member"}`, "association-meta"));
      $("person-associations").append(item);
    }
    if (person.managed) {
      const outside = person.status?.startsWith("Outside");
      if (!outside) {
        for (const [operation, label] of [["create_tenancy", "Create tenancy"], ["import_tenancy", "Import tenancy"], ["join_shared", "Add to shared tenancy"]]) $("person-commands").append(associationButton(label, () => openRegistryOperation(operation, person.id)));
        if (!person.association_count) $("person-commands").append(associationButton("No tenancy required", () => openRegistryOperation("no_tenancy_required", person.id)));
      }
      if (outside && person.source_present) $("person-commands").append(associationButton("Mark returned to organization", () => openRegistryOperation("return_to_org", person.id)));
      $("person-commands").append(associationButton("Offboard employee", () => openOffboarding(person.id)));
    } else if (person.source_present) $("person-commands").append(associationButton("Re-onboard", () => openRegistryOperation("reonboard", person.id)));
    $("person-dialog").showModal();
  } catch (error) {notice(error.message, true);}
}
/** Populate transfer choices from server eligibility, never by display-name matching. */
function fillRegistryRecipients(select, subjectId) {
  select.replaceChildren(new Option("Choose a new owner…", ""));
  for (const person of registryData.people.filter(person => person.id !== subjectId && (person.eligible_transfer ?? (person.source_present && person.managed)))) select.add(new Option(`${person.name || person.email} · ${person.email}`, person.id));
  if (select.options.length === 1) select.options[0].textContent = "No eligible owner is available";
}
/** Configure one explicit association command with a captured workspace revision. */
async function openRegistryOperation(operation, personId, tenancyId = null) {
  $("notice").hidden = true;
  try {
    await refreshRegistry();
    const person = registryPerson(personId);
    if (!person && operation !== "assign_owner") throw new Error("This employee is no longer available. Refresh the directory.");
    registryCommand = {context: registryContext(), operation, person_id: person?.id};
    if (tenancyId) registryCommand.tenancy_id = tenancyId;
    $("registry-form").reset(); $("registry-error").hidden = true;
    const labels = {return_to_org:"Mark returned to organization", no_tenancy_required:"No tenancy required", create_tenancy:"Create tenancy", import_tenancy:"Import tenancy", join_shared:"Add to shared tenancy", assign_owner:"Assign tenancy owner", transfer_owner:"Transfer tenancy ownership", remove_member:"Remove tenancy membership", delete_tenancy:"Delete tenancy", reonboard:"Re-onboard employee"};
    $("registry-title").textContent = labels[operation];
    $("registry-person").textContent = person ? `${person.name || person.email} · ${person.email}` : registryData.tenancies.find(tenancy => tenancy.id === tenancyId)?.name || "Shared tenancy";
    const create = operation === "create_tenancy" || operation === "import_tenancy";
    $("registry-name-field").hidden = !create; $("registry-kind-field").hidden = !create;
    $("registry-name").required = create;
    $("registry-target-field").hidden = operation !== "join_shared";
    $("registry-target").required = operation === "join_shared";
    $("registry-owner-field").hidden = !["transfer_owner", "assign_owner"].includes(operation);
    $("registry-owner").required = ["transfer_owner", "assign_owner"].includes(operation);
    $("registry-target").replaceChildren(new Option("Choose a shared tenancy…", ""));
    const joined = new Set((person?.associations || []).map(association => association.tenancy_id));
    for (const tenancy of registryData.tenancies.filter(tenancy => tenancy.status === "active" && tenancy.kind === "shared" && tenancy.owner_person_id && !joined.has(tenancy.id))) $("registry-target").add(new Option(`${tenancy.name} · ${tenancy.owner_name || tenancy.owner_email}`, tenancy.id));
    fillRegistryRecipients($("registry-owner"), person?.id);
    const descriptions = {return_to_org:"Mark this employee as returned to the organization. Existing tenancy associations are retained; no new tenancy is created.", no_tenancy_required:"Exclude this employee from the managed directory after verifying no active tenancy associations remain. Source and reporting records are retained; future feeds do not re-onboard the employee automatically.", create_tenancy:"Record a new owned tenancy and close any new employee review. Additional tenancies remain allowed.", import_tenancy:"Record an imported tenancy and close any new employee review. This prototype does not validate an OCI tenancy or change its parent.", join_shared:"Add this employee as a member of an existing shared tenancy and close any new employee review.", assign_owner:"Assign an accountable owner to this shared tenancy. Existing members remain; a selected member becomes the owner.", transfer_owner:"Assign a new accountable owner. The former owner's association is removed; other members remain.", remove_member:"Remove this employee's membership. The tenancy and its other associations remain.", delete_tenancy:"Delete this individual tenancy in the prototype and remove its association. Deletion is blocked while other members remain.", reonboard:"Return this employee to the managed directory and open a new tenancy setup review. No tenancy is created automatically."};
    $("registry-description").textContent = descriptions[operation] + " No OCI resources, users or access will be changed.";
    if (operation === "delete_tenancy" && person.is_manager) $("registry-description").textContent += " This tenancy belongs to a manager. Verify shared work and the selected tenancy before confirming.";
    $("confirm-registry").textContent = ["reonboard", "return_to_org", "no_tenancy_required"].includes(operation) ? labels[operation] : `Simulate ${labels[operation].toLowerCase()}`;
    $("confirm-registry").className = ["delete_tenancy", "remove_member"].includes(operation) ? "danger" : "primary";
    const noTarget = operation === "join_shared" && $("registry-target").options.length === 1;
    const noOwner = ["transfer_owner", "assign_owner"].includes(operation) && $("registry-owner").options.length === 1;
    $("confirm-registry").disabled = noTarget || noOwner;
    if (noTarget) $("registry-description").textContent += " No eligible shared tenancy is available. Create or import a shared tenancy first.";
    if (noOwner) $("registry-description").textContent += " No eligible owner is available. A current, managed employee must be available before ownership can change.";
    $("registry-dialog").showModal();
  } catch (error) {notice(error.message, true);}
}
/** Keep unsaved tenancy metadata from disappearing behind a separate membership command. */
function tenancyDetailsAreSaved() {
  if ($("tenancy-name").value === tenancyOriginal.name && $("tenancy-kind").value === tenancyOriginal.kind) return true;
  $("tenancy-error").textContent = "Save tenancy details before changing ownership, memberships or deletion status.";
  $("tenancy-error").hidden = false;
  return false;
}
/** Present registry tenancy metadata and server-authorized owner/member actions together. */
async function openTenancy(tenancyId) {
  try {
    await refreshRegistry();
    const tenancy = registryData.tenancies.find(item => item.id === tenancyId);
    if (!tenancy) throw new Error("This tenancy is no longer available. Refresh the directory.");
    tenancyEdit = {context: registryContext(), operation:"update_tenancy", person_id:tenancy.owner_person_id, tenancy_id:tenancy.id};
    tenancyOriginal = {name:tenancy.name, kind:tenancy.kind};
    $("tenancy-title").textContent = tenancy.name;
    $("tenancy-owner").textContent = tenancy.owner_person_id ? `Accountable owner: ${tenancy.owner_name || tenancy.owner_email}` : "Accountable owner: Unassigned. Assign an owner before editing tenancy details.";
    $("tenancy-name").value = tenancy.name; $("tenancy-kind").value = tenancy.kind;
    $("tenancy-error").hidden = true;
    for (const control of [$("tenancy-name"), $("tenancy-kind"), $("tenancy-form").querySelector("button[type=submit]")]) control.disabled = !tenancy.owner_person_id;
    $("tenancy-members").replaceChildren(); $("tenancy-commands").replaceChildren();
    if (!tenancy.owner_person_id && tenancy.kind === "shared") $("tenancy-commands").append(associationButton("Assign owner", () => openRegistryOperation("assign_owner", null, tenancyId)));
    const people = [...registryData.people, ...(registryData.unmanaged_people || [])];
    const seen = new Set();
    for (const person of people) for (const association of person.associations.filter(item => item.tenancy_id === tenancyId)) {
      if (seen.has(association.id)) continue; seen.add(association.id);
      const item = node("div", null, "association-card");
      item.append(node("strong", person.name || person.email), node("p", `${person.email} · ${association.role === "owner" ? "Owner" : "Member"}`, "association-meta"));
      if (association.role === "owner" && association.allowed_actions.includes("transfer")) item.append(associationButton("Transfer ownership", () => tenancyDetailsAreSaved() && openRegistryOperation("transfer_owner", person.id, tenancyId)));
      if (association.role === "member" && association.allowed_actions.includes("remove")) item.append(associationButton("Remove membership", () => tenancyDetailsAreSaved() && openRegistryOperation("remove_member", person.id, tenancyId)));
      if (association.role === "owner") {
        const remove = associationButton("Delete tenancy", () => tenancyDetailsAreSaved() && openRegistryOperation("delete_tenancy", person.id, tenancyId));
        remove.disabled = !association.allowed_actions.includes("delete");
        $("tenancy-commands").append(remove);
        const reason = association.block_reasons?.delete;
        if (reason) $("tenancy-commands").append(node("p", reason, "association-block"));
      }
      $("tenancy-members").append(item);
    }
    $("tenancy-dialog").showModal();
  } catch (error) {notice(error.message, true);}
}
/** Build a complete per-association plan instead of silently discarding residual ownership or access. */
async function openOffboarding(personId) {
  $("notice").hidden = true;
  try {
    await refreshRegistry();
    const person = registryPerson(personId);
    if (!person) throw new Error("This employee is no longer available. Refresh the directory.");
    offboardPerson = {person, context:registryContext()};
    $("offboard-form").reset(); $("offboard-error").hidden = true;
    $("offboard-person").textContent = `${person.name || person.email} · ${person.email}`;
    $("offboard-manager-warning").hidden = !person.is_manager;
    $("offboard-associations").replaceChildren();
    const labels = {delete:"Delete tenancy", remove:"Remove membership", transfer:"Transfer ownership", keep:"Keep association"};
    for (const association of person.associations) {
      const item = node("div", null, "association-card offboard-item");
      item.dataset.associationId = association.id;
      item.append(node("strong", association.tenancy_name), node("p", `${association.kind === "shared" ? "Shared" : "Individual"} tenancy · ${association.role === "owner" ? "Owner" : "Member"}`, "association-meta"));
      const actionLabel = node("label", "Action", "field");
      const action = node("select"); action.className = "offboard-action";
      action.setAttribute("aria-label", `Action for ${association.tenancy_name}`);
      action.add(new Option("Choose an action…", ""));
      for (const value of association.allowed_actions) action.add(new Option(labels[value], value));
      action.required = true; actionLabel.append(action); item.append(actionLabel);
      const recipientLabel = node("label", "New owner", "field offboard-recipient-field");
      recipientLabel.hidden = true;
      const recipient = node("select"); recipient.className = "offboard-recipient";
      recipient.setAttribute("aria-label", `New owner for ${association.tenancy_name}`);
      fillRegistryRecipients(recipient, person.id); recipientLabel.append(recipient); item.append(recipientLabel);
      for (const [actionName, reason] of Object.entries(association.block_reasons || {})) item.append(node("p", `${labels[actionName] || actionName} is unavailable: ${reason}`, "association-block"));
      action.addEventListener("change", () => {recipientLabel.hidden = action.value !== "transfer"; recipient.required = action.value === "transfer"; updateOffboardSummary();});
      recipient.addEventListener("change", updateOffboardSummary);
      $("offboard-associations").append(item);
    }
    $("offboard-empty-field").hidden = !!person.associations.length;
    $("offboard-empty").required = !person.associations.length;
    updateOffboardSummary(); $("offboard-dialog").showModal();
  } catch (error) {notice(error.message, true);}
}
/** Explain retention and prevent an incomplete inventory plan from reaching confirmation. */
function updateOffboardSummary() {
  const rows = [...$("offboard-associations").children];
  const keep = rows.filter(row => row.querySelector(".offboard-action").value === "keep").length;
  const ready = rows.length ? rows.every(row => row.querySelector(".offboard-action").value && (row.querySelector(".offboard-action").value !== "transfer" || row.querySelector(".offboard-recipient").value)) : $("offboard-empty").checked;
  $("confirm-offboard").disabled = !ready;
  $("offboard-plan-summary").textContent = !ready && rows.length ? "Choose an action for every association and a new owner for each ownership transfer before continuing." : keep ? `${keep} ${keep === 1 ? "association will" : "associations will"} remain. This employee stays visible as outside the organization until all associations are removed.` : "When no active associations remain, the employee leaves the managed directory. Source and reporting records are retained. A later absence-to-present return in a full organization feed opens a new tenancy setup review.";
}
/** Apply one guarded command and refresh directory, exception counts and offboarded profiles together. */
async function submitRegistryMutation(event, dialogId, errorId, command) {
  event.preventDefault();
  if (busyRegistryDialogs.has(dialogId)) return;
  busyRegistryDialogs.add(dialogId);
  const form = $(dialogId).querySelector("form");
  const controls = [...form.querySelectorAll("button,input,select,textarea")];
  const disabledBefore = controls.map(control => control.disabled);
  for (const control of controls) control.disabled = true;
  const submitButton = form.querySelector("button[type=submit]");
  const submitLabel = submitButton.textContent;
  submitButton.textContent = "Saving…";
  form.setAttribute("aria-busy", "true"); $(errorId).hidden = true;
  try {
    const result = await api("/api/local/tenancy-registry/operate", {method:"POST", headers:{"Content-Type":"application/json", "X-OTM-Local":"csv-upload"}, body:JSON.stringify(command)});
    // Close every related dialog before replacing controls backed by the previous registry revision.
    for (const id of ["registry-dialog", "offboard-dialog", "tenancy-dialog", "person-dialog", "review-dialog"]) if ($(id).open) $(id).close();
    state.page = 1; await summary(); await load();
    const retained = Array.isArray(result.remaining_associations) ? result.remaining_associations.length : result.remaining_associations;
    const message = command.operation === "return_to_org" ? "Employee marked as returned to the organization. Existing tenancy associations were retained." : command.operation === "no_tenancy_required" ? "No tenancy required. The employee is outside the managed directory; source and reporting records are retained." : command.operation === "reonboard" ? "Employee re-onboarded. A new tenancy setup review is available; no tenancy was created automatically." : result.person_removed ? "Offboarding complete. The employee is outside the managed directory; source and reporting history are retained." : command.operation === "offboard_person" ? `Offboarding recorded. ${retained} active tenancy ${retained === 1 ? "association remains" : "associations remain"}; the employee stays visible as outside the organization.` : "Tenancy associations updated in the prototype.";
    notice(message + " No OCI resources, users or access were changed.");
  } catch (error) {$(errorId).textContent = error.message; $(errorId).hidden = false;}
  finally {controls.forEach((control, i) => {control.disabled = disabledBefore[i];}); submitButton.textContent = submitLabel; form.removeAttribute("aria-busy"); busyRegistryDialogs.delete(dialogId);}
}
/** Read only the visible operation's fields so hidden form state cannot change the command. */
function submitRegistryOperation(event) {
  const command = {...registryCommand};
  if (["create_tenancy", "import_tenancy"].includes(command.operation)) {command.name = $("registry-name").value; command.kind = $("registry-kind").value;}
  if (command.operation === "join_shared") command.tenancy_id = $("registry-target").value;
  if (["transfer_owner", "assign_owner"].includes(command.operation)) command.owner_person_id = $("registry-owner").value;
  if (command.operation === "assign_owner") command.person_id = command.owner_person_id;
  return submitRegistryMutation(event, "registry-dialog", "registry-error", command);
}
/** Save editable tenancy metadata independently of owner and membership commands. */
function submitTenancyEdit(event) {return submitRegistryMutation(event, "tenancy-dialog", "tenancy-error", {...tenancyEdit, name:$("tenancy-name").value, kind:$("tenancy-kind").value});}
/** Submit exactly one explicit outcome for every active association shown in the checklist. */
function submitOffboarding(event) {
  const plan = [...$("offboard-associations").children].map(row => {
    const entry = {association_id:row.dataset.associationId, action:row.querySelector(".offboard-action").value};
    if (entry.action === "transfer") entry.recipient_person_id = row.querySelector(".offboard-recipient").value;
    return entry;
  });
  return submitRegistryMutation(event, "offboard-dialog", "offboard-error", {context:offboardPerson.context, operation:"offboard_person", person_id:offboardPerson.person.id, plan, confirm_no_associations:$("offboard-empty").checked});
}
/** Route organization-review choices into the association forms without prematurely closing the review. */
async function continueRegistryReview() {
  if (reviewBusy) return;
  reviewBusy = true; $("confirm-review").disabled = true;
  try {
    await refreshRegistry();
    const person = registryData.people.find(person => person.id === activeReview.person_id || person.email === activeReview.email);
    if (!person) throw new Error("This employee is no longer available. Refresh before taking action.");
    const operation = reviewOperation;
    $("review-dialog").close();
    if (operation === "offboard_person") await openOffboarding(person.id);
    else await openRegistryOperation(operation === "shared_membership" ? "join_shared" : operation, person.id);
  } catch (error) {$("review-error").textContent = error.message; $("review-error").hidden = false;}
  finally {reviewBusy = false; $("confirm-review").disabled = false;}
}

/** Initialize the URL-selected screen and wire all controls once. */
async function init() {
  $("organization-stats").hidden = isTenancies;
  $("tenancy-stats").hidden = !isTenancies;
  if (isEmployees) document.querySelector("table").className = "employee-table";
  const navigationId = isExceptions ? "nav-exceptions" : isTenancies ? "nav-tenancies" : "nav-employees";
  $(navigationId).classList.add("active");
  $(navigationId).setAttribute("aria-current", "page");
  if (isTenancies) {
    document.querySelector("table").className = "tenancy-table";
    document.title = "OCI Tenancy Manager · Tenancies";
    $("breadcrumb").textContent = "Tenancies"; $("page-title").textContent = "Tenancy directory";
    $("page-description").textContent = "Active tenancies, accountable owners and organizational alignment.";
    $("table-title").firstChild.textContent = "All active tenancies ";
    $("table-description").textContent = "Open a tenancy to manage its details, or an owner to review their associations.";
    $("exceptions-link").textContent = "View employees →"; $("exceptions-link").href = "/";
    $("search").placeholder = "Search tenancies, owners or LOB…"; $("search").setAttribute("aria-label", "Search tenancies");
    $("open-upload").hidden = true;
    $("footnote").textContent = "Member counts include the owner. This prototype records tenancy ownership and memberships; no OCI resources, users or access are changed.";
  }
  if (isExceptions) {
    document.querySelector("table").className = "review-table";
    document.title = "OCI Tenancy Manager · Exceptions";
    $("breadcrumb").textContent = "Exceptions"; $("page-title").textContent = "Organization exceptions";
    $("page-description").textContent = "A focused review list. Metadata syncs automatically; decisions stay with you.";
    $("review-tabs").hidden = false;
    $(state.tab === "actionable" ? "tab-actionable" : "tab-informational").classList.add("active");
    $(state.tab === "actionable" ? "tab-actionable" : "tab-informational").setAttribute("aria-current", "page");
    $("table-title").firstChild.textContent = state.tab === "actionable" ? "Administrator decisions " : "Information & change history ";
    $("table-description").textContent = state.tab === "actionable" ? "Complete a tenancy action or record a decision to close a review. Tenancy outcomes are simulated in this environment." : "Active warnings clear when source data is fixed. Dates and employee changes remain available.";
    $("exceptions-link").textContent = "Back to employees →"; $("exceptions-link").href = "/";
    $("filter-label").textContent = "Review type"; $("filter").setAttribute("aria-label", "Review type");
    $("search").placeholder = "Search review items…"; $("search").setAttribute("aria-label", "Search exceptions");
    $("footnote").textContent = "Successful tenancy simulations close their reviews without changing OCI. Organization removals, identity merges and other decisions update the local model and are audited.";
  }
  $("registry-form").addEventListener("submit", submitRegistryOperation);
  $("tenancy-form").addEventListener("submit", submitTenancyEdit);
  $("offboard-form").addEventListener("submit", submitOffboarding);
  $("offboard-empty").addEventListener("change", updateOffboardSummary);
  for (const [dialogId, closeIds] of [["person-dialog", ["close-person"]], ["tenancy-dialog", ["close-tenancy", "cancel-tenancy"]], ["registry-dialog", ["close-registry", "cancel-registry"]], ["offboard-dialog", ["close-offboard", "cancel-offboard"]]]) {
    for (const id of closeIds) $(id).addEventListener("click", () => $(dialogId).close());
    $(dialogId).addEventListener("cancel", event => {if (busyRegistryDialogs.has(dialogId)) event.preventDefault();});
  }
  $("review-form").addEventListener("submit", submitReview);
  $("review-dialog").addEventListener("cancel", event => {if (reviewBusy) event.preventDefault();});
  $("close-review").addEventListener("click", () => $("review-dialog").close());
  $("cancel-review").addEventListener("click", () => $("review-dialog").close());
  $("merge-partner").addEventListener("change", mergePreview);
  $("open-clean").addEventListener("click", openClean);
  $("cancel-clean").addEventListener("click", () => $("clean-dialog").close());
  $("close-clean").addEventListener("click", () => $("clean-dialog").close());
  $("clean-form").addEventListener("submit", cleanWorkspace);
  $("open-upload").addEventListener("click", openUpload); $("empty-upload").addEventListener("click", openUpload);
  $("close-upload").addEventListener("click", () => $("upload-dialog").close()); $("cancel-upload").addEventListener("click", () => $("upload-dialog").close());
  $("upload-form").addEventListener("submit", upload);
  let timer;
  $("search").addEventListener("input", () => {clearTimeout(timer); timer = setTimeout(() => {state.query = $("search").value; state.page = 1; load();}, 180);});
  $("filter").addEventListener("change", () => {state.filter = $("filter").value; state.page = 1; load();});
  $("page-size").addEventListener("change", () => {state.size = Number($("page-size").value); state.page = 1; load();});
  try {await summary(); await load();} catch (error) {notice(`Could not load ${isTenancies ? "tenancies" : "organization"}: ${error.message}`, true);}
}
init();
