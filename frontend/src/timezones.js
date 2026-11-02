/** IANA zones for the system clock. UTC stays first; the current value is kept even if it is unusual. */

const FALLBACK = [
  'UTC',
  'Europe/Amsterdam',
  'Europe/Brussels',
  'Europe/Berlin',
  'Europe/Paris',
  'Europe/London',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'Australia/Sydney',
  'Pacific/Auckland',
  'Asia/Tokyo',
  'Asia/Singapore',
]

export function timezoneChoices(current = '') {
  let zones = FALLBACK
  try {
    if (typeof Intl !== 'undefined' && typeof Intl.supportedValuesOf === 'function') {
      const supported = Intl.supportedValuesOf('timeZone')
      if (supported?.length) zones = supported
    }
  } catch {
    zones = FALLBACK
  }
  const names = []
  const seen = new Set()
  const add = (zone) => {
    const name = String(zone || '').trim()
    if (!name || seen.has(name)) return
    seen.add(name)
    names.push(name)
  }
  add('UTC')
  for (const zone of zones) add(zone)
  add(current)
  names.sort((a, b) => (a === 'UTC' ? -1 : b === 'UTC' ? 1 : a.localeCompare(b)))
  return names.map((value) => ({ value, label: value.replace(/_/g, ' ') }))
}
