import { apiError, apiJson } from './api.js'
import { useToasts } from './useToasts.js'

function openJellyfin(tab, helperUrl) {
  const url = new URL(helperUrl)
  const origin = url.origin
  url.hash = encodeURIComponent(window.location.origin)
  let authorizing = false
  const controller = new AbortController()
  function cleanup() {
    clearTimeout(timer)
    controller.abort()
    window.removeEventListener('message', onMessage)
    window.removeEventListener('pagehide', cleanup)
  }
  async function onMessage(event) {
    if (event.source !== tab || event.origin !== origin) return
    if (event.data?.type === 'aio-jellyfin-complete') {
      cleanup()
      return
    }
    if (authorizing || event.data?.type !== 'aio-jellyfin-code' || !/^[0-9]{6}$/.test(event.data.code)) return
    authorizing = true
    let ok = false
    let message = 'Automatic sign-in failed. Continue to Jellyfin to sign in manually.'
    try {
      const result = await apiJson('/api/applications/jellyfin/quick-connect', {
        method: 'POST', body: JSON.stringify({ code: event.data.code }), signal: controller.signal,
      })
      ok = result.res.ok && result.data.authorized === true
      if (!ok) message = apiError(result.data, message)
    } catch (_) {
      /* The helper keeps a manual sign-in link available. */
    }
    if (!controller.signal.aborted) tab.postMessage({ type: 'aio-jellyfin-authorized', ok, message: ok ? '' : message }, origin)
  }
  const timer = setTimeout(cleanup, 35000)
  window.addEventListener('message', onMessage)
  window.addEventListener('pagehide', cleanup)
  tab.location.href = url.href
}

/**
 * Open an app already signed in: ask the manager for a session (it lands as a
 * cookie on this browser), then navigate the tab opened on the click itself.
 * Jellyfin uses its own origin and Quick Connect to store its browser session.
 */
export async function openApp(event, name, fallbackUrl) {
  event.preventDefault()
  const tab = window.open('about:blank', '_blank')
  let url = fallbackUrl
  try {
    const { res, data } = await apiJson(`/api/applications/${encodeURIComponent(name)}/session`, {
      method: 'POST',
    })
    if (res.ok && data?.url) url = data.url
    if (res.ok && data?.handoff === 'jellyfin-quick-connect') {
      if (tab) {
        openJellyfin(tab, url)
        return
      }
      url = fallbackUrl
    }
    if (data?.detail && name === 'jellyfin') useToasts().showToast(data.detail, 'info')
  } catch (_) {
    /* fall back to the plain link */
  }
  if (tab) tab.location.href = url
  else window.open(url, '_blank', 'noopener,noreferrer')
}
