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

// Real HTTPS claim must change authority without changing the creator or activation contact.
test("take responsibility and continue guided work through the native worker", async ({page}) => {
  const errors:string[]=[];
  page.on("pageerror", error=>errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Password",{exact:true}).fill(process.env.OTM_E2E_PASSWORD!);
  await page.getByLabel("Authenticator code",{exact:true}).fill(authenticatorCode());
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Tenancies",exact:true})).toBeVisible();
  await page.goto("/operations/"+process.env.OTM_E2E_OPERATION_ID);
  const panel=page.getByRole("region",{name:"Administrator responsibility",exact:true});
  await expect(panel.getByRole("button",{name:"Take responsibility",exact:true})).toBeVisible();
  await page.reload();
  await panel.getByRole("button",{name:"Take responsibility",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"Take responsibility?",exact:true});
  await expect(dialog.getByRole("heading",{name:"Take responsibility?",exact:true})).toBeFocused();
  for(const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`responsibility-modal-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  await page.keyboard.press("Escape");
  await expect(panel.getByRole("button",{name:"Take responsibility",exact:true})).toBeFocused();
  await panel.getByRole("button",{name:"Take responsibility",exact:true}).click();
  const response=page.waitForResponse(value=>value.url().endsWith("/responsibility")&&value.request().method()==="POST");
  await dialog.getByRole("button",{name:"Take responsibility",exact:true}).click();
  const accepted=await response;
  expect(accepted.status()).toBe(200);
  expect(Object.keys(accepted.request().postDataJSON()).sort()).toEqual(["client_request_key","expected_revision"]);
  await expect(panel.getByText("Recovery administrator",{exact:true})).toBeVisible();
  await expect(panel.getByText("Creator",{exact:true})).toBeVisible();
  await expect(panel.getByRole("button",{name:"Take responsibility",exact:true})).toHaveCount(0);
  await expect(page.getByText("Owner: Engineer · Initiated by: Creator",{exact:true})).toBeVisible();
  // Taking responsibility must retain the original activation destination inside its disclosure.
  const delivery=page.locator(".onboarding-contacts");
  await expect(delivery).not.toHaveAttribute("open");
  await delivery.getByText("Delivery and administrator contacts",{exact:true}).click();
  await expect(delivery.locator(".operation-facts > div").filter({has:page.getByText("Activation delivery",{exact:true})}).locator("dd")).toHaveText("creator@example.test");
  for(const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    await panel.scrollIntoViewIfNeeded();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`responsibility-claimed-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole("button",{name:"Use simulated handoff",exact:true}).click();
  await page.getByRole("button",{name:"Verify handoff",exact:true}).click();
  await expect(page.getByRole("button",{name:"Start setup",exact:true})).toBeVisible({timeout:20000});
  expect(errors).toEqual([]);
});
