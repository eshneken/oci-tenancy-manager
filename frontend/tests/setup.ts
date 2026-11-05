import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Model native modal state in jsdom without connecting to a browser or database.
Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true; } });
Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.open = false; } });
afterEach(() => { cleanup(); history.replaceState(null, '', '/administrators'); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
