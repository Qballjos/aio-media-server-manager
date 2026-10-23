/** Liquid-glass tuning — panel opacity, backdrop blur, parallax depth and photo-wallpaper blur; localStorage cache + profile sync. */

import { ref } from 'vue'

export const GLASS_DEFAULTS = { alpha: 0.5, blur: 28, depth: 1, wallpaperBlur: 12 }
/** [min, max, step] per control. */
export const GLASS_RANGES = { alpha: [0.15, 0.9, 0.01], blur: [0, 60, 1], depth: [0, 2, 0.05], wallpaperBlur: [0, 40, 1] }
const KEY = 'amm-glass'

function clamp(key, value) {
  const [min, max] = GLASS_RANGES[key]
  const n = Number(value)
  if (!Number.isFinite(n)) return GLASS_DEFAULTS[key]
  return Math.min(max, Math.max(min, n))
}

function normalize(values = {}) {
  return {
    alpha: clamp('alpha', values.alpha ?? GLASS_DEFAULTS.alpha),
    blur: Math.round(clamp('blur', values.blur ?? GLASS_DEFAULTS.blur)),
    depth: clamp('depth', values.depth ?? GLASS_DEFAULTS.depth),
    wallpaperBlur: Math.round(clamp('wallpaperBlur', values.wallpaperBlur ?? GLASS_DEFAULTS.wallpaperBlur)),
  }
}

function read() {
  try {
    return normalize(JSON.parse(localStorage.getItem(KEY) || '{}'))
  } catch (_) {
    return { ...GLASS_DEFAULTS }
  }
}

export const glass = ref(read())

/** Push the values into CSS and remember them in this browser. */
export function applyGlass(values) {
  const next = normalize({ ...glass.value, ...values })
  glass.value = next
  if (typeof document !== 'undefined') {
    const root = document.documentElement.style
    root.setProperty('--glass-alpha', String(next.alpha))
    root.setProperty('--glass-blur', `${next.blur}px`)
    root.setProperty('--glass-depth', String(next.depth))
    root.setProperty('--wallpaper-blur', `${next.wallpaperBlur}px`)
  }
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch (_) {
    /* the profile still has it */
  }
  return next
}

export function applyGlassFromProfile(payload = {}) {
  if (!payload || typeof payload !== 'object') return glass.value
  const values = {}
  if (typeof payload.glass_alpha === 'number') values.alpha = payload.glass_alpha
  if (typeof payload.glass_blur === 'number') values.blur = payload.glass_blur
  if (typeof payload.glass_depth === 'number') values.depth = payload.glass_depth
  if (typeof payload.wallpaper_blur === 'number') values.wallpaperBlur = payload.wallpaper_blur
  return Object.keys(values).length ? applyGlass(values) : glass.value
}

export function glassProfileBody(values = glass.value) {
  const next = normalize(values)
  return { glass_alpha: next.alpha, glass_blur: next.blur, glass_depth: next.depth, wallpaper_blur: next.wallpaperBlur }
}

export function initGlass() {
  return applyGlass(glass.value)
}
