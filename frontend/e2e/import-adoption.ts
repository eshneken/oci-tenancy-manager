import {expect,type Page} from "@playwright/test";
import {resolve} from "node:path";

// Adopt observed humans through the actual API/worker, preserving shared scopes and consent guards.
export async function existingUserAdoption(page:Page,memberName="New Employee"){
 await page.getByRole("link",{name:"Organization",exact:true}).click();
 await page.getByRole("button",{name:"Leader One",exact:true}).click();
 const modal=page.getByRole("dialog");
 await modal.getByRole("combobox",{name:"Action",exact:true}).selectOption("import_tenancy");
 await modal.getByRole("combobox",{name:"Tenancy type",exact:true}).selectOption("shared");
 await modal.getByLabel("Simulated tenancy OCID",{exact:true}).fill("ocid1.tenancy.oc1..otmsimadoptbrowser");
 await modal.getByRole("button",{name:"Import tenancy",exact:true}).click();
 await modal.getByRole("link",{name:"View operation",exact:true}).click();
 const panel=page.getByRole("region",{name:"Administrator action required",exact:true});
 await panel.getByRole("button",{name:"Use simulated handoff",exact:true}).click();
 await panel.getByRole("button",{name:"Verify handoff",exact:true}).click();
 const review=page.getByRole("region",{name:"Ready for your review",exact:true});
 const accounts=review.getByRole("region",{name:"Existing accounts to adopt",exact:true});
 await expect(accounts.getByRole("combobox")).toHaveCount(3,{timeout:20000});
 const selects=accounts.getByRole("combobox");
 const ownerChoice=await selects.nth(0).locator("option").filter({hasText:/Leader One/}).getAttribute("value");
 const member=await selects.nth(2).locator("option").filter({hasText:memberName}).getAttribute("value");
 await selects.nth(0).selectOption(ownerChoice!);await selects.nth(2).selectOption(member!);
 const consent=review.getByRole("checkbox",{name:/I reviewed the selected identities/});
 const cleanup=review.getByRole("checkbox",{name:/I confirm the exact temporary accounts/});
 await cleanup.check();
 await expect(review.getByRole("button",{name:"Start setup",exact:true})).toBeDisabled();
 await consent.check();
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,className:el.className,width:el.getBoundingClientRect().width,right:el.getBoundingClientRect().right})).slice(0,12)}));
  await review.screenshot({path:resolve(".local-dev/browser",`import-adoption-${width}.png`)});
  expect(layout.scroll,JSON.stringify(layout)).toBeLessThanOrEqual(layout.width);
 }
 await page.setViewportSize({width:1280,height:900});
 await review.getByRole("button",{name:"Refresh existing users",exact:true}).click();
 await expect(consent).not.toBeChecked({timeout:20000});
 await expect(selects.nth(0)).toHaveValue("");
 await expect(review.getByRole("button",{name:"Start setup",exact:true})).toBeDisabled();
 await selects.nth(0).selectOption(ownerChoice!);await selects.nth(2).selectOption(member!);
 await cleanup.check();await consent.check();
 await review.getByRole("button",{name:"Start setup",exact:true}).click();
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
 const operationId=new URL(page.url()).pathname.split("/").at(-1)!;
 const data=await(await page.request.get("/api/tenancy-onboarding/"+operationId)).json();
 await page.goto("/tenancies/"+data.tenancy_id);
 await expect(page.getByText(/Adopted existing identity/)).toHaveCount(2);
 await page.getByRole("button",{name:"Refresh user data",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Adopted member access",exact:true})).toBeVisible();
 await expect(page.locator(".imported-access").getByText("Verified in simulation",{exact:true})).toBeVisible({timeout:20000});
 // Exercise root membership and owner promotion through the same restricted API/native worker.
 await expect(page.getByText(/Normal Atlas lifecycle|Existing scoped permissions/)).toHaveCount(0);
 const childPath=new URL(page.url()).pathname;
 const before=await(await page.request.get("/api"+childPath)).json();
 await page.getByRole("link",{name:"Organization",exact:true}).click();
 await page.getByRole("button",{name:"Leader Two",exact:true}).click();
 const join=page.getByRole("dialog");
 await join.getByRole("combobox",{name:"Action",exact:true}).selectOption("join_shared");
 await join.getByRole("combobox",{name:"Shared tenancy",exact:true}).selectOption(data.tenancy_id);
 await join.getByRole("combobox",{name:"Compartment assignment",exact:true}).selectOption("existing");
 await join.getByRole("combobox",{name:"Existing compartment",exact:true}).selectOption(before.tenancy.tenancy_ocid);
 await expect(join.getByText(/Root access covers the entire tenancy/)).toBeVisible();
 await capturePromotion(page,"root-member");
 await join.getByRole("button",{name:"Add to shared tenancy",exact:true}).click();
 await join.getByRole("link",{name:"View operation",exact:true}).click();
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
 await page.goto(childPath);
 const recipient=before.people.find((p:{name:string})=>p.name===memberName);
 const original=before.memberships.find((m:{person_id:string})=>m.person_id===recipient.id);
 await page.getByRole("button",{name:"Transfer owner",exact:true}).click();
 const transfer=page.getByRole("dialog");
 await transfer.getByRole("combobox",{name:"New owner",exact:true}).selectOption(recipient.id);
 await transfer.getByRole("combobox",{name:"Former owner",exact:true}).selectOption("keep_member");
 await expect(transfer.getByText(/The new owner receives tenancy-root resource administration/)).toBeVisible();
 await transfer.getByRole("checkbox",{name:/I reviewed the ownership change and retained access/}).check();
 await capturePromotion(page,"owner-root-promotion");
 await transfer.getByRole("button",{name:"Transfer tenancy ownership",exact:true}).click();
 await transfer.getByRole("link",{name:"View operation",exact:true}).click();
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
 await page.goto(childPath);
 const after=await(await page.request.get("/api"+childPath)).json();
 const owner=after.memberships.find((m:{role:string;status:string})=>m.role==="owner"&&m.status==="active");
 expect(owner.person_id).toBe(recipient.id);expect(owner.compartment_ocid).toBe(after.tenancy.tenancy_ocid);
 expect(owner.imported_access.identity).toEqual(original.imported_access.identity);
 expect(owner.imported_access.expected_owner.identity.administrator).toBe(true);
 await page.getByRole("button",{name:"Refresh user data",exact:true}).click();
 await expect(page.locator(".imported-access").getByText("Verified in simulation",{exact:true})).toBeVisible({timeout:20000});
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole("region",{name:"Tenancy membership",exact:true}).screenshot({path:resolve(".local-dev/browser",`import-membership-${width}.png`)});
  await page.locator(".imported-access").screenshot({path:resolve(".local-dev/browser",`import-access-${width}.png`)});
 }
 await page.setViewportSize({width:1280,height:900});

}

// Inspect both the grant warning and final controls inside the owned responsive dialog.
async function capturePromotion(page:Page,name:string){
 const modal=page.getByRole("dialog");
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await modal.getByRole("combobox",{name:name==="root-member"?"Existing compartment":"New owner",exact:true}).scrollIntoViewIfNeeded();
  await modal.screenshot({path:resolve(".local-dev/browser",`${name}-${width}.png`)});
 }
 await page.setViewportSize({width:1280,height:900});
}
