import type { CostRefreshReceipt, CostRefreshRequest } from "./contracts";
import type { EmailPolicyView } from "./contracts";
import type { ResponsibilityCommand } from "./contracts";
import type { ConfigurationDriftQuery, ConfigurationDriftDirectory, ConfigurationCheckSummary, ConfigurationCheckRequest } from "./contracts";
import type {OverrideEditor,OverridePreviewRequest,ConfigurationPlanView,CreateConfigurationPlan,SaveConfigurationReview} from "./contracts";
import type {ConfigurationPreview,ConfigurationUpdate,ConfigurationProgress} from "./contracts";
import type { BaselineDirectory, BaselineVersion, BaselineQuery, PublishBaseline, SaveBaselineDraft } from "./contracts";
import type {
  MappingSettings,
  MappingPreview,
  MappingRequest,
  MappingApply,
  OnboardingCommand,
  OnboardingView,
  TenancyDeletionCommand,
  TenancyDeletionPreview,
  OrganizationAction,
  ActionReceipt,
  PersonWorkflow,
  ReviewDirectory,
  ReviewQuery,
  TenancyDirectory,
  TenancyDetail,
  TenancyQuery,
} from "./contracts";
import type {
  OrganizationDirectory,
  OrganizationQuery,
  OrganizationOutcome,
} from "./contracts";
import type {
  BrandingView,
  AuditDirectory,
  AuditQuery,
  AuditExportQuery,
} from "./contracts";
import type {
  Acceptance,
  InspectionSubmission,
  SandboxCatalog,
  OperationDetail,
  OperationDirectory,
  OperationQuery,
} from "./contracts";
import type {
  AdministratorDirectory,
  AdministratorQuery,
  SessionView,
} from "./contracts";

// Keep provider/server details and credential input out of visible error messages.
export class ApiError extends Error {
  // Classify only the HTTP status; response bodies may contain private diagnostics.
  constructor(public status: number) {
    super("Request unavailable");
  }
}

// Send factors only in a same-origin POST body; never use browser storage or URL parameters.
async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method,
    signal,
    credentials: "same-origin",
    cache: "no-store",
    headers:
      method === "GET"
        ? {}
        : { "Content-Type": "application/json", "X-OTM-Request": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(response.status);
  return response.status === 204
    ? (undefined as T)
    : ((await response.json()) as T);
}
// Accept only the server's fixed CSV validation messages, never arbitrary provider error text.
export class CsvUploadError extends ApiError {
  // Parser messages contain locations and fixed guidance, never submitted cell contents.
  constructor(
    status: number,
    public guidance: string,
  ) {
    super(status);
  }
}

// Map only server diagnostic codes to fixed UI guidance; never display raw provider errors.
export class WorkflowError extends ApiError {
  // A code is used only as a key into the UI's static explanation map.
  constructor(
    status: number,
    public code: string,
  ) {
    super(status);
  }
}

export const api = {
  // Nonsecret delivery policy remains administrator-only; never expose SMTP settings or credentials.
  emailPolicy(signal?:AbortSignal) { return request<EmailPolicyView>("/api/email-policy","GET",undefined,signal); },
  // Transfer workflow responsibility only; frozen creation intent and tenancy ownership stay unchanged.
  takeResponsibility(id:string,body:ResponsibilityCommand,signal?:AbortSignal) {
    return request<ActionReceipt>("/api/operations/"+encodeURIComponent(id)+"/responsibility","POST",body,signal);
  },
  // Checks read exact assigned configuration; request bodies cannot author or repair managed objects.
  configurationDrift(query:ConfigurationDriftQuery,signal?:AbortSignal) {
    const params=new URLSearchParams(Object.entries(query).filter(([,value])=>value!==undefined&&value!==null).map(([key,value])=>[key,String(value)]));
    return request<ConfigurationDriftDirectory>("/api/configuration/drift?"+params,"GET",undefined,signal);
  },
  configurationCheck(id:string,signal?:AbortSignal) { return request<ConfigurationCheckSummary>("/api/configuration/drift/"+encodeURIComponent(id),"GET",undefined,signal); },
  startConfigurationCheck(body:ConfigurationCheckRequest,signal?:AbortSignal) { return request<ActionReceipt>("/api/configuration/checks","POST",body,signal); },
  overrideEditor(id:string,signal?:AbortSignal){return request<OverrideEditor>("/api/configuration/overrides/"+encodeURIComponent(id),"GET",undefined,signal);},
  previewOverride(body:OverridePreviewRequest,signal?:AbortSignal){return request<ConfigurationPreview>("/api/configuration/overrides/preview","POST",body,signal);},
  applyOverride(body:ConfigurationUpdate,signal?:AbortSignal){return request<ActionReceipt>("/api/configuration/overrides","POST",body,signal);},
  createConfigurationPlan(body:CreateConfigurationPlan,signal?:AbortSignal){return request<ConfigurationPlanView>("/api/configuration/plans","POST",body,signal);},
  configurationPlan(id:string,signal?:AbortSignal){return request<ConfigurationPlanView>("/api/configuration/plans/"+encodeURIComponent(id),"GET",undefined,signal);},
  reviewConfigurationPlan(id:string,body:SaveConfigurationReview,signal?:AbortSignal){return request<ConfigurationPlanView>("/api/configuration/plans/"+encodeURIComponent(id)+"/reviews","POST",body,signal);},
  configurationPreview(tenancyId?:string,signal?:AbortSignal){return request<ConfigurationPreview>("/api/configuration/updates/preview"+(tenancyId?"?tenancy_id="+encodeURIComponent(tenancyId):""),"GET",undefined,signal);},
  startConfigurationUpdate(body:ConfigurationUpdate,signal?:AbortSignal){return request<ActionReceipt>("/api/configuration/updates","POST",body,signal);},
  configurationProgress(id:string,signal?:AbortSignal){return request<ConfigurationProgress>("/api/configuration/updates/"+encodeURIComponent(id),"GET",undefined,signal);},
  retryConfigurationUpdate(id:string,signal?:AbortSignal){return request<ActionReceipt>("/api/configuration/updates/"+encodeURIComponent(id)+"/retry","POST",undefined,signal);},
  // Authoring is a scoped draft save; these endpoints cannot publish or touch OCI.
  baselines(signal?: AbortSignal, query: BaselineQuery = {}) {
    const params = new URLSearchParams();
    if (query.page) params.set("page", String(query.page));
    if (query.page_size) params.set("page_size", String(query.page_size));
    if (query.baseline_id) params.set("baseline_id", query.baseline_id);
    return request<BaselineDirectory>("/api/configuration/baselines" + (params.size ? "?" + params : ""), "GET", undefined, signal);
  },
  publishBaseline(body: PublishBaseline, signal?: AbortSignal) { return request<BaselineVersion>("/api/configuration/baselines/publish", "POST", body, signal); },
  saveBaselineDraft(body: SaveBaselineDraft, signal?: AbortSignal) { return request<BaselineVersion>("/api/configuration/baselines/draft", "POST", body, signal); },

  // Read a durable inbox/history page using the current session scope.
  organizationReviews(query: ReviewQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query).map(([key, value]) => [key, String(value)]),
    );
    return request<ReviewDirectory>(
      "/api/organization/reviews?" + params,
      "GET",
      undefined,
      signal,
    );
  },
  // Fetch a new exact-context preview; names and eligible recipients never come from query parameters.
  // Mapping writes carry only editable values and the server preview/revision fence.
  mapping(signal?: AbortSignal) {
    return request<MappingSettings>(
      "/api/organization/mapping",
      "GET",
      undefined,
      signal,
    );
  },
  previewMapping(body: MappingRequest, page = 1, signal?: AbortSignal) {
    return request<MappingPreview>(
      "/api/organization/mapping/preview?page=" + page,
      "POST",
      body,
      signal,
    );
  },
  applyMapping(body: MappingApply, signal?: AbortSignal) {
    return request<MappingSettings>(
      "/api/organization/mapping/apply",
      "POST",
      body,
      signal,
    );
  },
  personWorkflow(id: string, reviewId: string | null, signal?: AbortSignal) {
    return request<PersonWorkflow>(
      "/api/organization/people/" +
        encodeURIComponent(id) +
        "/workflow" +
        (reviewId ? "?review_id=" + encodeURIComponent(reviewId) : ""),
      "GET",
      undefined,
      signal,
    );
  },
  // Whole-tenancy deletion has a distinct, bounded request contract and complete server preview.
  deletionPreview(identifier: string, signal?: AbortSignal) {
    return request<TenancyDeletionPreview>(
      "/api/tenancies/" + identifier + "/deletion-preview",
      "GET",
      undefined,
      signal,
    );
  },
  deleteTenancy(body: TenancyDeletionCommand, signal?: AbortSignal) {
    return request<ActionReceipt>(
      "/api/tenancy-deletions",
      "POST",
      body,
      signal,
    );
  },
  // A single request identity is reused on uncertain transport retry; source/config revisions are explicit.
  // Persisted setup reads never submit jobs; commands use the same session and CSRF boundary.
  onboarding(identifier: string, signal?: AbortSignal) {
    return request<OnboardingView>(
      "/api/tenancy-onboarding/" + identifier,
      "GET",
      undefined,
      signal,
    );
  },
  onboardingAction(
    identifier: string,
    body: OnboardingCommand,
    signal?: AbortSignal,
  ) {
    return request<ActionReceipt>(
      "/api/tenancy-onboarding/" + identifier,
      "POST",
      body,
      signal,
    );
  },
  async organizationAction(
    body: OrganizationAction,
    signal?: AbortSignal,
  ): Promise<ActionReceipt> {
    const response = await fetch("/api/organization/actions", {
      method: "POST",
      signal,
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-OTM-Request": "1" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      if ([400, 409].includes(response.status)) {
        const value = await response.json();
        throw new WorkflowError(
          response.status,
          typeof value.code === "string" && /^[A-Z_]{1,80}$/.test(value.code)
            ? value.code
            : "WORKFLOW_UNAVAILABLE",
        );
      }
      throw new ApiError(response.status);
    }
    return response.json() as Promise<ActionReceipt>;
  },
  // Queue current-month reads without trusting browser-supplied OCI source identities.
  refreshCosts(command: CostRefreshRequest) { return request<CostRefreshReceipt>("/api/costs/refresh", "POST", command); },
  // Read only registered children, not a fabricated cloud-wide tenancy inventory.
  tenancies(query: TenancyQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query).map(([key, value]) => [key, String(value)]),
    );
    return request<TenancyDirectory>(
      "/api/tenancies?" + params,
      "GET",
      undefined,
      signal,
    );
  },
  // Details include retained cleanup guidance and discovered simulated compartment parents.
  tenancy(id: string, signal?: AbortSignal) {
    return request<TenancyDetail>(
      "/api/tenancies/" + encodeURIComponent(id),
      "GET",
      undefined,
      signal,
    );
  },
  // Read a scoped directory with allowlisted sort fields and literal search terms.
  organization(query: OrganizationQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query).map(([key, value]) => [key, String(value)]),
    );
    return request<OrganizationDirectory>(
      "/api/organization?" + params,
      "GET",
      undefined,
      signal,
    );
  },
  // File bytes remain outside React Query caches and browser storage; retry preserves delivery identity.
  async uploadOrganization(
    file: File,
    asOf: string,
    delivery: string,
    complete: boolean,
    signal?: AbortSignal,
  ): Promise<OrganizationOutcome> {
    const response = await fetch("/api/organization/feeds", {
      method: "POST",
      signal,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "text/csv",
        "X-OTM-Request": "1",
        "X-OTM-As-Of": asOf,
        "X-OTM-Delivery": delivery,
        "X-OTM-Complete": String(complete),
      },
      body: file,
    });
    if (!response.ok) {
      if (response.status === 400 || response.status === 413) {
        const value = await response.json();
        if (
          (value.code === "INVALID_CSV" || value.code === "CSV_TOO_LARGE") &&
          typeof value.message === "string"
        )
          throw new CsvUploadError(response.status, value.message);
      }
      throw new ApiError(response.status);
    }
    return response.json() as Promise<OrganizationOutcome>;
  },
  // Public nonsecret instance branding is available before sign-in and carries no session authority.
  branding(signal?: AbortSignal) {
    return request<BrandingView>("/api/branding", "GET", undefined, signal);
  },
  // Preserve verification outages while treating missing or denied administrator access as signed out.
  async session(signal?: AbortSignal): Promise<SessionView | null> {
    try {
      return await request<SessionView>(
        "/api/session",
        "GET",
        undefined,
        signal,
      );
    } catch (error) {
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403)
      )
        return null;
      throw error;
    }
  },
  // Factor values never become query keys or cached query data.
  signIn(password: string, code: string) {
    return request<SessionView>("/api/auth/local/sign-in", "POST", {
      username: "recovery-admin",
      password,
      totp_code: code,
    });
  },
  // End only the presented browser session, independent of corporate SSO availability.
  logout() {
    return request<void>("/api/logout", "POST");
  },
  // Send only actual input activity, separately from read-only polling.
  activity() {
    return request<SessionView>("/api/session/activity", "POST");
  },
  // The server resolves identity/workspace and allowlists all sort/filter controls.
  directory(query: AdministratorQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query).map(([key, value]) => [key, String(value)]),
    );
    return request<AdministratorDirectory>(
      "/api/administrators?" + params.toString(),
      "GET",
      undefined,
      signal,
    );
  },
  // Read only the server's redacted immutable audit projection; no raw event payload is requested.
  auditHistory(query: AuditQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query)
        .filter(([, value]) => value !== null && value !== undefined)
        .map(([key, value]) => [key, String(value)]),
    );
    return request<AuditDirectory>(
      "/api/audit-history?" + params.toString(),
      "GET",
      undefined,
      signal,
    );
  },
  // Fetch a guarded CSV directly, outside query caches and without trusting server-provided filenames.
  async exportAudit(
    query: AuditExportQuery,
    signal?: AbortSignal,
  ): Promise<Blob> {
    const response = await fetch("/api/audit-history/export", {
      method: "POST",
      signal,
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-OTM-Request": "1" },
      body: JSON.stringify(query),
    });
    if (!response.ok) throw new ApiError(response.status);
    if (!response.headers.get("content-type")?.startsWith("text/csv"))
      throw new ApiError(503);
    return response.blob();
  },
  // Read recorded operations only; list controls never dispatch provider work.
  operations(query: OperationQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query).map(([key, value]) => [key, String(value)]),
    );
    return request<OperationDirectory>(
      "/api/operations?" + params.toString(),
      "GET",
      undefined,
      signal,
    );
  },
  // Keep the operation identity opaque and scope resolution to the authenticated server session.
  operation(id: string, signal?: AbortSignal) {
    return request<OperationDetail>(
      "/api/operations/" + encodeURIComponent(id),
      "GET",
      undefined,
      signal,
    );
  },
  // Discover only explicitly configured synthetic targets; absence never enables submission.
  inspectionSandbox(signal?: AbortSignal) {
    return request<SandboxCatalog>(
      "/api/inspection-sandbox",
      "GET",
      undefined,
      signal,
    );
  },
  // Submit only a client request identity and synthetic target; server authorization supplies all binding fields.
  inspect(body: InspectionSubmission) {
    return request<Acceptance>("/api/operations/inspect", "POST", body);
  },
  // Require the exact displayed grant revision; server-side protected-account checks remain authoritative.
  revoke(id: string, revision: string) {
    return request<unknown>(
      "/api/administrators/" + encodeURIComponent(id) + "/revoke",
      "POST",
      { expected_revision: revision },
    );
  },
};
