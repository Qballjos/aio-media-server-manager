(() => {
  const opener = window.opener
  let manager
  let finished = false
  let timer
  function cleanup() {
    finished = true
    clearTimeout(timer)
    window.removeEventListener('message', receive)
    window.removeEventListener('pagehide', cleanup)
    if (opener && manager) opener.postMessage({ type: 'aio-cleanuparr-complete' }, manager.origin)
    window.opener = null
  }
  function receive(event) {
    if (finished || event.source !== opener || event.origin !== manager.origin || event.data?.type !== 'aio-cleanuparr-session') return
    const tokens = event.data.tokens
    try {
      if (typeof tokens?.accessToken !== 'string' || !tokens.accessToken || typeof tokens.refreshToken !== 'string' || !tokens.refreshToken) throw new Error('Missing session')
      // Match upstream AuthService's origin-scoped token storage.
      localStorage.setItem('access_token', tokens.accessToken)
      localStorage.setItem('refresh_token', tokens.refreshToken)
      cleanup()
      location.replace('/')
    } catch (_) {
      cleanup()
      document.getElementById('status').textContent = 'Automatic sign-in failed. Continue to Cleanuparr to sign in manually.'
    }
  }
  try {
    manager = new URL(decodeURIComponent(location.hash.slice(1)))
    history.replaceState(null, '', location.pathname)
    if (!opener || !/^https?:$/.test(manager.protocol) || manager.hostname !== location.hostname || manager.origin === location.origin) throw new Error('Invalid AIO window')
    window.addEventListener('message', receive)
    window.addEventListener('pagehide', cleanup)
    timer = setTimeout(() => {
      cleanup()
      document.getElementById('status').textContent = 'Automatic sign-in timed out. Continue to Cleanuparr to sign in manually.'
    }, 15000)
    opener.postMessage({ type: 'aio-cleanuparr-ready' }, manager.origin)
  } catch (_) {
    cleanup()
    document.getElementById('status').textContent = 'Open Cleanuparr from the AIO dashboard, or continue to sign in manually.'
  }
})()
