/** The one-line status under a Home status widget's title ("Running smoothly", "Almost full"), and its dot colour. */

export const MOOD_COLORS = { ok: 'var(--color-success)', warn: 'var(--color-warning)', crit: 'var(--color-danger)' }

const RANK = { ok: 0, warn: 1, crit: 2 }

export function serverMood(server) {
  const checks = [
    [server.temperature, 70, 85, 'Running warm', 'Running hot'],
    [server.memory_percent, 80, 92, 'Memory is filling up', 'Memory is almost full'],
    [server.cpu_percent, 70, 90, 'CPU is busy', 'CPU is under heavy load'],
  ]
  let worst = { level: 'ok', text: 'Running smoothly' }
  for (const [value, warn, crit, warnText, critText] of checks) {
    if (value == null) continue
    const found = value >= crit ? { level: 'crit', text: critText } : value >= warn ? { level: 'warn', text: warnText } : null
    if (found && RANK[found.level] > RANK[worst.level]) worst = found
  }
  return worst
}

export function storageMood(percent) {
  if (percent >= 90) return { level: 'crit', text: 'Almost full' }
  if (percent >= 80) return { level: 'warn', text: 'Filling up' }
  return { level: 'ok', text: 'Plenty of space' }
}

export function attentionMood(items) {
  if (!items.length) return { level: 'ok', text: 'All clear' }
  const levels = items.map((item) => item.level)
  const level = levels.includes('problem') ? 'crit' : levels.includes('warning') ? 'warn' : 'ok'
  const n = items.length
  return { level, text: level === 'ok' ? `${n} thing${n === 1 ? '' : 's'} to look at` : `${n} thing${n === 1 ? '' : 's'} need${n === 1 ? 's' : ''} a look` }
}
