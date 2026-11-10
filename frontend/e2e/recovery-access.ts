import {expect,type Page} from "@playwright/test";
import {resolve} from "node:path";

// Validate real disclosure without ever recording a password in screenshots, traces or logs.
export async function recoveryAccess(page:Page){
 const users=page.getByRole("region",{name:"Required users",exact:true});
 const refreshed=page.waitForResponse(response=>response.request().method()==="POST"&&response.url().endsWith("/required-users/check"));
 await users.getByRole("button",{name:"Refresh user data",exact:true}).click();await refreshed;
 await expect(users.getByText("Present",{exact:true})).toHaveCount(2,{timeout:20000});
 const launcher=users.getByRole("button",{name:"Request password",exact:true});
 await expect(users.getByText("Ready",{exact:true})).toBeVisible({timeout:10000});
 await launcher.click();const modal=page.getByRole("dialog"),submit=modal.getByRole("button",{name:"Get password",exact:true}),consent=modal.getByRole("checkbox");
 await expect(consent).not.toBeChecked();await expect(submit).toBeDisabled();
 const attempts:string[]=[];
 const track=(request:import("@playwright/test").Request)=>{if(request.method()==="POST"&&request.url().endsWith("/administrator-access/password"))attempts.push(request.url());};page.on("request",track);
 await consent.focus();await page.keyboard.press("Enter");await modal.locator("form").evaluate(form=>form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));expect(attempts).toHaveLength(0);
 for(const width of [1280,1024,768,390,320]){
  await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await modal.getByRole("heading",{name:"Administrator access",exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:resolve(".local-dev/browser",`recovery-access-consent-${width}.png`),fullPage:false});
  await submit.scrollIntoViewIfNeeded();await expect(submit).toBeVisible();
 }
 await page.setViewportSize({width:1280,height:900});
 await consent.check();const disclosure=page.waitForResponse(response=>response.request().method()==="POST"&&response.url().endsWith("/administrator-access/password"));await submit.click();
 const response=await disclosure;expect(response.status()).toBe(200);expect(response.headers()["cache-control"]).toBe("no-store");
 const secret=modal.getByLabel("Recovery password",{exact:true});await expect(secret).toBeVisible();await expect(secret).toHaveAttribute("type","password");await expect(secret).toBeFocused();
 // Check secret lifetime using booleans only, never include the value in assertion diagnostics.
 expect(await secret.evaluate((element:HTMLInputElement)=>element.value.length>=32)).toBe(true);
 await modal.getByRole("button",{name:"Show password",exact:true}).click();await expect(secret).toHaveAttribute("type","text");
 await modal.getByRole("button",{name:"Hide password",exact:true}).click();
 const before=await page.evaluate(async()=>{const response=await fetch(location.pathname.replace("/tenancies/","/api/tenancies/")+"/administrator-access");const data=await response.json();return{first:data.first_disclosure_at,due:data.rotation_due_at};});
 await modal.getByRole("button",{name:"Close",exact:true}).click();await expect(modal).not.toBeVisible();await expect(launcher).toBeFocused();
 await page.reload();await launcher.click();await expect(modal.getByLabel("Recovery password",{exact:true})).toHaveCount(0);await expect(consent).not.toBeChecked();await consent.check();await submit.click();await expect(secret).toBeVisible();
 const after=await page.evaluate(async()=>{const response=await fetch(location.pathname.replace("/tenancies/","/api/tenancies/")+"/administrator-access");const data=await response.json();return{first:data.first_disclosure_at,due:data.rotation_due_at};});expect(after).toEqual(before);
 const operationLink=modal.getByRole("link",{name:"View password operation",exact:true});
 const operationHref=await operationLink.getAttribute("href");const operationId=new URL(operationHref!,page.url()).pathname.split("/").at(-1)!;
 await operationLink.click();page.off("request",track);
 await expect(page).toHaveURL(new URL(operationHref!,page.url()).href);
 await expect(page.getByRole("link",{name:"← Back to tenancy",exact:true})).toBeVisible();
 const progress=page.getByRole("region",{name:"Password rotation",exact:true});
 await expect(progress.getByText("Scheduled",{exact:true})).toBeVisible();
 await expect(progress.locator("time").first()).toHaveAttribute("datetime",before.first);
 await expect(progress.locator("time").nth(1)).toHaveAttribute("datetime",before.due);
 await expect(progress.locator("dt").filter({hasText:"Authorized requests"}).locator("+ dd")).toHaveText("2");
 await expect(page.getByLabel("Recovery password",{exact:true})).toHaveCount(0);
 for(const width of [1280,1024,390,320]){
  await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await progress.screenshot({path:resolve(".local-dev/browser",`recovery-password-progress-${width}.png`)});
 }
 await page.setViewportSize({width:1280,height:900});
 await progress.getByRole("link",{name:"Open tenancy",exact:true}).click();await expect(launcher).toBeVisible();
 await expect.poll(async()=>{const detail=await(await page.request.get("/api/operations/"+operationId)).json();return detail.notifications?.some((notice:{event:string;state:string})=>notice.event==="recovery_password_requested"&&notice.state==="sent");},{timeout:10000}).toBe(true);
 await page.getByRole("link",{name:"Audit history",exact:true}).click();await expect(page.getByRole("table").getByText("Recovery password requested",{exact:true}).first()).toBeVisible();
}
