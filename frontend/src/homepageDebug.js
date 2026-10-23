/** Homepage widget debug — localStorage cache + profile sync. */

export const HOMEPAGE_WIDGET_DEBUG_KEY = 'amm-homepage-widget-debug'
export const HOMEPAGE_WIDGET_DEBUG_EVENT = 'amm-homepage-widget-debug'

export function readHomepageWidgetDebug() {
  try {
    return localStorage.getItem(HOMEPAGE_WIDGET_DEBUG_KEY) === '1'
  } catch (_) {
    return false
  }
}

export function cacheHomepageWidgetDebug(enabled) {
  const on = !!enabled
  try {
    localStorage.setItem(HOMEPAGE_WIDGET_DEBUG_KEY, on ? '1' : '0')
  } catch (_) {
    /* ignore */
  }
  if (typeof window !== 'undefined') {
    try {
      window.dispatchEvent(
        new CustomEvent(HOMEPAGE_WIDGET_DEBUG_EVENT, { detail: { enabled: on } })
      )
    } catch (_) {
      /* ignore */
    }
  }
  return on
}

/** @deprecated Prefer cacheHomepageWidgetDebug + profile save. */
export function writeHomepageWidgetDebug(enabled) {
  return cacheHomepageWidgetDebug(enabled)
}

export function applyHomepageWidgetDebugFromProfile(payload = {}) {
  if (!payload || typeof payload !== 'object') return readHomepageWidgetDebug()
  if (typeof payload.homepage_widget_debug === 'boolean') {
    return cacheHomepageWidgetDebug(payload.homepage_widget_debug)
  }
  return readHomepageWidgetDebug()
}
