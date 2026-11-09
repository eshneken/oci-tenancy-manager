import { expect, type Page } from "@playwright/test";
import { resolve } from "node:path";

// Exercise first-import gating and explicit typed-email setup against the installed restricted API.
export async function initialMapping(page: Page) {
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Upload organization CSV" }),
  ).toBeDisabled();
  const denied = await page.request.post("/api/organization/feeds", {
    headers: {
      "content-type": "text/csv",
      origin: new URL(page.url()).origin,
      "x-otm-request": "1",
      "x-otm-as-of": new Date(Date.now() - 60_000).toISOString(),
      "x-otm-delivery": crypto.randomUUID(),
      "x-otm-complete": "true",
    },
    data: "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nRoot,root@example.test,,\n",
  });
  expect(denied.status()).toBe(409);
  await page
    .getByRole("link", { name: "Organization Mapping", exact: true })
    .click();
  await page
    .getByLabel("Root manager email", { exact: true })
    .fill("root@example.test");
  await page.getByLabel("Segment name", { exact: true }).fill("Industry One");
  await page
    .getByLabel("Leader email", { exact: true })
    .fill("one@example.test");
  await page
    .getByLabel("Designee emails (optional)", { exact: true })
    .fill("delegate@example.test");
  await page.getByRole("button", { name: "Add industry segment" }).click();
  await page
    .getByLabel("Segment name", { exact: true })
    .nth(1)
    .fill("Industry Two");
  await page
    .getByLabel("Leader email", { exact: true })
    .nth(1)
    .fill("two@example.test");
  await expect(page.getByLabel("Leader email").first()).not.toHaveAttribute(
    "list",
  );
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `mapping-editor-${width}.png`),
      fullPage: true,
    });
  }
  await page
    .getByRole("button", { name: "Preview changes", exact: true })
    .click();
  await expect(
    page.getByText(
      "Employee impact cannot be calculated until the first feed.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to editing" }).click();
  // Editing a previewed form must remove Apply until the updated candidate is reviewed again.
  await page
    .getByLabel("Segment name", { exact: true })
    .first()
    .fill("Industry One revised");
  await expect(page.getByRole("button", { name: "Apply changes" })).toHaveCount(
    0,
  );
  await page
    .getByLabel("Segment name", { exact: true })
    .first()
    .fill("Industry One");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByRole("dialog", { name: "Mapping change preview" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("heading", { name: "Mapping change preview" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Preview changes" }),
  ).toBeFocused();
  // Long synthetic nominations stay in the preview only and never enter saved settings.
  await page
    .getByLabel("Designee emails (optional)")
    .first()
    .fill(
      "delegate@example.test\n" + "longemployee".repeat(8) + "@example.test",
    );
  await page.getByRole("button", { name: "Preview changes" }).click();
  const review = page.getByRole("dialog", { name: "Mapping change preview" });
  await expect(
    review.getByRole("heading", { name: "Mapping change preview" }),
  ).toBeFocused();
  const apply = page.getByRole("button", { name: "Apply changes" });
  await expect(apply).toBeEnabled();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      await review.evaluate((node) => node.scrollWidth <= node.clientWidth),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `mapping-initial-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Back to editing" }).click();
  await page
    .getByLabel("Designee emails (optional)")
    .first()
    .fill("delegate@example.test");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(apply).toBeEnabled();
  await apply.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Organization mapping applied/)).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Upload organization CSV" }),
  ).toBeEnabled();
}

// Verify independent role defects remain after no-tenancy offboarding, then repair actual mappings.
export async function departedMapping(page: Page) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page
    .getByRole("link", { name: "Organization Mapping", exact: true })
    .click();
  await expect(page.getByLabel("Root manager email")).toHaveAttribute(
    "readonly",
    "",
  );
  const lookup = page.getByLabel("Find designee for segment 1", {
    exact: true,
  });
  await lookup.fill("Deleg");
  await expect(
    page.locator('#mapping-employees option[value="delegate@example.test"]'),
  ).toHaveCount(1);
  await lookup.fill("delegate@example.test");
  const lookupBox = await lookup.boundingBox();
  const addBox = await page
    .getByRole("button", { name: "Add designee", exact: true })
    .first()
    .boundingBox();
  expect(
    Math.abs(lookupBox!.y + lookupBox!.height - (addBox!.y + addBox!.height)),
  ).toBeLessThanOrEqual(1);
  // Real lookup and email editing remain usable as the compact row stacks on narrow viewports.
  for (const width of [1280, 900, 768, 600, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    const search = (await lookup.boundingBox())!;
    const list = (await page
      .getByLabel("Designee emails (optional)")
      .first()
      .boundingBox())!;
    const add = (await page
      .getByRole("button", { name: "Add designee", exact: true })
      .first()
      .boundingBox())!;
    expect(search.width).toBeGreaterThanOrEqual(160);
    if (width > 480)
      expect(
        Math.abs(search.y + search.height - (add.y + add.height)),
      ).toBeLessThanOrEqual(1);
    else expect(add.y).toBeGreaterThan(search.y + search.height);
    if (width > 1100) {
      expect(list.x).toBeGreaterThan(search.x + search.width);
      expect(Math.abs(search.y - list.y)).toBeLessThanOrEqual(1);
    } else expect(list.y).toBeGreaterThan(search.y + search.height);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `mapping-designees-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page
    .getByRole("button", { name: "Add designee", exact: true })
    .first()
    .focus();
  await page.keyboard.press("Enter");
  await page
    .getByLabel("Designee emails (optional)")
    .first()
    .fill("one@example.test\ndelegate@example.test");
  await page
    .getByLabel("Designee emails (optional)")
    .nth(1)
    .fill("delegate@example.test");
  await page.getByRole("button", { name: "Preview changes" }).click();
  const application = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/organization/mapping/apply") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Apply changes" }).click();
  const applied = await application;
  expect(applied.status()).toBe(200);
  await expect(page.getByText(/Organization mapping applied/)).toBeVisible();
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await page.getByRole("button", { name: "Upload organization CSV" }).click();
  await page.getByLabel("Organization CSV", { exact: true }).setInputFiles({
    name: "departures.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nRoot,root@example.test,,\nLeader Two,two@example.test,root@example.test,root@example.test\nDelegate,delegate@example.test,root@example.test,root@example.test\n",
    ),
  });
  await page
    .getByLabel("Organization data as of (UTC)", { exact: true })
    .fill(new Date(Date.now() - 10 * 60_000).toISOString().slice(0, 16));
  await page.getByRole("button", { name: "Process feed", exact: true }).click();
  await expect(page.getByText(/Organization feed processed/)).toBeVisible();
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  // An unmapped branch cannot provision, but its departing leader can still be offboarded.
  const employeeMappingReview = page
    .getByRole("row")
    .filter({ hasText: "delegate@example.test" })
    .filter({ hasText: "Industry segment mapping review" });
  await expect(employeeMappingReview).toBeVisible();
  const nominee = page
    .getByRole("row")
    .filter({ hasText: "delegate@example.test" })
    .filter({ hasText: "Designee needs attention" })
    .first();
  await nominee.getByRole("button", { name: "Delegate", exact: true }).click();
  const blocked = page.getByRole("dialog");
  await expect(
    blocked.getByText(/Organization mapping must be corrected before/),
  ).toBeVisible();
  const blockedActions = blocked.getByRole("combobox", {
    name: "Action",
    exact: true,
  });
  for (const name of [
    "Create tenancy",
    "Import tenancy",
    "Add to shared tenancy",
  ])
    await expect(
      blockedActions.getByRole("option", { name, exact: true }),
    ).toHaveCount(0);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await blocked
      .getByText(/Organization mapping must be corrected before/)
      .scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `mapping-required-${width}.png`),
      fullPage: false,
    });
  }
  await blocked
    .getByRole("link", { name: "Repair Organization Mapping", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Organization Mapping", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  const leaderAbsence = page
    .getByRole("row")
    .filter({ hasText: "one@example.test" })
    .filter({ hasText: "Absence review" });
  await leaderAbsence
    .getByRole("button", { name: "Review", exact: true })
    .click();
  const modal = page.getByRole("dialog");
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("offboard_person");
  await modal
    .getByRole("checkbox", { name: /I verified that no tenancy associations/ })
    .check();
  await modal.getByRole("checkbox", {name:/I acknowledge the consequences/}).check();
  await modal
    .getByRole("button", { name: "Offboard employee", exact: true })
    .click();
  await expect(
    modal.getByText("Decision saved", { exact: true }),
  ).toBeVisible();
  await modal.getByRole("button", { name: "Done", exact: true }).click();
  const role = page
    .getByRole("row")
    .filter({ hasText: "one@example.test" })
    .filter({ hasText: "Leader needs attention" });
  await role.getByRole("link", { name: "Repair mapping", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Organization Mapping", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Industry One: Leader needs attention", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Industry Two: Designee needs attention", { exact: true }),
  ).toBeVisible();
  const leader = page.getByLabel("Leader email", { exact: true }).first();
  await expect(leader).toHaveValue("one@example.test");
  await leader.fill("delegate@example.test");
  await page
    .getByLabel("Segment name", { exact: true })
    .first()
    .fill("Renewed Industry");
  for (const field of await page.getByLabel("Designee emails (optional)").all())
    await field.fill("");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByRole("button", { name: "Apply changes" }),
  ).toBeEnabled();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `mapping-departure-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Apply changes" }).click();
  await expect(page.getByText(/Organization mapping applied/)).toBeVisible();
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  const delegate = page
    .getByRole("row")
    .filter({ hasText: "delegate@example.test" });
  await expect(delegate).toContainText("Renewed Industry");
  await delegate.getByRole("button", { name: "Delegate", exact: true }).click();
  // The auth harness has no lifecycle provider; PostgreSQL/native-worker tests cover provisioning.
  await expect(
    page
      .getByRole("dialog")
      .getByRole("combobox", { name: "Action", exact: true })
      .getByRole("option", { name: "No tenancy required", exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByText(/Organization mapping must be corrected before/),
  ).toHaveCount(0);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  // Repairing the mapping cannot settle the engineer's still-unresolved independent absence.
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "delegate@example.test" })
      .filter({ hasText: "Industry segment mapping review" }),
  ).toHaveCount(0);
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "engineer@example.test" })
      .filter({ hasText: "Absence review" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
}

// Reclassification updates both real directories immediately while preserving registered tenancy IDs.
export async function mappingInventory(page: Page, tenancyName: string) {
  await page
    .getByRole("link", { name: "Organization Mapping", exact: true })
    .click();
  await page
    .getByLabel("Segment name", { exact: true })
    .first()
    .fill("Renamed Industry");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await page.getByRole("button", { name: "Apply changes" }).click();
  await expect(page.getByText(/Organization mapping applied/)).toBeVisible();
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "one@example.test" }).first(),
  ).toContainText("Renamed Industry");
  await page.getByRole("link", { name: "Tenancies", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: tenancyName }),
  ).toContainText("Renamed Industry");
  // Dissolve an unrelated segment explicitly; its rooted employees must become unassigned.
  await page
    .getByRole("link", { name: "Organization Mapping", exact: true })
    .click();
  await page.getByRole("button", { name: "Remove segment 2" }).click();
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(
    page.getByRole("dialog", { name: "Mapping change preview" }),
  ).toContainText("Removed");
  await page.getByRole("button", { name: "Back to editing" }).click();
  // Cancel the draft so later membership scenarios retain their original segment fixtures.
  await page.getByRole("button", { name: "Cancel edits" }).click();
  await expect(page.getByLabel("Segment name", { exact: true })).toHaveCount(2);
}

// Replace an absent boundary deliberately, then repair it with a real CSV while preserving cleanup.
export async function replaceOrganizationLeader(page: Page) {
  await page
    .getByRole("link", { name: "Organization Mapping", exact: true })
    .click();
  // Helper text and its action share a vertical center on desktop; mobile may wrap naturally.
  const leaderButton = await page.getByRole("button", { name: "Change organization leader" }).boundingBox();
  const helperText = await page.getByText("Changing the email replaces the reporting boundary. Changing the name updates display metadata only.").boundingBox();
  expect(leaderButton && helperText).toBeTruthy();
  expect(Math.abs((leaderButton!.y + leaderButton!.height / 2) - (helperText!.y + helperText!.height / 2))).toBeLessThan(2);
  await page.screenshot({ path: resolve(".local-dev/browser", "mapping-helper-alignment-1280.png"), fullPage: true });
  const root = page.getByLabel("Root manager email", { exact: true });
  const rootName = page.getByLabel("Root manager name", { exact: true });
  await expect(rootName).toHaveAttribute("readonly", "");
  const emailBox = await root.boundingBox(), nameBox = await rootName.boundingBox();
  expect(Math.abs(emailBox!.y - nameBox!.y)).toBeLessThan(2);
  // A display-only edit uses the same preview/apply without a boundary-replacement confirmation.
  await page.getByRole("button", { name: "Change organization leader" }).click();
  await rootName.fill("Organization Director");
  await page.getByRole("button", { name: "Preview changes" }).click();
  await expect(page.getByLabel("Organization leader name change")).toContainText("Organization Director");
  await expect(page.getByRole("checkbox", {name: /I reviewed this leader replacement/})).toHaveCount(0);
  await page.getByRole("button", { name: "Apply changes" }).click();
  await expect(rootName).toHaveAttribute("readonly", "");
  await page.reload();
  await expect(rootName).toHaveValue("Organization Director");
  for (const width of [390, 320]) {
    await page.setViewportSize({width, height:900});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: resolve(".local-dev/browser", `mapping-root-${width}.png`), fullPage:true});
  }
  await page.setViewportSize({width:1280, height:900});
  await expect(root).toHaveAttribute("readonly", "");
  await page
    .getByRole("button", { name: "Change organization leader" })
    .click();
  await expect(root).toBeFocused();
  await root.fill("discard@example.test");
  await page.getByRole("button", { name: "Cancel edits" }).click();
  await expect(root).toHaveValue("root@example.test");
  await expect(root).toHaveAttribute("readonly", "");
  await page
    .getByRole("button", { name: "Change organization leader" })
    .click();
  await root.fill("successor@example.test");
  await rootName.fill("Successor Director");
  await page.getByRole("button", { name: "Preview changes" }).click();
  const modal = page.getByRole("dialog", { name: "Mapping change preview" });
  await expect(
    modal.getByRole("heading", { name: "Mapping change preview" }),
  ).toBeFocused();
  await expect(
    modal.getByText(/new leader is not in the latest feed/),
  ).toBeVisible();
  await expect(
    modal.getByRole("button", { name: "Apply changes" }),
  ).toBeDisabled();
  await modal
    .getByRole("checkbox", { name: /I reviewed this leader replacement/ })
    .check();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await modal.evaluate((node) => node.scrollWidth <= node.clientWidth),
    ).toBe(true);
    await modal
      .getByRole("heading", { name: "Mapping change preview" })
      .focus();
    await page.screenshot({
      path: resolve(".local-dev/browser", `root-replacement-${width}.png`),
      fullPage: true,
    });
  }
  await modal.getByRole("button", { name: "Apply changes" }).click();
  await expect(page.getByText(/Organization mapping applied/)).toBeVisible();
  await expect(root).toHaveValue("successor@example.test");
  await expect(root).toHaveAttribute("readonly", "");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await page.getByRole("button", { name: "Upload organization CSV" }).click();
  await page.getByLabel("Organization CSV", { exact: true }).setInputFiles({
    name: "new-organization-leader.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\nSuccessor,successor@example.test,,\nLeader Two,two@example.test,successor@example.test,successor@example.test\nDelegate,delegate@example.test,successor@example.test,successor@example.test\n",
    ),
  });
  await page
    .getByLabel("Organization data as of (UTC)", { exact: true })
    .fill(new Date(Date.now() - 5 * 60_000).toISOString().slice(0, 16));
  await page.getByRole("button", { name: "Process feed", exact: true }).click();
  await expect(page.getByText(/Organization feed processed/)).toBeVisible();
  await page
    .getByRole("link", { name: "Organization Mapping", exact: true })
    .click();
  await expect(
    page.getByText("No role defects detected.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "root@example.test" })
      .filter({ hasText: "Absence review" }),
  ).toBeVisible();
  // The successor remains the reporting root when its own tenancy onboarding is declined.
  const successor = page.getByRole("row").filter({ hasText: "successor@example.test" }).filter({ hasText: "New employee" });
  await successor.getByRole("button", { name: "Review", exact: true }).click();
  await page.getByRole("dialog").getByRole("combobox", { name: "Action", exact: true }).selectOption("no_tenancy_required");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.getByRole("dialog").evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    await page.screenshot({ path: resolve(".local-dev/browser", `root-no-tenancy-preview-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "No tenancy required", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Decision saved", exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(".local-dev/browser", "root-no-tenancy-complete-1280.png"), fullPage: true });
  await page.getByRole("dialog").getByRole("button", { name: "Done", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(successor).toHaveCount(0);
  await page.getByRole("link", { name: "Organization Mapping", exact: true }).click();
  await expect(page.getByLabel("Root manager email", { exact: true })).toHaveValue("successor@example.test");
  await expect(page.getByText("No role defects detected.", { exact: true })).toBeVisible();
}
