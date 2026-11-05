import { test, expect } from "@playwright/test";
import { createHmac } from "node:crypto";
import { resolve } from "node:path";

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

// Exercise this slice independently of unrelated baseline publication and offboarding browser setup.
test("check a qualified child through HTTPS and the separate native worker", async ({page}) => {
  const errors:string[]=[];
  page.on("pageerror", error=>errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Password",{exact:true}).fill(process.env.OTM_E2E_PASSWORD!);
  await page.getByLabel("Authenticator code",{exact:true}).fill(authenticatorCode());
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Tenancies",exact:true})).toBeVisible();
  const name=process.env.OTM_E2E_TENANCY_NAME!;
  const row=page.getByRole("row").filter({has:page.getByRole("link",{name,exact:true})});
  await expect(row.getByText("Not collected",{exact:true})).toBeVisible();
  const accepted=page.waitForResponse(response=>response.url().endsWith("/api/costs/refresh")&&response.request().method()==="POST");
  await page.getByRole("button",{name:"Refresh costs",exact:true}).click();
  const response=await accepted;expect(response.status()).toBe(202);
  const receipt=await response.json();expect(receipt.accepted_count).toBe(1);
  await expect(row.getByText("Not collected",{exact:true})).toHaveCount(0,{timeout:20000});
  await expect(row.getByLabel("actual: $0.00, within budget",{exact:true})).toBeVisible();
  await expect(row.getByLabel("budget: $200.00",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Sort by actual",exact:true}).click();
  for(const width of [1280,390,320]){
    await page.setViewportSize({width,height:900});
    const tooltip=row.getByRole("button",{name:/Cost retrieval time/});
    await tooltip.scrollIntoViewIfNeeded();await tooltip.blur();await tooltip.focus();
    await expect(page.getByRole("tooltip")).toContainText("OTM retrieved");
    // Focused details remain visible through the scroll/resize used to bring the trigger on screen.
    await page.evaluate(() => window.dispatchEvent(new Event("scroll")));
    await expect(page.getByRole("tooltip")).toBeVisible();
    const box=await page.getByRole("tooltip").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x+box!.width).toBeLessThanOrEqual(width);
    await page.keyboard.press("Escape");await expect(page.getByRole("tooltip")).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`cost-inventory-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});await row.getByRole("link",{name,exact:true}).click();
  await expect(page.getByRole("heading",{name:"Current month costs",exact:true})).toBeVisible();
  await page.reload();await expect(page.getByRole("heading",{name:"Current month costs",exact:true})).toBeVisible();
  const refreshed=page.waitForResponse(response=>response.url().endsWith("/api/costs/refresh")&&response.request().method()==="POST");
  await page.getByRole("button",{name:"Refresh costs",exact:true}).click();
  const detailResponse=await refreshed;expect(detailResponse.status()).toBe(202);const detailReceipt=await detailResponse.json();
  await expect.poll(async()=>{const response=await page.request.get(`/api/operations/${detailReceipt.operation_ids[0]}`);expect(response.ok()).toBe(true);return (await response.json()).operation.state;},{timeout:20000}).toBe("succeeded");
  await expect(page.getByText("Refreshing…",{exact:true})).toHaveCount(0,{timeout:20000});
  await expect(page.getByText(/Refresh queued/)).toHaveCount(0,{timeout:20000});
  await expect(page.getByRole("heading",{name:"Current month costs",exact:true})).toHaveCount(1);
  await page.getByText("Source details",{exact:true}).click();await expect(page.getByText("OCI calculation time",{exact:true})).toBeVisible();
  await page.screenshot({path:resolve(".local-dev/browser","cost-detail-1280.png"),fullPage:true});
  for(const width of [390,320]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:resolve(".local-dev/browser",`cost-detail-${width}.png`),fullPage:true});}
  // The actual worker's audit records must load and remain searchable after a real cost refresh.
  await page.getByRole("link",{name:"Audit history",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Audit history",exact:true})).toBeVisible();
  const search=page.getByRole("searchbox",{name:"Search audit history"});
  await search.fill("Cost collection worker");
  await expect(page.getByRole("cell",{name:"Cost collection worker",exact:true}).first()).toBeVisible();
  await expect(page.getByText(/Unable to load audit history/)).toHaveCount(0);
  // These explicit browser-only response fixtures qualify rendering, not real worker/provider facts.
  // The preceding fleet/detail flow proves actual HTTPS/native-worker behavior independently.
  let fixture: {state:string;actual:string;budget:string;forecast:string|null;actual_over_budget:boolean;forecast_over_budget:boolean}={state:"current",actual:"201.0000",budget:"200.0000",forecast:"320.0000",actual_over_budget:true,forecast_over_budget:true};
  await page.route("**/api/tenancies?*",async route=>{const response=await route.fetch();const body=await response.json();body.items[0].costs={...body.items[0].costs,...fixture};await route.fulfill({response,json:body});});
  await page.getByRole("link",{name:"Tenancies",exact:true}).click();await page.setViewportSize({width:1280,height:900});
  await expect(page.locator(".cost-over")).toHaveCount(1);await expect(page.locator(".cost-forecast-over")).toHaveCount(1);
  await page.screenshot({path:resolve(".local-dev/browser","cost-fixture-overrun-1280.png"),fullPage:true});
  fixture={...fixture,state:"partial",actual:"120.0000",forecast:null,actual_over_budget:false,forecast_over_budget:false};await page.reload();
  await expect(page.getByText("Forecast unavailable",{exact:true})).toBeVisible();await expect(page.locator(".cost-within")).toHaveCount(1);
  await page.screenshot({path:resolve(".local-dev/browser","cost-fixture-partial-1280.png"),fullPage:true});
  fixture={...fixture,state:"stale",forecast:"320.0000"};await page.reload();await expect(page.getByText("Stale data",{exact:true})).toBeVisible();await expect(page.locator(".cost-within,.cost-over,.cost-forecast-over")).toHaveCount(0);
  await page.screenshot({path:resolve(".local-dev/browser","cost-fixture-stale-1280.png"),fullPage:true});
  fixture={...fixture,state:"prior_cycle"};await page.reload();await expect(page.getByText("Prior month",{exact:true})).toBeVisible();await expect(page.locator(".cost-within,.cost-over,.cost-forecast-over")).toHaveCount(0);
  await page.screenshot({path:resolve(".local-dev/browser","cost-fixture-prior-cycle-1280.png"),fullPage:true});
  expect(errors).toEqual([]);
});
