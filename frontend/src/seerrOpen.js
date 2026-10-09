import { apiJson } from './api.js'

/**
 * Open Seerr already signed in: ask the manager for a Seerr session (it lands as a
 * cookie on this browser), then navigate a tab we opened on the click itself so
 * popup blockers stay quiet. Falls back to the plain URL when anything fails.
 */
export async function openSeerr(event, fallbackUrl) {
  event.preventDefault()
  const tab = window.open('about:blank', '_blank')
  let url = fallbackUrl
  try {
    const { res, data } = await apiJson('/api/applications/seerr/session', { method: 'POST' })
    if (res.ok && data?.url) url = data.url
  } catch (_) {
    /* fall back to the plain link */
  }
  if (tab) tab.location.href = url
  else window.open(url, '_blank', 'noopener,noreferrer')
}
