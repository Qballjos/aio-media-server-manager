import assert from 'node:assert/strict'
import test from 'node:test'
import { combinedServiceStatus, tunnelChip, vpnChip } from '../src/statusChips.js'

test('VPN chip appears only when the VPN is switched on and says when it is down', () => {
  assert.equal(vpnChip({ enabled: false, tunnel_up: false }), null)
  assert.equal(vpnChip(null), null)
  assert.deepEqual(vpnChip({ enabled: true, tunnel_up: true, handshake_ok: true, provider: 'privadovpn' }), {
    label: 'VPN', tone: 'ok', title: 'VPN connected (privadovpn)',
  })
  const down = vpnChip({ enabled: true, tunnel_up: false, last_error: 'handshake timed out' })
  assert.equal(down.label, 'VPN down')
  assert.equal(down.tone, 'bad')
  assert.match(down.title, /handshake timed out/)
})

test('tunnel chip distinguishes connected, connecting and stopped', () => {
  assert.equal(tunnelChip({ enabled: false }), null)
  assert.equal(tunnelChip({ enabled: true, running: true, connected: true }).tone, 'ok')
  assert.deepEqual(tunnelChip({ enabled: true, running: true, connected: false }), {
    label: 'Tunnel connecting', tone: 'warn', title: 'Cloudflare Tunnel is starting or reconnecting',
  })
  const stopped = tunnelChip({ enabled: true, running: false, connected: false, summary: 'Enabled — token missing' })
  assert.equal(stopped.label, 'Tunnel down')
  assert.equal(stopped.tone, 'bad')
  assert.match(stopped.title, /token missing/)
})

test('combined service status reports one healthy or failed indicator', () => {
  assert.equal(combinedServiceStatus([]), null)
  assert.deepEqual(combinedServiceStatus([
    { tone: 'ok', title: 'VPN connected' },
    { tone: 'ok', title: 'Cloudflare Tunnel connected' },
  ]), { tone: 'ok', title: 'VPN connected. Cloudflare Tunnel connected' })
  assert.equal(combinedServiceStatus([
    { tone: 'ok', title: 'VPN connected' },
    { tone: 'warn', title: 'Cloudflare Tunnel connecting' },
  ]).tone, 'bad')
})
