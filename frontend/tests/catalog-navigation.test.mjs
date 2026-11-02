import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import * as catalogQuery from '../src/catalogQuery.js'

function catalog() {
  const source = readFileSync(new URL('../src/CatalogView.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*\n/gm, '')
  const route = reactive({ name: 'catalog', query: {} })
  const emitted = []
  const rows = [
    { name: 'jellyfin', display_name: 'Jellyfin', category: 'media', installed: true, popularity: 20 },
    { name: 'sonarr', display_name: 'Sonarr', category: 'automation', installed: true, popularity: 10 },
    { name: 'plex', display_name: 'Plex', category: 'media', installed: false, popularity: 5 },
  ]
  const panel = runInNewContext(`${script}\n;({ selectCatalogSection, visibleServices, catalogSearchInput, showDiscovery, featuredService, moveFeatured, featuredPaused, advanceFeatured, onAppRowClick, openCardMenu })`, {
    ...catalogQuery, computed, ref,
    defineProps: () => ({ catalogApps: rows, updateStatus: {}, applications: [{ name: 'jellyfin', installed: true, state: 'running' }] }),
    defineEmits: () => (...args) => emitted.push(args),
    useRoute: () => route,
    useRouter: () => ({ replace: ({ query }) => { route.query = query } }),
    useToasts: () => ({}),
    appIconSrc: name => `/app-icons/${name}.svg`, appWebUrl: () => '', t: text => text,
    watch: () => {}, onMounted: () => {}, onUnmounted: () => {},
  })
  return { panel, route, emitted }
}

test('store sections retain URL filters and separate installed, available and active apps', () => {
  const { panel, route } = catalog()
  assert.equal(panel.showDiscovery.value, true)
  assert.equal(panel.featuredService.value.name, 'jellyfin')
  panel.selectCatalogSection('installed')
  assert.equal(route.query.status, 'installed')
  assert.equal(panel.visibleServices.value.map(s => s.name).join(','), 'jellyfin,sonarr')
  assert.equal(panel.showDiscovery.value, false)
  panel.selectCatalogSection('available')
  assert.equal(panel.visibleServices.value.map(s => s.name).join(','), 'plex')
  panel.selectCatalogSection('active')
  assert.equal(panel.visibleServices.value.map(s => s.name).join(','), 'jellyfin')
  panel.selectCatalogSection('', 'media')
  assert.equal(route.query.status, undefined)
  assert.equal(route.query.cat, 'media')
  assert.equal(panel.visibleServices.value.map(s => s.name).join(','), 'jellyfin,plex')
  panel.selectCatalogSection()
  assert.equal(panel.showDiscovery.value, true)
})

test('search narrows the selected section and hides featured content', () => {
  const { panel } = catalog()
  panel.catalogSearchInput.value = 'plex'
  assert.equal(panel.showDiscovery.value, false)
  assert.equal(panel.visibleServices.value.map(s => s.name).join(','), 'plex')
  panel.selectCatalogSection('installed')
  assert.equal(panel.visibleServices.value.length, 0)
})

test('app clicks open settings; direct action clicks do not open settings', () => {
  const { panel, emitted } = catalog()
  const service = panel.visibleServices.value[0]
  panel.openCardMenu.value = service.name
  panel.onAppRowClick({ target: { closest: () => null } }, service)
  assert.equal(emitted.length, 1)
  assert.equal(emitted[0][0], 'open-settings')
  assert.equal(emitted[0][1], service)
  assert.equal(panel.openCardMenu.value, '')
  for (const tag of ['button', 'a', 'input', 'select']) {
    panel.onAppRowClick({ target: { closest: () => ({ tagName: tag }) } }, service)
  }
  assert.equal(emitted.length, 1)
})

test('featured banner visits every app, wraps, and supports pause', () => {
  const { panel } = catalog()
  panel.advanceFeatured()
  assert.equal(panel.featuredService.value.name, 'sonarr')
  panel.featuredPaused.value = true
  panel.advanceFeatured()
  assert.equal(panel.featuredService.value.name, 'sonarr')
  panel.moveFeatured(1)
  assert.equal(panel.featuredService.value.name, 'plex')
  panel.moveFeatured(1)
  assert.equal(panel.featuredService.value.name, 'jellyfin')
  panel.moveFeatured(-1)
  assert.equal(panel.featuredService.value.name, 'plex')
  panel.featuredPaused.value = false
  panel.catalogSearchInput.value = 'sonarr'
  panel.advanceFeatured()
  assert.equal(panel.featuredService.value.name, 'plex')
})
