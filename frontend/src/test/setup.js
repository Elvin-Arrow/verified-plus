// FE-01: shared Vitest setup (TI-01's frontend-test-infra equivalent).
import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, expect } from 'vitest'
import { toHaveNoViolations } from 'vitest-axe/matchers'
import { server } from '../mocks/server.js'

// FE-15: toHaveNoViolations() matcher — registered manually since
// vitest-axe's own extend-expect.js entry point ships empty (v0.1.0).
expect.extend({ toHaveNoViolations })

// jsdom under this Node version doesn't reliably expose window.localStorage
// (Node's own experimental global localStorage shadows it without a
// --localstorage-file flag) — polyfill a minimal in-memory version so
// FE-03's device-fingerprint code has something real to read/write in tests.
if (typeof window !== 'undefined' && !window.localStorage) {
  const store = new Map()
  window.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
  }
}

// FE-02: MSW mock server lifecycle, shared by every contract-mocked test.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
