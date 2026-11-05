import {useEffect,useRef,useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {api,ApiError} from "./api";

// Select a registered active child using the same paginated search as the existing inventory.
export function OverrideChooser({expired,navigate}:{expired:()=>void;navigate:(path:string)=>void}){
 const [open,setOpen]=useState(false),[search,setSearch]=useState(""),[page,setPage]=useState(1);
 const dialog=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),launch=useRef<HTMLButtonElement>(null);
 const result=useQuery({queryKey:["tenancies","override-chooser",search,page],queryFn:({signal})=>api.tenancies({page,page_size:10,query:search,sort:"name",direction:"asc"},signal),enabled:open,retry:false});
 useEffect(()=>{if(open){dialog.current?.showModal();heading.current?.focus();}else{dialog.current?.close();}},[open]);
 useEffect(()=>{if(result.error instanceof ApiError&&[401,403].includes(result.error.status))expired();},[result.error,expired]);
 // Closing selection leaves assignments and override history unchanged.
 function close(){dialog.current?.close();setOpen(false);launch.current?.focus();}
 return <><button className="button secondary" ref={launch} onClick={()=>setOpen(true)}>Create tenancy override</button><dialog className="workflow-dialog" ref={dialog} aria-labelledby="override-chooser-title" onCancel={event=>{event.preventDefault();close();}}><h2 tabIndex={-1} ref={heading} id="override-chooser-title">Choose a tenancy</h2><label>Search tenancies<input type="search" value={search} onChange={event=>{setSearch(event.target.value);setPage(1);}} maxLength={128}/></label>
 {result.isPending?<p role="status">Loading tenancies…</p>:result.isError?<p role="alert">Tenancies could not be loaded. <button className="button secondary" onClick={()=>void result.refetch()}>Retry</button></p>:<><ul className="override-tenancy-choices">{result.data.items.map(row=><li key={row.id}><span><strong>{row.name}</strong><span className="cell-secondary">{row.owner_name??"Unassigned"} · {row.kind}{row.status!=="active"?" · Finish onboarding first":!row.baseline_version_id?" · Assign a baseline first":row.has_pending_operation?" · Another operation is unfinished":""}</span></span><button className="button secondary" disabled={row.status!=="active"||!row.baseline_version_id||Boolean(row.has_pending_operation)} onClick={()=>{close();navigate("/tenancies/"+row.id+"?override=1");}}>Choose</button></li>)}</ul>{result.data.items.length===0&&<p>No tenancies match this search.</p>}<div className="pagination"><button className="button secondary" disabled={result.data.page<=1} onClick={()=>setPage(value=>value-1)}>Previous</button><span>Page {result.data.page} of {result.data.pages}</span><button className="button secondary" disabled={result.data.page>=result.data.pages} onClick={()=>setPage(value=>value+1)}>Next</button></div></>}
 <div className="dialog-actions"><button className="button secondary" onClick={close}>Cancel</button></div></dialog></>;
}
