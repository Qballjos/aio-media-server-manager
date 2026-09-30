export function formatBytes(n) {
  const v = Number(n) || 0
  if (v < 1024) return `${Math.round(v)} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let x = v
  let i = -1
  do {
    x /= 1024
    i += 1
  } while (x >= 1024 && i < units.length - 1)
  return `${x >= 10 ? x.toFixed(0) : x.toFixed(1)} ${units[i]}`
}

export function formatCpu(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toFixed(1)}%`
}

export function formatMemShare(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return `${n < 10 ? n.toFixed(1) : Math.round(n)}%`
}

export function formatUptime(seconds) {
  if (!seconds || seconds < 0) return '0s'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function formatUpdateWhen(ts) {
  if (!ts) return 'never'
  const ms = ts > 1e12 ? ts : ts * 1000
  return new Date(ms).toLocaleString()
}
