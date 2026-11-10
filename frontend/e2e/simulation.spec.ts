import {recoveryAccess} from "./recovery-access";
import {keepOwnershipRoundTrip,removeFormerOwner} from "./ownership-transfer";
import {tenancyOverrides} from "./tenancy-overrides";
import {existingCompartmentMembership} from "./shared-membership";
import {configurationUpdates} from "./configuration-updates";
import { baselineAuthoring } from "./baseline-authoring";
import { auditSelectPickers } from "./select-audit";
import { initialMapping, mappingInventory } from "./mapping-helpers";
import { test, expect, type Page } from "@playwright/test";
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

// Submit through real HTTPS/SQL admission and wait for an independent native worker's publication.
test("submit simulated success and access failure through a real separate worker", async ({
  page,
}) => {
  test.setTimeout(210_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.name));
  await page.goto("/login");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.OTM_E2E_PASSWORD!);
  await page
    .getByLabel("Authenticator code", { exact: true })
    .fill(authenticatorCode());
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Operations", exact: true }).click();
  await page
    .getByRole("button", { name: "Run simulated inspection", exact: true })
    .click();
  const modal = page.getByRole("dialog");
  await expect(modal.getByRole("button", { name: "Cancel" })).toBeFocused();
  await modal
    .getByLabel("Synthetic target")
    .selectOption("ocid1.tenancy.oc1..otmsimhealthy");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `simulation-form-${width}.png`),
      fullPage: true,
    });
  }
  const response = page.waitForResponse(
    (value) =>
      value.url().endsWith("/api/operations/inspect") &&
      value.request().method() === "POST",
  );
  await modal
    .getByRole("button", { name: "Run simulated inspection", exact: true })
    .click();
  const accepted = await response;
  expect(accepted.status()).toBe(202);
  expect(Object.keys(accepted.request().postDataJSON()).sort()).toEqual([
    "client_request_key",
    "tenancy_ocid",
  ]);
  await expect(page.getByText("Succeeded", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await expect(
    page.getByText("TENANCY_INSPECTED", { exact: true }),
  ).toHaveCount(2);
  await page.getByRole("link", { name: /Back to operations/ }).click();
  await page
    .getByRole("button", { name: "Run simulated inspection", exact: true })
    .click();
  await modal
    .getByLabel("Synthetic target")
    .selectOption("ocid1.tenancy.oc1..otmsimaccessdenied");
  await modal
    .getByRole("button", { name: "Run simulated inspection", exact: true })
    .click();
  await expect(page.getByText("ACCESS_DENIED", { exact: true })).toHaveCount(
    2,
    { timeout: 20000 },
  );
  await expect(
    page.getByText("Simulation issue", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Simulation ended with an issue. No action is required.", {
      exact: true,
    }),
  ).toBeVisible();
  // A read-only failed diagnostic stays in history but creates no actionable workload badge.
  await expect.poll(async () => (await (await page.request.get("/api/operations")).json()).attention_count).toBe(0);
  const operationsNavigation = page.getByRole("link", { name: "Operations", exact: true });
  await expect(operationsNavigation.locator(".nav-count")).toHaveCount(0, { timeout: 10000 });
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.screenshot({
      path: resolve(".local-dev/browser", `simulation-issue-${width}.png`),
      fullPage: true,
    });
  }
  await page.getByRole("link", { name: /Back to operations/ }).click();
  await expect(
    page
      .getByRole("table")
      .getByText("Simulation issue", { exact: true })
      .first(),
  ).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("table").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: resolve(".local-dev/browser/simulation-issue-list-1280.png"),
    fullPage: true,
  });
  await page.goBack();
  await page.reload();
  await expect(page.getByText("ACCESS_DENIED", { exact: true })).toHaveCount(2);
  await organizationFlows(page);
  expect(errors).toEqual([]);
});

// Exercise the actual organization UI, restricted API role and native lifecycle worker with synthetic feeds.
async function organizationFlows(page: Page) {
  let userRefreshCaptured=false;
  page.setDefaultTimeout(10_000);
  const rows = [
    "Root,root@example.test,,",
    "Leader One,one@example.test,root@example.test,root@example.test",
    "Leader Two,two@example.test,root@example.test,root@example.test",
    "Delegate,delegate@example.test,one@example.test,one@example.test",
    "Engineer,engineer@example.test,one@example.test,one@example.test",
  ];
  let uploadIndex = 0;
  const modal = page.getByRole("dialog");
  const employeeReview = page.getByRole("row").filter({hasText:"new@example.test"});

  // Distinct qualified source times keep successive observations ordered without wall-clock waits.
  async function upload(values: string[]) {
    await page.getByRole("link", { name: "Organization", exact: true }).click();
    await page.getByRole("button", { name: "Upload organization CSV" }).click();
    await page.getByLabel("Organization CSV", { exact: true }).setInputFiles({
      name: "synthetic.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "EMPLOYEE_FULL_NAME,EMAIL,MGR,TOP_MGR\n" + values.join("\n") + "\n",
      ),
    });
    await page
      .getByLabel("Organization data as of (UTC)", { exact: true })
      .fill(
        new Date(Date.now() - (40 - uploadIndex++) * 60_000)
          .toISOString()
          .slice(0, 16),
      );
    // Await this upload's committed receipt, not a success notice retained from an earlier feed.
    const delivery=page.waitForResponse(response=>response.url().endsWith("/api/organization/feeds")&&response.request().method()==="POST");
    await page
      .getByRole("button", { name: "Process feed", exact: true })
      .click();
    const response=await delivery;expect(response.ok()).toBe(true);expect((await response.json()).state).toBe("published");
    await expect(page.getByRole("heading",{name:"Upload organization CSV",exact:true})).not.toBeVisible();
    await expect(
      page.getByText(
        "Organization feed processed. Valid metadata is up to date.",
        { exact: true },
      ),
    ).toBeVisible();
  }

  let sharedName = "",
    personalName = "";
  // Acceptance closes the handoff; verified completion is observed separately in real Operations.
  let defaultAdvanced=false;
  let latestVersion=1;
  let assignmentRenderReviewed=false;
  async function finish(action: string) {
    if (action === "Create tenancy") {
      await modal
        .getByLabel("Requested tenancy name", { exact: true })
        .fill("sandbox" + Date.now().toString());
      await modal
        .getByRole("combobox", { name: "Home region", exact: true })
        .selectOption("us-phoenix-1");
      const requestedName=await modal.getByLabel("Requested tenancy name",{exact:true}).inputValue();
      await modal.getByRole("link",{name:`Version ${latestVersion}`,exact:true}).click();
      await expect(modal.getByRole("heading",{name:`Published baseline v${latestVersion}`,exact:true})).toBeVisible();
      await page.goBack();
      await expect(modal.getByLabel("Requested tenancy name",{exact:true})).toHaveValue(requestedName);
      await page.goForward();
      await expect(modal.getByRole("heading",{name:`Published baseline v${latestVersion}`,exact:true})).toBeVisible();
      await modal.getByRole("link",{name:/Back to create tenancy/}).click();
      await expect(modal.getByLabel("Requested tenancy name",{exact:true})).toHaveValue(requestedName);
      await expect(modal.getByRole("combobox",{name:"Home region",exact:true})).toHaveValue("us-phoenix-1");
      for (const width of [1280, 390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        expect(
          await modal.evaluate(
            (element) => element.scrollWidth <= element.clientWidth,
          ),
        ).toBe(true);
        await page.screenshot({
          path: resolve(
            ".local-dev/browser",
            `create-metadata-form-${width}.png`,
          ),
          fullPage: true,
        });
      }
      await page.setViewportSize({ width: 1280, height: 900 });
    }
    const response = page.waitForResponse(
      (value) =>
        value.url().endsWith("/api/organization/actions") &&
        value.request().method() === "POST",
    );
    await modal.getByRole("button", { name: action, exact: true }).click();
    const result = await response;
    expect(result.status()).toBe(202);
    await expect(
      modal.getByText("Operation accepted", { exact: true }),
    ).toBeVisible();
    if (action === "Create tenancy") {
      const target = await modal.getByRole("link", { name: "View operation" }).getAttribute("href");
      await modal.getByRole("button", { name: "Done", exact: true }).click();
      // A queued request may become waiting after admission; navigating elsewhere must refresh it.
      await expect.poll(async () => {
        const response = await page.request.get("/api" + target);
        return (await response.json()).operation.state;
      }, { timeout: 20_000 }).toBe("waiting");
      await page.getByRole("link", { name: "Audit history", exact: true }).click();
      const link = page.getByRole("link", { name: "Operations", exact: true });
      await expect(link.locator(".nav-count")).toBeVisible();
      const count = await (await page.request.get("/api/operations")).json();
      await expect(link.locator(".nav-count")).toHaveText(String(count.attention_count));
      await page.getByRole("link", { name: "Administrators", exact: true }).click();
      await expect(link.locator(".nav-count")).toBeVisible();
      await page.goto(target!);
    } else await modal.getByRole("link", { name: "View operation" }).click();
    if (action === "Create tenancy" || action === "Import tenancy") {
      const panel = page.getByRole("region", {
        name: "Administrator action required",
      });
      await expect(panel).toBeVisible({ timeout: 20_000 });
      const expectedVersion=latestVersion;
      await expect(panel.getByRole("link",{name:`Version ${expectedVersion}`,exact:true})).toBeVisible();
      if (!defaultAdvanced) {
        const originalUrl=page.url();
        await page.getByRole("link",{name:"Configuration",exact:true}).click();
        await page.getByRole("button",{name:"Publish",exact:true}).click();
        await page.getByRole("button",{name:"Publish baseline",exact:true}).click();
        await expect(page.getByRole("heading",{name:"Published baseline v2",exact:true})).toBeVisible();
        defaultAdvanced=true;latestVersion=2;
        await page.goto(originalUrl);
        await expect(panel.getByRole("link",{name:"Version 1",exact:true})).toBeVisible();
        await page.screenshot({path:resolve(".local-dev/browser","baseline-pinned-after-publication-1280.png"),fullPage:true});
      }
      if (action === "Import tenancy") {
        const target = panel.getByLabel("Tenancy OCID", { exact: true });
        await expect(target).toHaveAttribute("readonly", "");
        await expect(target).not.toHaveValue("");
      } else {
        await expect(
          panel.getByLabel("Tenancy OCID", { exact: true }),
        ).toBeEditable();
      }
      const checklist=panel.locator("details.operator-instructions");
      const checklistToggle=checklist.locator(":scope > summary");
      await expect(checklistToggle).toHaveText("OCI administrator checklist");
      await expect(checklist).not.toHaveAttribute("open");
      await expect(panel.getByText(/A work-request ID is not a tenancy OCID/)).not.toBeVisible();
      await expect(panel.getByRole("button",{name:"Use simulated handoff",exact:true})).toBeVisible();
      for(const width of [1280,390,320]) {
        await page.setViewportSize({width,height:900});
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
        await panel.screenshot({path:`.local-dev/browser/instructions-${action==="Create tenancy"?"create":"import"}-closed-${width}.png`});
      }
      await checklistToggle.focus();
      await checklistToggle.press("Enter");
      await expect(checklist).toHaveAttribute("open");
      await expect(
        panel.getByText(/A work-request ID is not a tenancy OCID/),
      ).toBeVisible();
      await expect(
        panel.getByRole("link", { name: "Upload an API public key" }),
      ).toHaveAttribute(
        "href",
        "https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm",
      );
      if (action === "Create tenancy") {
        await expect(
          panel.getByRole("link", { name: "Oracle activation guide" }),
        ).toBeVisible();
      } else {
        await panel.getByText("Oracle transfer procedures").click();
        await expect(
          panel.getByRole("link", {
            name: "Transfer a created child (approval uses the CLI)",
          }),
        ).toBeVisible();
      }
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
            `onboarding-${action === "Create tenancy" ? "create" : "import"}-handoff-${width}.png`,
          ),
          fullPage: true,
        });
      }
      await page.setViewportSize({ width: 1280, height: 900 });
      await checklistToggle.focus();
      await checklistToggle.press("Space");
      await expect(checklist).not.toHaveAttribute("open");
      await expect(panel.getByLabel("Tenancy OCID",{exact:true})).toBeVisible();
      await panel
        .getByRole("button", { name: "Use simulated handoff" })
        .click();
      if (!sharedName) {
        await panel
          .getByLabel("Bootstrap user OCID", { exact: true })
          .fill("ocid1.user.oc1..otmsimwrong");
        await panel
          .getByRole("button", { name: "Verify handoff", exact: true })
          .click();
        const blocked = page.getByRole("region", {
          name: "Setup needs attention",
        });
        await expect(blocked).toBeVisible({ timeout: 20_000 });
        await page.reload();
        await expect(
          blocked.getByLabel("Bootstrap user OCID", { exact: true }),
        ).toHaveValue("ocid1.user.oc1..otmsimwrong");
        await blocked
          .getByRole("button", { name: "Use simulated handoff" })
          .click();
        await blocked
          .getByRole("button", { name: "Verify handoff", exact: true })
          .click();
      } else {
        await panel
          .getByRole("button", { name: "Verify handoff", exact: true })
          .click();
      }

      const review = page.getByRole("region", {
        name: "Ready for your review",
      });
      await expect(review).toBeVisible({ timeout: 20_000 });
      if (action === "Create tenancy")
        await expect(
          review.getByText("us-phoenix-1", { exact: true }),
        ).toBeVisible();
      // Read the named discovery fact; read-only contact fields may appear earlier in this panel.
      const text = await review.getByText("Discovered tenancy",{exact:true}).locator("..").locator("dd").textContent();
      if (!sharedName) sharedName = text!.split("ocid1")[0].trim();
      else personalName = text!.split("ocid1")[0].trim();
      await page.reload();
      await expect(review).toBeVisible();
      await expect(
        review.getByRole("button", { name: "Start setup" }),
      ).toBeDisabled();
      // The pending child has no registered account identities; a GET must not invent them.
      const setupUrl = page.url();
      const operationId = new URL(setupUrl).pathname.split("/").at(-1)!;
      const setupData = await (await page.request.get("/api/tenancy-onboarding/" + operationId)).json();
      await page.goto("/tenancies/" + setupData.tenancy_id);
      const pendingUsers = page.getByRole("region", { name: "Required users", exact: true });
      await expect(pendingUsers.getByText("Not recorded", { exact: true })).toHaveCount(4);
      await expect(pendingUsers.getByText(/Setup is still in progress/)).toBeVisible();
      await expect(pendingUsers.locator("details.required-user-details")).toHaveCount(0);
      await page.goto(setupUrl);
      await expect(review).toBeVisible();
      await reviewCheckboxControl(
        page,
        "I confirm the exact temporary accounts above may be removed after replacement access is verified.",
        "onboarding-cleanup",
      );
      await review.getByRole("checkbox").check();
      await review.getByRole("button", { name: "Start setup" }).click();
      await expect(
        page.getByRole("heading", {
          name: "Local setup verified",
          exact: true,
        }),
      ).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText("Record permanent user identities", { exact: true })).toBeVisible();
    }
    await expect(page.getByText("Succeeded", { exact: true })).toBeVisible({
      timeout: 20_000,
    });
    if (action === "Create tenancy" || action === "Import tenancy") {
      const link = page.getByRole("link", {
        name: "Open tenancy",
        exact: true,
      });
      await expect(link).toHaveCount(1);
      await expect(link).toHaveAttribute("href", /\/tenancies\/[a-f0-9-]+$/);
      await link.click();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        action === "Create tenancy" && sharedName && !personalName
          ? sharedName
          : personalName,
      );
      const users = page.getByRole("region", { name: "Required users", exact: true });
      await expect(users.getByText("Recorded", { exact: true })).toHaveCount(2);
      await expect(users.getByText("Not checked", { exact: true })).toHaveCount(9);
      await expect(users.getByText("otm-automation", { exact: true })).toBeVisible();
      await expect(users.getByRole("button", { name: "Refresh required users", exact: true })).toHaveCount(0);
      // Real HTTPS admission and the native worker publish independent fixture observations.
      const childUrl = page.url();
      const check = users.getByRole("button", { name: "Refresh user data", exact: true });
      await expect(check).toBeEnabled();
      await expect(check).toHaveClass(/secondary/);
      const accepted = page.waitForResponse(response =>
        response.request().method() === "POST" && response.url().endsWith("/required-users/check"));
      await check.click();
      const response = await accepted;
      expect(response.status()).toBe(202);
      const checkId = (await response.json()).operation_id;
      await expect(users.getByText("Present", { exact: true })).toHaveCount(2, { timeout: 20_000 });
      await expect(users.getByText("Not checked", { exact: true })).toHaveCount(0);
      const keyPanel=page.getByRole("region",{name:"Automation signing keys",exact:true});
      await expect(keyPanel.getByText("Fingerprint",{exact:true})).toBeVisible();
      await expect(keyPanel.getByText("Under 30 days",{exact:true})).toBeVisible();
      await expect(keyPanel.getByRole("link",{name:/^View automation signing-key inventory check,/})).toHaveAttribute("href",new RegExp("/operations/"+checkId+"\\?returnTo=[^#]+#automation-keys$"));
      const automation = users.locator(".required-user-card").filter({has:page.getByRole("heading",{name:"Automation user",exact:true})});
      await expect(automation.getByText("Verified in simulation",{exact:true})).toHaveCount(2);
      await expect(automation.getByRole("link",{name:/^View assignment check, /})).toHaveAttribute("href",/\/operations\/[a-f0-9-]+\?returnTo=[^#]+#automation-assignment$/);
      await expect(users.getByText("Console MFA exemption", { exact: true })).toBeVisible();
      await expect(users.getByText("Approved-network restriction", { exact: true })).toBeVisible();
      await expect(users.locator(".required-user-card").filter({has:page.getByRole("heading",{name:"Recovery user",exact:true})}).getByText("Verified in simulation", { exact: true })).toHaveCount(4);
      // Private provider perimeter evidence must not appear in ordinary authenticated responses.
      const privateCheck=await page.request.get(new URL(childUrl).pathname.replace("/tenancies/","/api/tenancies/")+"/required-users");
      const privateBody=await privateCheck.text();
      expect(privateBody).not.toContain("198.51.100");
      expect(privateBody).not.toContain("2001:db8");
      await expect(users.getByText("Presence checked (UTC)", { exact: true })).toHaveCount(2);
      await expect(users.getByRole("link", { name: /^View presence check, / })).toHaveCount(2);
      if(!userRefreshCaptured) {
        await expect(check).toBeEnabled();
        for(const width of [1280,390,320]) {
          await page.setViewportSize({width,height:900});
          expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
          await users.screenshot({path:`.local-dev/browser/user-refresh-controls-${width}.png`});
        }
        await page.setViewportSize({width:1280,height:900});
        userRefreshCaptured=true;
      }
      await users.getByRole("link", { name: /^View presence check, / }).first().click();
      await expect(page).toHaveURL(new RegExp("/operations/" + checkId + "\\?returnTo=[^#]+#automation-presence$"));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Check required users");
      await expect(page.getByRole("link",{name:"← Back to tenancy",exact:true})).toHaveAttribute("href",new URL(childUrl).pathname);

      await expect(page.getByRole("heading", {name:"Recovery user · Console policy",exact:true})).toBeVisible();
      await expect(page.locator("#automation-presence")).toBeFocused();
      await expect(page.locator("#recovery-policy").getByText("Console MFA exemption",{exact:true})).toBeVisible();

      await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible();
      await page.goto(childUrl);
      await expect(users.getByText("Present", { exact: true })).toHaveCount(2);
      // The consolidated inventory reuses these exact stored facts and deep-links with focus.
      const childName=await page.getByRole("heading",{level:1}).textContent();
      await page.getByRole("link",{name:"Tenancies",exact:true}).click();
      const inventoryRow=page.getByRole("row").filter({has:page.getByRole("link",{name:childName!,exact:true})});
      const summary=inventoryRow.getByRole("link",{name:`Users: 2/2 present for ${childName}`});
      await expect(summary).toHaveAttribute("href",new URL(childUrl).pathname+"#required-users");
      await expect(summary).toHaveAccessibleDescription(/does not establish permissions/);
      for(const width of [1280,768,390,320]){
        await page.setViewportSize({width,height:900});
        await page.getByRole("table").scrollIntoViewIfNeeded();
        await page.screenshot({path:resolve(".local-dev/browser",`required-user-inventory-${action === "Create tenancy" ? "create" : "import"}-${width}.png`),fullPage:true});
        const sizing=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,offenders:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth&&!e.closest(".table-scroll")).slice(0,20).map(e=>({tag:e.tagName,class:e.className,right:e.getBoundingClientRect().right}))}));
        expect(sizing.document,JSON.stringify(sizing)).toBeLessThanOrEqual(sizing.width);
      }
      await summary.click();
      await expect(page).toHaveURL(new RegExp("#required-users$"));
      await expect(users.getByRole("heading",{name:"Required users",exact:true})).toBeFocused();
      await expect(users.getByText("Present", { exact: true })).toHaveCount(2);
      const disclosure = users.locator("details.required-user-details").first().locator("summary");
      await disclosure.focus(); await disclosure.press("Enter");
      await expect(users.locator("details.required-user-details").first()).toHaveAttribute("open", "");
      await expect(users.getByRole("link", { name: "View setup operation" }).first()).toHaveAttribute("href", /\/operations\/[a-f0-9-]+\?returnTo=[^#]+$/);
      const recoveryCard=users.locator(".required-user-card").nth(1);
      await expect(recoveryCard.getByLabel("Administrator assignments: Assigned (simulation)")).toBeVisible();
      const recoveryDetails=recoveryCard.getByText("Identity details",{exact:true});
      await recoveryDetails.focus(); await recoveryDetails.press("Enter");
      await expect(recoveryCard.getByText("Administrators group",{exact:true})).toBeVisible();
      await expect(recoveryCard.getByText("Domain administrator role",{exact:true})).toBeVisible();
      await expect(recoveryCard.getByRole("link",{name:/^View assignment check, /})).toHaveAttribute("href",/\/operations\/[a-f0-9-]+\?returnTo=[^#]+#recovery-assignment$/);
      await recoveryDetails.press("Enter");
      for (const width of [1280, 1024, 768, 390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const accessPanel=users.getByRole("region",{name:"Administrator access",exact:true});
        const accessBox=await accessPanel.boundingBox();
        const automationBox=await users.locator(".required-user-card").first().boundingBox();
        expect(Math.abs(accessBox!.x-automationBox!.x)).toBeLessThan(2);
        expect(Math.abs(accessBox!.width-automationBox!.width)).toBeLessThan(2);
        expect(accessBox!.y-(automationBox!.y+automationBox!.height)).toBeGreaterThanOrEqual(15);
        const cards = await users.locator(".required-user-card").evaluateAll(elements => elements.map(e => {
          const r = e.getBoundingClientRect(); return { x: r.x, y: r.y };
        }));
        if (width <= 900) expect(cards[1].y).toBeGreaterThan(cards[0].y);
        else expect(Math.abs(cards[0].y - cards[1].y)).toBeLessThan(2);
        // Laptop status pairs share a row; mobile keeps label/value groups readable in one column.
        const facts = users.locator(".required-user-card").first().locator(":scope > .required-user-facts");
        const identity = await facts.locator("div").filter({has:page.getByText("Identity record",{exact:true})}).boundingBox();
        const presence = await facts.locator("div").filter({has:page.getByText("Presence",{exact:true})}).boundingBox();
        expect(identity).not.toBeNull(); expect(presence).not.toBeNull();
        if(width > 700) expect(Math.abs(identity!.y-presence!.y)).toBeLessThan(2);
        else expect(presence!.y).toBeGreaterThan(identity!.y);
        // Recovery's three short facts share one row while policy controls retain their wider pair.
        const recoveryFacts=users.locator(".required-recovery-facts");
        const overview=await recoveryFacts.locator(".required-user-overview-fact").evaluateAll(nodes=>nodes.map(node=>{const box=node.getBoundingClientRect();return {x:box.x,y:box.y};}));
        expect(overview).toHaveLength(3);
        const wholeWords=await recoveryFacts.locator(".required-user-overview-fact dd").evaluateAll(nodes=>nodes.every(node=>{
          const walk=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);
          for(let text=walk.nextNode();text;text=walk.nextNode()){
            if(!text.textContent?.trim())continue;
            const range=document.createRange();range.selectNodeContents(text);
            if(range.getClientRects().length!==1)return false;
          }
          return true;
        }));
        expect(wholeWords).toBe(true);
        if(width>700){
          expect(Math.abs(overview[0].y-overview[1].y)).toBeLessThan(2);expect(Math.abs(overview[1].y-overview[2].y)).toBeLessThan(2);
          expect(overview[1].x).toBeGreaterThan(overview[0].x);expect(overview[2].x).toBeGreaterThan(overview[1].x);
        }else{expect(overview[1].y).toBeGreaterThan(overview[0].y);expect(overview[2].y).toBeGreaterThan(overview[1].y);}
        // Evidence dates follow all badges, share a laptop row and retain compact exact check links.
        for(const card of await users.locator(".required-user-card").all()){
          const factsBox=await card.locator(":scope > .required-user-facts").boundingBox();
          const footer=card.locator(".required-user-checks");
          const footerBox=await footer.boundingBox();
          expect(footerBox!.y).toBeGreaterThan(factsBox!.y+factsBox!.height);
          const dates=await footer.locator(":scope > div").evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y};}));
          expect(dates).toHaveLength(await card.getByRole("heading",{name:"Recovery user",exact:true}).count()?3:2);
          if(width>700){
            expect(Math.abs(dates[0].y-dates[1].y)).toBeLessThan(2);expect(dates[1].x).toBeGreaterThan(dates[0].x);
            const values=await footer.locator("dd").evaluateAll(nodes=>nodes.map(node=>node.getBoundingClientRect().y));
            expect(Math.abs(values[0]-values[1])).toBeLessThan(2);
          }
          else expect(dates[1].y).toBeGreaterThan(dates[0].y);
          for(const link of await footer.getByRole("link").all()){
            await expect(link).toHaveText(/^[A-Z][a-z]{2} \d{1,2}, \d{4}$/);
            const purpose=await card.getByRole("heading",{name:"Recovery user",exact:true}).count()?"recovery":"automation";
            const name=await link.getAttribute("aria-label");
            const kind=name?.includes("assignment")?"assignment":name?.includes("policy")?"policy":"presence";
            await expect(link).toHaveAttribute("href",new RegExp("/operations/[a-f0-9-]+\\?returnTo=[^#]+#"+purpose+"-"+kind+"$"));
          }
        }
        const costs = page.getByRole("region",{name:"Current month costs",exact:true});
        const overrides = page.getByRole("region",{name:"Overrides",exact:true});
        const costBox = await costs.boundingBox(), overrideBox = await overrides.boundingBox();
        expect(costBox).not.toBeNull(); expect(overrideBox).not.toBeNull();
        if(width > 1000) {
          expect(Math.abs(costBox!.y-overrideBox!.y)).toBeLessThan(2);
          const refreshBox=await costs.getByRole("button",{name:"Refresh costs",exact:true}).boundingBox();
          const manageBox=await overrides.getByRole("button",{name:"Manage overrides",exact:true}).boundingBox();
          expect(Math.abs(refreshBox!.y+refreshBox!.height/2-manageBox!.y-manageBox!.height/2)).toBeLessThan(2);
          expect(Math.abs(costBox!.x+costBox!.width-refreshBox!.x-refreshBox!.width-(overrideBox!.x+overrideBox!.width-manageBox!.x-manageBox!.width))).toBeLessThan(2);
          expect(overrideBox!.x).toBeGreaterThanOrEqual(costBox!.x+costBox!.width);
        } else expect(overrideBox!.y).toBeGreaterThanOrEqual(costBox!.y+costBox!.height);
        // Whole-section rhythm matters as much as card internals: no panel may touch its neighbour.
        const rollout = page.getByRole("region",{name:"Tenancy baseline update",exact:true});
        // Snapshot panel geometry together: delayed focus scrolling must not mix viewport origins.
        const layout=await page.evaluate(({grid,users,members,keys,rollout})=>{
          // Copy one optional panel rectangle into the shared viewport snapshot.
          const rect=(node:Element|null)=>{
            if(!node)return null;
            const box=node.getBoundingClientRect();
            return {x:box.x,y:box.y,width:box.width,height:box.height};
          };
          return {gridBox:rect(grid),usersBox:rect(users),membersBox:rect(members),keysBox:rect(keys),rolloutBox:rect(rollout)};
        },{
          grid:await page.locator(".tenancy-summary-grid").elementHandle(),
          users:await users.elementHandle(),
          members:await page.locator(".table-panel").filter({has:page.getByRole("heading",{name:"Current members",exact:true})}).elementHandle(),
          keys:await keyPanel.elementHandle(),
          rollout:await rollout.count()?await rollout.elementHandle():null,
        });
        const {gridBox,usersBox,membersBox,keysBox,rolloutBox}=layout;
        expect(gridBox).not.toBeNull(); expect(usersBox).not.toBeNull(); expect(membersBox).not.toBeNull();
        expect(keysBox).not.toBeNull();
        expect(keysBox!.y-(usersBox!.y+usersBox!.height)).toBeCloseTo(24,0);
        expect(gridBox!.y-(keysBox!.y+keysBox!.height)).toBeCloseTo(24,0);
        if(rolloutBox) {
          expect(rolloutBox.y-(gridBox!.y+gridBox!.height)).toBeCloseTo(24,0);
          expect(membersBox!.y-(rolloutBox.y+rolloutBox.height)).toBeCloseTo(24,0);
        } else expect(membersBox!.y-(gridBox!.y+gridBox!.height)).toBeCloseTo(24,0);
        if(width > 1000) expect(overrideBox!.x-(costBox!.x+costBox!.width)).toBeCloseTo(24,0);
        else expect(overrideBox!.y-(costBox!.y+costBox!.height)).toBeCloseTo(24,0);
        await keyPanel.screenshot({path:resolve(".local-dev/browser",`automation-keys-${action === "Create tenancy" ? "create" : "import"}-${width}.png`)});
        await page.screenshot({path:resolve(".local-dev/browser",`tenancy-detail-spacing-${action === "Create tenancy" ? "create" : "import"}-${rolloutBox ? "baseline-update" : "no-baseline-update"}-${width}.png`),fullPage:true});
        await page.locator(".tenancy-summary-grid").screenshot({path:resolve(".local-dev/browser",`tenancy-summary-${action === "Create tenancy" ? "create" : "import"}-${width}.png`)});
        await users.screenshot({ path: resolve(".local-dev/browser", `required-users-${action === "Create tenancy" ? "create" : "import"}-${width}.png`) });
      }
      if(!assignmentRenderReviewed){
        assignmentRenderReviewed=true;
        const resource="**/api"+new URL(childUrl).pathname+"/required-users";
        // Render-only cases use separate ephemeral pages so old-document requests cannot satisfy assertions.
        const assignmentBaseline=JSON.parse(privateBody);
        for(const stale of [false,true]){
          const fixturePage=await page.context().newPage();
          const fixtureErrors:string[]=[];
          fixturePage.on("pageerror",error=>fixtureErrors.push(error.name));
          // Capture one fixed response per page; real persisted negative cases remain in PostgreSQL tests.
          const assignmentFixture=async (route: import("@playwright/test").Route)=>{
            const body=structuredClone(assignmentBaseline);
            for(const user of body.users){
              user.administrator_access={...user.administrator_access,group:stale?"verified":"missing",domain_role:"verified",stale};
            }
            await route.fulfill({status:200,json:body});
          };
          try{
            await fixturePage.route(resource,assignmentFixture);
            const loaded=fixturePage.waitForResponse(response=>response.request().method()==="GET" && response.url().endsWith(new URL(childUrl).pathname+"/required-users"));
            await fixturePage.goto(childUrl);
            const fixture=await (await loaded).json();
            expect(fixture.users[0].administrator_access.stale).toBe(stale);
            expect(fixture.users[1].administrator_access.stale).toBe(stale);
            const fixtureUsers=fixturePage.getByRole("region",{name:"Required users",exact:true});
            const card=fixtureUsers.locator(".required-user-card").first();
            await expect(card.getByText(stale?"Check out of date":"Missing or disabled",{exact:true})).toHaveCount(stale?2:1);
            const recoveryCard=fixtureUsers.locator(".required-user-card").nth(1);
            await expect(recoveryCard.getByLabel(`Administrator assignments: ${stale?"Out of date":"Missing"} (simulation)`)).toBeVisible();
            for(const width of [1280,320]){
              await fixturePage.setViewportSize({width,height:900});
              expect(await fixturePage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
              await fixturePage.screenshot({path:resolve(".local-dev/browser",`automation-assignment-render-only-${stale?"stale":"missing"}-${width}.png`),fullPage:true});
            }
            expect(fixtureErrors).toEqual([]);
          }finally{
            await fixturePage.unrouteAll({behavior:"wait"});
            await fixturePage.close();
          }
        }
        await page.reload();
        await expect(users.locator(".required-user-card").first().getByText("Verified in simulation",{exact:true})).toHaveCount(2);
      }
      await page.setViewportSize({ width: 1280, height: 900 });
    }
  }

  await initialMapping(page);
  await baselineAuthoring(page);
  await upload(rows);
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await expect(
    page.getByText("No actionable organization drift", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await page.getByRole("button", { name: "Leader One", exact: true }).click();
  await expect(
    modal.getByRole("combobox", { name: "Action", exact: true }),
  ).toHaveValue("");
  await expect(
    modal.getByRole("button", { name: "Continue", exact: true }),
  ).toBeDisabled();
  await expect(modal.getByLabel("Tenancy name", { exact: true })).toHaveCount(
    0,
  );
  await page.screenshot({
    path: resolve(".local-dev/browser/employee-action-choice-1280.png"),
    fullPage: true,
  });
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("create_tenancy");
  await reviewSelectControl(page);
  await modal
    .getByRole("combobox", { name: "Tenancy type", exact: true })
    .selectOption("shared");
  await finish("Create tenancy");
  await mappingInventory(page, sharedName);

  const joinedRows = [
    ...rows,
    "New Employee,new@example.test,one@example.test,one@example.test",
  ];
  await upload(joinedRows);
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await employeeReview.filter({has:page.getByText("New employee",{exact:true})}).getByRole("button", { name: "Review", exact: true }).click();
  await expect(
    modal.getByRole("combobox", { name: "Action", exact: true }),
  ).toHaveValue("");
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("create_tenancy");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 760 });
    expect(
      await modal.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `organization-create-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await finish("Create tenancy");
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await expect(
    page.getByText("No actionable organization drift", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Tenancies", exact: true }).click();
  await page.getByRole("link", { name: sharedName, exact: true }).click();
  const membersToolbar=page.locator(".tenancy-members-toolbar");
  await expect(membersToolbar.getByRole("button",{name:"Add member",exact:true})).toHaveClass(/secondary/);
  for(const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    if(width===1280) {
      const titleBox=await membersToolbar.getByRole("heading").boundingBox();
      const actionBox=await membersToolbar.getByRole("button",{name:"Add member",exact:true}).boundingBox();
      expect(Math.abs(titleBox!.y+titleBox!.height/2-actionBox!.y-actionBox!.height/2)).toBeLessThanOrEqual(1);
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await membersToolbar.screenshot({path:`.local-dev/browser/shared-members-toolbar-${width}.png`});
  }
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole("button", { name: "Add member", exact: true }).click();
  await modal.getByLabel("Find employee",{exact:true}).fill("new@example.test");
  await modal.getByRole("combobox",{name:"Employee",exact:true}).selectOption({label:"New Employee · new@example.test"});
  for(const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await modal.screenshot({path:`.local-dev/browser/add-shared-member-${width}.png`});
  }
  await page.setViewportSize({width:1280,height:900});
  await modal.getByRole("button",{name:"Continue",exact:true}).click();
  await expect(modal.getByRole("combobox",{name:"Action",exact:true})).toHaveValue("join_shared");
  await expect(modal.getByRole("combobox",{name:"Shared tenancy",exact:true}).locator("option:checked")).toHaveText(sharedName + " · owner Leader One");
  await modal
    .getByRole("combobox", { name: "Shared tenancy", exact: true })
    .selectOption({ label: sharedName + " · owner Leader One" });
  const parents = modal.getByRole("combobox", {
    name: "Existing parent compartment",
    exact: true,
  });
  await expect(parents).toBeEnabled();
  const parent = await parents.locator("option").nth(1).getAttribute("value");
  await parents.selectOption(parent!);
  await finish("Add to shared tenancy");
  await page.getByRole("link", { name: "Tenancies", exact: true }).click();
  const sharedRow = page.getByRole("row").filter({
    has: page.getByRole("link", { name: sharedName, exact: true }),
  });
  await expect(sharedRow).toContainText("2");
  await page.getByLabel("Shared tenancies only", { exact: true }).check();
  await expect(
    page.getByRole("link", { name: personalName, exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: sharedName, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Total tenancies", { exact: true }).locator(".."),
  ).toContainText("2");
  await reviewCheckboxControl(page, "Shared tenancies only", "shared-only");
  await page.getByLabel("Shared tenancies only", { exact: true }).uncheck();
  await expect(
    page.getByRole("link", { name: personalName, exact: true }),
  ).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: resolve(".local-dev/browser", `tenancy-inventory-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await keepOwnershipRoundTrip(page,sharedName);
  await configurationUpdates(page,sharedName);latestVersion=3;
  latestVersion=await tenancyOverrides(page,sharedName);
  await existingCompartmentMembership(page,sharedName);
  await upload(rows);
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await employeeReview.filter({has:page.getByText("Absence review",{exact:true})}).getByRole("button", { name: "Review", exact: true }).click();
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("offboard_person");
  await modal
    .getByRole("combobox", {
      name: "Action for " + personalName,
      exact: true,
    })
    .selectOption("delete");
  await modal
    .getByRole("combobox", {
      name: "Action for " + sharedName,
      exact: true,
    })
    .selectOption("remove");
  await reviewCheckboxControl(
    page,
    "I reviewed the shared tenancy impact",
    "shared-impact",
  );
  await modal.getByLabel(/I reviewed the shared tenancy impact/).check();
  await modal.getByLabel(/I acknowledge the consequences/).check();
  await page.screenshot({
    path: resolve(".local-dev/browser/organization-offboard-1280.png"),
    fullPage: true,
  });
  await finish("Offboard employee");
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "New Employee", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Tenancies", exact: true }).click();
  await page.getByRole("link", { name: sharedName, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Manual cleanup guidance", exact: true }),
  ).toBeVisible();
  // A partial positive row immediately restores directory presence, not deleted infrastructure.
  await upload(joinedRows.filter(row=>row.startsWith("New Employee,")));
  await expect(page.getByRole("button",{name:"New Employee",exact:true})).toBeVisible();
  const afterPartial=await(await page.request.get("/api/organization/reviews")).json();
  const restored=afterPartial.items.filter((row:{kind:string,email:string})=>row.kind==="TENANCY_SETUP_REVIEW"&&row.email==="new@example.test");
  expect(restored).toHaveLength(1);
  const afterRestore=await(await page.request.get("/api/tenancies")).json();
  expect(afterRestore.items.some((child:{name:string})=>child.name===personalName)).toBe(false);
  await upload(joinedRows);
  const afterFull=await(await page.request.get("/api/organization/reviews")).json();
  expect(afterFull.items.filter((row:{kind:string,email:string})=>row.kind==="TENANCY_SETUP_REVIEW"&&row.email==="new@example.test").map((row:{id:string})=>row.id)).toEqual([restored[0].id]);
  await page
    .getByRole("link", { name: "Organization drift", exact: true })
    .click();
  await expect(employeeReview.getByText("New employee", { exact: true })).toBeVisible();
  await employeeReview.filter({has:page.getByText("New employee",{exact:true})}).getByRole("button", { name: "Review", exact: true }).click();
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("import_tenancy");
  await finish("Import tenancy");

  // Exclusion is a real organization decision; the visibility toggle must reach the backend filter.
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await page.getByRole("button", { name: "Delegate", exact: true }).click();
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("no_tenancy_required");
  await modal
    .getByRole("button", { name: "No tenancy required", exact: true })
    .click();
  await expect(
    modal.getByText("Decision saved", { exact: true }),
  ).toBeVisible();
  await modal.getByRole("button", { name: "Done", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Delegate", exact: true }),
  ).toHaveCount(0);
  await reviewCheckboxControl(page);
  await page.getByLabel("Include excluded profiles", { exact: true }).check();
  await expect(
    page.getByRole("button", { name: "Delegate", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No tenancy required", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Include excluded profiles", { exact: true }).uncheck();
  await expect(
    page.getByRole("button", { name: "Delegate", exact: true }),
  ).toHaveCount(0);
  // Whole-tenancy deletion is distinct from member removal and uses the installed API/worker roles.
  await page.getByRole("link", { name: "Organization", exact: true }).click();
  await page.getByRole("button", { name: "New Employee", exact: true }).click();
  await modal
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("join_shared");
  await modal
    .getByRole("combobox", { name: "Shared tenancy", exact: true })
    .selectOption({ label: sharedName + " · owner Leader One" });
  const returningParent = modal.getByRole("combobox", {
    name: "Existing parent compartment",
    exact: true,
  });
  await expect(returningParent).toBeEnabled();
  const projects = await returningParent
    .getByRole("option", { name: /^Projects/ })
    .getAttribute("value");
  await returningParent.selectOption(projects!);
  await modal
    .getByLabel("Employee compartment name", { exact: true })
    .fill("returning-shared-member");
  await finish("Add to shared tenancy");
  for (const name of [sharedName, personalName]) {
    await page.getByRole("link", { name: "Tenancies", exact: true }).click();
    await page.getByRole("link", { name, exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Delete tenancy", exact: true }),
    ).toBeVisible();
    // Synthetic long-title stress changes only this disposable page DOM, never registry data.
    if (name === sharedName) {
      const heading = page.getByRole("heading", { level: 1 });
      const original = await heading.textContent();
      await heading.evaluate((node) => {
        node.textContent = "SyntheticLongTenancyName".repeat(8);
      });
      for (const width of [1280, 900, 768, 390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        const buttons = await page
          .locator(".page-actions button")
          .evaluateAll((nodes) =>
            nodes.map((node) => node.getBoundingClientRect().height),
          );
        expect(buttons).toHaveLength(2);
        expect(Math.abs(buttons[0] - buttons[1])).toBeLessThanOrEqual(1);
      }
      await heading.evaluate((node, value) => {
        node.textContent = value;
      }, original);
      await page.setViewportSize({ width: 1280, height: 900 });
    }
    await page
      .getByRole("button", { name: "Delete tenancy", exact: true })
      .click();
    await expect(
      modal.getByRole("button", { name: "Initiate termination" }),
    ).toBeDisabled();
    if (name === sharedName) {
      await expect(
        modal.getByText("New Employee", { exact: true }),
      ).toBeVisible();
      await expect(
        modal.getByText(/1 other tenancy association/),
      ).toBeVisible();
      await reviewCheckboxControl(
        page,
        "I have reviewed the affected people and confirm termination of this entire tenancy.",
        "tenancy-deletion",
      );
      for (const width of [390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        const consent = modal.getByRole("checkbox");
        await consent.check();
        await expect(consent).toBeChecked();
        await expect(
          modal.getByRole("button", { name: "Initiate termination" }),
        ).toBeEnabled();
        await consent.uncheck();
      }
      await page.setViewportSize({ width: 1280, height: 900 });
    }
    await modal.getByRole("checkbox").check();
    const accepted = page.waitForResponse(
      (value) =>
        value.url().endsWith("/api/tenancy-deletions") &&
        value.request().method() === "POST",
    );
    await modal.getByRole("button", { name: "Initiate termination" }).click();
    expect((await accepted).status()).toBe(202);
    await expect(
      modal.getByText("Termination requested", { exact: true }),
    ).toBeVisible();
    await modal.getByRole("link", { name: "View operation" }).click();
    await expect(page.getByText("Succeeded", { exact: true })).toBeVisible({
      timeout: 20_000,
    });
    // Even the final tenancy deletion leaves every employee independently managed.
    await page.getByRole("link",{name:"Organization",exact:true}).click();
    await expect(page.getByRole("button",{name:"New Employee",exact:true})).toBeVisible();
    await expect(page.getByRole("button",{name:"Leader One",exact:true})).toBeVisible();
  }
  // Accept onboarding without exemption or provider work, then retain later provisioning choices.
  const unassignedRows=[...joinedRows,"Unassigned Engineer,unassigned@example.test,one@example.test,one@example.test"];
  await upload(unassignedRows);
  await page.getByRole("link",{name:"Organization drift",exact:true}).click();
  const unassignedReview=page.getByRole("row").filter({hasText:"unassigned@example.test"}).filter({has:page.getByText("New employee",{exact:true})});
  await unassignedReview.getByRole("button",{name:"Review",exact:true}).click();
  await modal.getByRole("combobox",{name:"Action",exact:true}).selectOption("keep_without_tenancy");
  for(const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await modal.screenshot({path:`.local-dev/browser/keep-without-tenancy-${width}.png`});
  }
  await page.setViewportSize({width:1280,height:900});
  await expect(modal.getByRole("checkbox")).toHaveCount(0);
  await modal.getByRole("button",{name:"Keep in organization",exact:true}).click();
  await expect(modal.getByText("Decision saved",{exact:true})).toBeVisible();
  await modal.getByRole("button",{name:"Done",exact:true}).click();
  await upload(unassignedRows);
  await page.getByRole("link",{name:"Organization drift",exact:true}).click();
  await expect(unassignedReview).toHaveCount(0);
  await page.getByRole("link",{name:"Organization",exact:true}).click();
  await page.getByRole("button",{name:"Unassigned Engineer",exact:true}).click();
  const later=modal.getByRole("combobox",{name:"Action",exact:true});
  for(const value of ["create_tenancy","import_tenancy","join_shared"])
    await expect(later.locator(`option[value="${value}"]`)).toHaveCount(1);
  await modal.getByRole("button",{name:"Cancel",exact:true}).click();
  // A separate fresh shared tenancy exercises removal without changing preceding fixture flows.
  await page.getByRole("button",{name:"Unassigned Engineer",exact:true}).click();
  await modal.getByRole("combobox",{name:"Action",exact:true}).selectOption("create_tenancy");
  await modal.getByRole("combobox",{name:"Tenancy type",exact:true}).selectOption("shared");
  await finish("Create tenancy");
  await removeFormerOwner(page);
  await recoveryAccess(page);

}

// Inspect real native picker geometry and pointer/keyboard behavior inside the scrolling dialog.
async function reviewSelectControl(page: Page) {
  const select = page
    .getByRole("dialog")
    .getByRole("combobox", { name: "Tenancy type", exact: true });
  expect(
    await page.evaluate(() => CSS.supports("appearance", "base-select")),
  ).toBe(true);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await select.selectOption("individual");
    await select.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: resolve(".local-dev/browser", `select-closed-${width}.png`),
      fullPage: true,
    });
    await select.click();
    const option = page.getByRole("option", { name: "Shared", exact: true });
    await expect(option).toBeVisible();
    const field = (await select.boundingBox())!;
    const first = (await page
      .getByRole("option", { name: "Individual", exact: true })
      .boundingBox())!;
    const last = (await option.boundingBox())!;
    expect(first.x).toBeGreaterThanOrEqual(field.x - 1);
    expect(last.x + last.width).toBeLessThanOrEqual(field.x + field.width + 1);
    if (900 - field.y - field.height >= 130) {
      expect(first.y).toBeGreaterThanOrEqual(field.y + field.height);
    } else {
      expect(
        first.y >= field.y + field.height || last.y + last.height <= field.y,
      ).toBe(true);
    }
    expect(last.x + last.width).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: resolve(".local-dev/browser", `select-open-${width}.png`),
      fullPage: true,
    });
    await option.click();
    await expect(select).toHaveValue("shared");
    await expect(select).toBeFocused();
    await select.click();
    await page.keyboard.press("Escape");
    await expect(select).toHaveValue("shared");
    await expect(select).toBeFocused();
    await select.click();
    await page.keyboard.press("Home");
    await page.keyboard.press("Enter");
    await expect(select).toHaveValue("individual");
  }
  await page.emulateMedia({ forcedColors: "active" });
  await expect(select).toHaveCSS("appearance", "auto");
  await expect(select).toBeVisible();
  await page.emulateMedia({ forcedColors: "none" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await auditSelectPickers(page, "workflow-dialog");
}

// Compare the actual text line and checkbox centers, not just their inherited container heights.
async function reviewCheckboxControl(
  page: Page,
  labelText = "Include excluded profiles",
  snapshot = "checkbox-alignment",
) {
  const checkbox = page.getByLabel(labelText);
  for (const width of [1280, 900, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await checkbox.scrollIntoViewIfNeeded();
    if (labelText === "Shared tenancies only") {
      const search = await page
        .getByRole("searchbox", { name: "Search tenancies" })
        .boundingBox();
      expect(search!.width).toBeGreaterThanOrEqual(220);
    }
    const geometry = await checkbox.evaluate((element, expectedText) => {
      const label = element.closest("label")!;
      const walker = document.createTreeWalker(label, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        if (node.textContent?.includes(expectedText)) break;
      }
      const range = document.createRange();
      range.selectNodeContents(node!);
      const line = [...range.getClientRects()].find((rect) => rect.width > 0)!;
      const box = element.getBoundingClientRect();
      return {
        centerDifference: Math.abs(
          box.y + box.height / 2 - line.y - line.height / 2,
        ),
        height: box.height,
        labelHeight: label.getBoundingClientRect().height,
      };
    }, labelText);
    expect(geometry.centerDifference).toBeLessThanOrEqual(2);
    expect(geometry.height).toBeGreaterThanOrEqual(16);
    expect(geometry.height).toBeLessThanOrEqual(24);
    expect(geometry.labelHeight).toBeGreaterThanOrEqual(44);
    await page.screenshot({
      path: resolve(".local-dev/browser", `${snapshot}-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1280, height: 900 });
}
