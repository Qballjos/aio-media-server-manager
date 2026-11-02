import { createRouter, createWebHashHistory } from 'vue-router'

const emptyView = { name: 'EmptyView', render: () => null }

import { SETTINGS_SECTIONS, resolveSettingsSection } from './settingsNavigation.js'
export { SETTINGS_SECTIONS, SETTINGS_ALIASES, SETTINGS_NAV, resolveSettingsSection } from './settingsNavigation.js'

const SETTINGS_SET = new Set(SETTINGS_SECTIONS)

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
