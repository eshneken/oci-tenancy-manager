import {test,expect} from "@playwright/test";
import {createHmac} from "node:crypto";
import {resolve} from "node:path";

// Hold fixture factors only in memory; no live enrollment, browser storage, URLs or traces.
function authenticatorCode() {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...process.env.OTM_E2E_SEED!]
    .map((character) =>
      alphabet.indexOf(character).toString(2).padStart(5, "0"),
    )
    .join("");
  const key = Buffer.from(
    bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)),
  );
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[19] & 15;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000)
    .toString()
    .padStart(6, "0");
}

// Real admission and native-worker progress prove the persisted phases across page reloads.
test("rotate a managed signing key through the independent native worker",async({page})=>{
  const errors:string[]=[];page.on("pageerror",error=>errors.push(error.name));
  await page.goto("/login");
  await page.getByLabel("Password",{exact:true}).fill(process.env.OTM_E2E_PASSWORD!);
  await page.getByLabel("Authenticator code",{exact:true}).fill(authenticatorCode());
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Tenancies",exact:true})).toBeVisible();
  // Both daily directories center shortcuts against search and preserve their narrow stacked layout.
  for(const path of ["tenancies","organization"]){
    await page.goto("/"+path);
    const toolbar=page.locator(".directory-toolbar");
    await expect(toolbar.getByRole("searchbox")).toBeVisible();
    for(const width of [1280,900,390,320]){
      await page.setViewportSize({width,height:900});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await toolbar.scrollIntoViewIfNeeded();
      if(width===1280){
        const search=await toolbar.getByRole("searchbox").boundingBox();
        const link=await toolbar.getByRole("link").boundingBox();
        expect(Math.abs(search!.y+search!.height/2-link!.y-link!.height/2)).toBeLessThan(2);
        const checkbox=await toolbar.locator(".directory-filter").boundingBox();
        expect(Math.abs(search!.y+search!.height/2-checkbox!.y-checkbox!.height/2)).toBeLessThan(2);
      }
      await page.screenshot({path:resolve(".local-dev/browser",`directory-${path}-${width}.png`),fullPage:true});
    }
  }
  await page.setViewportSize({width:1280,height:900});
  const id=process.env.OTM_E2E_TENANCY_ID!;
  await page.goto("/tenancies/"+id);
  const region=page.getByRole("region",{name:"Automatic key rotation"});
  await expect(region.getByText("Next rotation scheduled",{exact:true})).toBeVisible();
  await expect(region.getByText(/Current key: generation 1/)).toBeVisible();
  await region.getByRole("link",{name:"View scheduled rotation",exact:true}).click();
  await expect(page.getByText(/Scheduled start \(UTC\):/)).toBeVisible();
  await expect(page.getByText(/not paused while it waits/)).toBeVisible();
  for(const width of [1280,320]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`signing-scheduled-operation-${width}.png`),fullPage:true});
  }
  await page.getByRole("link",{name:"← Back to tenancy",exact:true}).click();
  for(const width of [1280,900,390,320]){
    await page.setViewportSize({width,height:900});
    await region.scrollIntoViewIfNeeded();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`signing-key-panel-${width}.png`),fullPage:true});
    await region.getByRole("button",{name:"Rotate key",exact:true}).click();
    const dialog=page.getByRole("dialog");
    await expect(dialog.getByRole("checkbox")).not.toBeChecked();
    await expect(dialog.getByRole("button",{name:"Rotate now",exact:true})).toBeDisabled();
    await page.screenshot({path:resolve(".local-dev/browser",`signing-key-dialog-${width}.png`)});
    await dialog.getByRole("button",{name:"Cancel",exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:resolve(".local-dev/browser",`signing-key-actions-${width}.png`)});
    await dialog.getByRole("button",{name:"Cancel",exact:true}).click();
  }
  await page.setViewportSize({width:1280,height:900});
  await region.getByRole("button",{name:"Rotate key",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await dialog.getByRole("checkbox").check();
  const accepted=page.waitForResponse(response=>response.url().endsWith("/signing-key-rotation")&&response.request().method()==="POST");
  await dialog.getByRole("button",{name:"Rotate now",exact:true}).click();
  const response=await accepted;expect(response.status()).toBe(202);const receipt=await response.json();
  await expect.poll(async()=>{
    const result=await page.request.get("/api/operations/"+receipt.operation_id);
    expect(result.ok()).toBe(true);return(await result.json()).operation.state;
  },{timeout:30000}).toBe("succeeded");
  await expect(region.getByText(/Current key: generation 2/)).toBeVisible({timeout:10000});
  await page.reload();await expect(region.getByText(/Current key: generation 2/)).toBeVisible();
  await region.getByRole("link",{name:"View last completed key rotation"}).click();
  await expect(page.getByText(/Signing credential operation verified in local simulation/)).toBeVisible();
  await expect(page.getByText(/Inspection completed successfully/)).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"Replacement signer verified",exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Key rotation completed",exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Signing-key maintenance",exact:true})).toHaveCount(0);
  for(const width of [1280,320]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole("heading",{name:"Recent events",exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:resolve(".local-dev/browser",`signing-history-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole("link",{name:"← Back to tenancy",exact:true}).click();
  await expect(region.getByText(/Current key: generation 2/)).toBeVisible();
  await page.screenshot({path:resolve(".local-dev/browser","signing-key-completed-1280.png"),fullPage:true});
  // Actual API filtering isolates recurring work without changing the workspace-wide action badge.
  await page.getByRole("link",{name:"Operations",exact:true}).click();
  await page.getByLabel("Operation type",{exact:true}).selectOption("configuration_check");
  await expect(page.getByRole("heading",{name:"No operations match your filters"})).toBeVisible();
  await page.getByRole("button",{name:"Clear filters",exact:true}).click();
  await expect(page.getByLabel("Operation type",{exact:true})).toHaveValue("");
  await page.getByLabel("Operation type",{exact:true}).selectOption("signing_key");
  await page.getByLabel("State",{exact:true}).selectOption("waiting");
  const operations=page.getByRole("region",{name:"Operations directory"});
  await expect(operations.locator("tbody tr")).toHaveCount(1);
  for(const width of [1280,900,390,320]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const searchBounds=await page.getByRole("searchbox",{name:"Search operations"}).boundingBox();
    expect(searchBounds!.width).toBeGreaterThan(200);
    await page.screenshot({path:resolve(".local-dev/browser",`operation-type-filter-${width}.png`),fullPage:true});
    await page.getByLabel("Operation type",{exact:true}).click();
    await page.getByRole("option",{name:"Tenancy & organization workflows",exact:true}).scrollIntoViewIfNeeded();
    await expect(page.getByRole("option",{name:"Tenancy & organization workflows",exact:true})).toBeVisible();
    await page.screenshot({path:resolve(".local-dev/browser",`operation-type-menu-${width}.png`)});
    await page.keyboard.press("Escape");
    await expect(page.getByLabel("Operation type",{exact:true})).toBeFocused();
    await page.getByLabel("State",{exact:true}).click();
    await expect(page.getByRole("option",{name:"Needs attention",exact:true})).toBeVisible();
    await page.screenshot({path:resolve(".local-dev/browser",`operation-state-menu-${width}.png`)});
    await page.keyboard.press("Escape");
    await expect(page.getByLabel("State",{exact:true})).toBeFocused();
  }
  await page.setViewportSize({width:1280,height:900});
  await operations.locator("tbody tr").getByRole("link").first().click();
  await expect(page.getByText(/Scheduled start \(UTC\):/)).toBeVisible();
  await page.getByRole("link",{name:"← Back to operations",exact:true}).click();
  await expect(page.getByLabel("Operation type",{exact:true})).toHaveValue("signing_key");
  await expect(page.getByLabel("State",{exact:true})).toHaveValue("waiting");
  await page.goto("/tenancies/"+id);
  // Browser-only response fixtures inspect rare presentation states without adding app controls.
  const endpoint="**/api/tenancies/"+id+"/signing-key-rotation";
  const current=await(await page.request.get("/api/tenancies/"+id+"/signing-key-rotation")).json();
  let simulatedState="attention";
  await page.route(endpoint,async route=>{
    if(route.request().method()==="POST"){await route.fulfill({status:503,json:{code:"TEST_RESPONSE_LOST"}});return;}
    await route.fulfill({json:{...current,state:simulatedState,available:simulatedState==="attention",preview_hash:simulatedState==="attention"?current.preview_hash:null}});
  });
  await page.reload();await expect(region.getByText("Rotation needs attention",{exact:true})).toBeVisible();
  await page.screenshot({path:resolve(".local-dev/browser","signing-key-attention-1280.png"),fullPage:true});
  await region.getByRole("button",{name:"Resume rotation",exact:true}).click();
  await page.getByRole("dialog").getByRole("checkbox").check();
  await page.getByRole("dialog").getByRole("button",{name:"Resume rotation",exact:true}).click();
  await expect(page.getByText(/request may have been accepted/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button",{name:"Cancel",exact:true}).click();
  simulatedState="rotating";
  await region.getByRole("button",{name:"Recover request",exact:true}).click();
  await expect(page.getByRole("dialog").getByRole("checkbox")).not.toBeChecked();
  await expect(page.getByRole("dialog").getByRole("button",{name:"Retry same request",exact:true})).toBeVisible();
  for(const width of [1280,320]){
    await page.setViewportSize({width,height:900});
    await page.getByRole("dialog").getByRole("button",{name:"Retry same request",exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:resolve(".local-dev/browser",`signing-key-uncertain-${width}.png`)});
  }
  await page.unroute(endpoint);
  expect(errors).toEqual([]);
});
