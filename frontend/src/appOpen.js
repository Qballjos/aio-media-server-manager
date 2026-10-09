import { apiJson } from './api.js'

/**
 * Open an app already signed in: ask the manager for a session (it lands as a
 * cookie on this browser), then navigate a tab we opened on the click itself so
 * popup blockers stay quiet. Apps without a cookie login just open their URL.
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
  } catch (_) {
    /* fall back to the plain link */
  }
  if (tab) tab.location.href = url
  else window.open(url, '_blank', 'noopener,noreferrer')
}
