import {baselineHref,baselineReturn} from "../src/baselineNavigation";
import {expect,it} from "vitest";
import {operationHref,operationReturn,operationDestination} from "../src/operationNavigation";

const id="11111111-1111-4111-8111-111111111111",child="22222222-2222-4222-8222-222222222222";

// Actual hrefs carry safe tenancy context and retain target check fragments across reloads.
it("preserves tenancy origin in operation URLs and their return links",()=>{
 history.replaceState(null,"",`/tenancies/${child}#required-users`);
 const href=operationHref(id,"recovery-policy");const url=new URL(href,location.origin);
 expect(url.searchParams.get("returnTo")).toBe(`/tenancies/${child}#required-users`);
 expect(url.hash).toBe("#recovery-policy");history.replaceState(null,"",href);
 expect(operationReturn()).toEqual({path:`/tenancies/${child}#required-users`,label:"Back to tenancy"});
 expect(operationHref(id)).toBe(`/operations/${id}?${new URLSearchParams({returnTo:`/tenancies/${child}#required-users`})}`);
});

// Supported entry pages have bounded backlinks; the Operations directory clears stale context.
it.each([
 ["/tenancies","Back to tenancies"],["/organization","Back to Organization"],
 ["/organization/drift","Back to Organization drift"],["/configuration","Back to configuration"],
 ["/configuration/drift","Back to configuration drift"],["/audit-history","Back to audit history"],
 [`/configuration/drift/${child}`,"Back to configuration check"],
 ["/operations","Back to operations"],["/administrators","Back to operations"],
])("returns to %s with its proper label",(path,label)=>{
 history.replaceState(null,"",path+"?returnTo="+encodeURIComponent(`/tenancies/${child}`));
 const url=new URL(operationHref(id),location.origin);
 expect(operationReturn(url.search)).toEqual({path:label==="Back to operations"?"/operations":path,label});
});

// Direct and hostile/ambiguous inputs never become arbitrary return navigation.
it.each(["https://example.test/","//example.test/","javascript:alert(1)","/tenancies/../administrators","/tenancies/not-a-uuid","/tenancies/"+child+"?override=1","constructor","__proto__","/tenancies/"+child+"\n",""])("rejects unsafe return context %s",path=>{
 expect(operationReturn("?"+new URLSearchParams({returnTo:path}))).toEqual({path:"/operations",label:"Back to operations"});
});

// Missing IDs and duplicate origin parameters use conservative list fallbacks.
it("does not manufacture detail routes or accept duplicate origins",()=>{
 expect(operationHref(null)).toBe("/operations");expect(operationHref(undefined)).toBe("/operations");
 expect(operationReturn("?returnTo=%2Ftenancies&returnTo=%2Faudit-history").path).toBe("/operations");
});

// Intermediate pages retain the originating operation URL rather than dropping its tenancy context.
it("validates nested operation returns while retaining the tenancy origin",()=>{
 history.replaceState(null,"",`/tenancies/${child}`);
 const href=operationHref(id,"automation-presence");expect(operationDestination(href)).toBe(href);
 const baseline=baselineHref(id,href);
 expect(baselineReturn(new URL(baseline,location.origin).search)).toEqual({path:href,label:"Back to operation"});
 for(const invalid of [`/operations/${id}?returnTo=https%3A%2F%2Fexample.test`,`/operations/${id}?other=1`,`/operations/${id}?returnTo=%2Ftenancies&returnTo=%2Faudit-history`,`//example.test/operations/${id}`,`/operations/${id}#unrecognized`,`/operations/${id}#automation-policy`,`/operations/${id}\n`])expect(operationDestination(invalid)).toBeNull();
 expect(operationDestination("x".repeat(513))).toBeNull();
});
