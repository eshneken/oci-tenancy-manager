import { expect, type Page, type Locator } from "@playwright/test";
import { resolve } from "node:path";
import {auditSelectPickers} from "./select-audit";

// Reveal the status column before capturing narrow inventory tables; horizontal table scroll is intentional.
async function inventoryEvidence(page:Page,target:Locator,prefix:string){
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});await target.scrollIntoViewIfNeeded();await expect(target).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:resolve(".local-dev/browser",`${prefix}-${width}.png`)});
 }
 await page.setViewportSize({width:1280,height:900});
}

// Admit real read-only work and wait for this exact sealed attempt, without manually refreshing the UI.
async function checkAssigned(page:Page,identifier:string){
 const accepted=page.waitForResponse(response=>response.url().endsWith("/api/configuration/checks")&&response.request().method()==="POST");
 await page.getByRole("button",{name:"Check now",exact:true}).click();const response=await accepted;expect(response.status()).toBe(202);const receipt=await response.json();
 // Reads use the disposable authenticated session; they cannot make the UI refresh itself.
 await expect.poll(async()=>{const read=await page.request.get(`/api/configuration/drift/${identifier}`);expect(read.ok()).toBe(true);const summary=await read.json();return summary.last_operation_id===receipt.operation_id&&!summary.pending_operation_id?summary.state:"pending";},{timeout:20000}).toBe("matching");
 await expect(page.getByText("Matching",{exact:true})).toHaveCount(5,{timeout:20000});await expect(page.getByText(/Check request accepted/)).toHaveCount(0);
}

// One qualified child progresses from unchecked to verified; no fake age/drift controls are exposed.
export async function configurationDrift(page: Page, tenancyName: string) {
 const initialRow=page.getByRole("row").filter({has:page.getByRole("link",{name:tenancyName,exact:true})});
 const unchecked=initialRow.getByRole("link",{name:`Not checked for ${tenancyName}`,exact:true});await expect(unchecked).toBeVisible();await inventoryEvidence(page,unchecked,"configuration-inventory-unchecked");
 await page.getByRole("link",{name:"Configuration drift",exact:true}).click();await expect(page.getByRole("heading",{name:"No confirmed configuration drift"})).toBeVisible();await expect(page.getByText(/Check status: 0 out of date · 1 not checked · 0 unable to verify/)).toBeVisible();
 await page.getByRole("button",{name:"View checks",exact:true}).click();await page.getByRole("searchbox",{name:"Search tenancies"}).fill(tenancyName);
 const checksRow=page.getByRole("row").filter({has:page.getByRole("link",{name:tenancyName,exact:true})});await expect(checksRow.locator(".configuration-status-messages").getByText("Not checked",{exact:true})).toBeVisible();await expect(checksRow.getByText(/Configuration drift ·/)).toHaveCount(0);
 await expect(page.getByRole("combobox",{name:"Check status",exact:true}).getByRole("option",{name:"Check out of date",exact:true})).toHaveCount(1);await auditSelectPickers(page,"configuration-status");
 await page.getByRole("link",{name:tenancyName,exact:true}).click();await expect(page.getByRole("heading",{name:tenancyName,exact:true})).toBeVisible();await page.reload();
 const identifier=page.url().split("/configuration/drift/")[1].split("?")[0];await checkAssigned(page,identifier);
 // Rechecking an already matching assignment must finish automatically, including clearing the new acknowledgement.
 await checkAssigned(page,identifier);
 for(const width of [1280,390,320]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:resolve(".local-dev/browser",`configuration-check-${width}.png`),fullPage:true});}
 await page.setViewportSize({width:1280,height:900});await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 const finished=page.getByRole("row").filter({has:page.getByRole("link",{name:tenancyName,exact:true})});
 for(const label of ["Not checked","Unable to verify","Check out of date","Checking","Configuration drift"])await expect(finished.getByRole("link",{name:new RegExp(label)})).toHaveCount(0);
 await inventoryEvidence(page,finished.locator("td").last(),"configuration-inventory-matching");
 await page.getByRole("link",{name:"Configuration drift",exact:true}).click();await expect(page.getByRole("heading",{name:"No confirmed configuration drift"})).toBeVisible();
}
