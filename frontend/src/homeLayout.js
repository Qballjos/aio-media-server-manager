/** Home block order and hidden blocks — localStorage cache + profile sync, arranged in Home's edit mode. */

import { ref } from 'vue'
import { apiRequest } from './api.js'

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

function read(key, fn) {
  try {
    return fn(JSON.parse(localStorage.getItem(key) || 'null'))
  } catch (_) {
    return fn(null)
  }
}

/** Home's edit mode; the toggle lives in the page tabs (App.vue), the panels in HomepagePanel. */
export const homeEditing = ref(false)

export const homeLayout = ref(read(KEY, complete))
export const homeHidden = ref(read(HIDDEN_KEY, known))
export const homeSizes = ref(read(SIZES_KEY, sizes))

function cache(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (_) {
    /* the profile still has it */
  }
}

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
}

async function patch(body) {
  try {
    await apiRequest('/api/auth/visuals', { method: 'PATCH', body: JSON.stringify(body) })
  } catch (_) {
    /* kept in this browser; the next save syncs it */
  }
}

export async function saveHomeLayout(list) {
  homeLayout.value = complete(list)
  cache(KEY, homeLayout.value)
  await patch({ homepage_layout: homeLayout.value })
}

export async function saveHomeHidden(list) {
  homeHidden.value = known(list)
  cache(HIDDEN_KEY, homeHidden.value)
  await patch({ homepage_hidden: homeHidden.value })
}

export async function saveHomeSizes(obj) {
  homeSizes.value = sizes(obj)
  cache(SIZES_KEY, homeSizes.value)
  await patch({ homepage_sizes: homeSizes.value })
}
