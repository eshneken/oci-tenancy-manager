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
  const id=process.env.OTM_E2E_TENANCY_ID!;
  await page.goto("/tenancies/"+id);
  const region=page.getByRole("region",{name:"Automatic key rotation"});
  await expect(region.getByText("Rotation scheduled",{exact:true})).toBeVisible();
  await expect(region.getByText(/Generation 1/)).toBeVisible();
  for(const width of [1280,900,390,320]){
    await page.setViewportSize({width,height:900});
    await region.scrollIntoViewIfNeeded();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`signing-key-panel-${width}.png`),fullPage:true});
    await region.getByRole("button",{name:"Rotate key",exact:true}).click();
    const dialog=page.getByRole("dialog");
    await expect(dialog.getByRole("checkbox")).not.toBeChecked();
    await expect(dialog.getByRole("button",{name:"Start rotation",exact:true})).toBeDisabled();
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
  await dialog.getByRole("button",{name:"Start rotation",exact:true}).click();
  const response=await accepted;expect(response.status()).toBe(202);const receipt=await response.json();
  await expect.poll(async()=>{
    const result=await page.request.get("/api/operations/"+receipt.operation_id);
    expect(result.ok()).toBe(true);return(await result.json()).operation.state;
  },{timeout:30000}).toBe("succeeded");
  await expect(region.getByText(/Generation 2/)).toBeVisible({timeout:10000});
  await page.reload();await expect(region.getByText(/Generation 2/)).toBeVisible();
  await region.getByRole("link",{name:"View last completed key rotation"}).click();
  await expect(page.getByText(/Signing credential operation verified in local simulation/)).toBeVisible();
  await expect(page.getByText(/Inspection completed successfully/)).toHaveCount(0);
  await page.getByRole("link",{name:"← Back to tenancy",exact:true}).click();
  await expect(region.getByText(/Generation 2/)).toBeVisible();
  await page.screenshot({path:resolve(".local-dev/browser","signing-key-completed-1280.png"),fullPage:true});
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
