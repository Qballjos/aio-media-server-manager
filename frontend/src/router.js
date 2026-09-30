import { createRouter, createWebHashHistory } from 'vue-router'

const emptyView = { name: 'EmptyView', render: () => null }

/** Canonical Settings hashes (`#/settings/<id>`). */
export const SETTINGS_SECTIONS = [
  'account',
  'system',
  'updates',
  'backups',
  'network',
  'homepage',
  'diagnostics',
]

/** Older hashes from the 11-tab layout. */
export const SETTINGS_ALIASES = {
  general: 'system',
  storage: 'system',
  permissions: 'system',
  github: 'updates',
  vpn: 'network',
  remote: 'network',
  integrations: 'homepage',
  debug: 'diagnostics',
}

export const SETTINGS_NAV = [
  ['account', 'Account'],
  ['system', 'System'],
  ['updates', 'Updates'],
  ['backups', 'Backups'],
  ['network', 'Network'],
  ['homepage', 'Homepage'],
  ['diagnostics', 'Diagnostics'],
]

const SETTINGS_SET = new Set(SETTINGS_SECTIONS)

export function resolveSettingsSection(section) {
  const value = String(section || '')
  if (SETTINGS_SET.has(value)) return value
  if (value in SETTINGS_ALIASES) return SETTINGS_ALIASES[value]
  return 'account'
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', name: 'home', component: emptyView },
    { path: '/catalog', name: 'catalog', component: emptyView },
    { path: '/settings', redirect: '/settings/account' },
    {
      path: '/settings/:section',
      name: 'settings',
      component: emptyView,
      beforeEnter(to) {
        const section = String(to.params.section || '')
        if (SETTINGS_SET.has(section)) return true
        const canonical = resolveSettingsSection(section)
        return { name: 'settings', params: { section: canonical } }
      },
    },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})
