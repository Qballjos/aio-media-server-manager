export const HOMEPAGE_WIDGET_DEBUG_KEY = 'amm-homepage-widget-debug'

export function readHomepageWidgetDebug() {
  try {
    return localStorage.getItem(HOMEPAGE_WIDGET_DEBUG_KEY) === '1'
  } catch (_) {
    return false
  }
}

export function writeHomepageWidgetDebug(enabled) {
  try {
    localStorage.setItem(HOMEPAGE_WIDGET_DEBUG_KEY, enabled ? '1' : '0')
  } catch (_) {
    /* ignore */
  }
}
