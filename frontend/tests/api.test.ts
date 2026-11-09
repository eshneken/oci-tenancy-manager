import { describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../src/api";
import type { MappingRequest } from "../src/contracts";

// Isolate transport contracts and ensure factors appear only in the POST body.
describe("API transport", () => {
  // Recovery-network commands retain target encoding, cancellation, CSRF and closed body fields.
  it("keeps network repair previews and consent on fixed same-origin endpoints",async()=>{
    const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({})});
    vi.stubGlobal("fetch",fetch);const signal=new AbortController().signal;
    await api.previewRecoveryNetworks("unit/id",signal);
    expect(fetch).toHaveBeenLastCalledWith("/api/tenancies/unit%2Fid/recovery-network-preview",expect.objectContaining({method:"GET",signal,cache:"no-store",credentials:"same-origin"}));
    const command={client_request_key:"11111111-1111-4111-8111-111111111111",preview_hash:"a".repeat(64),acknowledged:true};
    await api.repairRecoveryNetworks("unit/id",command,signal);
    expect(fetch).toHaveBeenLastCalledWith("/api/tenancies/unit%2Fid/recovery-network-repair",expect.objectContaining({method:"POST",signal,body:JSON.stringify(command),headers:{"Content-Type":"application/json","X-OTM-Request":"1"}}));
  });
  // Verify routing, abort signals, privacy options and exact grant revisions.
  it("sends same-origin requests without caching or URL factor leakage", async () => {
    const session = {
      workspace_id: "unit-only",
      display_name: "Test",
      expires_at: "2099-01-01",
    };
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => session });
    vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    await api.branding(signal);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/branding",
      expect.objectContaining({
        method: "GET",
        signal,
        credentials: "same-origin",
        cache: "no-store",
      }),
    );
    expect(await api.session(signal)).toEqual(session);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/session",
      expect.objectContaining({
        method: "GET",
        signal,
        credentials: "same-origin",
        cache: "no-store",
        headers: {},
      }),
    );
    await api.signIn("invented-test-factor", "000000");
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/auth/local/sign-in",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json", "X-OTM-Request": "1" },
        body: JSON.stringify({
          username: "recovery-admin",
          password: "invented-test-factor",
          totp_code: "000000",
        }),
      }),
    );
    await api.directory(
      {
        page: 2,
        page_size: 25,
        sort: "email",
        direction: "desc",
        query: "one & two",
      },
      signal,
    );
    expect(fetch.mock.calls.at(-1)![0]).toBe(
      "/api/administrators?page=2&page_size=25&sort=email&direction=desc&query=one+%26+two",
    );
    await api.operations(
      {
        page: 2,
        page_size: 25,
        sort: "updated_at",
        direction: "desc",
        state: "running",
        query: "unit & only",
      },
      signal,
    );
    expect(fetch.mock.calls.at(-1)![0]).toBe(
      "/api/operations?page=2&page_size=25&sort=updated_at&direction=desc&state=running&query=unit+%26+only",
    );
    expect(fetch.mock.calls.at(-1)![1]).toMatchObject({
      method: "GET",
      signal,
    });
    await api.operation("unit/id", signal);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/operations/unit%2Fid",
      expect.objectContaining({ method: "GET", signal }),
    );
    await api.auditHistory(
      {
        page: 2,
        page_size: 25,
        sort: "actor_name",
        direction: "desc",
        category: "operations",
        query: "unit & only",
      },
      signal,
    );
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/audit-history?page=2&page_size=25&sort=actor_name&direction=desc&category=operations&query=unit+%26+only",
      expect.objectContaining({ method: "GET", signal }),
    );
    await api.inspectionSandbox(signal);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/inspection-sandbox",
      expect.objectContaining({ method: "GET", signal }),
    );
    const inspection = {
      client_request_key: "22222222-2222-4222-8222-222222222222",
      tenancy_ocid: "ocid1.tenancy.oc1..synthetic",
    };
    await api.inspect(inspection);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/operations/inspect",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(inspection),
      }),
    );
    expect(Object.keys(JSON.parse(fetch.mock.calls.at(-1)![1].body))).toEqual([
      "client_request_key",
      "tenancy_ocid",
    ]);
    await api.revoke("unit/id", "r2");
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/administrators/unit%2Fid/revoke",
      expect.objectContaining({ body: '{"expected_revision":"r2"}' }),
    );
    await api.activity();
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/session/activity",
      expect.objectContaining({ method: "POST" }),
    );
    fetch.mockResolvedValue({ ok: true, status: 204 });
    expect(await api.logout()).toBeUndefined();
  });

  // Interpret missing sessions only; outages and diagnostic bodies stay separate.
  it.each([401, 403])(
    "maps %s to signed out but preserves server and network failures",
    async (status) => {
      const json = vi.fn();
      const fetch = vi.fn().mockResolvedValue({ ok: false, status, json });
      vi.stubGlobal("fetch", fetch);
      expect(await api.session()).toBeNull();
      expect(json).not.toHaveBeenCalled();
      await expect(api.signIn("test", "000000")).rejects.toBeInstanceOf(
        ApiError,
      );
      fetch.mockResolvedValue({ ok: false, status: 503, json });
      await expect(api.session()).rejects.toMatchObject({
        status: 503,
        message: "Request unavailable",
      });
      fetch.mockRejectedValue(new TypeError("offline"));
      await expect(api.session()).rejects.toThrow("offline");
    },
  );
});

// CSV transport retains the normal POST boundary, omits null GET dates, and never parses private error bodies.
describe("Audit export transport", () => {
  // Successful CSV uses only fixed API endpoints and explicitly forwarded cancellation.
  it("returns CSV bytes and uses same-origin guarded POST controls", async () => {
    const blob = new Blob(["id,at\r\nsynthetic,now"]);
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/csv; charset=utf-8" }),
      blob: async () => blob,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    const query = {
      category: "administration" as const,
      query: "Example",
      sort: "at" as const,
      direction: "desc" as const,
      from_at: "2026-10-01T00:00:00Z",
      to_at: null,
    };
    expect(await api.exportAudit(query, signal)).toBe(blob);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/audit-history/export",
      expect.objectContaining({
        method: "POST",
        signal,
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "X-OTM-Request": "1" },
        body: JSON.stringify(query),
      }),
    );
    await api.auditHistory({ from_at: null, to_at: undefined });
    expect(fetch.mock.calls.at(-1)![0]).toBe("/api/audit-history?");
  });

  // Mapping transport carries a bounded preview fence without actor/workspace or source-policy fields.
  it("uses protected mapping requests and exact preview binding", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    const body: MappingRequest = {
      context: { registry_revision: 0 },
      candidate: {
        root_email: "root@example.test",
        segments: [{ label: "Segment", leader_email: "leader@example.test" }],
      },
    };
    await api.mapping(signal);
    expect(fetch.mock.calls.at(-1)![0]).toBe("/api/organization/mapping");
    await api.previewMapping(body, 2, signal);
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/organization/mapping/preview?page=2",
      expect.objectContaining({
        method: "POST",
        signal,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-OTM-Request": "1" },
        body: JSON.stringify(body),
      }),
    );
    await api.applyMapping({ ...body, preview_token: "a".repeat(64) }, signal);
    expect(fetch.mock.calls.at(-1)![0]).toBe("/api/organization/mapping/apply");
  });

  // Non-CSV successful responses cannot be downloaded as trusted history; failed bodies stay unparsed.
  it.each([413, 503, "text/html", null])(
    "rejects export response %s without disclosing diagnostics",
    async (responseType) => {
      const blob = vi.fn();
      const json = vi.fn();
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: typeof responseType !== "number",
          status: typeof responseType === "number" ? responseType : 200,
          headers: new Headers(
            responseType && typeof responseType === "string"
              ? { "content-type": responseType }
              : {},
          ),
          blob,
          json,
        }),
      );
      await expect(api.exportAudit({})).rejects.toBeInstanceOf(ApiError);
      expect(blob).not.toHaveBeenCalled();
      expect(json).not.toHaveBeenCalled();
    },
  );
});

// Workflow transport pins exact URLs, current-session CSRF headers and closed conflict codes.
it("transports scoped review/tenancy commands and refuses untrusted error codes", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ state: "queued" }) });
  vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  await api.organizationReviews(
    { category: "history", query: "one & two", page: 2 },
    signal,
  );
  expect(fetch.mock.calls.at(-1)![0]).toBe(
    "/api/organization/reviews?category=history&query=one+%26+two&page=2",
  );
  await api.personWorkflow("person/id", "review&id", signal);
  expect(fetch.mock.calls.at(-1)![0]).toBe(
    "/api/organization/people/person%2Fid/workflow?review_id=review%26id",
  );
  await api.personWorkflow("person/id", null, signal);
  expect(fetch.mock.calls.at(-1)![0]).toBe(
    "/api/organization/people/person%2Fid/workflow",
  );
  await api.tenancies({ query: "owner & team", sort: "member_count" }, signal);
  expect(fetch.mock.calls.at(-1)![0]).toBe(
    "/api/tenancies?query=owner+%26+team&sort=member_count",
  );
  await api.tenancy("tenant/id", signal);
  expect(fetch.mock.calls.at(-1)![0]).toBe("/api/tenancies/tenant%2Fid");
  await api.requiredUsers("tenant/id", signal);
  expect(fetch.mock.calls.at(-1)![0]).toBe("/api/tenancies/tenant%2Fid/required-users");
  const body = {
    client_request_key: "key",
    context: {
      applied_version_id: "a",
      proposed_version_id: "b",
      configuration_id: "c",
      registry_revision: 1,
    },
    person_id: "p",
    action: "no_tenancy_required" as const,
  };
  expect(await api.organizationAction(body, signal)).toEqual({
    state: "queued",
  });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/organization/actions",
    expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      signal,
      headers: { "Content-Type": "application/json", "X-OTM-Request": "1" },
      body: JSON.stringify(body),
    }),
  );
  for (const [status, code, expected] of [
    [409, "ORGANIZATION_PREVIEW_CHANGED", "ORGANIZATION_PREVIEW_CHANGED"],
    [400, "<script>private</script>", "WORKFLOW_UNAVAILABLE"],
  ] as const) {
    fetch.mockResolvedValueOnce({
      ok: false,
      status,
      json: async () => ({ code }),
    });
    await expect(api.organizationAction(body)).rejects.toMatchObject({
      status,
      code: expected,
    });
  }
  fetch.mockResolvedValueOnce({ ok: false, status: 403 });
  await expect(api.organizationAction(body)).rejects.toMatchObject({
    status: 403,
  });
});

// Publication transmits only a saved identity/revision, retaining same-origin CSRF and precise strings.
it("scopes paged baseline reads and publishes exact saved revisions", async()=>{
  const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({})});
  vi.stubGlobal("fetch",fetch);
  const signal=new AbortController().signal;
  await api.baselines(signal,{page:2,page_size:25,baseline_id:"unit/id"});
  expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/baselines?page=2&page_size=25&baseline_id=unit%2Fid");
  await api.publishBaseline({baseline_id:"11111111-1111-4111-8111-111111111111",expected_revision:2},signal);
  expect(fetch).toHaveBeenLastCalledWith("/api/configuration/baselines/publish",expect.objectContaining({method:"POST",signal,credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json","X-OTM-Request":"1"},body:JSON.stringify({baseline_id:"11111111-1111-4111-8111-111111111111",expected_revision:2})}));
});


// Override statements stay in bounded JSON bodies; plan reads/reviews retain exact internal identities.
it("routes override and staged-plan transport through authenticated same-origin requests",async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({})});vi.stubGlobal("fetch",fetch);
 const id="11111111-1111-4111-8111-111111111111",key="22222222-2222-4222-8222-222222222222",signal=new AbortController().signal;
 const context={baseline_version_id:key,tenancy_revision:2,configuration_id:null};
 await api.overrideEditor(id,signal);expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/overrides/"+id);
 await api.previewOverride({tenancy_id:id,values:{monthly_budget_override_amount:"500"},context},signal);
 expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/overrides/preview");expect(JSON.parse(fetch.mock.calls.at(-1)![1].body)).toMatchObject({context,values:{monthly_budget_override_amount:"500"}});
 await api.applyOverride({client_request_key:key,tenancy_id:id,overrides:{monthly_budget_override_amount:"500"},override_mode:true,override_context:context,preview_hash:"a".repeat(64)},signal);
 expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/overrides");
 await api.createConfigurationPlan({client_request_key:key,tenancy_id:id},signal);expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/plans");
 await api.configurationPlan(id,signal);expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/plans/"+id);
 await api.reviewConfigurationPlan(id,{expected_revision:2,tenancy_id:key,policy_choice:"keep_override"},signal);expect(fetch.mock.calls.at(-1)![0]).toBe("/api/configuration/plans/"+id+"/reviews");
 expect(fetch.mock.calls.at(-1)![1]).toMatchObject({method:"POST",signal,credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json","X-OTM-Request":"1"}});
});

// Manual reads send only an opaque replay key through the protected child URL.
it("posts a scoped required-user check without browser-selected authority", async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true,status:202,json:async()=>({operation_id:"operation"})});
  vi.stubGlobal("fetch", fetch);
  await api.checkRequiredUsers("tenant/id", {client_request_key:"request-key"});
  expect(fetch).toHaveBeenCalledWith("/api/tenancies/tenant%2Fid/required-users/check", expect.objectContaining({
    method:"POST", cache:"no-store", credentials:"same-origin",
    body:JSON.stringify({client_request_key:"request-key"}),
  }));
});
