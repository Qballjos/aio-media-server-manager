/** Network use for Home's Server widget: cumulative byte counters from successive status polls turned into rates. */

/**
 * Add `sample` ({at: seconds, rx, tx: bytes since boot}) to `history` and return the new history (at most `limit`
 * points). Each point carries the bytes per second since the one before it; the first point has none. A counter that
 * went backwards (reboot, wrap) starts the history over rather than drawing a spike.
 */
export function addNetSample(history, sample, limit = 30) {
  const prev = history.at(-1)
  if (prev && sample.at <= prev.at) return history
  if (prev && (sample.rx < prev.rx || sample.tx < prev.tx)) return [{ ...sample, rxRate: null, txRate: null }]
  const seconds = prev ? sample.at - prev.at : 0
  const point = {
    ...sample,
    rxRate: prev ? (sample.rx - prev.rx) / seconds : null,
    txRate: prev ? (sample.tx - prev.tx) / seconds : null,
  }
  return [...history, point].slice(-limit)
}
