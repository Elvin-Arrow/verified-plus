// FE-01: shared Vitest setup (TI-01's frontend-test-infra equivalent).
import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from '../mocks/server.js'

// FE-02: MSW mock server lifecycle, shared by every contract-mocked test.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
