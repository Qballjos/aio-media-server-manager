import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'

const helperSource = readFileSync(new URL('../../applications/jellyfin/aio-login.js', import.meta.url), 'utf8')
const openerSource = readFileSync(new URL('../src/appOpen.js', import.meta.url), 'utf8')
  .replace(/^import .*\n/gm, '').replace('export async function', 'async function')

function browser() {
  const listeners = new Map(), timers = new Map(), storage = new Map()
  const window = {
    location: { origin: 'http://localhost:8080' },
    addEventListener: (type, fn) => listeners.set(type, fn),
    removeEventListener: (type) => listeners.delete(type),
  }
  return {
    window, listeners, timers, storage, URL, AbortController, crypto: webcrypto,
    setTimeout: (fn) => { const id = timers.size + 1; timers.set(id, fn); return id },
    clearTimeout: (id) => timers.delete(id),
    localStorage: { getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value) },
  }
}

async function helper({ disabled = false } = {}) {
  const env = browser(), sent = [], requests = [], status = { textContent: '' }
  const opener = { postMessage: (data, origin) => sent.push({ data, origin }) }
  env.window.opener = opener
  env.location = {
    hash: '#http%3A%2F%2Flocalhost%3A8080', pathname: '/web/aio-login.html',
    href: 'http://localhost:8096/web/aio-login.html', replace: (url) => { env.redirect = url },
  }
  env.history = { replaceState: (_, __, path) => { env.clearedPath = path } }
  env.document = { getElementById: () => status }
  env.fetch = async (url, options) => {
    requests.push({ url: url.href, ...options })
    return {
      ok: !disabled, status: disabled ? 401 : 200,
      json: async () => url.pathname.endsWith('/Initiate')
        ? { Code: '123456', Secret: 'browser-only-secret' }
        : { ServerId: 'server', User: { Id: 'user' }, AccessToken: 'browser-only-token' },
    }
  }
  env.storage.set('_deviceId2', 'existing-browser-id')
  env.storage.set('jellyfin_credentials', JSON.stringify({ Servers: [{ Id: 'other-server', AccessToken: 'keep' }] }))
  await runInNewContext(helperSource, env)
  return { env, sent, requests, status, opener }
}

test('Jellyfin helper keeps secrets local, validates its opener and preserves other servers', async () => {
  const { env, sent, requests, opener } = await helper()
  assert.equal(env.clearedPath, '/web/aio-login.html')
  assert.equal(sent.length, 1)
  assert.deepEqual(JSON.parse(JSON.stringify(sent[0])), {
    data: { type: 'aio-jellyfin-code', code: '123456' }, origin: 'http://localhost:8080',
  })
  const receive = env.listeners.get('message')
  const data = { type: 'aio-jellyfin-authorized', ok: true }
  await receive({ source: opener, origin: 'https://evil.test', data })
  await receive({ source: {}, origin: 'http://localhost:8080', data })
  assert.equal(requests.length, 1)
  await receive({ source: opener, origin: 'http://localhost:8080', data })
  assert.equal(requests.length, 2)
  assert.equal(requests[1].url, 'http://localhost:8096/Users/AuthenticateWithQuickConnect')
  assert.deepEqual(JSON.parse(requests[1].body), { Secret: 'browser-only-secret' })
  assert.match(requests[0].headers.Authorization, /DeviceId="existing-browser-id"/)
  const servers = JSON.parse(env.storage.get('jellyfin_credentials')).Servers
  assert.equal(servers[0].AccessToken, 'keep')
  assert.equal(servers[1].AccessToken, 'browser-only-token')
  assert.equal(servers[1].ManualAddress, 'http://localhost:8096')
  assert.equal(env.redirect, 'index.html')
  assert.equal(env.window.opener, null)
  assert.equal(env.listeners.size, 0)
  assert.equal(env.timers.size, 0)
  assert.doesNotMatch(JSON.stringify(sent), /browser-only/)
})

test('disabled Quick Connect keeps manual login available and does not change credentials', async () => {
  const { env, requests, status, sent } = await helper({ disabled: true })
  assert.match(status.textContent, /Quick Connect is disabled/)
  assert.equal(requests.length, 1)
  assert.equal(JSON.parse(env.storage.get('jellyfin_credentials')).Servers.length, 1)
  assert.equal(env.redirect, undefined)
  assert.equal(env.listeners.size, 0)
  assert.equal(env.timers.size, 0)
  assert.equal(sent[0].data.type, 'aio-jellyfin-complete')
})

test('Jellyfin helper timeout aborts pending work and leaves saved sessions intact', async () => {
  const { env, requests, status } = await helper()
  const saved = env.storage.get('jellyfin_credentials')
  env.timers.values().next().value()
  assert.match(status.textContent, /timed out/)
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(env.storage.get('jellyfin_credentials'), saved)
  assert.equal(env.listeners.size, 0)
  assert.equal(env.timers.size, 0)
  assert.equal(env.window.opener, null)
})

test('AIO only authorizes a code from the exact popup and Jellyfin origin', async () => {
  const env = browser(), calls = [], replies = []
  const tab = { location: {}, postMessage: (data, origin) => replies.push({ data, origin }) }
  env.apiJson = async (path, options) => {
    calls.push({ path, ...options })
    return { res: { ok: true }, data: { authorized: true } }
  }
  env.apiError = (_, fallback) => fallback
  const { openJellyfin } = runInNewContext(`${openerSource}\n;({openJellyfin})`, env)
  openJellyfin(tab, 'http://localhost:8096/web/aio-login.html')
  assert.equal(new URL(tab.location.href).hash, '#http%3A%2F%2Flocalhost%3A8080')
  const receive = env.listeners.get('message')
  const data = { type: 'aio-jellyfin-code', code: '123456' }
  await receive({ source: {}, origin: 'http://localhost:8096', data })
  await receive({ source: tab, origin: 'https://evil.test', data })
  await receive({ source: tab, origin: 'http://localhost:8096', data: { ...data, code: 'bad' } })
  assert.equal(calls.length, 0)
  await receive({ source: tab, origin: 'http://localhost:8096', data })
  await receive({ source: tab, origin: 'http://localhost:8096', data })
  assert.equal(calls.length, 1)
  assert.equal(calls[0].path, '/api/applications/jellyfin/quick-connect')
  assert.deepEqual(JSON.parse(calls[0].body), { code: '123456' })
  assert.equal(replies[0].origin, 'http://localhost:8096')
  assert.equal(replies[0].data.ok, true)
  await receive({ source: tab, origin: 'http://localhost:8096', data: { type: 'aio-jellyfin-complete' } })
  assert.equal(env.listeners.size, 0)
  assert.equal(env.timers.size, 0)
  assert.equal(calls[0].signal.aborted, true)
})

test('cookie-based app opening still navigates to the session endpoint URL', async () => {
  const env = browser(), tab = { location: {} }
  env.window.open = () => tab
  env.apiJson = async () => ({ res: { ok: true }, data: { url: 'http://localhost:8989', signed_in: true } })
  const { openApp } = runInNewContext(`${openerSource}\n;({openApp})`, env)
  await openApp({ preventDefault() {} }, 'sonarr', 'http://fallback:8989')
  assert.equal(tab.location.href, 'http://localhost:8989')
  assert.equal(env.listeners.size, 0)
})
