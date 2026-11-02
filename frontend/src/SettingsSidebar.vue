<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { filterSettingsGroups, SETTINGS_PAGES } from './settingsNavigation.js'
const props = defineProps({ section: { type: String, required: true } })
const { t } = useI18n()
const query = ref('')
const expanded = ref(false)
const mobileToggle = ref(null)
const headerHeight = ref(0)
let headerObserver
onMounted(() => {
  const header = document.querySelector('.top-nav')
  if (!header) return
  const measureHeader = () => { headerHeight.value = header.getBoundingClientRect().height }
  measureHeader()
  headerObserver = new ResizeObserver(measureHeader)
  headerObserver.observe(header)
})
onBeforeUnmount(() => headerObserver?.disconnect())
const groups = computed(() => filterSettingsGroups(query.value, t))
const current = computed(() => SETTINGS_PAGES.find(item => item.id === props.section))
watch(() => props.section, async () => {
  if (!expanded.value) return
  expanded.value = false
  await nextTick()
  mobileToggle.value?.focus()
})
const paths = {
  user: 'M20 21v-2a7 7 0 0 0-14 0v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  palette: 'M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-3.7 1.5 1.5 0 0 1 1-2.8h2a4 4 0 0 0 4-4A9 9 0 0 0 12 3M7 10h.01M10 6h.01M15 6h.01M18 10h.01',
  grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  shield: 'M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7z',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18',
  link: 'm10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  refresh: 'M20 7a9 9 0 0 0-16 2M4 3v6h6M4 17a9 9 0 0 0 16-2m0 6v-6h-6',
  database: 'M21 6c0 2-4 3-9 3S3 8 3 6s4-3 9-3 9 1 9 3M3 6v12c0 2 4 3 9 3s9-1 9-3V6M3 12c0 2 4 3 9 3s9-1 9-3',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  server: 'M3 3h18v7H3zM3 14h18v7H3zM7 6h.01M7 17h.01',
  help: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M9 9a3 3 0 1 1 4 3c-1 1-1 1-1 3m0 3h.01',
  info: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M12 11v6m0-10h.01',
}
</script>

<template>
  <aside class="settings-sidebar glass-card" :style="{ '--settings-header-height': `${headerHeight}px` }">
    <button ref="mobileToggle" class="settings-mobile-toggle" type="button" :aria-expanded="expanded" aria-controls="settings-navigation" @click="expanded = !expanded">
      <span>{{ $t('Settings') }} / {{ $t(current?.label || 'Profile') }}</span>
      <span aria-hidden="true">{{ expanded ? '−' : '+' }}</span>
    </button>
    <div id="settings-navigation" class="settings-navigation" :class="{ expanded }">
      <label class="settings-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10" cy="10" r="6" /><path d="m15 15 5 5" /></svg>
        <input v-model="query" type="search" :placeholder="$t('Search settings…')" :aria-label="$t('Search settings…')" />
      </label>
      <nav :aria-label="$t('Settings sections')">
        <div v-for="group in groups" :key="group.label" class="settings-nav-group">
          <h3>{{ $t(group.label) }}</h3>
          <RouterLink v-for="item in group.items" :key="item.id" :to="{ name: 'settings', params: { section: item.id } }" class="settings-sidebar-link" :class="{ 'is-active': section === item.id }" :aria-current="section === item.id ? 'page' : undefined">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[item.icon]" /></svg>
            <span>{{ $t(item.label) }}</span>
          </RouterLink>
        </div>
        <p v-if="!groups.length" class="settings-search-empty" role="status">{{ $t('No settings found. Try another search.') }}</p>
      </nav>
    </div>
  </aside>
</template>

<style scoped>
.settings-sidebar { position: sticky; top: calc(var(--settings-header-height, 0px) + 1rem); align-self: start; min-width: 0; padding: 1rem; }
.settings-navigation { max-height: calc(100dvh - var(--settings-header-height, 0px) - 4rem); overscroll-behavior-y: contain; scrollbar-gutter: auto; overflow-y: auto; scrollbar-width: none; }
.settings-search { display:flex; align-items:center; gap:.55rem; padding:.65rem; border:1px solid var(--border-subtle); border-radius:var(--radius-tile); background:var(--bg-input); color:var(--text-dim); margin-bottom:1rem; }
.settings-search:focus-within { outline:2px solid var(--color-primary); outline-offset:2px; }
.settings-search svg { width:18px; height:18px; flex-shrink:0; }
.settings-search input { width:100%; min-width:0; border:0; outline:0; background:transparent; color:var(--text-main); font:inherit; font-size:.8rem; }
.settings-search input::placeholder { color:var(--text-dim); }
.settings-nav-group + .settings-nav-group { margin-top:.75rem; padding-top:.65rem; border-top:1px solid var(--border-subtle); }
.settings-nav-group h3 { margin:0 0 .35rem; padding:0 .65rem; color:var(--text-dim); font-size:.72rem; font-weight:600; letter-spacing:.04em; }
.settings-sidebar-link { display:flex; align-items:center; gap:.65rem; padding:.55rem .65rem; margin:.12rem 0; text-decoration:none; color:var(--text-main); font-size:.85rem; border-radius:var(--radius-inset); border-left:3px solid transparent; transition:background .15s; }
.settings-sidebar-link span { min-width:0; overflow-wrap:anywhere; }
.settings-sidebar-link svg { width:19px; height:19px; flex-shrink:0; color:var(--text-muted); }
.settings-sidebar-link:hover { background:var(--bg-surface); }
.settings-sidebar-link.is-active { background:rgba(var(--color-primary-rgb),.14); color:var(--color-primary-text); border-left-color:var(--color-primary); font-weight:600; }
.settings-sidebar-link.is-active svg { color:inherit; }
.settings-search-empty { color:var(--text-muted); font-size:.85rem; padding:.65rem; }
.settings-mobile-toggle { display:none; }
.settings-mobile-toggle span:first-child { min-width:0; overflow-wrap:anywhere; }
@media (max-width: 760px) {
  .settings-sidebar { position:static; padding:.75rem; }
  .settings-mobile-toggle { display:flex; align-items:center; justify-content:space-between; gap:1rem; width:100%; padding:.3rem; background:none; border:0; color:var(--text-heading); font:inherit; text-align:left; cursor:pointer; }
  .settings-navigation { display:none; max-height:none; margin-top:1rem; scrollbar-gutter:auto; }
  .settings-navigation.expanded { display:block; }
}
</style>
