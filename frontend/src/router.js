import { createRouter, createWebHashHistory } from 'vue-router'

const emptyView = { name: 'EmptyView', render: () => null }

export const SETTINGS_SECTIONS = [
  'account',
  'general',
  'updates',
  'storage',
  'permissions',
  'backups',
  'vpn',
  'remote',
  'integrations',
  'github',
  'debug',
]

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
        if (!SETTINGS_SET.has(section)) {
          return { name: 'settings', params: { section: 'account' } }
        }
      },
    },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})
