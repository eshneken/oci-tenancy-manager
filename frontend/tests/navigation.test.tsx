import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { useNavigation } from "../src/navigation";

// Re-selecting the same menu item and native history both publish fresh count-refresh signals.
it("tracks every menu activation even when its pathname stays the same", () => {
  history.replaceState(null, "", "/tenancies");
  const { result } = renderHook(() => useNavigation());
  expect(result.current.revision).toBe(0);
  act(() => result.current.navigate("/tenancies"));
  expect(result.current.path).toBe("/tenancies");
  expect(result.current.revision).toBe(1);
  act(() => result.current.navigate("/tenancies"));
  expect(result.current.revision).toBe(2);
  act(() => { history.replaceState(null, "", "/audit-history"); window.dispatchEvent(new PopStateEvent("popstate")); });
  expect(result.current.path).toBe("/audit-history");
  expect(result.current.revision).toBe(3);
});
