/** Home's layout: one grid per screen size on the profile (cached in localStorage), arranged in Home's edit mode. */

import { computed, ref } from 'vue'
import { apiRequest } from './api.js'
import { BP_ORDER, bpForWidth, deriveLayout, fromLegacy, normalizeLayout } from './homeGrid.js'

// HomepagePanel takes everything layout-related from here.
export { BREAKPOINTS, BP_ORDER, GRID_IDS, WIDGETS, collapseEmptyRows, firstFree, fitItem, resolve } from './homeGrid.js'

/** The blocks of the old order-and-width Home; still read to build the first grid. */
export const HOME_BLOCKS = [
  ['search', 'Greeting & search'],
  ['recent', 'Recently added'],
  ['calendar', 'Calendar'],
  ['downloads', 'Downloading'],
  ['requests', 'Requests'],
  ['trending', 'Trending'],
  ['apps', 'Dock'],
]
const IDS = HOME_BLOCKS.map(([id]) => id)
const KEY = 'amm-home-layout'
const HIDDEN_KEY = 'amm-home-hidden'
const SIZES_KEY = 'amm-home-sizes'
const GRID_KEY = 'amm-home-grid'
const SPANS = [4, 6, 12]

/** Known ids in the saved order, then any block the saved order does not mention yet. */
function complete(list) {
  const kept = (Array.isArray(list) ? list : []).filter((id) => IDS.includes(id))
  return [...new Set([...kept, ...IDS])]
}

function known(list) {
  return [...new Set((Array.isArray(list) ? list : []).filter((id) => IDS.includes(id)))]
}

/** Card widths in grid columns (4 = a third, 6 = half, 12 = full); cards not listed share a row. */
function sizes(obj) {
  const out = {}
  for (const [id, span] of Object.entries(obj && typeof obj === 'object' ? obj : {})) {
    if (IDS.includes(id) && SPANS.includes(Number(span))) out[id] = Number(span)
  }
  return out
}

/** Only the screen sizes someone arranged; the others follow from desktop. */
function grid(obj) {
  const out = {}
  if (!obj || typeof obj !== 'object') return out
  for (const bp of BP_ORDER) {
    if (Array.isArray(obj[bp])) out[bp] = normalizeLayout(obj[bp], bp)
  }
  return out
}

function read(key, fn) {
  try {
    return fn(JSON.parse(localStorage.getItem(key) || 'null'))
  } catch (_) {
    return fn(null)
  }
}

/** Home's edit mode; the toggle lives in the page tabs (App.vue), the grid in HomepagePanel. */
export const homeEditing = ref(false)

export const homeLayout = ref(read(KEY, complete))
export const homeHidden = ref(read(HIDDEN_KEY, known))
export const homeSizes = ref(read(SIZES_KEY, sizes))
export const homeGrid = ref(read(GRID_KEY, grid))
/** Goes up on every saved change, so the edit bar can say so. */
export const homeGridSaves = ref(0)

/** The screen size this window is, by the same widths Home's CSS uses. */
export const viewportBp = ref(typeof window === 'undefined' ? 'desktop' : bpForWidth(window.innerWidth))
if (typeof window !== 'undefined') {
  window.addEventListener('resize', () => {
    viewportBp.value = bpForWidth(window.innerWidth)
  }, { passive: true })
}

function cache(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (_) {
    /* the profile still has it */
  }
}

let gridPending = false
let gridTimer = null
let gridSeq = 0

export function applyHomeLayoutFromProfile(payload = {}) {
  if (Array.isArray(payload?.homepage_layout) && payload.homepage_layout.length) {
    homeLayout.value = complete(payload.homepage_layout)
    cache(KEY, homeLayout.value)
  }
  if (Array.isArray(payload?.homepage_hidden)) {
    homeHidden.value = known(payload.homepage_hidden)
    cache(HIDDEN_KEY, homeHidden.value)
  }
  if (payload?.homepage_sizes && typeof payload.homepage_sizes === 'object') {
    homeSizes.value = sizes(payload.homepage_sizes)
    cache(SIZES_KEY, homeSizes.value)
  }
  // A change still on its way to the server wins over an older copy coming back.
  if (payload?.homepage_grid && typeof payload.homepage_grid === 'object' && !gridPending) {
    homeGrid.value = grid(payload.homepage_grid)
    cache(GRID_KEY, homeGrid.value)
  }
}

async function patch(body) {
  try {
    await apiRequest('/api/auth/visuals', { method: 'PATCH', body: JSON.stringify(body) })
  } catch (_) {
    /* kept in this browser; the next save syncs it */
  }
}

/** Desktop as arranged, or as the old order-and-width Home looked. */
function desktopBase() {
  return homeGrid.value.desktop || normalizeLayout(fromLegacy({ order: homeLayout.value, sizes: homeSizes.value, hidden: homeHidden.value }), 'desktop')
}

/** The layout for a screen size: as arranged there, or derived from desktop until someone arranges it. */
export function layoutFor(bp) {
  return homeGrid.value[bp] || normalizeLayout(deriveLayout(desktopBase(), bp), bp)
}

function storeGrid(next) {
  homeGrid.value = next
  cache(GRID_KEY, next)
  homeGridSaves.value += 1
  gridPending = true
  clearTimeout(gridTimer)
  const seq = ++gridSeq
  gridTimer = setTimeout(async () => {
    await patch({ homepage_grid: homeGrid.value })
    if (seq === gridSeq) gridPending = false
  }, 300)
}

export function saveGridLayout(bp, layout) {
  const next = { ...homeGrid.value }
  if (!next.desktop) next.desktop = desktopBase()
  next[bp] = normalizeLayout(layout, bp)
  storeGrid(next)
}

/** Put back a copy of homeGrid taken earlier (Undo). */
export function restoreGrid(snapshot) {
  storeGrid(grid(snapshot))
}

export async function saveHomeHidden(list) {
  homeHidden.value = known(list)
  cache(HIDDEN_KEY, homeHidden.value)
  await patch({ homepage_hidden: homeHidden.value })
}

/** The dock is not part of the grid; whether it shows is kept with the hidden blocks, leaving the others as they are. */
export const dockHidden = computed(() => homeHidden.value.includes('apps'))

export function setDockHidden(hidden) {
  const rest = homeHidden.value.filter((id) => id !== 'apps')
  return saveHomeHidden(hidden ? [...rest, 'apps'] : rest)
}
