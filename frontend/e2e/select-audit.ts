import { expect, type Page } from "@playwright/test";
import { resolve } from "node:path";

const shortLabels = new Set(["All states", "Queued", "Running", "Waiting", "Needs attention", "Succeeded", "Cancelled", "Failed", "All categories", "Authentication", "Administration", "Operations", "Organization", "Email delivery", "Check out of date"]);

// Inspect the actual shared native picker, including short labels, option bounds and keyboard exit.
export async function auditSelectPickers(page: Page, tag: string) {
  expect(await page.evaluate(() => CSS.supports("appearance", "base-select"))).toBe(true);
  for (const width of [1280, 900, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    // A modal makes background fields inert even though their CSS boxes remain visible.
    const dialog = page.locator("dialog[open]");
    const scope = await dialog.count() ? dialog : page;
    const fields = scope.locator("select:visible:enabled");
    for (let index = 0; index < await fields.count(); index++) {
      const field = fields.nth(index);
      const value = await field.inputValue();
      await field.scrollIntoViewIfNeeded();
      await field.click();
      await expect.poll(() => field.evaluate(node => node.matches(":open"))).toBe(true);
      const options = await field.locator("option").evaluateAll(nodes => nodes.map(node => {
        const box = node.getBoundingClientRect();
        return { text: node.textContent?.trim() ?? "", x: box.x, width: box.width, height: box.height };
      }));
      for (const option of options.filter(option => option.width > 0)) {
        expect(option.x).toBeGreaterThanOrEqual(0);
        expect(option.x + option.width).toBeLessThanOrEqual(width + 1);
        if (shortLabels.has(option.text)) expect(option.height).toBeLessThanOrEqual(46);
      }
      await page.screenshot({ path: resolve(".local-dev/browser", `select-audit-${tag}-${index}-${width}.png`), fullPage: true });
      await field.press("Escape");
      await expect(field).toBeFocused();
      await expect(field).toHaveValue(value);
      // Keyboard opening must use the same bounded picker without committing another option.
      await field.press("Space");
      await expect.poll(() => field.evaluate(node => node.matches(":open"))).toBe(true);
      await field.press("Escape");
      await expect(field).toHaveValue(value);
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
}
