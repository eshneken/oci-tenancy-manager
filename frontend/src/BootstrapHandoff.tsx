import {useEffect, useId, useLayoutEffect, useRef, useState} from "react";

// Keep actionable OCI inputs visible; only the public half of the managed key is copyable.
export function BootstrapHandoff({username, publicKey, canGenerate, busy, generate}: {
 username:string; publicKey:string|null; canGenerate:boolean; busy:boolean; generate:()=>void;
}) {
 const id=useId();
 const textarea=useRef<HTMLTextAreaElement>(null);
 // Fit the complete PEM after wrapping changes; watch width only to avoid height-observer loops.
 useLayoutEffect(()=>{
  const field=textarea.current;if(!field)return;
  // Include the borders when fitting wrapped content without changing the read-only value.
  function fit(){
   field!.style.height="auto";
   field!.style.height=`${field!.scrollHeight+field!.offsetHeight-field!.clientHeight}px`;
  }
  fit();let width=field.getBoundingClientRect().width;
  const observer=new ResizeObserver(entries=>{
   const next=entries[0]?.contentRect.width;
   if(next!==undefined&&next!==width){width=next;fit();}
  });
  observer.observe(field);return()=>observer.disconnect();
 },[publicKey]);
 const [copied,setCopied]=useState("");const [error,setError]=useState("");
 useEffect(()=>{setCopied("");setError("");},[username,publicKey]);
 // Copy exact field bytes, retaining labelled read-only controls when clipboard access is blocked.
 async function copy(field:string, value:string) {
  try {await navigator.clipboard.writeText(value);setCopied(field);setError("");}
  catch {setError("Clipboard access is unavailable. Select the field text and copy it manually.");}
 }
 return <section className="bootstrap-handoff" aria-labelledby={id+"-heading"}>
  <h3 id={id+"-heading"}>Enter in OCI</h3>
  <p className="muted">Use this username for the temporary bootstrap user, then add this public key to its API keys.</p>
  <label htmlFor={id+"-username"}>Bootstrap username</label>
  <div className="bootstrap-copy-row"><input id={id+"-username"} readOnly value={username}/><button type="button" className="button secondary" onClick={()=>void copy("username",username)}>Copy username</button></div>
  <label htmlFor={id+"-public"}>Public API key (PEM)</label>
  {publicKey ? <div className="bootstrap-copy-row bootstrap-public-row"><textarea ref={textarea} id={id+"-public"} readOnly rows={9} spellCheck={false} value={publicKey}/><button type="button" className="button secondary" onClick={()=>void copy("public key",publicKey)}>Copy public key</button></div> : <div className="notice"><p>No bootstrap public key has been prepared for this operation.</p>{canGenerate&&<button type="button" className="button secondary" disabled={busy} onClick={generate}>{busy?"Preparing key…":"Generate bootstrap key"}</button>}</div>}
  <p className="muted">The private key stays in application custody and is never shown here.</p>
  {copied&&<p role="status">Copied {copied}.</p>}{error&&<p className="alert" role="alert">{error}</p>}
 </section>;
}
