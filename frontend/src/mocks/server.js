// FE-02: Node-side MSW server, started/stopped by test setup.
import { setupServer } from 'msw/node'
import { handlers } from './handlers.js'

export const server = setupServer(...handlers)
