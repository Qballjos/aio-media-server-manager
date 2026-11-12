/** The one-line status under a Home status widget's title ("Running smoothly", "Almost full"), and its dot colour. */

import { t } from './i18n/index.js'

export const MOOD_COLORS = { ok: 'var(--color-success)', warn: 'var(--color-warning)', crit: 'var(--color-danger)' }

const RANK = { ok: 0, warn: 1, crit: 2 }

export function serverMood(server) {
  const checks = [
    [server.temperature, 70, 85, t('Running warm'), t('Running hot')],
    [server.memory_percent, 80, 92, t('Memory is filling up'), t('Memory is almost full')],
    [server.cpu_percent, 70, 90, t('CPU is busy'), t('CPU is under heavy load')],
  ]
  let worst = { level: 'ok', text: t('Running smoothly') }
  for (const [value, warn, crit, warnText, critText] of checks) {
    if (value == null) continue
    const found = value >= crit ? { level: 'crit', text: critText } : value >= warn ? { level: 'warn', text: warnText } : null
    if (found && RANK[found.level] > RANK[worst.level]) worst = found
  }
  return worst
}

export function storageMood(percent) {
  if (percent >= 90) return { level: 'crit', text: t('Almost full') }
  if (percent >= 80) return { level: 'warn', text: t('Filling up') }
  return { level: 'ok', text: t('Plenty of space') }
}

export function attentionMood(items) {
  if (!items.length) return { level: 'ok', text: t('All clear') }
  const levels = items.map((item) => item.level)
  const level = levels.includes('problem') ? 'crit' : levels.includes('warning') ? 'warn' : 'ok'
  const n = items.length
  return { level, text: level === 'ok'
    ? t(n === 1 ? '{count} thing to look at' : '{count} things to look at', { count: n })
    : t(n === 1 ? '{count} thing needs a look' : '{count} things need a look', { count: n }) }
}
