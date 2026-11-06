import { test, expect } from "@playwright/test";
import { createHmac } from "node:crypto";

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
test("repair each managed category with assigned overrides through HTTPS and the native worker", async ({page},testInfo) => {
  const errors:string[]=[];
  page.on("pageerror", error=>errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Password",{exact:true}).fill(process.env.OTM_E2E_PASSWORD!);
  await page.getByLabel("Authenticator code",{exact:true}).fill(authenticatorCode());
  await page.getByRole("button",{name:"Sign in",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Tenancies",exact:true})).toBeVisible();
  await page.getByRole("link",{name:"Configuration drift",exact:true}).click();
  await page.getByRole("link",{name:process.env.OTM_E2E_TENANCY_NAME!,exact:true}).click();
  for(const width of [1280,390,320]){
    await page.setViewportSize({width,height:900});
    await page.getByRole("button",{name:"Repair configuration",exact:true}).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:testInfo.outputPath(`repair-selection-${width}.png`)});
    await page.getByRole("button",{name:"Cancel",exact:true}).click();
  }
  const labels={policy:"Policy statements",quota:"Quota statements",budget:"Monthly budget",tags:"Tag defaults"} as const;
  const expected=JSON.parse(process.env.OTM_E2E_REPAIR_EXPECTED!) as Record<keyof typeof labels,Record<string,unknown>>;
  const repaired=new Set<string>();
  for(const category of ["policy","quota","budget","tags"] as const){
    await page.getByRole("button",{name:"Repair configuration",exact:true}).click();
    const dialog=page.getByRole("dialog");
    for(const checkbox of await dialog.getByRole("checkbox").all())await checkbox.uncheck();
    await dialog.getByRole("checkbox",{name:new RegExp("^"+labels[category]+" ·")}).check();
    await dialog.getByRole("button",{name:"Preview repair",exact:true}).click();
    await expect(dialog.getByRole("heading",{name:"Confirm configuration repair"})).toBeVisible();
    await expect(dialog.getByRole("heading",{name:"Confirm configuration repair"})).toBeFocused();
    const intended=dialog.getByRole("heading",{name:"Expected after repair",exact:true}).locator("..").locator("pre");
    await expect(intended).toBeVisible();
    if(category==="policy"||category==="quota")expect(await intended.textContent()).toBe((expected[category].statements as string[]).join("\n"));
    else {const actual=JSON.parse((await intended.textContent())!);expect(actual).toEqual({...expected[category],...(category==="budget"?{monthly_amount:"650"}:{})});}
    await page.screenshot({path:testInfo.outputPath(`repair-confirmation-${category}-320.png`)});
    await dialog.getByRole("button",{name:"Repair selected objects",exact:true}).click();
    const matched=page.getByRole("heading",{name:labels[category],exact:true}).locator("..").getByText("Matching",{exact:true});
    await expect(matched).toBeVisible();
    repaired.add(category);
    for(const other of ["policy","quota","budget","tags"] as const){
      const row=page.getByRole("heading",{name:labels[other],exact:true}).locator("..");
      await expect(row.getByText(repaired.has(other)?"Matching":other==="quota"?"Missing":"Different",{exact:true})).toBeVisible();
    }
  }
  await expect(page.getByText("Selected objects verified. Current check results are shown below.")).toBeVisible();
  await expect(page.getByRole("button",{name:"Repair configuration",exact:true})).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button",{name:"Repair configuration",exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});
