import type {Locator} from "@playwright/test";

// Read related rectangles and their viewport origin in one browser task so scrolling cannot split a comparison.
export async function layoutSnapshot(elements: Locator) {
  return elements.evaluateAll(nodes => ({
    viewportWidth: innerWidth,
    scrollX,
    scrollY,
    boxes: nodes.map(element => {
      const {x, y, width, height} = element.getBoundingClientRect();
      if (width <= 0 || height <= 0) throw new Error("Layout target is not rendered");
      return {x, y, width, height};
    }),
  }));
}
