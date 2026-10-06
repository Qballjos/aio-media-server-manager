/** Theme preference — localStorage cache + profile sync. */

const STORAGE_KEY = 'amm-theme'
const PREFS = new Set(['dark', 'light', 'system'])
const THEME_COLORS = {
  dark: '#0b0f17',
  light: '#f4f6fb',
}

let mediaQuery = null
let mediaHandler = null

function normalizePreference(value) {
  return PREFS.has(value) ? value : 'dark'
}

export function getThemePreference() {
  try {
    return normalizePreference(localStorage.getItem(STORAGE_KEY))
  } catch (_) {
    return 'dark'
  }
}

export function resolveTheme(preference = getThemePreference()) {
  const pref = normalizePreference(preference)
  if (pref !== 'system') return pref
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark'
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function syncMetaThemeColor(theme) {
  if (typeof document === 'undefined') return
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', THEME_COLORS[theme] || THEME_COLORS.dark)
}

export function applyResolvedTheme(theme) {
  const resolved = theme === 'light' ? 'light' : 'dark'
  const root = document.documentElement
  root.setAttribute('data-theme', resolved)
  root.style.colorScheme = resolved
  syncMetaThemeColor(resolved)
  return resolved
}

export function applyThemePreference(preference = getThemePreference()) {
  const pref = normalizePreference(preference)
  return applyResolvedTheme(resolveTheme(pref))
}

export function cacheThemePreference(preference) {
  const pref = normalizePreference(preference)
  try {
    localStorage.setItem(STORAGE_KEY, pref)
  } catch (_) {}
  return pref
}

export function setThemePreference(preference) {
  const pref = cacheThemePreference(preference)
  bindSystemListener(pref)
  return applyThemePreference(pref)
}

function bindSystemListener(preference = getThemePreference()) {
  if (typeof window === 'undefined' || !window.matchMedia) return
  if (!mediaQuery) {
    mediaQuery = window.matchMedia('(prefers-color-scheme: light)')
  }
  if (mediaHandler) {
    mediaQuery.removeEventListener('change', mediaHandler)
    mediaHandler = null
  }
  if (normalizePreference(preference) !== 'system') return
  mediaHandler = () => applyResolvedTheme(resolveTheme('system'))
  mediaQuery.addEventListener('change', mediaHandler)
}

export function initTheme() {
  const pref = getThemePreference()
  applyThemePreference(pref)
  bindSystemListener(pref)
  return pref
}

export const THEME_OPTIONS = [
  ['dark', 'Dark'],
  ['light', 'Light'],
  ['system', 'System'],
]
