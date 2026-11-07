import {expect,type Page} from "@playwright/test";

// Exercise both retention directions without changing any existing user's OCI identity or scope.
export async function keepOwnershipRoundTrip(page:Page,sharedName:string){
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 await page.getByRole("link",{name:sharedName,exact:true}).click();
 const path=new URL(page.url()).pathname;
 const read=async()=>{const response=await page.request.get("/api"+path);expect(response.ok()).toBe(true);return response.json();};
 const original=await read();
 const bindings=original.memberships.filter((a:{status:string})=>a.status==="active");
 const originalOwner=original.tenancy.owner_person_id;
 const member=bindings.find((a:{person_id:string})=>a.person_id!==originalOwner).person_id;
 for(const recipient of [member,originalOwner]){
  await page.getByRole("button",{name:"Transfer owner",exact:true}).click();
  const modal=page.getByRole("dialog");
  await modal.getByRole("combobox",{name:"New owner",exact:true}).selectOption(recipient);
  const disposition=modal.getByRole("combobox",{name:"Former owner",exact:true});
  await expect(disposition).toHaveValue("");
  await disposition.selectOption("keep_member");
  await expect(modal.getByText(/including any administrator access/)).toBeVisible();
  await expect(modal.getByRole("checkbox",{name:/I acknowledge the consequences/})).toHaveCount(0);
  await modal.getByRole("checkbox",{name:/I reviewed the ownership change and retained access/}).check();
  await capture(page,"transfer-keep");
  const accepted=page.waitForResponse(r=>r.url().endsWith("/api/organization/actions")&&r.request().method()==="POST");
  await modal.getByRole("button",{name:"Transfer tenancy ownership",exact:true}).click();
  const response=await accepted;expect(response.status()).toBe(202);
  expect(response.request().postDataJSON().former_owner_disposition).toBe("keep_member");
  expect(response.request().postDataJSON().confirm_destructive).toBeUndefined();
  await modal.getByRole("link",{name:"View operation",exact:true}).click();
  await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
  await page.goto(path);
  const after=await read();expect(after.tenancy.owner_person_id).toBe(recipient);
  const active=after.memberships.filter((a:{status:string})=>a.status==="active");expect(active).toHaveLength(2);
  for(const before of bindings){
   const next=active.find((a:{person_id:string})=>a.person_id===before.person_id);
   expect(next.user_ocid).toBe(before.user_ocid);expect(next.compartment_ocid).toBe(before.compartment_ocid);
  }
 }
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
}

// Verify explicit access removal after transfer and retain visible unknown-scope manual obligations.
export async function removeFormerOwner(page:Page){
 const path=new URL(page.url()).pathname;
 const before=await (await page.request.get("/api"+path)).json();
 await page.getByRole("button",{name:"Transfer owner",exact:true}).click();
 const modal=page.getByRole("dialog");
 await modal.getByRole("combobox",{name:"New owner",exact:true}).selectOption({label:"New Employee · new@example.test"});
 const disposition=modal.getByRole("combobox",{name:"Former owner",exact:true});
 await disposition.selectOption("remove");
 const consent=modal.getByRole("checkbox",{name:/I acknowledge the consequences/});
 const submit=modal.getByRole("button",{name:"Transfer tenancy ownership",exact:true});
 await expect(submit).toBeDisabled();
 await modal.locator("form").evaluate(form=>form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));
 await expect(modal.getByText("Confirm former-owner access removal",{exact:true})).toBeVisible();
 const help=modal.locator("details.operator-instructions");await expect(help).not.toHaveAttribute("open");
 await help.locator(":scope > summary").focus();await page.keyboard.press("Enter");
 await expect(modal.getByText(/If a dedicated compartment was created/)).toBeVisible();
 await expect(modal.getByText(/Review additional users, API keys/)).toBeVisible();
 await modal.getByRole("checkbox",{name:/I reviewed the shared tenancy impact/}).check();
 await consent.check();
 await capture(page,"transfer-remove-cleanup-expanded");
 await disposition.selectOption("keep_member");await disposition.selectOption("remove");
 await expect(consent).not.toBeChecked();await expect(submit).toBeDisabled();
 await capture(page,"transfer-remove");
 await modal.getByRole("checkbox",{name:/I reviewed the shared tenancy impact/}).check();await consent.check();
 const accepted=page.waitForResponse(r=>r.url().endsWith("/api/organization/actions")&&r.request().method()==="POST");
 await submit.click();expect((await accepted).status()).toBe(202);
 await modal.getByRole("link",{name:"View operation",exact:true}).click();
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
 await expect(page.getByRole("heading",{name:"Delete tenancy user",exact:true})).toBeVisible();
 await page.goto(path);
 await expect(page.getByRole("heading",{name:"Manual cleanup guidance",exact:true})).toBeVisible();
 await expect(page.getByText(/Scope not recorded/).first()).toBeVisible();
 const after=await (await page.request.get("/api"+path)).json();
 const former=after.memberships.find((a:{person_id:string})=>a.person_id===before.tenancy.owner_person_id);
 expect(former.status).toBe("removed");expect(former.cleanup_required).toBe(true);
 expect(after.tenancy.member_count).toBe(1);
 await capture(page,"transfer-cleanup");
}

// Keep long identity/removal text contained and final controls reachable on narrow native dialogs.
async function capture(page:Page,name:string){
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const modal=page.getByRole("dialog");
  if(await modal.count()) {
   expect(await modal.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
   await modal.evaluate(el=>{el.scrollTop=0;});
   await page.screenshot({path:`.local-dev/browser/${name}-${width}.png`,fullPage:false});
   if(name==="transfer-remove-cleanup-expanded") {
    const instructions=modal.locator(".operator-instructions");
    await instructions.locator(":scope > summary").evaluate(el=>el.scrollIntoView({block:"start"}));
    await page.screenshot({path:`.local-dev/browser/${name}-body-${width}.png`,fullPage:false});
    await instructions.locator("li").last().evaluate(el=>el.scrollIntoView({block:"end"}));
    await page.screenshot({path:`.local-dev/browser/${name}-body-bottom-${width}.png`,fullPage:false});
   }
   await modal.locator(".dialog-actions").scrollIntoViewIfNeeded();
   for(const control of [modal.getByRole("button",{name:"Cancel",exact:true}),modal.getByRole("button",{name:"Transfer tenancy ownership",exact:true})]) {
    const box=await control.boundingBox();expect(box!.y).toBeGreaterThanOrEqual(0);expect(box!.y+box!.height).toBeLessThanOrEqual(900);
   }
   await page.screenshot({path:`.local-dev/browser/${name}-controls-${width}.png`,fullPage:false});
  } else {
   await page.screenshot({path:`.local-dev/browser/${name}-${width}.png`,fullPage:true});
  }
 }
 await page.setViewportSize({width:1280,height:900});
}
