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
  query.value = ''
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
  <aside class="settings-sidebar" :style="{ '--settings-header-height': `${headerHeight}px` }">
    <button ref="mobileToggle" class="settings-mobile-toggle" type="button" :aria-label="`${$t('Settings')} / ${$t(current?.label || 'Profile')}`" :aria-expanded="expanded" aria-controls="settings-navigation" @click="expanded = !expanded">
      <svg class="settings-mobile-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[current?.icon || 'user']" /></svg>
      <span class="settings-mobile-copy">
        <span>{{ $t('Settings sections') }}</span>
        <strong>{{ $t(current?.label || 'Profile') }}</strong>
      </span>
      <svg class="settings-mobile-chevron" :class="{ 'is-expanded': expanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
    </button>
    <div id="settings-navigation" class="settings-navigation" :class="{ expanded }">
      <h2 class="settings-sidebar-title">{{ $t('Settings') }}</h2>
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
.settings-sidebar { position:relative; min-width:0; padding:1.5rem .875rem; border-right:1px solid var(--border-subtle); border-radius:var(--radius-glass) 0 0 var(--radius-glass); background:var(--panel-shine); }
.settings-navigation { position:sticky; top:calc(var(--settings-header-height, 0px) + 1rem); max-height:calc(100dvh - var(--settings-header-height, 0px) - 2rem); overscroll-behavior-y:contain; overflow-y:auto; scrollbar-width:thin; scrollbar-color:var(--border-strong) transparent; }
.settings-sidebar-title { margin:0 .5rem 1rem; font-size:var(--text-title); font-weight:600; letter-spacing:-.04em; }
.settings-search { display:flex; align-items:center; gap:.55rem; padding:.7rem; border:1px solid var(--border-subtle); border-radius:var(--radius-inset); background:var(--bg-input); color:var(--text-dim); margin-bottom:1rem; }
.settings-search:focus-within { outline:0; border-color:var(--color-primary); box-shadow:inset 0 0 0 1px var(--color-primary); }
.settings-search svg { width:16px; height:16px; flex-shrink:0; }
.settings-search input { width:100%; min-width:0; border:0; outline:0; background:transparent; color:var(--text-main); font:inherit; font-size:var(--text-body); }
.settings-search input::placeholder { color:var(--text-dim); }
.settings-nav-group + .settings-nav-group { margin-top:1rem; }
.settings-nav-group h3 { margin:0 0 .35rem; padding:0 .65rem; color:var(--text-dim); font-size:var(--text-kicker); font-weight:400; }
.settings-sidebar-link { display:flex; align-items:center; gap:.6rem; padding:.65rem; margin:.2rem 0; text-decoration:none; color:var(--text-muted); font-size:var(--text-body); border-radius:10px; border:1px solid transparent; transition:background .15s; }
.settings-sidebar-link span { min-width:0; overflow-wrap:anywhere; }
.settings-sidebar-link svg { width:1.1rem; height:1.1rem; flex-shrink:0; color:var(--color-primary-text); }
.settings-sidebar-link:hover { background:var(--bg-surface); }
.settings-sidebar-link.is-active { background:var(--pill-active); color:var(--color-primary-text); font-weight:500; }
.settings-search-empty { color:var(--text-muted); font-size:var(--text-body); padding:.65rem; }
.settings-mobile-toggle { display:none; }
.settings-mobile-copy { min-width:0; flex:1; display:flex; flex-direction:column; gap:.15rem; overflow-wrap:anywhere; }
.settings-mobile-copy > span { font-size:var(--text-kicker); color:var(--text-muted); }
.settings-mobile-copy strong { font-size:var(--text-body); font-weight:600; }
.settings-mobile-icon, .settings-mobile-chevron { width:1.25rem; height:1.25rem; flex-shrink:0; }
.settings-mobile-icon { color:var(--color-primary-text); }
.settings-mobile-chevron { color:var(--text-muted); transition:transform .15s ease; }
.settings-mobile-chevron.is-expanded { transform:rotate(180deg); }
@media (max-width: 760px) {
  .settings-sidebar { padding:.875rem 1rem; border-right:0; border-bottom:1px solid var(--border-subtle); border-radius:var(--radius-glass) var(--radius-glass) 0 0; }
  .settings-mobile-toggle { display:flex; align-items:center; justify-content:space-between; gap:.75rem; min-height:3rem; width:100%; padding:.25rem .35rem; background:none; border:0; color:var(--text-heading); font:inherit; text-align:left; cursor:pointer; }
  .settings-sidebar-title { display:none; }
  .settings-navigation { position:static; display:none; max-height:min(55dvh,28rem); margin-top:.75rem; padding: .75rem .15rem .15rem; border-top:1px solid var(--border-subtle); }
  .settings-navigation.expanded { display:block; }
  .settings-sidebar-link, .settings-search { min-height:2.75rem; }
}
</style>
