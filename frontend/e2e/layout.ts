import type {ElementHandle, Locator, Page} from "@playwright/test";

// Retain fractional browser coordinates without copying page text into failure diagnostics.
type LayoutBox = {x: number; y: number; width: number; height: number};

// Resolve named targets first, then measure them in one browser task without mixing viewport origins.
export async function layoutSnapshot<K extends string>(page: Page, targets: Record<K, Locator>) {
  const names = Object.keys(targets) as K[];
  const handles: (ElementHandle<HTMLElement | SVGElement> | null)[] = [];
  try {
    for (const name of names) handles.push(await targets[name].elementHandle());
    return await page.evaluate(({names, nodes}) => ({
      viewportWidth: innerWidth,
      scrollX,
      scrollY,
      boxes: Object.fromEntries(names.map((name, index) => {
        const element = nodes[index];
        if (!element?.isConnected) throw new Error("Layout target is not attached");
        const {x, y, width, height} = element.getBoundingClientRect();
        if (width <= 0 || height <= 0) throw new Error("Layout target is not rendered");
        return [name, {x, y, width, height}];
      })) as Record<K, LayoutBox>,
    }), {names, nodes: handles});
  } finally {
    // Release references even when a later target is ambiguous or an assertion fixture is hidden.
    await Promise.all(handles.map(handle => handle?.dispose()));
  }
}
