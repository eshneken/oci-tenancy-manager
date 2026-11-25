import { expect, test } from "@playwright/test";

// Run real browser layout and keyboard behavior with synthetic sign-in endpoints and no OCI calls.
test("Corporate SSO leads and a failed attempt leaves recovery available", async ({ page }) => {
  let starts = 0;
  await page.route("**/api/session", async route => route.fulfill({ status: 401 }));
  await page.route("**/api/auth/sso/status", async route => route.fulfill({ json: { enabled: true } }));
  await page.route("**/api/auth/sso/start", async route => {
    starts += 1;
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-otm-request"]).toBe("1");
    await route.fulfill({ status: 503 });
  });
  await page.goto("/login");
  const primary = page.getByRole("button", { name: "Sign in with Corporate SSO" });
  const recovery = page.getByText("Recovery administrator sign-in", { exact: true });
  const password = page.getByLabel("Password", { exact: true });
  await expect(primary).toBeVisible();
  await expect(primary).toHaveClass(/\bprimary\b/);
  await expect(password).toBeHidden();
  await primary.click();
  expect(starts).toBe(1);
  await expect(page.getByRole("alert")).toHaveText("Oracle SSO could not complete. Please try again.");

  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(password).toBeHidden();
    await recovery.focus();
    await expect(recovery).toBeFocused();
    await recovery.press("Enter");
    await expect(password).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toHaveClass(/\bsecondary\b/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await recovery.press("Enter");
    await expect(password).toBeHidden();
  }
});

// A configured installation waits for method discovery and sends a successful start to the IdP.
test("sign-in method discovery does not flash recovery before Oracle SSO", async ({ page }) => {
  let finishDiscovery!: () => void;
  const discovery = new Promise<void>(resolve => { finishDiscovery = resolve; });
  const provider = "https://identity.example.test/oauth2/v1/authorize";
  await page.route("**/api/session", async route => route.fulfill({ status: 401 }));
  await page.route("**/api/auth/sso/status", async route => {
    await discovery;
    await route.fulfill({ json: { enabled: true } });
  });
  await page.route("**/api/auth/sso/start", async route => {
    await route.fulfill({ json: { authorization_url: provider } });
  });
  await page.route(provider, async route => route.fulfill({
    contentType: "text/html",
    body: "<h1>Synthetic provider</h1>",
  }));
  await page.goto("/login");
  await expect(page.getByRole("status")).toHaveText("Loading sign-in methods…");
  await expect(page.getByLabel("Password", { exact: true })).toBeHidden();
  finishDiscovery();
  await page.getByRole("button", { name: "Sign in with Corporate SSO" }).click();
  await expect(page).toHaveURL(provider);
  await expect(page.getByRole("heading", { name: "Synthetic provider" })).toBeVisible();
});
