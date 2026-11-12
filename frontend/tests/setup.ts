import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

// Model native modal state in jsdom without connecting to a browser or database.
Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true; } });
Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.open = false; } });
afterEach(() => { cleanup(); history.replaceState(null, '', '/administrators'); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

// jsdom has no layout observer; real responsive sizing is covered by the browser geometry checks.
class LayoutObserver {
  // Registering a target is inert because jsdom cannot compute element geometry.
  observe() {}
  // Match the browser cleanup contract for component unmounts.
  disconnect() {}
}
beforeEach(() => vi.stubGlobal("ResizeObserver", LayoutObserver));
