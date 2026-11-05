import { expect, type Page } from "@playwright/test";
import { resolve } from "node:path";

// Save literal recipes through real HTTPS and SQL grants without changing any tenancy assignment.
export async function baselineAuthoring(page: Page, reviewLatest=false) {
  await page.getByRole("link", { name: "Configuration", exact: true }).click();
  await page.getByRole("button", { name: "New baseline", exact: true }).click();
  const policy = Array.from({ length: 50 }, (_,i) => `Allow group Example${i+1} to inspect instances in tenancy`).join("\n");
  await page.getByLabel("Policy statements", { exact: true }).fill(policy);
  await page.getByLabel("Quota statements", { exact: true }).fill(Array.from({ length: 50 }, (_,i) => `Set compute-core quota example-${i+1} to 4 in tenancy`).join("\n"));
  await page.getByLabel("Monthly amount", { exact: true }).fill("250");
  await page.getByLabel("Currency code", { exact: true }).fill("USD");
  await page.getByRole("button", { name: "Add tag default", exact: true }).click();
  await page.getByLabel("Tag key 1", { exact: true }).fill("Environment");
  await page.getByLabel("Static value 1", { exact: true }).fill("Test");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width <= 390) {
      const amount = await page.getByLabel("Monthly amount", { exact: true }).boundingBox();
      const currency = await page.getByLabel("Currency code", { exact: true }).locator("..").boundingBox();
      expect(currency!.y - amount!.y - amount!.height).toBeGreaterThanOrEqual(16);
    }
    await page.screenshot({ path: resolve(".local-dev/browser", `baseline-authoring-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status").filter({hasText:"Baseline draft saved."})).toHaveText("Baseline draft saved.");
  const first = await (await page.request.get("/api/configuration/baselines")).json();
  expect(first.draft.content.policy_statements).toEqual(policy.split("\n"));
  expect(first.draft.content.quota_statements).toHaveLength(50);
  expect(first.draft.content.monthly_budget_amount).toBe("250.0000");
  expect(first.draft.content.tag_defaults).toEqual([{ key: "Environment", value: "Test" }]);
  expect(first.draft.edit_revision).toBe(1);
  expect((await page.reload())?.status()).toBe(200);
  await page.getByRole("button", { name: "Open draft", exact: true }).click();
  await page.screenshot({ path: resolve(".local-dev/browser", "baseline-after-reopen.png"), fullPage: true });
  await expect(page.getByLabel("Policy statements", { exact: true })).toHaveValue(policy);
  await expect(page.getByLabel("Monthly amount", { exact: true })).toHaveValue("250");
  await page.getByLabel("Monthly amount", { exact: true }).fill("500");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status").filter({hasText:"Baseline draft saved."})).toHaveText("Baseline draft saved.");
  const changed = await (await page.request.get("/api/configuration/baselines")).json();
  expect(changed.draft.edit_revision).toBe(2);
  expect(changed.draft.content.monthly_budget_amount).toBe("500.0000");
  await page.goto(`/configuration?baseline=${first.draft.id}`);
  await expect(page.getByRole("button", { name: "Open draft", exact: true })).toBeVisible();
  await page.goto("/configuration?baseline=00000000-0000-4000-8000-000000000099");
  await expect(page.getByRole("alert")).toContainText("This baseline is not available.");
  await page.getByRole("link", { name: "Return to Configuration", exact: true }).click();
  await expect(page.getByRole("button", { name: "Open draft", exact: true })).toBeVisible();
  // Publish the exact saved revision with explicit local-only qualification, then inspect immutable history.
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("No tenancy will be changed.");
  await expect(page.getByRole("heading",{name:"Publish baseline v1?",exact:true})).toBeFocused();
  await page.setViewportSize({width:320,height:500});
  const publishDialog=page.getByRole("dialog");
  expect(await publishDialog.evaluate(element=>element.getBoundingClientRect().height<=innerHeight-32)).toBe(true);
  await page.screenshot({path:resolve(".local-dev/browser","baseline-publish-modal-320.png"),fullPage:true});
  await page.setViewportSize({width:1280,height:900});
  // Resolve the final desktop geometry after resizing the previously scrolled mobile dialog.
  const cancelPublication = page.getByRole("button", { name: "Cancel", exact: true });
  await cancelPublication.scrollIntoViewIfNeeded();
  await expect(cancelPublication).toBeInViewport();
  await cancelPublication.click();
  await page.getByRole("button", { name: "Publish", exact: true }).click();
  await page.getByRole("button", { name: "Publish baseline", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Published baseline v1", exact: true })).toBeVisible();
  await expect(page.getByLabel("Policy statements", { exact: true })).toHaveAttribute("readonly", "");
  await expect(page.getByText("500 USD / month", { exact: true })).toBeVisible();
  const immutable = await (await page.request.get("/api/configuration/baselines")).json();
  expect(immutable.draft).toBeNull();
  expect(immutable.latest.id).toBe(first.draft.id);
  expect(immutable.latest.publication_mode).toBe("simulated");
  for (const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`baseline-published-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole("link",{name:/Back to baselines/}).click();
  await expect(page.getByText("Latest published",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"New baseline",exact:true}).click();
  await expect(page.getByLabel("Policy statements",{exact:true})).toHaveValue(policy);
  await expect(page.getByLabel("Monthly amount",{exact:true})).toHaveValue("500");
  await page.getByLabel("Monthly amount",{exact:true}).fill("750");
  await page.getByRole("button",{name:"Save draft",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"Baseline draft saved."})).toHaveText("Baseline draft saved.");
  const derived=await(await page.request.get("/api/configuration/baselines")).json();
  expect(derived.draft.version_number).toBe(2);
  expect(derived.draft.based_on_id).toBe(first.draft.id);
  expect(derived.latest.content.monthly_budget_amount).toBe("500.0000");
  for (const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:resolve(".local-dev/browser",`baseline-history-${width}.png`),fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  if (reviewLatest) {
    await page.getByRole("button",{name:"Publish",exact:true}).click();
    await page.getByRole("button",{name:"Publish baseline",exact:true}).click();
    await expect(page.getByRole("heading",{name:"Published baseline v2",exact:true})).toBeVisible();
    await page.getByRole("link",{name:/Back to baselines/}).click();
    expect((await(await page.request.get("/api/configuration/baselines")).json()).latest.version_number).toBe(2);
    await expect(page.getByRole("button",{name:"Use for new",exact:true})).toHaveCount(0);
    const history=await(await page.request.get("/api/configuration/baselines")).json();
    expect(history).not.toHaveProperty("current");
    for(const width of [1280,390,320]) {
      await page.setViewportSize({width,height:900});
      await page.getByRole("region",{name:"Baseline versions",exact:true}).scrollIntoViewIfNeeded();
      await page.screenshot({path:resolve(".local-dev/browser",`baseline-latest-only-${width}.png`),fullPage:false});
    }
    await page.setViewportSize({width:1280,height:900});
    await page.getByRole("button",{name:"New baseline",exact:true}).click();
    await expect(page.getByLabel("Monthly amount",{exact:true})).toHaveValue("750");
    await page.getByRole("button",{name:"Cancel",exact:true}).click();
  }

}
