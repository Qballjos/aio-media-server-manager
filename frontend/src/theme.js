/** Theme preference — localStorage cache + profile sync. */

const STORAGE_KEY = 'amm-theme'
const PREFS = new Set(['dark', 'light', 'system'])
const THEME_COLORS = {
  dark: '#0b0f17',
  light: '#f4f6fb',
}

let mediaQuery = null
let mediaHandler = null
/** First-run setup / wizard always follow OS theme until unlocked. */
let lockedToSystem = false

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
  if (lockedToSystem) {
    bindSystemListener('system')
    return applyResolvedTheme(resolveTheme('system'))
  }
  const pref = normalizePreference(preference)
  bindSystemListener(pref)
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
  if (lockedToSystem) {
    bindSystemListener('system')
    return applyResolvedTheme(resolveTheme('system'))
  }
  bindSystemListener(pref)
  return applyThemePreference(pref)
}

/** Force OS light/dark for setup + first-run wizard (does not change saved preference). */
export function lockThemeToSystem() {
  lockedToSystem = true
  bindSystemListener('system')
  return applyResolvedTheme(resolveTheme('system'))
}

/** Resume saved / profile theme after wizard completes. */
export function unlockTheme() {
  lockedToSystem = false
  const pref = getThemePreference()
  bindSystemListener(pref)
  return applyThemePreference(pref)
}

export function isThemeLockedToSystem() {
  return lockedToSystem
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
  const pref = lockedToSystem ? 'system' : normalizePreference(preference)
  if (pref !== 'system') return
  mediaHandler = () => applyResolvedTheme(resolveTheme('system'))
  mediaQuery.addEventListener('change', mediaHandler)
}

export function initTheme() {
  // First paint: follow OS until App decides setup/wizard vs saved preference.
  return lockThemeToSystem()
}

export const THEME_OPTIONS = [
  ['dark', 'Dark'],
  ['light', 'Light'],
  ['system', 'System'],
]
