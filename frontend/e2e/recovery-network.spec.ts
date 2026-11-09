import {test,expect} from "@playwright/test";
import {createHmac} from "node:crypto";
import {resolve} from "node:path";

// Disposable fixture factors stay in memory and never enter URLs, browser storage or traces.
function authenticatorCode(){
 const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
 const bits=[...process.env.OTM_E2E_SEED!].map(c=>alphabet.indexOf(c).toString(2).padStart(5,"0")).join("");
 const key=Buffer.from(bits.match(/.{8}/g)!.map(byte=>parseInt(byte,2))),counter=Buffer.alloc(8);
 counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
 const digest=createHmac("sha1",key).update(counter).digest(),offset=digest[19]&15;
 return ((digest.readUInt32BE(offset)&0x7fffffff)%1000000).toString().padStart(6,"0");
}

// Prove consent, safe preview, native dispatch, independent readback and persisted reload behavior.
test("repair owned recovery networks through the real API and native worker",async({page})=>{
 const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
 await page.goto("/login");
 await page.getByLabel("Password",{exact:true}).fill(process.env.OTM_E2E_PASSWORD!);
 await page.getByLabel("Authenticator code",{exact:true}).fill(authenticatorCode());
 await page.getByRole("button",{name:"Sign in",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Tenancies",exact:true})).toBeVisible();
 const id=process.env.OTM_E2E_TENANCY_ID!;
 await page.goto(`/tenancies/${id}`);
 await page.getByRole("button",{name:"Refresh user data",exact:true}).click();
 const recovery=page.locator(".required-user-card").filter({has:page.getByRole("heading",{name:"Recovery user",exact:true})});
 await expect(recovery.getByText("Policy drift",{exact:true})).toBeVisible({timeout:20000});
 await recovery.getByRole("button",{name:"Repair approved networks",exact:true}).click();
 const modal=page.getByRole("dialog");
 await expect(modal.getByText("Configured replacement",{exact:true})).toBeVisible();
 await modal.getByRole("button",{name:"Cancel",exact:true}).click();
 await expect(recovery.getByRole("button",{name:"Repair approved networks",exact:true})).toBeFocused();
 await recovery.getByRole("button",{name:"Repair approved networks",exact:true}).click();
 await expect(modal.getByText("Configured replacement",{exact:true})).toBeVisible();
 const consent=modal.getByRole("checkbox"),submit=modal.getByRole("button",{name:"Confirm network repair",exact:true});
 await expect(consent).not.toBeChecked();await expect(submit).toBeDisabled();
 const attempts:string[]=[];
 page.on("request",request=>{if(request.method()==="POST"&&request.url().endsWith("/recovery-network-repair"))attempts.push(request.url());});
 await consent.focus();await page.keyboard.press("Enter");
 await modal.locator("form").evaluate(form=>form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));
 expect(attempts).toHaveLength(0);
 const rejected=await page.evaluate(async identifier=>{
   const preview=await(await fetch(`/api/tenancies/${identifier}/recovery-network-preview`)).json();
   const response=await fetch(`/api/tenancies/${identifier}/recovery-network-repair`,{method:"POST",headers:{"Content-Type":"application/json","X-OTM-Request":"1"},body:JSON.stringify({client_request_key:crypto.randomUUID(),preview_hash:preview.preview_hash,acknowledged:false})});
   return response.status;
 },id);
 expect(rejected).toBe(409);
 for(const width of [1280,1024,768,390,320]){
   await page.setViewportSize({width,height:900});
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await expect(submit).toBeDisabled();
   await modal.evaluate(element=>{element.scrollTop=0;});
   await modal.getByRole("heading",{name:"Repair approved recovery networks",exact:true}).scrollIntoViewIfNeeded();
   const box=await modal.boundingBox();expect(box).not.toBeNull();
   expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);
   await page.screenshot({path:resolve(".local-dev/browser",`recovery-network-preview-${width}.png`),fullPage:false});
   await submit.scrollIntoViewIfNeeded();await expect(submit).toBeVisible();
   await page.screenshot({path:resolve(".local-dev/browser",`recovery-network-actions-${width}.png`),fullPage:false});
 }
 await page.setViewportSize({width:1280,height:900});
 await consent.check();await submit.click();
 await expect(modal).not.toBeVisible();
 await expect(recovery.getByRole("status")).toBeFocused();
 await expect(recovery.getByText(/Approved networks verified in simulation/)).toBeVisible({timeout:20000});
 await expect(recovery.getByText("Policy drift",{exact:true})).toHaveCount(0,{timeout:20000});
 await expect(recovery.getByRole("button",{name:"Repair approved networks",exact:true})).toHaveCount(0);
 await page.reload();
 await expect(recovery.getByText("Policy drift",{exact:true})).toHaveCount(0);
 await expect(recovery.locator(":scope > .required-user-facts").getByText("Verified in simulation",{exact:true})).toHaveCount(2);
 expect(errors).toEqual([]);
});
