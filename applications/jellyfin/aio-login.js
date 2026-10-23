(async () => {
  const opener = window.opener
  const originFragment = location.hash.slice(1)
  // Where to land after sign-in: only a page inside this web app, never another site.
  const requested = new URL(location.href).searchParams.get('next') || ''
  const next = /^\/web\//.test(requested) && !/^\/\//.test(requested) ? requested : 'index.html'
  history.replaceState(null, '', location.pathname)
  const server = new URL('../', location.href)
  let managerOrigin
  let secret
  let headers
  let timer
  let complete = false
  let closed = false
  const controller = new AbortController()

  function cleanup() {
    if (closed) return
    closed = true
    complete = true
    clearTimeout(timer)
    controller.abort()
    window.removeEventListener('message', onMessage)
    window.removeEventListener('pagehide', cleanup)
    if (opener && managerOrigin) opener.postMessage({ type: 'aio-jellyfin-complete' }, managerOrigin)
    window.opener = null
  }

  function fail(message) {
    cleanup()
    document.getElementById('status').textContent = message
  }

  async function onMessage(event) {
    if (complete || event.source !== opener || event.origin !== managerOrigin || event.data?.type !== 'aio-jellyfin-authorized') return
    if (!event.data.ok) {
      fail(event.data.message || 'Automatic sign-in failed. Continue to Jellyfin to sign in manually.')
      return
    }
    complete = true
    clearTimeout(timer)
    timer = setTimeout(() => fail('Automatic sign-in timed out. Continue to Jellyfin to sign in manually.'), 10000)
    try {
      const response = await fetch(new URL('Users/AuthenticateWithQuickConnect', server), {
        method: 'POST', headers, body: JSON.stringify({ Secret: secret }),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error('Authentication failed')
      const result = await response.json()
      if (closed) return
      if (!result.ServerId || !result.User?.Id || !result.AccessToken) throw new Error('Incomplete authentication')
      let credentials
      try { credentials = JSON.parse(localStorage.getItem('jellyfin_credentials') || '{}') } catch (_) { credentials = {} }
      if (!credentials || typeof credentials !== 'object' || Array.isArray(credentials)) credentials = {}
      const servers = Array.isArray(credentials.Servers) ? credentials.Servers : []
      credentials.Servers = [
        ...servers.filter((item) => item.Id !== result.ServerId),
        {
          Id: result.ServerId, UserId: result.User.Id, AccessToken: result.AccessToken,
          ManualAddress: server.href.replace(/\/$/, ''), LastConnectionMode: 2,
          manualAddressOnly: true, DateLastAccessed: Date.now(),
        },
      ]
      // Jellyfin Web stores authentication per origin, not in a cookie shared by ports.
      localStorage.setItem('jellyfin_credentials', JSON.stringify(credentials))
      localStorage.setItem('enableAutoLogin', 'true')
      cleanup()
      location.replace(next)
    } catch (_) {
      fail('Automatic sign-in failed. Continue to Jellyfin to sign in manually.')
    }
  }

  try {
    managerOrigin = new URL(decodeURIComponent(originFragment)).origin
    if (!opener || !/^https?:\/\//.test(managerOrigin)) throw new Error('Missing AIO window')
    let deviceId = localStorage.getItem('_deviceId2')
    if (!deviceId) {
      deviceId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join('')
      localStorage.setItem('_deviceId2', deviceId)
    }
    const auth = `MediaBrowser Client="Jellyfin Web", Device="Web Browser", DeviceId="${deviceId.replace(/["\\\r\n]/g, '')}", Version="1.0.0"`
    headers = { 'Content-Type': 'application/json', Authorization: auth, 'X-Emby-Authorization': auth }
    window.addEventListener('message', onMessage)
    window.addEventListener('pagehide', cleanup)
    timer = setTimeout(() => fail('Automatic sign-in timed out. Continue to Jellyfin to sign in manually.'), 30000)
    const response = await fetch(new URL('QuickConnect/Initiate', server), {
      method: 'POST', headers, signal: controller.signal,
    })
    if (response.status === 401) {
      fail('Quick Connect is disabled in Jellyfin. Continue to Jellyfin to sign in manually.')
      return
    }
    if (!response.ok) throw new Error('Quick Connect unavailable')
    const result = await response.json()
    if (!result.Secret || !/^[0-9]{6}$/.test(result.Code)) throw new Error('Invalid Quick Connect response')
    secret = result.Secret
    if (!complete) opener.postMessage({ type: 'aio-jellyfin-code', code: result.Code }, managerOrigin)
  } catch (_) {
    fail('Automatic sign-in is unavailable. Continue to Jellyfin to sign in manually.')
  }
})()
