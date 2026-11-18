import { BREAKPOINTS, WIDGETS, firstFree, normalizeLayout } from './homeGrid.js'

const compact = { min: [3, 2], max: [12, 5], size: { desktop: [6, 2], tablet: [4, 2], phone: [4, 2] } }
export const MEMBER_WIDGETS = {
  greeting: WIDGETS.greeting,
  searchbar: { ...WIDGETS.searchbar, max: [12, 3] },
  requests: { ...WIDGETS.requests, label: 'My requests' },
  recent: { ...WIDGETS.recent, label: 'Newly available' },
  calendar: WIDGETS.calendar,
  trending: WIDGETS.trending,
  limits: { ...compact, label: 'Request limits' },
  support: { ...compact, label: 'Support' },
}

export function addMemberWidget(layout, id, bp) {
  const [w, h] = MEMBER_WIDGETS[id].size[bp]
  const spot = firstFree(layout, w, h, BREAKPOINTS[bp].cols)
  return [...layout, { id, ...spot, w, h }]
}

export function defaultMemberLayout(bp) {
  return Object.keys(MEMBER_WIDGETS).reduce((layout, id) => addMemberWidget(layout, id, bp), [])
}

function storageKey(account) {
  return `amm-member-home:${account}`
}

export function readMemberLayouts(account) {
  try {
    return JSON.parse(localStorage.getItem(storageKey(account))) || {}
  } catch (_) {
    return {}
  }
}

export function saveMemberLayouts(account, layouts) {
  try {
    localStorage.setItem(storageKey(account), JSON.stringify(layouts))
  } catch (_) {}
}

export function memberLayoutFor(layouts, bp) {
  if (!Array.isArray(layouts[bp])) return defaultMemberLayout(bp)
  const layout = normalizeLayout(layouts[bp], bp, MEMBER_WIDGETS)
  if (layouts.greetingAdded || layout.some(item => item.id === 'greeting')) return layout
  const [w, h] = MEMBER_WIDGETS.greeting.size[bp]
  return [{ id: 'greeting', x: 0, y: 0, w, h }, ...layout.map(item => ({ ...item, y: item.y + h }))]
}
