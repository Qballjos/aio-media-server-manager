/** Home block order — localStorage cache + profile sync, arranged in Home's edit mode. */

import { ref } from 'vue'
import { apiRequest } from './api.js'

export const HOME_BLOCKS = [
  ['apps', 'Apps'],
  ['search', 'Search'],
  ['recent', 'Recently added'],
  ['requests', 'Requests'],
  ['trending', 'Trending'],
  ['calendar', 'Calendar'],
  ['downloads', 'Downloading'],
]
const IDS = HOME_BLOCKS.map(([id]) => id)
const KEY = 'amm-home-layout'

/** Known ids in the saved order, then any block the saved order does not mention yet. */
function complete(list) {
  const kept = (Array.isArray(list) ? list : []).filter((id) => IDS.includes(id))
  return [...new Set([...kept, ...IDS])]
}

function read() {
  try {
    return complete(JSON.parse(localStorage.getItem(KEY) || '[]'))
  } catch (_) {
    return complete([])
  }
}

export const homeLayout = ref(read())

function cache(list) {
  homeLayout.value = complete(list)
  try {
    localStorage.setItem(KEY, JSON.stringify(homeLayout.value))
  } catch (_) {
    /* the profile still has it */
  }
}

export function applyHomeLayoutFromProfile(payload = {}) {
  if (Array.isArray(payload?.homepage_layout) && payload.homepage_layout.length) cache(payload.homepage_layout)
}

export async function saveHomeLayout(list) {
  cache(list)
  try {
    await apiRequest('/api/auth/visuals', {
      method: 'PATCH',
      body: JSON.stringify({ homepage_layout: homeLayout.value }),
    })
  } catch (_) {
    /* kept in this browser; the next save syncs it */
  }
}
