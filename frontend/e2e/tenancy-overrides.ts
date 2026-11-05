import {expect,type Page} from "@playwright/test";
import {resolve} from "node:path";

// Exercise independent overrides, durable conflict review and async application using real API/worker roles.
export async function tenancyOverrides(page:Page,name:string){
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 await page.getByRole("link",{name,exact:true}).click();
 const tenancyPath=new URL(page.url()).pathname;
 const id=tenancyPath.split("/").at(-1)!;
 await page.getByRole("button",{name:"Manage overrides",exact:true}).click();
 const editor=page.getByRole("dialog",{name:"Tenancy overrides",exact:true});
 await expect(editor.getByRole("link",{name:"baseline v3",exact:true})).toBeVisible();
 await editor.getByRole("checkbox",{name:"Override policy statements",exact:true}).check();
 await editor.getByRole("textbox",{name:"Policy statement override",exact:true}).fill("Allow group SpecialPolicy to inspect instances in tenancy");
 await editor.getByRole("checkbox",{name:"Override quota statements",exact:true}).check();
 await editor.getByRole("textbox",{name:"Quota statement override",exact:true}).fill("Set compute-core quota special-quota to 4 in tenancy");
 await editor.getByRole("checkbox",{name:"Override monthly budget",exact:true}).check();
 await editor.getByRole("textbox",{name:"Monthly budget override (USD)",exact:true}).fill("1200");
 await capture(page,"tenancy-override-editor");
 await editor.getByRole("button",{name:"Preview changes",exact:true}).click();
 const preview=page.getByRole("dialog",{name:"Review override changes",exact:true});
 await expect(preview.getByText("1200 USD · Override",{exact:true})).toBeVisible();
 await capture(page,"tenancy-override-preview");
 const response=page.waitForResponse(r=>r.url().endsWith("/api/configuration/overrides")&&r.request().method()==="POST");
 await preview.getByRole("button",{name:"Apply overrides",exact:true}).click();
 expect((await response).status()).toBe(202);
 await expect(page.getByRole("region",{name:"Overrides",exact:true}).getByText("Verified in simulation",{exact:true})).toBeVisible({timeout:20000});
 await expect(page.getByRole("region",{name:"Overrides",exact:true})).toContainText("Policy statements, Quota statements, Monthly budget");
 await expect(page.getByRole("region",{name:"Tenancy baseline update",exact:true})).toHaveCount(0);
 const assigned=await (await page.request.get("/api/configuration/overrides/"+id)).json();
 expect(assigned.baseline.version_number).toBe(3);expect(assigned.values.monthly_budget_override_amount).toBe("1200.0000");
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 await expect(page.getByRole("link",{name:"Override",exact:true})).toHaveCount(1);
 await capture(page,"tenancy-override-status");
 await page.getByRole("link",{name:"Override",exact:true}).click();
 await expect(page.getByRole("dialog",{name:"Tenancy overrides",exact:true}).getByRole("checkbox",{name:"Override monthly budget",exact:true})).toBeChecked();
 await page.goBack();await expect(page.getByRole("dialog")).toHaveCount(0);
 await page.goForward();await expect(page.getByRole("dialog",{name:"Tenancy overrides",exact:true})).toBeVisible();
 await page.keyboard.press("Escape");
 await expect(page.getByRole("dialog")).toHaveCount(0);
 await expect(page.getByRole("button",{name:"Manage overrides",exact:true})).toBeFocused();
 // The dashboard chooser is separate from baseline authoring and leads to the same scoped editor.
 await page.getByRole("link",{name:"Configuration",exact:true}).click();
 await page.getByRole("button",{name:"Create tenancy override",exact:true}).click();
 const chooser=page.getByRole("dialog",{name:"Choose a tenancy",exact:true});
 await chooser.getByRole("searchbox",{name:"Search tenancies",exact:true}).fill(name);
 await expect(chooser.getByRole("button",{name:"Choose",exact:true})).toHaveCount(1);
 await chooser.getByRole("button",{name:"Choose",exact:true}).click();
 await expect(page.getByRole("dialog",{name:"Tenancy overrides",exact:true})).toBeVisible();
 await page.getByRole("dialog").getByRole("button",{name:"Cancel",exact:true}).click();
 await page.getByRole("link",{name:"Configuration",exact:true}).click();
 await page.getByRole("button",{name:"New baseline",exact:true}).click();
 await page.getByLabel("Policy statements",{exact:true}).fill("Allow group NewBaselinePolicy to inspect instances in tenancy");
 await page.getByLabel("Quota statements",{exact:true}).fill("Set compute-core quota new-baseline-quota to 8 in tenancy");
 await page.getByLabel("Monthly amount",{exact:true}).fill("1000");
 await page.getByLabel("Static value 1",{exact:true}).fill("Updated");
 await page.getByRole("button",{name:"Save draft",exact:true}).click();
 await expect(page.getByRole("status").filter({hasText:"Baseline draft saved."})).toBeVisible();
 await page.getByRole("button",{name:"Publish",exact:true}).click();
 await page.getByRole("button",{name:"Publish baseline",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Published baseline v4",exact:true})).toBeVisible();
 await page.getByRole("link",{name:/Back to baselines/}).click();
 await page.getByRole("button",{name:"Update existing tenancies",exact:true}).click();
 const update=page.getByRole("dialog",{name:"Update existing tenancies",exact:true});
 await expect(update.getByText("1",{exact:true})).toBeVisible();
 await expect(update.getByRole("button",{name:"Start update",exact:true})).toBeDisabled();
 await update.getByRole("button",{name:"Review override",exact:true}).click();
 const conflict=page.getByRole("dialog",{name:"Review overrides · "+name,exact:true});
 await expect(conflict.getByRole("heading",{name:"Old baseline v3",exact:true})).toHaveCount(2);
 await expect(conflict.getByRole("heading",{name:"New baseline v4",exact:true})).toHaveCount(2);
 await conflict.getByRole("group",{name:"Choose policy content for this update",exact:true}).getByRole("radio",{name:"Use new baseline",exact:true}).check();
 await expect(conflict.getByRole("button",{name:"Save review",exact:true})).toBeDisabled();
 await conflict.getByRole("group",{name:"Choose quota content for this update",exact:true}).getByRole("radio",{name:"Keep override",exact:true}).check();
 await capture(page,"override-conflict-review");
 await conflict.getByRole("button",{name:"Save review",exact:true}).click();
 await expect(update.getByRole("button",{name:"Start update",exact:true})).toBeEnabled();
 await expect(update.getByRole("heading",{name:"Update existing tenancies",exact:true})).toBeFocused();
 await expect(update.getByText("Reviewed · staged",{exact:true})).toBeVisible();
 const unchanged=await (await page.request.get("/api/configuration/overrides/"+id)).json();
 expect(unchanged.baseline.version_number).toBe(3);expect(unchanged.configuration.id).toBe(assigned.configuration.id);
 const planUrl=page.url();expect(planUrl).toContain("?plan=");
 await page.reload();
 await expect(update).toBeVisible();await expect(update.getByRole("button",{name:"Start update",exact:true})).toBeEnabled();
 await capture(page,"override-review-staged");
 await update.getByRole("button",{name:"Start update",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Baseline v4 · Verified in simulation",exact:true})).toBeVisible({timeout:20000});
 const current=await (await page.request.get("/api/configuration/overrides/"+id)).json();
 expect(current.baseline.version_number).toBe(4);expect(current.values.policy_override_statements).toBeNull();
 expect(current.values.quota_override_statements).toEqual(["Set compute-core quota special-quota to 4 in tenancy"]);
 expect(current.values.monthly_budget_override_amount).toBe("1200.0000");
 expect(current.baseline.content.tag_defaults).toEqual([{key:"Environment",value:"Updated"}]);
 await page.getByRole("button",{name:"Acknowledge",exact:true}).click();
 await expect(page.getByText("No active tenancies need updating.",{exact:true})).toBeVisible();
 await page.goto(tenancyPath);
 await page.getByRole("button",{name:"Manage overrides",exact:true}).click();
 const clear=page.getByRole("dialog",{name:"Tenancy overrides",exact:true});
 await expect(clear.getByRole("checkbox",{name:"Override policy statements",exact:true})).not.toBeChecked();
 await clear.getByRole("checkbox",{name:"Override quota statements",exact:true}).uncheck();
 await clear.getByRole("checkbox",{name:"Override monthly budget",exact:true}).uncheck();
 await clear.getByRole("button",{name:"Preview changes",exact:true}).click();
 await expect(page.getByRole("dialog").getByText("1000 USD · Inherited",{exact:true})).toBeVisible();
 await page.getByRole("dialog").getByRole("button",{name:"Apply overrides",exact:true}).click();
 await expect(page.getByRole("region",{name:"Overrides",exact:true}).getByText("Quota statements, Monthly budget",{exact:true})).toHaveCount(0,{timeout:20000});
 await expect.poll(async()=>{const result=await (await page.request.get("/api/configuration/overrides/"+id)).json();return result.values;},{timeout:20000}).toEqual({policy_override_statements:null,quota_override_statements:null,monthly_budget_override_amount:null});
 await expect.poll(async()=>{const detail=await (await page.request.get("/api/tenancies/"+id)).json();return {pending:detail.tenancy.has_pending_operation,verified:detail.tenancy.desired_configuration_id===detail.tenancy.last_verified_configuration_id};},{timeout:20000}).toEqual({pending:false,verified:true});
 await page.getByRole("link",{name:"Tenancies",exact:true}).click();
 await expect(page.getByRole("link",{name:"Override",exact:true})).toHaveCount(0);
 return 4;
}

// Capture only disposable synthetic UI and verify both native modal and document horizontal bounds.
async function capture(page:Page,name:string){
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const dialog=page.getByRole("dialog");if(await dialog.count())expect(await dialog.evaluate(node=>node.scrollWidth<=node.clientWidth)).toBe(true);
  for(const control of await page.locator('dialog input[type="checkbox"], dialog input[type="radio"]').all()){
   const bounds=await control.boundingBox();expect(bounds?.width).toBe(18);expect(bounds?.height).toBe(18);
   const geometry=await control.evaluate(element=>{const label=element.closest("label")!;const walker=document.createTreeWalker(label,NodeFilter.SHOW_TEXT);let text:Node|null=null;while(text=walker.nextNode()){if(text.textContent?.trim())break;}const range=document.createRange();range.selectNodeContents(text!);const line=[...range.getClientRects()].find(rect=>rect.width>0)!;const box=element.getBoundingClientRect();return {difference:Math.abs(box.y+box.height/2-line.y-line.height/2),target:label.getBoundingClientRect().height};});
   expect(geometry.difference).toBeLessThanOrEqual(2);expect(geometry.target).toBeGreaterThanOrEqual(44);
  }
  if(await dialog.count())await dialog.evaluate(node=>{node.scrollTop=0;});
  await page.screenshot({path:resolve(".local-dev/browser",`${name}-${width}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1280,height:900});
}
