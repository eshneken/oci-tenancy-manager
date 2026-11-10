const uuid="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const tenancyRoute=new RegExp(`^/tenancies/${uuid}(?:#required-users)?$`,"i");
const configurationRoute=new RegExp(`^/configuration/drift/${uuid}$`,"i");
const operationRoute=new RegExp(`^/operations/${uuid}$`,"i");
const pageLabels:Record<string,string>={"/tenancies":"Back to tenancies","/organization":"Back to Organization","/organization/drift":"Back to Organization drift","/configuration":"Back to configuration","/configuration/drift":"Back to configuration drift","/audit-history":"Back to audit history"};

// Return only recognized application pages; query input never becomes an external redirect.
export function operationReturn(search=location.search) {
  const values=new URLSearchParams(search).getAll("returnTo");
  const raw=values.length===1?values[0]:"";
  const candidate=raw.trim()===raw?raw:"";
  const label=tenancyRoute.test(candidate)?"Back to tenancy":configurationRoute.test(candidate)?"Back to configuration check":Object.hasOwn(pageLabels,candidate)?pageLabels[candidate]:null;
  return label?{path:candidate,label}:{path:"/operations",label:"Back to operations"};
}

// Store origin in the actual href so reload, history and open-in-new-tab retain the same return.
export function operationHref(id:string|null|undefined,anchor="") {
  if(!id)return "/operations";
  const pathname=location.pathname;
  const source=operationRoute.test(pathname)?operationReturn().path:
    tenancyRoute.test(pathname)?pathname+(location.hash==="#required-users"?location.hash:""):
    configurationRoute.test(pathname)||Object.hasOwn(pageLabels,pathname)?pathname:"/operations";
  const query=source!=="/operations"?"?"+new URLSearchParams({returnTo:source}):"";
  return "/operations/"+encodeURIComponent(id)+query+(anchor?"#"+encodeURIComponent(anchor):"");
}

// Nested pages return to an operation only with its validated origin and check anchor.
export function operationDestination(candidate:string) {
  if(candidate.length>512||candidate.trim()!==candidate)return null;
  const match=candidate.match(new RegExp(`^(/operations/${uuid})(?:\\?([^#]*))?(?:#((?:automation|recovery)-(?:presence|assignment)|recovery-policy|automation-keys))?$`,"i"));
  if(!match)return null;
  if(match[2]!==undefined){
    const params=new URLSearchParams(match[2]);
    if([...params.keys()].length!==1||!params.has("returnTo")||operationReturn("?"+match[2]).path==="/operations")return null;
  }
  return candidate;
}
