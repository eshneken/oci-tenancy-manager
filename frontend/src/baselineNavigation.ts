import {operationDestination} from "./operationNavigation";
// Permit only known local destinations; query parameters cannot create an external return redirect.
export function baselineReturn(search=location.search) {
  const path=new URLSearchParams(search).get("returnTo")??"/configuration";
  const uuid="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  const label=new RegExp(`^/configuration/drift/${uuid}$`,"i").test(path)?"Back to configuration check"
    :new RegExp(`^/tenancies/${uuid}$`,"i").test(path)?"Back to tenancy"
    :operationDestination(path)?"Back to operation"
    :path==="/tenancies"?"Back to tenancies":path==="/organization"?"Back to Organization":path==="/organization/drift"?"Back to Organization drift":path==="/audit-history"?"Back to audit history":null;
  return label?{path,label}:{path:"/configuration",label:"Back to baselines"};
}

// Carry the initiating page through read-only baseline detail and historical-parent links.
export function baselineHref(id:string,returnTo="/configuration") {
  const safe=baselineReturn("?"+new URLSearchParams({returnTo}));
  return "/configuration?"+new URLSearchParams({baseline:id,...(safe.path!=="/configuration"?{returnTo:safe.path}:{})});
}
