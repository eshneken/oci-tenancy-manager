import {operationHref} from "./operationNavigation";
import { CleanupResponsibilities } from "./CleanupResponsibilities";
import { AddSharedMember } from "./AddSharedMember";
import { RequiredUserSummary } from "./RequiredUserSummary";
import { RequiredUsers } from "./RequiredUsers";
import { CostCells, CostPanel, RefreshCosts } from "./FinancialCosts";
import { configurationMessages, configurationMessageClass } from "./configurationStatus";
import {TenancyOverride} from "./TenancyOverride";
import { ConfigurationRollout } from "./ConfigurationRollout";
import { DeleteTenancy } from "./DeleteTenancy";
import { Onboarding } from "./Onboarding";
import { Select } from "./Select";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { OrganizationAction, TenancyQuery, TenancyView } from "./contracts";
import { PersonActions } from "./PersonActions";
import { baselineHref } from "./baselineNavigation";
import { followLink } from "./navigation";

const statusNames: Record<string, string> = {
  pending: "Pending verification",
  active: "Active",
  terminating: "Termination pending",
  terminated: "Termination initiated",
  failed: "Review required",
  cancelled: "Creation cancelled",
};

// Consistent read-health links stay separate from confirmed drift and always open this tenancy's evidence.
function ConfigurationCheckLinks({tenancy,navigate,detail=false}:{tenancy:TenancyView;navigate:(path:string)=>void;detail?:boolean}) {
  if(tenancy.status!=="active")return null;
  const messages=configurationMessages({state:tenancy.configuration_check_state??"not_checked",stale:tenancy.configuration_check_stale,confirmed:tenancy.configuration_confirmed_issue_count}).filter(message=>detail||message.kind!=="matching");
  const href="/configuration/drift/"+tenancy.id+"?returnTo="+encodeURIComponent(detail?"/tenancies/"+tenancy.id:"/tenancies");
  return <span className="configuration-status-links">{messages.map(message=>{
    const label=detail?message.label:"Config: "+message.label.replace(/^Configuration drift/,"Drift");
    return <a key={message.kind} className={"badge configuration-issue-link "+configurationMessageClass(message.kind)} href={href} aria-label={`${label} for ${tenancy.name}`} onClick={event=>followLink(event,href,navigate)}>{label}</a>;
  })}</span>;
}

const overrideNames: Record<"policy" | "quota" | "budget", string> = { policy: "Policy statements", quota: "Quota statements", budget: "Monthly budget" };

// Expose creation time without using a completed operation as an inventory action.
function TenancyStatus({ tenancy }: { tenancy: TenancyView }) {
  const [dismissed, setDismissed] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({left:8,top:8});
  // Consolidated inventory can scroll the status column near either viewport edge.
  function showCreated(event: React.MouseEvent<HTMLElement> | React.FocusEvent<HTMLElement>) {
    const box=event.currentTarget.getBoundingClientRect();
    setTooltipPosition({left:Math.max(8,Math.min(box.left,window.innerWidth-264)),top:Math.max(8,box.top-72)});
    setDismissed(false);
  }
  const tooltipId = "tenancy-created-" + tenancy.id;
  const created = "Created " + new Date(tenancy.created_at).toLocaleString("en-US", {
    timeZone: "UTC", timeZoneName: "short",
  });
  return (
    <span className="tenancy-status-info" data-tooltip-dismissed={dismissed ? "" : undefined} onMouseEnter={showCreated}>
      <span
        className={"badge tenancy-status-label " + (tenancy.status === "active" ? "active" : "review-open")}
        tabIndex={0}
        aria-describedby={tooltipId}
        onFocus={showCreated}
        onKeyDown={event => { if (event.key === "Escape") setDismissed(true); }}
      >
        {tenancy.status === "active" ? "✓ " : ""}{statusNames[tenancy.status]}
      </span>
      <span id={tooltipId} role="tooltip" style={tooltipPosition} className="tenancy-created-tooltip">{created}</span>
    </span>
  );
}

// Keep unfinished workflow entry points while completed history remains in the operation screens.
function hasInventoryOperation(tenancy: TenancyView) {
  return Boolean(tenancy.operation_id && (
    ["queued", "running", "waiting"].includes(tenancy.operation_state ?? "") ||
    (tenancy.has_pending_operation && tenancy.operation_state === "needs_attention")
  ));
}

// Present one registered-child inventory, ready for later configuration and cost columns.
export function Tenancies({
  identifier,
  expired,
  navigate,
}: {
  identifier: string | null;
  expired: () => void;
  navigate: (path: string) => void;
}) {
  const [addingMember, setAddingMember] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [query, setQuery] = useState<TenancyQuery>({
    shared_only: false,
    page: 1,
    page_size: 10,
    query: "",
    sort: "name",
    direction: "asc",
  });
  const [selected, setSelected] = useState<{
    person: string;
    action?: OrganizationAction["action"];
    tenancy?: string;
  } | null>(null);
  // Browser Back or a different detail cannot reopen a deletion/person dialog for another target.
  useEffect(() => {
    setAddingMember(false);
    setDeleting(null);
    setSelected(null);
  }, [identifier]);
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["tenancies", "list", query],
    queryFn: ({ signal }) => api.tenancies(query, signal),
    enabled: !identifier,
    placeholderData: (previous, previousQuery) =>
      Boolean(
        (previousQuery?.queryKey[2] as TenancyQuery | undefined)?.shared_only,
      ) === Boolean(query.shared_only)
        ? previous
        : undefined,
    retry: false,
    refetchInterval: (value) =>
      (value.state.data?.pending_count || value.state.data?.costs_pending_count || value.state.data?.items.some(row=>row.required_users?.checking)) ? 2000 : false,
  });
  const detail = useQuery({
    queryKey: ["tenancies", "detail", identifier],
    queryFn: ({ signal }) => api.tenancy(identifier!, signal),
    enabled: Boolean(identifier),
    retry: false,
    refetchInterval: (value) =>
      ["queued", "running", "waiting"].includes(
        value.state.data?.tenancy.operation_state ?? "",
      ) || value.state.data?.tenancy.costs?.pending
        ? 2000
        : false,
  });
  useEffect(() => {
    const failure = list.error ?? detail.error;
    if (failure instanceof ApiError && [401, 403].includes(failure.status))
      expired();
  }, [list.error, detail.error, expired]);
  const data = list.data;
  const tenant = detail.data?.tenancy;
  const pageStart = Math.max(
    1,
    Math.min((data?.page ?? 1) - 2, (data?.pages ?? 1) - 4),
  );
  const pages = Array.from(
    { length: Math.min(5, data?.pages ?? 1) },
    (_, index) => pageStart + index,
  );

  // Keep each visible sortable label tied to an allowlisted server projection.
  function sort(column: NonNullable<TenancyQuery["sort"]>) {
    setQuery({
      ...query,
      page: 1,
      sort: column,
      direction:
        query.sort === column && query.direction === "asc" ? "desc" : "asc",
    });
  }

  return (
    <>
      {identifier && (
        <a
          className="back-link"
          href="/tenancies"
          onClick={(event) => followLink(event, "/tenancies", navigate)}
        >
          ← Back to tenancies
        </a>
      )}
      <div className="page-heading tenancy-heading">
        <div>
          <span className="eyebrow">TENANCIES</span>
          <h1 tabIndex={-1}>
            {identifier ? (tenant?.name ?? "Tenancy details") : "Tenancies"}
          </h1>
          <p className="muted">
            {identifier
              ? "Registered ownership, memberships and verified local workflow results."
              : "Registered child tenancies and their accountable owners."}
          </p>
        </div>
        <div className="page-actions">
          {!identifier && <RefreshCosts disabled={!data?.can_refresh_costs || !!data?.costs_pending_count} expired={expired}/>}
          {identifier &&
            tenant?.status === "active" &&
            detail.data &&
            !detail.data.memberships.some((m) => m.operation_id) && (
              <button
                className="button danger"
                onClick={() => setDeleting(identifier)}
              >
                Delete tenancy
              </button>
            )}
          <button
            className="button secondary"
            disabled={identifier ? detail.isFetching : list.isFetching}
            onClick={() =>
              void (identifier ? Promise.all([
                detail.refetch(),
                client.invalidateQueries({ queryKey: ["tenancies", "required-users", identifier] }),
              ]) : list.refetch())
            }
          >
            Refresh
          </button>
        </div>
      </div>
      <p className="notice">
        OCI lifecycle execution is simulated locally. This inventory does not
        claim discovery or changes in OCI.
      </p>
      {!identifier && (
        <>
          <div
            className="metrics tenancy-metrics"
            aria-label="Tenancy statistics"
          >
            {[
              ["Total tenancies", data?.total_tenancies],
              ["Individual", data?.individual_count],
              ["Shared", data?.shared_count],
              ["Pending", data?.pending_count],
            ].map(([label, value]) => (
              <div className="metric" key={label}>
                <span>{label}</span>
                <strong>{value ?? "—"}</strong>
              </div>
            ))}
          </div>
          <section className="table-panel">
            <div className="table-toolbar tenancy-toolbar directory-toolbar">
              <label className="search-field">
                Search tenancies
                <input
                  type="search"
                  maxLength={128}
                  value={query.query}
                  placeholder="Tenancy, owner, manager or industry segment"
                  onChange={(event) =>
                    setQuery({ ...query, query: event.target.value, page: 1 })
                  }
                />
              </label>
              <label className="workflow-check directory-filter">
                <input
                  type="checkbox"
                  checked={query.shared_only ?? false}
                  onChange={(event) =>
                    setQuery({
                      ...query,
                      shared_only: event.target.checked,
                      page: 1,
                    })
                  }
                />
                Shared tenancies only
              </label>
              <a
                href="/organization"
                onClick={(event) =>
                  followLink(event, "/organization", navigate)
                }
              >
                Choose an owner to create or import a tenancy
              </a>
            </div>
            {list.isPending ? (
              <p className="table-feedback" role="status">
                Loading tenancies…
              </p>
            ) : list.isError ? (
              <p className="table-feedback alert" role="alert">
                Tenancies could not be loaded. Use Refresh to try again.
              </p>
            ) : (
              data && (
                <>
                  <div
                    className="table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label="Registered tenancy inventory"
                  >
                    <table>
                      <caption className="sr-only">
                        Registered child tenancy inventory
                      </caption>
                      <thead>
                        <tr>
                          {[
                            ["name", "Tenancy"],
                            ["owner_name", "Owner"],
                          ].map(([key, label]) => (
                            <th
                              scope="col"
                              key={key}
                              aria-sort={
                                query.sort === key
                                  ? query.direction === "asc"
                                    ? "ascending"
                                    : "descending"
                                  : "none"
                              }
                            >
                              <button
                                className="sort-button"
                                onClick={() =>
                                  sort(key as NonNullable<TenancyQuery["sort"]>)
                                }
                              >
                                {label}{" "}
                                <span aria-hidden="true">
                                  {query.sort === key
                                    ? query.direction === "asc"
                                      ? "↑"
                                      : "↓"
                                    : "↕"}
                                </span>
                              </button>
                            </th>
                          ))}
                          <th scope="col">Status</th>
                          <th scope="col" aria-sort={["actual", "budget"].includes(query.sort ?? "") ? query.direction === "asc" ? "ascending" : "descending" : "none"}><div className="cost-header-pair">{(["actual", "budget"] as const).map(key => <button key={key} className="sort-button" aria-label={`Sort by ${key}`} aria-pressed={query.sort === key} title={query.sort === key ? `Sorted ${query.direction === "asc" ? "ascending" : "descending"}` : `Sort by ${key}`} onClick={() => sort(key)}>{key === "actual" ? "Actual" : "Budget"} <span aria-hidden="true">{query.sort === key ? query.direction === "asc" ? "↑" : "↓" : "↕"}</span></button>)}</div></th>
                          <th scope="col" aria-sort={query.sort === "forecast" ? query.direction === "asc" ? "ascending" : "descending" : "none"}><button className="sort-button" onClick={() => sort("forecast")}>Forecast <span aria-hidden="true">{query.sort === "forecast" ? query.direction === "asc" ? "↑" : "↓" : "↕"}</span></button></th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.items.map((row) => (
                          <tr key={row.id}>
                            <td>
                              <a
                                href={"/tenancies/" + row.id}
                                onClick={(event) =>
                                  followLink(
                                    event,
                                    "/tenancies/" + row.id,
                                    navigate,
                                  )
                                }
                              >
                                {row.name}
                              </a>
                              <span className="cell-secondary">
                                {row.kind} · {row.member_count} {row.member_count === 1 ? "member" : "members"}
                              </span>
                            </td>
                            <td>
                              {row.owner_person_id ? (
                                <button
                                  className="text-link"
                                  onClick={() =>
                                    setSelected({
                                      person: row.owner_person_id!,
                                    })
                                  }
                                >
                                  {row.owner_name}
                                </button>
                              ) : (
                                "Unassigned"
                              )}
                              <span className="cell-secondary">
                                {row.owner_email}
                                <span className="cell-secondary">{row.lob_name ?? "Unmapped"}</span>
                              </span>
                            </td>
                            <td>
                              <TenancyStatus tenancy={row} />
                              <RequiredUserSummary id={row.id} name={row.name} status={row.status} summary={row.required_users} navigate={navigate}/>
                              <ConfigurationCheckLinks tenancy={row} navigate={navigate}/>
                              <div className="tenancy-configuration">{row.baseline_version_id?<><a href={baselineHref(row.baseline_version_id,location.pathname)} onClick={event=>followLink(event,baselineHref(row.baseline_version_id!,location.pathname),navigate)}>Baseline v{row.baseline_version_number??"?"}</a>{data.latest_baseline_id===row.baseline_version_id?<span className={row.verified_baseline_version_id===row.baseline_version_id&&row.desired_configuration_id===row.last_verified_configuration_id?"baseline-latest":"muted"} title={row.verified_baseline_version_id===row.baseline_version_id&&row.desired_configuration_id===row.last_verified_configuration_id?"Latest baseline verified in simulation":"Latest baseline selected; verification pending"}>Latest</span>:data.latest_baseline_version_number&&<a href={"/tenancies/"+row.id} onClick={event=>followLink(event,"/tenancies/"+row.id,navigate)} aria-label={`Update ${row.name} to baseline v${data.latest_baseline_version_number}`}>↑ v{data.latest_baseline_version_number}</a>}</>:<span className="muted">No baseline assigned</span>}{!!row.override_categories?.length&&<a className="override-indicator" title={"Overrides: "+row.override_categories.join(", ")} href={"/tenancies/"+row.id+"?override=1"} onClick={event=>followLink(event,"/tenancies/"+row.id+"?override=1",navigate)}>Override</a>}</div>
                              {hasInventoryOperation(row) && (
                                <a
                                  className="cell-secondary"
                                  href={operationHref(row.operation_id)}
                                  onClick={(event) =>
                                    followLink(
                                      event,
                                      operationHref(row.operation_id),
                                      navigate,
                                    )
                                  }
                                >
                                  {row.operation_state === "needs_attention" ? "Review operation" : "View operation"}
                                </a>
                              )}
                            </td>
                            <CostCells cost={row.costs} name={row.name}/>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.items.length === 0 && (
                    <div className="table-feedback">
                      <h2>
                        {query.query
                          ? "No tenancies match your search"
                          : query.shared_only
                            ? "No shared tenancies registered yet"
                            : "No tenancies registered yet"}
                      </h2>
                      <p>
                        Create or import a tenancy from an employee's
                        Organization record.
                      </p>
                    </div>
                  )}
                  <div className="table-footer">
                    <label>
                      Rows per page{" "}
                      <Select
                        aria-label="Tenancy rows per page"
                        value={query.page_size}
                        onChange={(event) =>
                          setQuery({
                            ...query,
                            page: 1,
                            page_size: Number(event.target.value) as
                              10 | 25 | 50,
                          })
                        }
                      >
                        {[10, 25, 50].map((size) => (
                          <option key={size}>{size}</option>
                        ))}
                      </Select>
                    </label>
                    <span>
                      {data.total} tenancies · Page {data.page} of {data.pages}
                    </span>
                    <div className="pagination">
                      <button
                        className="button secondary"
                        disabled={data.page <= 1}
                        onClick={() =>
                          setQuery({ ...query, page: data.page - 1 })
                        }
                      >
                        Previous
                      </button>
                      <nav className="page-numbers" aria-label="Tenancy pages">
                        {pages.map((page) => (
                          <button
                            key={page}
                            className="button secondary"
                            aria-label={"Page " + page}
                            aria-current={
                              page === data.page ? "page" : undefined
                            }
                            onClick={() => setQuery({ ...query, page })}
                          >
                            {page}
                          </button>
                        ))}
                      </nav>
                      <button
                        className="button secondary"
                        disabled={data.page >= data.pages}
                        onClick={() =>
                          setQuery({ ...query, page: data.page + 1 })
                        }
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </>
              )
            )}
          </section>
        </>
      )}
      {identifier &&
        (detail.isPending ? (
          <p role="status">Loading tenancy details…</p>
        ) : detail.isError ? (
          <p className="alert" role="alert">
            This tenancy is unavailable in the current workspace. Use Refresh or
            return to the inventory.
          </p>
        ) : (
          tenant &&
          detail.data && (
            <>
              {detail.data.onboarding_operation_id && (
                <Onboarding
                  key={detail.data.onboarding_operation_id}
                  operationId={detail.data.onboarding_operation_id}
                  expired={expired}
                  navigate={navigate}
                />
              )}
              <section className="operation-panel">
                <div className="tenancy-detail-heading">
                  <h2>Accountability &amp; registration</h2>
                  <span
                    className={
                      "badge " +
                      (tenant.status === "active" ? "active" : "review-open")
                    }
                  >
                    {statusNames[tenant.status]}
                  </span>
                </div>
                <dl className="operation-facts">
                  <div>
                    <dt>Owner</dt>
                    <dd>{tenant.owner_name ?? "Unassigned"}</dd>
                  </div>
                  <div>
                    <dt>Type</dt>
                    <dd>{tenant.kind}</dd>
                  </div>
                  <div>
                    <dt>Industry segment / accountable leader</dt>
                    <dd>
                      {tenant.lob_name ?? "Unmapped"} ·{" "}
                      {tenant.leader_name ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Home region</dt>
                    <dd>{tenant.home_region}</dd>
                  </div>
                  <div><dt>Selected baseline</dt><dd>{tenant.baseline_version_id ? <a href={baselineHref(tenant.baseline_version_id!,`/tenancies/${tenant.id}`)} onClick={event=>followLink(event,baselineHref(tenant.baseline_version_id!,`/tenancies/${tenant.id}`),navigate)}>Baseline v{tenant.baseline_version_number??"?"}</a> : "Not assigned"}<span className="cell-secondary">{tenant.verified_baseline_version_id ? <>Last verified: <a href={baselineHref(tenant.verified_baseline_version_id,`/tenancies/${tenant.id}`)} onClick={event=>followLink(event,baselineHref(tenant.verified_baseline_version_id!,`/tenancies/${tenant.id}`),navigate)}>Baseline v{tenant.verified_baseline_version_number}</a> (simulation)</> : "Not yet verified in simulation"}</span></dd></div>
                  <div><dt>Configuration check</dt><dd>{tenant.status==="active"?<><ConfigurationCheckLinks tenancy={tenant} navigate={navigate} detail/><span className="cell-secondary">{tenant.configuration_checked_at?"Last attempt: "+new Date(tenant.configuration_checked_at).toLocaleString("en-US",{timeZone:"UTC",timeZoneName:"short"}):"No check recorded"}</span></>:<span className="muted">Checks are available for active managed tenancies.</span>}</dd></div>
                  <div>
                    <dt>Tenancy OCID</dt>
                    <dd className="technical-id">{tenant.tenancy_ocid}</dd>
                  </div>
                  <div>
                    <dt>Parent tenancy OCID</dt>
                    <dd className="technical-id">
                      {tenant.parent_tenancy_ocid}
                    </dd>
                  </div>
                  <div>
                    <dt>Members including owner</dt>
                    <dd>{tenant.member_count}</dd>
                  </div>
                  <div>
                    <dt>Origin</dt>
                    <dd>
                      {tenant.origin === "import" ? "Imported" : "Created"} ·
                      Simulated
                    </dd>
                  </div>
                </dl>
                {tenant.operation_id && (
                  <a
                    className="tenancy-operation-link"
                    href={operationHref(tenant.operation_id)}
                    onClick={(event) =>
                      followLink(
                        event,
                        operationHref(tenant.operation_id),
                        navigate,
                      )
                    }
                  >
                    View latest operation
                  </a>
                )}
              </section>
              <RequiredUsers key={"required-users-"+tenant.id} tenancyId={tenant.id} expired={expired} navigate={navigate}/>
              <div className="tenancy-summary-grid">
              <CostPanel key={"costs-"+tenant.id} cost={tenant.costs} tenancyId={tenant.id} expired={expired}/>
              {tenant.status === "active" && (
                <section className="operation-panel tenancy-overrides" aria-labelledby="tenancy-overrides-title">
                  <div className="cost-panel-heading">
                    <h2 id="tenancy-overrides-title">Overrides</h2>
                    <div className="tenancy-override-actions"><TenancyOverride key={tenant.id} tenancyId={tenant.id} expired={expired} navigate={navigate} /></div>
                  </div>
                  {tenant.override_categories?.length ? (
                    <>
                      <p>{tenant.override_categories.map(category => overrideNames[category]).join(", ")}</p>
                      <p className="muted">{tenant.desired_configuration_id && tenant.desired_configuration_id === tenant.last_verified_configuration_id ? "Verified in simulation" : "Verification pending"}</p>
                    </>
                  ) : <p className="muted">All categories inherit the assigned baseline. No tenancy-specific overrides are configured.</p>}
                </section>
              )}
              </div>
              {tenant.status==="active"&&<ConfigurationRollout key={tenant.id} tenancyId={tenant.id} selectedId={tenant.baseline_version_id} initialOperationId={detail.data.configuration_operation_id??undefined} expired={expired} navigate={navigate}/>}
              <section className="table-panel">
                <div className="table-toolbar tenancy-members-toolbar">
                  <h2>Current members</h2>
                  {tenant.kind === "shared" && tenant.status === "active" && <button type="button" className="button secondary" disabled={Boolean(tenant.has_pending_operation)} onClick={() => setAddingMember(true)}>Add member</button>}
                </div>
                <div
                  className="table-scroll"
                  tabIndex={0}
                  role="region"
                  aria-label="Tenancy membership"
                >
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Employee</th>
                        <th scope="col">Role</th>
                        <th scope="col">Access / compartment</th>
                        <th scope="col">Status</th>
                        <th scope="col">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.memberships
                        .filter((a) =>
                          ["active", "pending", "removing"].includes(a.status),
                        )
                        .map((link) => {
                          return (
                            <MembershipRow
                              key={link.id}
                              link={link}
                              people={detail.data!.people}
                              onSelect={(id, action) =>
                                setSelected({
                                  person: id,
                                  action,
                                  tenancy: tenant.id,
                                })
                              }
                            />
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </section>
              {tenant.cleanup_count > 0 && (
                <section className="operation-panel">
                  <h2>Manual cleanup guidance</h2>
                  <p>
                    Coordinate manual cleanup with the current owner,{" "}
                    {tenant.owner_name ?? "the assigned tenancy owner"}. Review
                    the former members and scopes below. The tool removes recorded
                    user/group access; resources, compartments and additional accounts
                    remain. Cleanup completion is handled outside this screen.
                  </p>
                  <CleanupResponsibilities/>
                  <ul>
                    {detail.data.memberships
                      .filter((a) => a.cleanup_required)
                      .map((a) => (
                        <li key={a.id}>
                          <strong>{detail.data!.people.find(p=>p.id===a.person_id)?.name ?? "Former member"}</strong>{" · "}
                          {a.compartment_name ?? "Scope not recorded — review with the tenancy owner"}{" "}
                          <span className="technical-id">
                            {a.compartment_ocid}
                          </span>
                        </li>
                      ))}
                  </ul>
                </section>
              )}
            </>
          )
        ))}
      {deleting === identifier && identifier && (
        <DeleteTenancy
          key={identifier}
          tenancyId={identifier}
          expired={expired}
          navigate={navigate}
          onClose={() => setDeleting(null)}
        />
      )}
      {addingMember && tenant?.kind === "shared" && tenant.status === "active" && detail.data && (
        <AddSharedMember tenancyName={tenant.name}
          memberIds={detail.data.memberships.filter(link => ["active","pending","removing"].includes(link.status)).map(link => link.person_id)}
          expired={expired} onClose={() => setAddingMember(false)}
          onChoose={person => {setAddingMember(false);setSelected({person,action:"join_shared",tenancy:tenant.id});}}/>
      )}
      {selected && (
        <PersonActions
          personId={selected.person}
          initialAction={selected.action}
          tenancyId={selected.tenancy}
          expired={expired}
          navigate={navigate}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}

// Bind each action to the displayed stable person and registered tenancy instead of a free-form OCID.
function MembershipRow({
  link,
  people,
  onSelect,
}: {
  link: import("./contracts").AssociationView;
  people: import("./contracts").PersonOption[];
  onSelect: (person: string, action: OrganizationAction["action"]) => void;
}) {
  const person = people.find((p) => p.id === link.person_id);
  return (
    <tr>
      <td>
        {person ? (
          <button
            className="text-link"
            onClick={() =>
              onSelect(
                person.id,
                link.role === "owner" ? "transfer_owner" : "remove_member",
              )
            }
          >
            {person.name}
          </button>
        ) : (
          "Recorded employee"
        )}
        <span className="cell-secondary">{person?.email}</span>
      </td>
      <td className="tenancy-member-role">{link.role}</td>
      <td>
        {link.compartment_name ??
          (link.role === "owner" ? "Accountable owner" : "Existing access — scope not recorded")}
        <span className="technical-id cell-secondary">
          {link.compartment_ocid}
        </span>
      </td>
      <td>{link.status}</td>
      <td>
        {person &&
          link.actions.includes(
            link.role === "owner" ? "transfer" : "remove",
          ) && (
            <button
              className="button secondary"
              onClick={() =>
                onSelect(
                  person.id,
                  link.role === "owner" ? "transfer_owner" : "remove_member",
                )
              }
            >
              {link.role === "owner" ? "Transfer owner" : "Remove member"}
            </button>
          )}
      </td>
    </tr>
  );
}
