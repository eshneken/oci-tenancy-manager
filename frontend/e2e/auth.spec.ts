import { baselineAuthoring } from "./baseline-authoring";
import { auditSelectPickers } from "./select-audit";
import {
  initialMapping,
  departedMapping,
  replaceOrganizationLeader,
} from "./mapping-helpers";
import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { resolve } from "node:path";

// Generate a synthetic fixture factor in memory; no authenticator seed/code enters reports or URLs.
function code(): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...process.env.OTM_E2E_SEED!]
    .map((char) => alphabet.indexOf(char).toString(2).padStart(5, "0"))
    .join("");
  const key = Buffer.from(
    bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)),
  );
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[19] & 15;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000)
    .toString()
    .padStart(6, "0");
}

// Exercise actual built JS, HTTPS cookies, SQL grants and native browser interactions together.
test("local MFA, directory controls, revocation, responsive layout and logout", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.name));
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  // Runtime branding is public, nonsecret and independent of the sign-in/session contract.
  const brandingResponse = await context.request.get("/api/branding");
  expect(brandingResponse.status()).toBe(200);
  const branding = await brandingResponse.json();
  expect(Object.keys(branding).sort()).toEqual([
    "display_name",
    "icon_url",
    "logo_url",
  ]);
  await expect(page).toHaveTitle(branding.display_name);
  await expect(page.locator(".brand")).toHaveAccessibleName(
    branding.display_name,
  );
  const logo = page.getByRole("img", {
    name: branding.display_name,
    exact: true,
  });
  await expect(logo).toHaveAttribute("src", branding.logo_url);
  await expect
    .poll(() =>
      logo.evaluate(
        (image: HTMLImageElement) => image.complete && image.naturalWidth > 0,
      ),
    )
    .toBe(true);
  await expect(
    page.locator('link[rel="icon"][data-application-branding]'),
  ).toHaveAttribute("href", branding.icon_url);
  expect((await context.request.get(branding.icon_url)).status()).toBe(200);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(logo).toBeVisible();
    await page.screenshot({
      path: resolve(".local-dev/browser", `branding-sign-in-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.OTM_E2E_PASSWORD!);
  await page.getByLabel("Authenticator code", { exact: true }).fill(code());
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/tenancies$/);
  await expect(page.getByRole("heading", { name: "Tenancies", exact: true })).toBeVisible();
  // Direct navigation and reload must serve the shell, retain the route and fetch current API data.
  for (const [route, title] of [
    ["/tenancies", "Tenancies"], ["/organization", "Organization"],
    ["/organization/drift", "Organization drift"], ["/organization-mapping", "Organization Mapping"],
    ["/operations", "Operations"], ["/audit-history", "Audit history"],
    ["/configuration", "Configuration"], ["/administrators", "Administrators"],
  ]) {
    const direct = await page.goto(route);
    expect(direct?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    const read = page.waitForResponse(response => response.url().includes("/api/") && response.request().method() === "GET");
    const refreshed = await page.reload();
    expect(refreshed?.status()).toBe(200);
    await read;
    expect(new URL(page.url()).pathname).toBe(route);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await auditSelectPickers(page, route.slice(1).replaceAll("/", "-"));
  }

  await expect(
    page.getByRole("heading", { name: "Administrators", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Protected recovery account", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".sidebar .brand")).toHaveAccessibleName(
    branding.display_name,
  );
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.locator(".sidebar .brand-logo")).toBeVisible();
    await page.screenshot({
      path: resolve(".local-dev/browser", `branding-sidebar-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  // Production organization screens use a private synthetic source policy and the restricted API role.
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Organization", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No organization feed loaded", { exact: true }),
  ).toBeVisible();
  // The local reset button only explains the privileged CLI, never executes a browser command.
  await page
    .getByRole("button", { name: "Reset test organization", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "--confirm-reset-organization",
  );
  await expect(page.getByRole("dialog")).toContainText(
    '--directory "/absolute/path/to/this/installation"',
  );
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 720 });
    const resetTitle = page.getByRole("heading", {
      name: "Reset test organization",
      exact: true,
    });
    await resetTitle.focus();
    await expect(resetTitle).toBeFocused();
    await expect(resetTitle).toBeInViewport();
    await page.screenshot({
      path: resolve(
        ".local-dev/browser",
        `organization-reset-top-${width}.png`,
      ),
      fullPage: false,
    });
    await page
      .getByRole("button", { name: "Refresh organization", exact: true })
      .scrollIntoViewIfNeeded();
    expect(
      await page
        .getByRole("dialog")
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBe(true);
    await expect(
      page.getByRole("button", { name: "Close", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(".local-dev/browser", `organization-reset-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Reset test organization", exact: true }),
  ).toBeFocused();
  await page.setViewportSize({ width: 1280, height: 900 });
  await initialMapping(page);
  const organizationCsv =
    "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n" +
    "Root,root@example.test,,\n" +
    "Leader One,one@example.test,root@example.test,root@example.test\n" +
    "Leader Two,two@example.test,root@example.test,root@example.test\n" +
    "Delegate,delegate@example.test,one@example.test,one@example.test\n" +
    "O'Connor <script>window.csvExecuted=true</script>,engineer@example.test,one@example.test,one@example.test\n";
  // Fixed earlier source times let later snapshots advance without waiting on a wall clock.
  const captured = new Date(Date.now() - 30 * 60_000)
    .toISOString()
    .slice(0, 16);
  await page.getByRole("button", { name: "Upload organization CSV" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("Organization CSV", { exact: true }).setInputFiles({
    name: "malformed.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("WRONG,HEADERS\n"),
  });
  await page.getByRole("button", { name: "Process feed", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Expected exactly these headers",
  );
  await page.getByLabel("Organization CSV", { exact: true }).setInputFiles({
    name: "organization.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(organizationCsv),
  });
  await page
    .getByLabel("Organization data as of (UTC)", { exact: true })
    .fill(captured);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 720 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("button", { name: "Process feed", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(".local-dev/browser", `organization-upload-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Process feed", exact: true }).click();
  await expect(
    page.getByText(
      "Organization feed processed. Valid metadata is up to date.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByText("O'Connor <script>window.csvExecuted=true</script>", {
      exact: true,
    }),
  ).toBeVisible();
  expect(await page.evaluate(() => "csvExecuted" in window)).toBe(false);
  const firstOrg = await (
    await context.request.get("/api/organization")
  ).json();
  expect(firstOrg.employee_count).toBe(5);
  expect(
    firstOrg.findings.some(
      (finding: { code: string }) => finding.code === "TOP_MANAGER_MISMATCH",
    ),
  ).toBe(false);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(
        ".local-dev/browser",
        `organization-directory-${width}.png`,
      ),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("searchbox").fill("O'Connor");
  await expect(
    page.getByText("1 employee · Page 1 of 1", { exact: true }),
  ).toBeVisible();
  await page.getByRole("searchbox").fill("");
  await page.getByRole("button", { name: "Email", exact: false }).click();
  await page.getByRole("button", { name: "Upload organization CSV" }).click();
  await page.getByLabel("Organization CSV", { exact: true }).setInputFiles({
    name: "absence.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      organizationCsv
        .split("\n")
        .filter((line) => !line.includes("engineer@example.test"))
        .join("\n"),
    ),
  });
  await page
    .getByLabel("Organization data as of (UTC)", { exact: true })
    .fill(new Date(Date.now() - 20 * 60_000).toISOString().slice(0, 16));
  await page.getByRole("button", { name: "Process feed", exact: true }).click();
  await expect(page.getByText("Absence review", { exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await expect(page.getByText("Absence review", { exact: true })).toBeVisible();
  await page.screenshot({
    path: resolve(".local-dev/browser", "organization-drift-1280.png"),
    fullPage: true,
  });
  // Navigation reflects all open actionable reviews even while the page shows a different scope.
  const driftLink = page.getByRole("link", { name: "Organization drift", exact: true });
  const reviewCounts = await (await page.request.get("/api/organization/reviews")).json();
  await expect(driftLink.locator(".nav-count")).toHaveText(String(reviewCounts.actionable_count));
  await expect(driftLink).toHaveAccessibleDescription(`${reviewCounts.actionable_count} actionable organization reviews`);
  // Geometry-only fixture: render a three-digit count with real production CSS, then restore data.
  const badge = driftLink.locator(".nav-count");
  const actualCount = await badge.textContent();
  await badge.evaluate(node => { node.textContent = "125"; });
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await driftLink.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    const box = await badge.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(24);
    await page.screenshot({ path: resolve(".local-dev/browser", `navigation-count-layout-${width}.png`), fullPage: true });
  }
  await badge.evaluate((node, value) => { node.textContent = value; }, actualCount);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: /Informational & history/ }).click();
  await expect(
    page.getByText("5 employees in the initial baseline.", { exact: true }),
  ).not.toBeVisible();
  const historyScope = page.getByRole("checkbox", { name: "Show all history" });
  await expect(historyScope).not.toBeChecked();
  await historyScope.check();
  await expect(page.getByText("5 employees in the initial baseline.", { exact: true })).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(".local-dev/browser", `organization-history-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await historyScope.uncheck();
  await expect(page.getByText("5 employees in the initial baseline.", { exact: true })).not.toBeVisible();
  await departedMapping(page);
  await replaceOrganizationLeader(page);
  await baselineAuthoring(page,true);
  await page.getByRole("link", { name: "Administrators", exact: true }).click();
  const cookie = (await context.cookies()).find(
    (value) => value.name === "__Host-otm_session",
  );
  expect(
    Boolean(cookie?.secure && cookie.httpOnly && cookie.sameSite === "Lax"),
  ).toBe(true);
  // Verify real queued/simulated-completed operation records and native list/detail navigation.
  await page.getByRole("link", { name: "Operations", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Operations", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search operations").fill("browserverified");
  await expect(
    page.getByRole("link", { name: /Import inspection/ }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("table").getByText("Succeeded", { exact: true }),
  ).toBeVisible();
  expect(
    await page
      .getByRole("table")
      .getByText("Succeeded", { exact: true })
      .evaluate((element) => getComputedStyle(element).whiteSpace),
  ).toBe("nowrap");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("table").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: resolve(".local-dev/browser", `operations-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("link", { name: /Import inspection/ }).press("Enter");
  await expect(
    page.getByRole("heading", { name: "Import inspection", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("TENANCY_INSPECTED", { exact: true }),
  ).toHaveCount(2);
  await expect(
    page.getByText(
      "Inspection completed successfully. This tenancy has not been adopted by this inspection.",
    ),
  ).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `operation-detail-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("link", { name: /Back to operations/ }).click();
  await expect(page.getByLabel("Search operations")).toHaveValue(
    "browserverified",
  );
  await page.getByRole("link", { name: /Import inspection/ }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Import inspection", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Back to operations/ }).click();
  await page.getByLabel("Search operations").fill("browsersandbox");
  await expect(
    page.getByRole("table").getByText("Queued", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Administrators", exact: true }).click();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(
    page.getByRole("button", { name: "Add administrator" }),
  ).toBeDisabled();
  await page.getByLabel("Search administrators").fill("Synthetic corporate");
  await expect(
    page.getByText("Synthetic corporate", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Revoke", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Revoke", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /Revoke/ })
    .click();
  await expect(page.getByText("Revoked", { exact: true })).toBeVisible();
  await page.getByLabel("Search administrators").fill("");
  await expect(
    page.getByText("Protected recovery account", { exact: true }),
  ).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      JSON.stringify(
        await page.evaluate(() =>
          [...document.querySelectorAll("body *")]
            .filter(
              (element) =>
                element.getBoundingClientRect().right > innerWidth &&
                !element.closest(".table-scroll"),
            )
            .map((element) => ({
              tag: element.tagName,
              class: element.className,
              text: element.textContent?.slice(0, 60),
              right: element.getBoundingClientRect().right,
            })),
        ),
      ),
    ).toBe(true);
    await expect(
      page.getByText("LOCAL ENVIRONMENT", { exact: true }),
    ).toBeVisible();
    expect(
      await page
        .getByRole("button", { name: "Sign out" })
        .evaluate((element) => element.getBoundingClientRect().height),
    ).toBeGreaterThanOrEqual(44);
    await page.locator(".table-scroll").evaluate((element) => {
      element.scrollLeft = 0;
    });
    await page.getByRole("table").scrollIntoViewIfNeeded();
    await page.screenshot({
      path: resolve(".local-dev/browser", `administrators-${width}.png`),
      fullPage: true,
    });
  }
  // History is retrospective and uses the real event formats and restricted API role.
  await page.getByRole("link", { name: "Audit history", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Audit history", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Category", { exact: true })
    .selectOption("organization");
  const categoryFilter = page.getByLabel("Category", { exact: true });
  for (const width of [1280, 900, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect((await categoryFilter.boundingBox())!.width).toBeGreaterThanOrEqual(
      192,
    );
    await categoryFilter.click();
    const adminOption = categoryFilter.getByRole("option", {
      name: "Administration",
      exact: true,
    });
    await expect(adminOption).toBeVisible();
    const optionHeights = await categoryFilter
      .locator("option")
      .evaluateAll((options) =>
        options.map((option) => option.getBoundingClientRect().height),
      );
    expect(
      Math.max(...optionHeights) - Math.min(...optionHeights),
    ).toBeLessThanOrEqual(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `audit-category-${width}.png`),
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await expect(categoryFilter).toBeFocused();
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  const mappingAudit = page
    .getByRole("row")
    .filter({ hasText: "Updated organization mappings" })
    .first();
  const disclosure = mappingAudit.locator("summary");
  await expect(disclosure).toBeVisible();
  await disclosure.focus();
  await page.keyboard.press("Enter");
  await expect(mappingAudit.locator("details")).toHaveAttribute("open", "");
  await expect(
    mappingAudit.getByText(
      "Organization leader: root@example.test → successor@example.test",
      { exact: true },
    ),
  ).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    const tableViewport = page.getByRole("region", {
      name: "Scrollable audit history table",
    });
    await tableViewport.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
    });
    await disclosure.scrollIntoViewIfNeeded();
    await disclosure.focus();
    await mappingAudit
      .locator("details")
      .evaluate((element) =>
        element.scrollIntoView({ block: "center", inline: "nearest" }),
      );
    await expect(disclosure).toBeInViewport();
    await expect(
      mappingAudit.getByText(
        "Organization leader: root@example.test → successor@example.test",
        { exact: true },
      ),
    ).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect((await disclosure.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await page.screenshot({
      path: resolve(".local-dev/browser", `audit-mapping-details-${width}.png`),
      fullPage: false,
    });
  }
  await page.keyboard.press("Enter");
  await expect(mappingAudit.locator("details")).not.toHaveAttribute("open");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByLabel("Category", { exact: true }).selectOption("operations");
  const filteredAudit = page.waitForResponse(
    (response) =>
      response.url().includes("/api/audit-history?") &&
      new URL(response.url()).searchParams.get("query") === "Inspection worker",
  );
  await page.getByLabel("Search audit history").fill("Inspection worker");
  await filteredAudit;
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(3);
  await expect(
    page.getByRole("button", { name: "Refresh", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("table").getByText("Inspection worker", { exact: true }),
  ).toHaveCount(2);
  // Native datetime-local fields can retain five-digit years despite max; invalid input stays local.
  await page
    .getByLabel("From (UTC)", { exact: true })
    .fill("10000-01-01T00:00");
  await expect(page.getByRole("alert")).toContainText(
    "Enter valid UTC dates between years 0001 and 9999",
  );
  await expect(
    page.getByRole("button", { name: "Export CSV", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(3);
  await page.getByLabel("From (UTC)", { exact: true }).fill("");
  await expect(page.getByRole("alert")).toHaveCount(0);
  // UTC bounds filter recorded events; invalid intervals never issue an invalid export.
  await page.getByLabel("From (UTC)", { exact: true }).fill("2100-01-01T00:00");
  await page
    .getByLabel("Before (UTC)", { exact: true })
    .fill("2000-01-01T00:00");
  await expect(page.getByRole("alert")).toContainText(
    "From must be earlier than Before",
  );
  await expect(
    page.getByRole("button", { name: "Export CSV", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("From (UTC)", { exact: true }).fill("2000-01-01T00:00");
  await page
    .getByLabel("Before (UTC)", { exact: true })
    .fill("2100-01-01T00:00");
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(3);
  await expect(
    page.getByRole("button", { name: "Export CSV", exact: true }),
  ).toBeEnabled();
  const preparing = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().endsWith("/api/audit-history/export"),
  );
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const request = await preparing;
  expect(request.postDataJSON()).toEqual({
    category: "operations",
    query: "Inspection worker",
    sort: "at",
    direction: "desc",
    from_at: "2000-01-01T00:00:00.000Z",
    to_at: "2100-01-01T00:00:00.000Z",
  });
  const download = await downloading;
  expect(download.suggestedFilename()).toBe("audit-history.csv");
  const stream = await download.createReadStream();
  let csv = "";
  for await (const chunk of stream!) csv += chunk.toString("utf8");
  expect(csv.replace(/^\uFEFF/, "").split("\r\n")[0]).toBe(
    '"id","at","kind","category","actor_name","operation_id","administrator_id","administrator_name","safe_code","organization_subject_name","summary","changes"',
  );
  expect(csv.trim().split("\r\n")).toHaveLength(3);
  expect(csv).toContain("Inspection worker");
  expect(csv).not.toContain("actor_snapshot");
  await expect(
    page.getByText("Export prepared. Your browser download has started.", {
      exact: true,
    }),
  ).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(page.getByRole("table").getByRole("row")).toHaveCount(3);
    await expect(
      page.getByRole("button", { name: "Refresh", exact: true }),
    ).toBeEnabled();
    await page.getByRole("table").scrollIntoViewIfNeeded();
    // Search remains useful when dates and actions wrap rather than shrinking to a few characters.
    expect(
      (await page.getByLabel("Search audit history").boundingBox())?.width,
    ).toBeGreaterThanOrEqual(200);
    // Column layout must keep normal touch-target heights instead of treating flex widths as heights.
    for (const control of await page
      .locator(".audit-toolbar > .button")
      .all()) {
      const bounds = await control.boundingBox();
      expect(bounds?.height).toBeGreaterThanOrEqual(44);
      expect(bounds?.height).toBeLessThanOrEqual(64);
    }
    await page.screenshot({
      path: resolve(".local-dev/browser", `audit-history-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("table").getByRole("link").first().click();
  await expect(
    page.getByRole("heading", { name: "Import inspection", exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("Search audit history")).toHaveValue(
    "Inspection worker",
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Audit history", exact: true }),
  ).toBeVisible();
  // Real source receipt/publication events are visible without leaking employee rows.
  await page.getByLabel("Search audit history").fill("");
  await page
    .getByLabel("Category", { exact: true })
    .selectOption("organization");
  await expect(
    page.getByText("Organization metadata applied", { exact: true }).first(),
  ).toBeVisible();
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.screenshot({
      path: resolve(
        ".local-dev/browser",
        `organization-audit-populated-${width}.png`,
      ),
      fullPage: true,
    });
  }
  await page
    .getByLabel("Category", { exact: true })
    .selectOption("administration");
  await expect(
    page.getByRole("table").getByText("Database operator", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table").getByText("Audit export prepared", { exact: true }),
  ).toBeVisible();
  const target = page
    .getByRole("table")
    .locator(".audit-target")
    .filter({ hasText: "Administrator" })
    .first();
  await expect(target.locator("strong")).not.toHaveText("Name unavailable");
  await expect(target.locator(".technical-id")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect(
    (await context.cookies()).some(
      (value) => value.name === "__Host-otm_session",
    ),
  ).toBe(false);
  expect((await context.request.get("/api/administrators")).status()).toBe(401);
  await page.screenshot({
    path: resolve(".local-dev/browser/sign-in-320.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
