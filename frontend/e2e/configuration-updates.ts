import {expect,type Page} from "@playwright/test";
import {resolve} from "node:path";

// Exercise contextual recipe navigation plus individual/bulk updates against real API/SQL/native jobs.
export async function configurationUpdates(page:Page,firstName:string){
 await page.getByRole("link",{name:firstName,exact:true}).click();
 const tenancyUrl=page.url();
 await page.getByRole("link",{name:"Baseline v1",exact:true}).first().click();
 const back=page.getByRole("link",{name:/Back to tenancy/});
 const heading=page.getByRole("heading",{name:"Published baseline v1",exact:true});
 expect((await heading.boundingBox())!.y-((await back.boundingBox())!.y+(await back.boundingBox())!.height)).toBeGreaterThanOrEqual(16);
 await back.click();expect(page.url()).toBe(tenancyUrl);
 await alignActions(page);
 await page.getByRole("button",{name:"Update to baseline v2",exact:true}).click();
 const dialog=page.getByRole("dialog",{name:"Update tenancy baseline",exact:true});
 await expect(dialog.getByText("1",{exact:true})).toBeVisible();
 await dialog.getByRole("link",{name:"Baseline v2",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Published baseline v2",exact:true})).toBeFocused();
 await page.getByRole("link",{name:/Back to baseline update/}).click();
 await expect(dialog.getByRole("link",{name:"Baseline v2",exact:true})).toBeFocused();
 await alignActions(page);
 await capture(page,"individual-baseline-preview");
 const accepted=page.waitForResponse(r=>r.url().endsWith("/api/configuration/updates")&&r.request().method()==="POST");
 await dialog.getByRole("button",{name:"Start update",exact:true}).click();
 expect((await accepted).status()).toBe(202);
 await expect(page.getByRole("region",{name:"Tenancy baseline update",exact:true})).toHaveCount(0,{timeout:20000});
 await expect(page.getByRole("link",{name:"Baseline v2",exact:true})).toHaveCount(2);
 await expect(page.getByRole("heading",{level:1})).toBeFocused();
 await capture(page,"individual-baseline-verified");
 await page.getByRole("link",{name:"Configuration",exact:true}).click();
 await page.getByRole("button",{name:"New baseline",exact:true}).click();
 await page.getByLabel("Monthly amount",{exact:true}).fill("900");
 await page.getByRole("button",{name:"Save draft",exact:true}).click();
 await expect(page.getByRole("status").filter({hasText:"Baseline draft saved."})).toHaveText("Baseline draft saved.");
 await page.getByRole("button",{name:"Publish",exact:true}).click();
 await page.getByRole("button",{name:"Publish baseline",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Published baseline v3",exact:true})).toBeVisible();
 await page.getByRole("link",{name:/Back to baselines/}).click();
 await alignActions(page);
 await page.getByRole("button",{name:"Update existing tenancies",exact:true}).click();
 const batch=page.getByRole("dialog",{name:"Update existing tenancies",exact:true});
 await expect(batch.getByText("2",{exact:true})).toBeVisible();
 await capture(page,"bulk-baseline-preview");
 await batch.getByRole("button",{name:"Start update",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Baseline v3 · Verified in simulation",exact:true})).toBeVisible({timeout:20000});
 await expect(page.getByRole("region",{name:"Baseline update progress",exact:true}).getByRole("status")).toContainText("2 of 2 tenancies verified");
 await expect(page.getByRole("button",{name:"Refresh progress",exact:true})).toHaveCount(0);
 await capture(page,"bulk-baseline-verified");
 const operationUrl=await page.getByRole("link",{name:"View operation history",exact:true}).getAttribute("href");
 await page.reload();
 await expect(page.getByRole("heading",{name:"Baseline v3 · Verified in simulation",exact:true})).toBeVisible();
 await page.getByRole("button",{name:"Acknowledge",exact:true}).click();
 await expect(page.getByRole("region",{name:"Baseline update progress",exact:true})).toHaveCount(0);
 await expect(page.getByText("No active tenancies need updating.",{exact:true})).toHaveClass("configuration-current");
 await page.reload();
 await expect(page.getByRole("button",{name:"Acknowledge",exact:true})).toHaveCount(0);
 await expect(page.getByText("No active tenancies need updating.",{exact:true})).toHaveClass("configuration-current");
 await capture(page,"bulk-baseline-acknowledged");
 await page.goto(operationUrl!);
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible();
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 await expect(page.getByRole("table").getByRole("link",{name:"Baseline v3",exact:true})).toHaveCount(2);
 await capture(page,"tenancy-baseline-status");
 await page.getByRole("table").getByRole("link",{name:"Baseline v3",exact:true}).first().click();
 await page.getByRole("link",{name:/Back to tenancies/}).click();
 await expect(page.getByRole("heading",{level:1,name:"Tenancies",exact:true})).toBeVisible();
 await page.getByRole("link",{name:"Audit history",exact:true}).click();
 await page.getByRole("combobox",{name:"Category",exact:true}).selectOption("operations");
 await expect(page.getByRole("table").getByRole("link",{name:firstName,exact:true}).first()).toBeVisible();
 await capture(page,"audit-lifecycle-resources");
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
}

// Save only disposable synthetic pages, checking real narrow viewport geometry on each state.
async function capture(page:Page,name:string){
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:resolve(".local-dev/browser",`${name}-${width}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1280,height:900});
}


// Compare actual action/description centers and eliminate heading margins from horizontal rows.
async function alignActions(page:Page){
 for(const width of [1280,900]){
  await page.setViewportSize({width,height:900});
  for(const toolbar of await page.locator(".configuration-toolbar").all()){
   const button=toolbar.getByRole("button");
   if(await button.count()!==1)continue;
   const text=toolbar.locator(":scope > p,:scope > h3");
   if(await text.count()!==1)continue;
   const a=await text.boundingBox(),b=await button.boundingBox();
   if(a&&b&&b.x>=a.x+a.width)expect(Math.abs(a.y+a.height/2-b.y-b.height/2)).toBeLessThanOrEqual(1);
  }
 }
 await page.setViewportSize({width:1280,height:900});
}
