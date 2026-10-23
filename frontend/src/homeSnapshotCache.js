/** Last Home snapshot and network history of this browser tab, so returning to Home renders at once. */
export const homeSnapshotCache = { snapshot: null, netHistory: [] }

const PARTIAL_RETRIES = 8

/**
 * Delay before re-fetching a partial snapshot (the server is still collecting
 * widgets), or null to fall back to the regular poll.
 */
export function partialRetryDelay(attempt) {
  if (attempt >= PARTIAL_RETRIES) return null
  return Math.min(800 * 2 ** attempt, 5000)
}
