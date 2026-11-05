import {test,expect,type Page,type Locator} from "@playwright/test";
import {createHmac} from "node:crypto";
import {resolve} from "node:path";
import {readFile} from "node:fs/promises";
import {auditSelectPickers} from "./select-audit";

// Keep disposable test factors in memory and never export credentials in screenshots, URLs or traces.
function authenticatorCode(){
 const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567",bits=[...process.env.OTM_E2E_SEED!].map(character=>alphabet.indexOf(character).toString(2).padStart(5,"0")).join("");
 const key=Buffer.from(bits.match(/.{8}/g)!.map(byte=>parseInt(byte,2))),counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
 const digest=createHmac("sha1",key).update(counter).digest(),offset=digest[19]&15;
 return((digest.readUInt32BE(offset)&0x7fffffff)%1000000).toString().padStart(6,"0");
}

// Capture the new read-only content where it is visible, including narrow screens with native scrolling.
async function capture(page:Page,target:Locator,prefix:string){
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});await target.scrollIntoViewIfNeeded();await expect(target).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:resolve(".local-dev/browser",`${prefix}-${width}.png`)});
 }
 await page.setViewportSize({width:1280,height:900});
}

// Read real routing/contact snapshots and independent SMTP acceptance; never create or retarget contacts from the browser.
test("inspect redirected lifecycle delivery and immutable identities through real HTTPS",async({page})=>{
 test.setTimeout(90000);const errors:string[]=[];page.on("pageerror",error=>errors.push(error.name));
 const email=process.env.OTM_E2E_EMAIL_TEST_ADDRESS!,operation=process.env.OTM_E2E_EMAIL_OPERATION_ID!,candidate=process.env.OTM_E2E_EMAIL_EMPLOYEE_NAME!;
 expect(email).toBeTruthy();expect(operation).toBeTruthy();expect(candidate).toBeTruthy();
 await page.goto("/login");await page.getByLabel("Password",{exact:true}).fill(process.env.OTM_E2E_PASSWORD!);await page.getByLabel("Authenticator code",{exact:true}).fill(authenticatorCode());await page.getByRole("button",{name:"Sign in",exact:true}).click();
 await expect(page.getByRole("heading",{name:"Tenancies",exact:true})).toBeVisible();
 const banner=page.locator(".email-routing-banner");await expect(banner).toContainText(email);await expect(banner).toContainText("Stored identities and previously recorded activation contacts remain unchanged");await capture(page,banner,"email-routing-banner");
 await page.getByRole("link",{name:"Organization",exact:true}).click();await page.getByLabel("Search employees",{exact:true}).fill(candidate);await page.getByRole("button",{name:candidate,exact:true}).click();
 const dialog=page.getByRole("dialog",{name:"Employee & tenancy associations"});await expect(dialog.getByRole("combobox",{name:"Action",exact:true})).toHaveValue("");
 const original=await dialog.locator(".workflow-person span").innerText();expect(original).not.toBe(email);
 for(const action of ["create_tenancy","import_tenancy"]){
  await dialog.getByRole("combobox",{name:"Action",exact:true}).selectOption(action);
  const contacts=dialog.getByRole("region",{name:"Tenancy email contacts"});await expect(contacts.getByText("Test delivery: "+email,{exact:true})).toHaveCount(2);await expect(contacts).toContainText("Original contact: "+original);await expect(dialog.locator(".workflow-person span")).toHaveText(original);await expect(contacts.getByRole("textbox")).toHaveCount(0);
  await expect(contacts.getByText(action==="create_tenancy"?"Activation / bootstrap email":"Bootstrap contact email",{exact:true})).toBeVisible();
  await capture(page,contacts,action==="create_tenancy"?"email-create-preview":"email-import-preview");
  await dialog.getByRole("button",{name:"Cancel",exact:true}).scrollIntoViewIfNeeded();await expect(dialog.getByRole("button",{name:"Cancel",exact:true})).toBeVisible();
 }
 await dialog.getByRole("button",{name:"Cancel",exact:true}).click();
 await page.goto("/operations/"+operation);
 const notifications=page.getByRole("region",{name:"Email notifications"});await expect(notifications.getByText("Accepted by mail server",{exact:true})).toBeVisible({timeout:25000});await expect(notifications.locator("dd").filter({hasText:email})).toContainText(email);await expect(notifications.getByRole("button")).toHaveCount(0);await expect(notifications.getByRole("link")).toHaveCount(0);
 await expect(page.getByText("Responsibility change recorded.")).toHaveCount(0);
 const contacts=page.getByRole("region",{name:"Tenancy email contacts"});await expect(contacts.getByText("Activation / bootstrap email",{exact:true})).toBeVisible();await expect(contacts).toContainText(email);await expect(page.getByText(/Activation delivery:/)).toContainText(email);await expect(page.getByText(/No OCI activation email is sent/)).toBeVisible();
 await capture(page,contacts,"email-onboarding-contacts");await capture(page,notifications,"email-delivery");

 // Audit filtering and export use the same real category; delivery never crowds operational rows.
 await page.getByRole("link",{name:"Audit history",exact:true}).click();
 const category=page.getByRole("combobox",{name:"Category",exact:true});
 await expect(category.getByRole("option",{name:"Email delivery",exact:true})).toHaveCount(1);
 await category.selectOption("email_delivery");
 await expect(page.locator("tbody tr").first().locator(".audit-category")).toHaveText("Email delivery");
 await expect(page.locator("tbody").getByText("Email delivery worker").first()).toBeVisible();
 const noticeRows=await page.locator("tbody tr").count();
 for(let index=0;index<noticeRows;index++)await expect(page.locator("tbody tr").nth(index).locator(".audit-category")).toHaveText("Email delivery");
 const downloading=page.waitForEvent("download");
 await page.getByRole("button",{name:"Export CSV",exact:true}).click();
 const download=await downloading;const csv=await readFile((await download.path())!,"utf8");
 expect(csv).toContain('"email_delivery","email_delivery"');
 await auditSelectPickers(page,"email-delivery-category");
 await category.selectOption("operations");
 await expect(page.locator("tbody tr").first().locator(".audit-category")).toHaveText("Operations");
 expect(await page.locator("tbody .audit-category").allTextContents()).not.toContain("Email delivery");
 await category.selectOption("");
 await expect(page.locator("tbody .audit-category").filter({hasText:"Email delivery"}).first()).toBeVisible();
 expect(errors).toEqual([]);
});
