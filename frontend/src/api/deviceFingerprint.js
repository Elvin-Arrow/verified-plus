// FR-105 / docs/design.md §3: a UUID written to localStorage on first page
// load, sent with every submission from that browser.
const STORAGE_KEY = 'verified_plus_device_fingerprint_id'

function generateId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `dev_${crypto.randomUUID()}`
  }
  // Fallback for environments without crypto.randomUUID.
  return `dev_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

export function getDeviceFingerprintId() {
  let id = window.localStorage.getItem(STORAGE_KEY)
  if (!id) {
    id = generateId()
    window.localStorage.setItem(STORAGE_KEY, id)
  }
  return id
}
