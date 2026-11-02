import test from 'node:test'
import assert from 'node:assert/strict'
import * as nav from '../src/settingsNavigation.js'

test('legacy links retain their destination and new sections are reachable', () => {
  for (const [old, current] of Object.entries({ network: 'vpn', remote: 'remote', integrations: 'integrations', general: 'system', theming: 'visuals', debug: 'diagnostics' })) {
    assert.equal(nav.resolveSettingsSection(old), current)
  }
  for (const id of ['account', 'visuals', 'homepage', 'vpn', 'remote', 'integrations', 'usenet', 'updates', 'backups', 'notifications', 'system', 'diagnostics', 'about']) {
    assert.equal(nav.resolveSettingsSection(id), id)
  }
  assert.equal(nav.resolveSettingsSection('__proto__'), 'account')
  assert.equal(nav.resolveSettingsSection('unknown'), 'account')
})

test('search uses translated labels and keywords and handles empty results', () => {
  const translate = key => ({ 'App connections': 'App-koppelingen', Connections: 'Verbindingen' }[key] || key)
  const ids = query => nav.filterSettingsGroups(query, translate).flatMap(g => g.items.map(i => i.id))
  assert.deepEqual(ids('  JELLYFIN  '), ['integrations'])
  assert.deepEqual(ids('app-koppelingen'), ['integrations'])
  assert.ok(ids('verbindingen').includes('vpn'))
  assert.deepEqual(ids('no-such-setting'), [])
  assert.equal(ids('   ').length, 13)
})

test('Homey pairing is discoverable in app connections', () => {
  const pages = nav.filterSettingsGroups('Homey').flatMap(group => group.items)
  assert.deepEqual(pages.map(page => page.id), ['integrations'])
})
