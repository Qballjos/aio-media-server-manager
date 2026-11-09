import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'

const helper = readFileSync(new URL('../../applications/cleanuparr-login.js', import.meta.url), 'utf8')
const parent = readFileSync(new URL('../src/appOpen.js', import.meta.url), 'utf8')
  .replace(/^import .*\n/gm, '').replace('export async function', 'async function')

test('Cleanuparr only accepts a session from the exact AIO opener and origin', () => {
  const listeners = new Map(), storage = new Map(), sent = []
  const opener = { postMessage: (data, origin) => sent.push({ data, origin }) }
  let destination = ''
  const location = { hash: '#http%3A%2F%2Flocalhost%3A8080', hostname: 'localhost', origin: 'http://localhost:11011', pathname: '/aio-login.html', replace: value => { destination = value } }
  const window = { opener, addEventListener: (type, fn) => listeners.set(type, fn), removeEventListener: type => listeners.delete(type) }
  runInNewContext(helper, { window, location, URL, history: { replaceState() {} }, setTimeout: () => 1, clearTimeout() {}, document: { getElementById: () => ({ textContent: '' }) }, localStorage: { setItem: (key, value) => storage.set(key, value) } })
  assert.equal(sent[0].origin, 'http://localhost:8080')
  const receive = listeners.get('message')
  const data = { type: 'aio-cleanuparr-session', tokens: { accessToken: 'jwt', refreshToken: 'refresh' } }
  receive({ source: {}, origin: 'http://localhost:8080', data })
  receive({ source: opener, origin: 'https://evil.example', data })
  assert.equal(storage.size, 0)
  receive({ source: opener, origin: 'http://localhost:8080', data })
  assert.equal(storage.get('access_token'), 'jwt')
  assert.equal(storage.get('refresh_token'), 'refresh')
  assert.equal(destination, '/')
  assert.equal(window.opener, null)
  assert.equal(listeners.size, 0)
})

test('AIO only sends Cleanuparr tokens to the opened app window, never through the URL', async () => {
  const listeners = new Map(), sent = []
  const tab = { location: { href: '' }, postMessage: (data, origin) => sent.push({ data, origin }) }
  const window = { location: { origin: 'http://localhost:8080' }, open: () => tab,
    addEventListener: (type, fn) => listeners.set(type, fn), removeEventListener: type => listeners.delete(type) }
  const tokens = { accessToken: 'jwt', refreshToken: 'refresh' }
  const env = { window, URL, setTimeout: () => 1, clearTimeout() {}, apiJson: async () => ({ res: { ok: true }, data: { url: 'http://localhost:11011/aio-login.html', handoff: 'cleanuparr-session', tokens } }) }
  runInNewContext(`${parent}; globalThis.open = openApp`, env)
  await env.open({ preventDefault() {} }, 'cleanuparr', 'http://localhost:11011')
  assert.match(tab.location.href, /^http:\/\/localhost:11011\/aio-login.html#/)
  assert.doesNotMatch(tab.location.href, /jwt|refresh/)
  const receive = listeners.get('message')
  receive({ source: tab, origin: 'https://evil.example', data: { type: 'aio-cleanuparr-ready' } })
  assert.equal(sent.length, 0)
  receive({ source: tab, origin: 'http://localhost:11011', data: { type: 'aio-cleanuparr-ready' } })
  assert.equal(sent[0].origin, 'http://localhost:11011')
  assert.equal(sent[0].data.tokens.accessToken, 'jwt')
  receive({ source: tab, origin: 'http://localhost:11011', data: { type: 'aio-cleanuparr-complete' } })
  assert.equal(listeners.size, 0)
})
