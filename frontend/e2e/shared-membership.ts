import {expect,type Page} from "@playwright/test";
import {resolve} from "node:path";

// Exercise existing-compartment assignment and explicit identity retirement through real UI/API/jobs.
export async function existingCompartmentMembership(page:Page,sharedName:string){
 await page.getByRole("link",{name:"Organization",exact:true}).click();
 await page.getByRole("button",{name:"Leader Two",exact:true}).click();
 const modal=page.getByRole("dialog");
 await modal.getByRole("combobox",{name:"Action",exact:true}).selectOption("join_shared");
 const selector=modal.getByRole("combobox",{name:"Shared tenancy",exact:true});
 const option=await selector.locator("option").allTextContents();
 const chosen=option.find(label=>label.includes(sharedName))!;await selector.selectOption({label:chosen});
 const selectedTenancy=await selector.inputValue();
 await modal.getByRole("combobox",{name:"Compartment assignment",exact:true}).selectOption("existing");
 const picker=modal.getByRole("combobox",{name:"Existing compartment",exact:true});
 await expect(picker.locator("selectedcontent")).toHaveText("Choose an existing compartment");
 await modal.getByRole("combobox",{name:"Compartment assignment",exact:true}).selectOption("create");
 await expect(modal.getByRole("combobox",{name:"Existing parent compartment",exact:true}).locator("selectedcontent")).toHaveText("Choose an existing parent");
 await modal.getByRole("combobox",{name:"Compartment assignment",exact:true}).selectOption("existing");
 await expect(picker.locator("selectedcontent")).toHaveText("Choose an existing compartment");
 await expect(picker.locator("option")).toHaveCount(3);
 await picker.selectOption({index:1});
 await expect(modal.getByLabel("Employee compartment name",{exact:true})).toHaveCount(0);
 await capture(page,"shared-existing-compartment");
 const pending=page.waitForResponse(r=>r.url().endsWith("/api/organization/actions")&&r.request().method()==="POST");
 await modal.getByRole("button",{name:"Add to shared tenancy",exact:true}).click();
 const accepted=await pending;expect(accepted.status()).toBe(202);
 const command=accepted.request().postDataJSON();expect(command.existing_compartment_ocid).toBeTruthy();
 expect(command.parent_compartment_ocid).toBeUndefined();expect(command.compartment_name).toBeUndefined();
 await modal.getByRole("link",{name:"View operation",exact:true}).click();
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
 await page.getByRole("link",{name:"Organization",exact:true}).click();
 const workflowResponse=page.waitForResponse(response=>response.url().includes("/workflow")&&response.request().method()==="GET");
 await page.getByRole("button",{name:"Leader Two",exact:true}).click();
 const workflow=await(await workflowResponse).json();
 await modal.getByRole("combobox",{name:"Action",exact:true}).selectOption("remove_member");
 await modal.getByRole("combobox",{name:"Tenancy",exact:true}).selectOption(selectedTenancy);
 await modal.getByRole("checkbox",{name:/I reviewed the shared tenancy impact/}).check();
 const destructiveConsent=modal.getByRole("checkbox",{name:/I acknowledge the consequences/});
 const removal=modal.getByRole("button",{name:"Remove shared member",exact:true});
 await expect(destructiveConsent).not.toBeChecked();await expect(removal).toBeDisabled();
 const attempted:string[]=[];
 const track=(request:import("@playwright/test").Request)=>{if(request.method()==="POST"&&request.url().endsWith("/api/organization/actions"))attempted.push(request.url());};
 page.on("request",track);
 await destructiveConsent.focus();await page.keyboard.press("Enter");
 await modal.locator("form").evaluate(form=>form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));
 expect(attempted).toHaveLength(0);
 const rejected=await page.evaluate(async body=>{const response=await fetch("/api/organization/actions",{method:"POST",headers:{"Content-Type":"application/json","X-OTM-Request":"1"},body:JSON.stringify(body)});return{status:response.status,data:await response.json()};},{client_request_key:crypto.randomUUID(),context:workflow.context,person_id:workflow.person.id,action:"remove_member",tenancy_id:selectedTenancy,confirm_shared:true,confirm_destructive:false});
 expect(rejected.status).toBe(409);expect(rejected.data.code).toBe("DESTRUCTIVE_CONFIRMATION_REQUIRED");
 page.off("request",track);
 await destructiveConsent.check();
 await modal.getByRole("combobox",{name:"Tenancy",exact:true}).selectOption("");
 await expect(destructiveConsent).not.toBeChecked();
 await modal.getByRole("combobox",{name:"Tenancy",exact:true}).selectOption(selectedTenancy);
 await expect(removal).toBeDisabled();
 await modal.getByRole("checkbox",{name:/I reviewed the shared tenancy impact/}).check();
 await destructiveConsent.check();
 await capture(page,"destructive-member-confirmation");
 await modal.getByRole("button",{name:"Remove shared member",exact:true}).click();
 await modal.getByRole("link",{name:"View operation",exact:true}).click();
 await expect(page.getByText("Succeeded",{exact:true})).toBeVisible({timeout:20000});
 await expect(page.getByRole("heading",{name:"Remove user group memberships",exact:true})).toBeVisible();
 await expect(page.getByRole("heading",{name:"Delete tenancy user",exact:true})).toBeVisible();
 await capture(page,"shared-user-removal-evidence");
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 const row=page.getByRole("row").filter({has:page.getByRole("link",{name:sharedName,exact:true})});
 const status=row.locator(".tenancy-status-label");await status.focus();
 await expect(row.getByRole("tooltip")).toContainText("Created");
 await capture(page,"tenancy-created-tooltip");
 await page.keyboard.press("Escape");await expect(row.getByRole("tooltip")).not.toBeVisible();
 await page.getByRole("link",{name:sharedName,exact:true}).click();
 await expect(page.getByRole("region",{name:"Overrides",exact:true})).toBeVisible();
 await expect(page.getByRole("button",{name:"Manage owner & associations",exact:true})).toHaveCount(0);
 await capture(page,"tenancy-override-section");
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
}

// Capture synthetic responsive screens while keeping overflow inside tables/native dialogs.
async function capture(page:Page,name:string){
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  if(name==="tenancy-created-tooltip"){
   const status=page.locator(".tenancy-status-label:focus");await status.scrollIntoViewIfNeeded();await status.hover();
   const tooltip=status.locator("..").getByRole("tooltip");await expect(tooltip).toBeVisible();
   const box=await tooltip.boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const dialog=page.getByRole("dialog");if(await dialog.count())expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.screenshot({path:resolve(".local-dev/browser",`${name}-${width}.png`),fullPage:true});
  if(name==="destructive-member-confirmation"){
   await dialog.locator(".dialog-actions").scrollIntoViewIfNeeded();
   const consent=dialog.getByRole("checkbox",{name:/I acknowledge the consequences/});
   const submit=dialog.getByRole("button",{name:"Remove shared member",exact:true});
   for(const control of [consent,submit,dialog.getByRole("button",{name:"Cancel",exact:true})]){
    await expect(control).toBeVisible();const box=(await control.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);expect(box.y+box.height).toBeLessThanOrEqual(900);
   }
   await page.screenshot({path:resolve(".local-dev/browser",`${name}-controls-${width}.png`),fullPage:true});
  }
 }
 await page.setViewportSize({width:1280,height:900});
}
