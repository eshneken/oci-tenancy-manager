import { expect, test } from "@playwright/test";

// Exercise responsive review, keyboard cancellation, scoped removal and cleanup retry with synthetic provider receipts.
for (const existingAccount of [true, false]) {
test(`recovery administrator reviews and changes Atlas access (${existingAccount ? "existing" : "new"} account)`, async ({ page }) => {
  const commands: unknown[] = [];
  let cleanupAttempts = 0;
  let cleanupComplete = false;
  let confirmAttempts = 0;
  const user = {
    id: "synthetic-admin",
    display_name: "Synthetic pilot",
    email: "synthetic-pilot-with-a-long-corporate-name@example.test",
    identity_kind: "corporate_sso",
    status: "active",
    authorization_revision: "active-revision",
  };
  await page.route("**/api/session", route => route.fulfill({
    json: { display_name: "Recovery administrator", workspace_id: "synthetic", expires_at: "2099-01-01T00:00:00Z" },
  }));
  await page.route("**/api/administrators?*", route => route.fulfill({
    json: { items: cleanupComplete ? [] : [user], page: 1, page_size: 10, pages: 1,
      total: cleanupComplete ? 0 : 1, statistics: { total: cleanupComplete ? 0 : 1,
      active: Number(user.status === "active"), protected_recovery: 0 } },
  }));
  await page.route("**/api/administrators/onboarding", route => route.fulfill({
    json: { enabled: true, environment: "development" },
  }));
  await page.route("**/api/administrators/onboarding/preview", route => route.fulfill({
    json: { display_name: user.display_name, work_email: user.email, username: user.email,
      environment: "development", role: "Administrator", existing_account: existingAccount, confirmation: "review" },
  }));
  await page.route("**/api/administrators/onboarding/confirm", route => {
    commands.push(route.request().postDataJSON());
    confirmAttempts += 1;
    if (!existingAccount && confirmAttempts === 1) {
      return route.fulfill({ status: 503, json: { code: "ADMINISTRATOR_SERVICE_UNAVAILABLE" } });
    }
    return route.fulfill({ json: user });
  });
  await page.route("**/api/administrators/synthetic-admin/revoke", route => {
    commands.push(route.request().postDataJSON());
    user.status = "revoked";
    user.authorization_revision = "revoked-revision";
    return route.fulfill({ json: { authorization_revision: user.authorization_revision, group_cleanup: "pending" } });
  });
  await page.route("**/api/administrators/synthetic-admin/group-cleanup", route => {
    commands.push(route.request().postDataJSON());
    cleanupAttempts += 1;
    if (cleanupAttempts === 1) return route.fulfill({ status: 503, json: { code: "ADMINISTRATOR_SERVICE_UNAVAILABLE" } });
    cleanupComplete = true;
    return route.fulfill({ json: { group_cleanup: "complete" } });
  });
  await page.goto("/administrators");
  const open = page.getByRole("button", { name: "Add administrator" });
  const add = page.getByRole("dialog", { name: "Add administrator" });
  for (const width of [1024, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await open.click();
    const email = add.getByLabel("Corporate work email");
    const alignment = await email.evaluate(input => {
      const label = input.closest("label")!;
      const range = document.createRange();
      range.selectNodeContents(label.firstChild!);
      const text = range.getBoundingClientRect();
      const field = input.getBoundingClientRect();
      return { gap: field.top - text.bottom, left: Math.abs(field.left - text.left) };
    });
    expect(alignment.gap).toBeGreaterThanOrEqual(7);
    expect(alignment.left).toBeLessThan(2);
    await email.fill(user.email);
    await add.getByRole("button", { name: "Review access" }).click();
    await expect(add.getByRole("heading", { name: "Review administrator access" })).toBeFocused();
    await expect(add.getByText(user.email)).toBeVisible();
    await expect(add.getByText(existingAccount ? /use the existing OCI account/ : /create a federated/)).toBeVisible();
    const firstName = add.getByRole("textbox", { name: "First name" });
    const lastName = add.getByRole("textbox", { name: "Last name" });
    if (existingAccount) {
      await expect(firstName).toHaveCount(0);
      await expect(lastName).toHaveCount(0);
    } else {
      await expect(firstName).toBeVisible();
      await expect(lastName).toBeVisible();
      await expect(firstName).toBeEmpty();
      await expect(lastName).toBeEmpty();
      await add.getByRole("button", { name: "Grant access" }).click();
      await expect(firstName).toBeFocused();
      await firstName.fill("  Synthetic  ");
      await add.getByRole("button", { name: "Grant access" }).click();
      await expect(lastName).toBeFocused();
      expect(commands).toEqual([]);
      await lastName.fill("D’Ávila");
    }
    await expect(add.getByText("development", { exact: true })).toBeVisible();
    const details = await add.locator(".administrator-review-details").evaluate(list => {
      const label = list.querySelector("dt")!;
      const value = list.querySelector("dd")!;
      return {
        labelWeight: Number(getComputedStyle(label).fontWeight),
        valueWeight: Number(getComputedStyle(value).fontWeight),
        labelTop: label.getBoundingClientRect().top,
        valueTop: value.getBoundingClientRect().top,
      };
    });
    expect(details.valueWeight).toBeGreaterThan(details.labelWeight);
    if (width === 1024) {
      expect(details.valueTop).toBe(details.labelTop);
    } else {
      expect(details.valueTop).toBeGreaterThan(details.labelTop);
    }
    expect(await add.evaluate(dialog => dialog.scrollWidth <= dialog.clientWidth)).toBe(true);
    if (width !== 320) {
      await page.keyboard.press("Escape");
      await expect(add).toBeHidden();
      expect(commands).toEqual([]);
    } else {
      await add.getByRole("button", { name: "Grant access" }).click();
      if (!existingAccount) {
        await expect(add.getByRole("alert")).toContainText("Grant could not be confirmed");
        await expect(email).toHaveValue(user.email);
        await add.getByRole("button", { name: "Review access" }).click();
        await expect(firstName).toHaveValue("  Synthetic  ");
        await expect(lastName).toHaveValue("D’Ávila");
        await add.getByRole("button", { name: "Grant access" }).click();
      }
    }
  }
  await expect(page.getByText("Administrator access granted.")).toBeVisible();
  await page.getByRole("button", { name: "Remove access" }).click();
  const remove = page.getByRole("dialog", { name: "Revoke administrator access?" });
  await expect(remove.getByText(user.email)).toBeVisible();
  await expect(remove.getByText(user.email)).toHaveCSS("font-weight", "700");
  await expect(remove.getByText("development", { exact: true })).toBeVisible();
  expect(await remove.evaluate(dialog => dialog.scrollWidth <= dialog.clientWidth)).toBe(true);
  await remove.getByRole("button", { name: "Revoke access" }).click();
  await expect(page.getByText("Atlas access is revoked. OCI group cleanup can be retried.")).toBeVisible();
  await expect(page.getByRole("searchbox")).toBeFocused();
  const cleanup = page.getByRole("button", { name: "Retry OCI group cleanup for Synthetic pilot" });
  await cleanup.click();
  await expect(page.getByRole("row", { name: /Synthetic pilot/ }).getByText("Cleanup failed")).toBeVisible();
  await cleanup.click();
  await expect(page.getByText("OCI group cleanup complete.", { exact: true })).toBeVisible();
  await expect(page.getByRole("row", { name: /Synthetic pilot/ })).toHaveCount(0);
  await expect(page.getByRole("searchbox")).toBeFocused();
  await page.reload();
  await expect(page.getByText("No administrators match your search")).toBeVisible();
  await expect(page.getByRole("row", { name: /Synthetic pilot/ })).toHaveCount(0);
  const confirmation = { value: user.email, confirmation: "review" };
  const newAccount = { ...confirmation, name: { first_name: "Synthetic", last_name: "D’Ávila" } };
  expect(commands).toEqual([
    ...(existingAccount ? [confirmation] : [newAccount, newAccount]),
    { expected_revision: "active-revision" },
    { expected_revision: "revoked-revision" },
    { expected_revision: "revoked-revision" },
  ]);
});
}
