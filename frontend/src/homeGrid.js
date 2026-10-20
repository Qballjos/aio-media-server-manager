/** Home's widget grid: sizes per widget, collisions, the move from the old order-and-width layout, and clean-up of saved data. No Vue in here. */

/** Columns per screen size; `preview` is how wide edit mode shows a smaller screen on a bigger one. */
export const BREAKPOINTS = {
  phone: { cols: 4, gap: 12, preview: 420, label: 'Phone' },
  tablet: { cols: 8, gap: 16, preview: 860, label: 'Tablet' },
  desktop: { cols: 12, gap: 16, preview: null, label: 'Desktop' },
}
export const BP_ORDER = ['phone', 'tablet', 'desktop']

/** The same widths Home's CSS breaks at: under 720 px a phone, under 1200 px a tablet. */
export function bpForWidth(width) {
  return width < 720 ? 'phone' : width < 1200 ? 'tablet' : 'desktop'
}

/** Sizes are [columns, rows]; `size` is where a widget starts on each screen, `presets` what its sheet offers. */
export const WIDGETS = {
  search: { label: 'Greeting & search', min: [4, 1], max: [12, 3], size: { desktop: [12, 2], tablet: [8, 2], phone: [4, 2] }, presets: [[12, 1, 'Slim'], [12, 2, 'Standard'], [6, 2, 'Half']] },
  recent: { label: 'Recently added', min: [3, 3], max: [12, 6], size: { desktop: [12, 3], tablet: [8, 3], phone: [4, 3] }, presets: [[4, 3, 'Small'], [8, 3, 'Wide'], [12, 3, 'Full'], [12, 4, 'Tall']] },
  calendar: { label: 'Calendar', min: [3, 3], max: [12, 8], size: { desktop: [12, 4], tablet: [8, 4], phone: [4, 5] }, presets: [[4, 4, 'Agenda'], [12, 4, 'Week'], [12, 6, 'Large']] },
  downloads: { label: 'Downloading', min: [2, 2], max: [12, 8], size: { desktop: [4, 4], tablet: [4, 4], phone: [4, 4] }, presets: [[2, 2, 'Counter'], [4, 4, 'List'], [6, 4, 'Wide']] },
  requests: { label: 'Requests', min: [3, 3], max: [12, 6], size: { desktop: [6, 3], tablet: [4, 3], phone: [4, 3] }, presets: [[4, 3, 'Small'], [6, 3, 'Half'], [12, 3, 'Full']] },
  trending: { label: 'Trending', min: [3, 4], max: [12, 6], size: { desktop: [6, 4], tablet: [4, 4], phone: [4, 4] }, presets: [[4, 4, 'Small'], [6, 4, 'Half'], [12, 4, 'Full']] },
  playing: { label: 'Now playing', min: [3, 2], max: [12, 6], size: { desktop: [6, 3], tablet: [4, 3], phone: [4, 3] }, presets: [[4, 2, 'Small'], [6, 3, 'List'], [12, 4, 'Large']] },
  storage: { label: 'Storage', min: [2, 2], max: [12, 4], size: { desktop: [4, 2], tablet: [4, 2], phone: [4, 2] }, presets: [[2, 2, 'Counter'], [4, 2, 'List'], [6, 3, 'Wide']] },
  server: { label: 'Server', min: [2, 2], max: [8, 4], size: { desktop: [4, 2], tablet: [4, 2], phone: [4, 2] }, presets: [[2, 2, 'Counter'], [4, 2, 'Standard'], [6, 2, 'Wide']] },
  attention: { label: 'Needs attention', min: [3, 2], max: [12, 6], size: { desktop: [4, 3], tablet: [4, 3], phone: [4, 3] }, presets: [[3, 2, 'Small'], [4, 3, 'List'], [8, 3, 'Wide']] },
}
export const GRID_IDS = Object.keys(WIDGETS)
/** The blocks the old order-and-width Home had; newer widgets are added from Add widget, not slipped into an existing Home. */
export const LEGACY_IDS = ['search', 'recent', 'calendar', 'downloads', 'requests', 'trending']

const clamp = (value, low, high) => Math.max(low, Math.min(high, value))

export function collides(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
}

const inside = (c, o) => c.x >= o.x && c.y >= o.y && c.x + c.w <= o.x + o.w && c.y + c.h <= o.y + o.h

/** Rows the layout takes up. */
export function rows(layout) {
  return layout.reduce((most, item) => Math.max(most, item.y + item.h), 0)
}

/** The first spot in reading order where a w × h widget fits. */
export function firstFree(layout, w, h, cols) {
  for (let y = 0; ; y++) {
    for (let x = 0; x + w <= cols; x++) {
      if (!layout.some((item) => collides(item, { x, y, w, h }))) return { x, y }
    }
  }
}

/** The free spot closest to where `item` was; spots inside `origin` (the place just vacated) win. */
function freeSpot(placed, item, cols, origin) {
  const w = Math.min(item.w, cols)
  const limit = rows(placed)
  let best = { x: 0, y: limit }
  let cost = Infinity
  for (let y = 0; y <= limit; y++) {
    for (let x = 0; x + w <= cols; x++) {
      const spot = { x, y, w, h: item.h }
      if (placed.some((other) => collides(other, spot))) continue
      let score = Math.hypot(x - item.x, (y - item.y) * 1.2)
      if (origin && inside(spot, origin)) score -= 1000
      if (score < cost) {
        cost = score
        best = { x, y }
      }
    }
  }
  return { ...best, w }
}

/** Put `rect` for `id` into the layout. Widgets it touches move to the nearest free spot; the others stay where they are. */
export function resolve(layout, id, rect, cols, origin = null) {
  const placed = [{ ...rect, id }]
  const pushed = []
  for (const item of layout) {
    if (item.id === id) continue
    if (collides(item, rect)) pushed.push(item)
    else placed.push({ ...item })
  }
  pushed.sort((a, b) => a.y - b.y || a.x - b.x)
  for (const item of pushed) placed.push({ ...item, ...freeSpot(placed, item, cols, origin) })
  return placed
}

/** Keep a widget within its own minimum and maximum and inside the columns. */
export function fitItem(item, cols) {
  const spec = WIDGETS[item.id]
  const [minW, minH] = spec ? spec.min : [1, 1]
  const [maxW, maxH] = spec ? spec.max : [cols, 12]
  const w = clamp(item.w, Math.min(minW, cols), Math.min(maxW, cols))
  const h = clamp(item.h, minH, maxH)
  return { id: item.id, x: clamp(item.x, 0, cols - w), y: Math.max(0, item.y), w, h }
}

/** Saved data made safe: known widgets once each, whole numbers, inside the grid, nothing on top of anything else. */
export function normalizeLayout(list, bp) {
  const cols = BREAKPOINTS[bp].cols
  const seen = new Set()
  const items = []
  for (const raw of Array.isArray(list) ? list : []) {
    if (!raw || !WIDGETS[raw.id] || seen.has(raw.id)) continue
    const [x, y, w, h] = ['x', 'y', 'w', 'h'].map((key) => Math.round(Number(raw[key])))
    if (![x, y, w, h].every(Number.isFinite)) continue
    seen.add(raw.id)
    items.push(fitItem({ id: raw.id, x, y, w, h }, cols))
  }
  items.sort((a, b) => a.y - b.y || a.x - b.x)
  const placed = []
  for (const item of items) {
    placed.push(placed.some((other) => collides(other, item)) ? { ...item, ...firstFree(placed, item.w, item.h, cols) } : item)
  }
  return placed
}

const LEGACY_SPANS = [4, 6, 12]

/**
 * The desktop grid that matches the old Home: blocks in the saved order, hidden ones left out, the greeting on a row
 * of its own and cards sharing rows of 12 columns (a chosen 4, 6 or 12 keeps its width, the rest share what is left).
 */
export function fromLegacy({ order = [], sizes = {}, hidden = [] } = {}) {
  const gone = new Set(Array.isArray(hidden) ? hidden : [])
  const ids = [...new Set([...(Array.isArray(order) ? order : []), ...LEGACY_IDS])].filter((id) => LEGACY_IDS.includes(id) && !gone.has(id))
  const fixed = (id) => (LEGACY_SPANS.includes(Number(sizes?.[id])) ? Number(sizes[id]) : 0)
  const out = []
  let y = 0
  let row = []
  let used = 0
  const flush = () => {
    if (!row.length) return
    const autos = row.filter((id) => !fixed(id))
    const free = 12 - row.reduce((sum, id) => sum + fixed(id), 0)
    const share = autos.length ? Math.max(3, Math.floor(free / autos.length)) : 0
    const h = Math.max(...row.map((id) => WIDGETS[id].size.desktop[1]))
    let x = 0
    for (const id of row) {
      const w = Math.min(fixed(id) || share, 12 - x)
      out.push({ id, x, y, w, h })
      x += w
    }
    y += h
    row = []
    used = 0
  }
  for (const id of ids) {
    if (id === 'search') {
      flush()
      const [w, h] = WIDGETS.search.size.desktop
      out.push({ id, x: 0, y, w, h })
      y += h
      continue
    }
    const want = fixed(id) || 4
    if (used + want > 12) flush()
    row.push(id)
    used += want
  }
  flush()
  return out
}

/** A smaller screen's starting layout: the desktop widgets in reading order, scaled down and flowed into rows. A phone gets every widget full width. */
export function deriveLayout(desktop, bp) {
  const cols = BREAKPOINTS[bp].cols
  if (cols === 12) return desktop.map((item) => ({ ...item }))
  const out = []
  let x = 0
  let y = 0
  let rowH = 0
  for (const item of [...desktop].sort((a, b) => a.y - b.y || a.x - b.x)) {
    const spec = WIDGETS[item.id]
    const fitted = fitItem({ ...item, x: 0, w: bp === 'phone' ? cols : Math.round((item.w * cols) / 12) }, cols)
    const h = fitted.w === cols && spec ? spec.size[bp][1] : fitted.h
    if (x + fitted.w > cols) {
      y += rowH
      x = 0
      rowH = 0
    }
    out.push({ id: item.id, x, y, w: fitted.w, h })
    x += fitted.w
    rowH = Math.max(rowH, h)
  }
  return out
}

/** Outside edit mode: rows no widget covers (left by widgets with nothing to show) close up; holes beside a widget stay. */
export function collapseEmptyRows(layout) {
  const used = new Set()
  for (const item of layout) for (let r = item.y; r < item.y + item.h; r++) used.add(r)
  const empty = (y) => {
    let n = 0
    for (let r = 0; r < y; r++) if (!used.has(r)) n++
    return n
  }
  return layout.map((item) => ({ ...item, y: item.y - empty(item.y) }))
}
