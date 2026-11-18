/** Pull a YouTube id from a watch/share/embed URL so the Trailer button can open an in-app player. */
export function youtubeIdFromUrl(url) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    const host = parsed.hostname.replace(/^www\./, '').toLowerCase()
    let ident = ''
    if (host === 'youtu.be') {
      ident = parsed.pathname.replace(/^\/+/, '').split('/')[0] || ''
    } else if (host === 'youtube.com' || host === 'm.youtube.com' || host === 'youtube-nocookie.com') {
      ident = parsed.searchParams.get('v') || ''
      if (!ident && parsed.pathname.startsWith('/embed/')) {
        ident = parsed.pathname.split('/').filter(Boolean)[1] || ''
      }
    }
    return /^[A-Za-z0-9_-]{6,32}$/.test(ident) ? ident : ''
  } catch {
    return ''
  }
}
