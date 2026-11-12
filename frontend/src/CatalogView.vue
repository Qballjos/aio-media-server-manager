<script setup>
import { computed, onMounted, onUnmounted, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appIconSrc } from './appIcons.js'
import { catalogQueryFromState, catalogStateFromQuery, sameCatalogQuery } from './catalogQuery.js'
import { appWebUrl } from './appWebUrl.js'
import { openApp } from './appOpen.js'
import { apiError, apiRequest, readJson } from './api.js'
import { formatUptime } from './format.js'
import { useToasts } from './useToasts.js'
import { t } from './i18n/index.js'
import UiSelect from './UiSelect.vue'
import InstallationActivity from './InstallationActivity.vue'
import PreflightReview from './PreflightReview.vue'

const props = defineProps({
  catalogApps: { type: Array, default: () => [] },
  applications: { type: Array, default: () => [] },
  systemInfo: { type: Object, default: null },
  updateStatus: { type: Object, default: () => ({}) },
  backupStatus: { type: Object, default: () => ({}) },
  isLoadingData: { type: Boolean, default: false },
  refreshDashboard: { type: Function, required: true },
  fetchApplications: { type: Function, required: true },
  showHealthModal: { type: Boolean, default: false },
})
const emit = defineEmits(['open-logs', 'open-settings', 'open-health'])
const { showToast } = useToasts()

const catalogSearchInput = ref('')
const categoryFiltersExpanded = ref(false)
const categoryFiltersToggle = ref(null)
const categoryNavigation = ref(null)
let catalogSearchTimer = null
const actionLoading = ref({})
const iconFailed = ref({})
const openCardMenu = ref('')
const activity = ref(null)
const preflightReview = ref(null)
async function retryJob(job) {
  if (job.status === 'rollback_failed') { showToast(t('Resolve incomplete recovery before retrying the update.'), 'error'); return }
  const service = combinedServices.value.find(item => item.name === job.name)
  if (job.operation === 'update') return updateApp(job.name)
  if (service?.installed) {
    try {
      const response = await apiRequest(`/api/catalog/${job.name}/retry-setup`, { method: 'POST' })
      const data = await readJson(response)
      if (!response.ok) throw new Error(apiError(data))
      activity.value?.show()
      await props.refreshDashboard()
    } catch (err) { showToast(err.message, 'error') }
  } else installApp(job.name)
}

function openLogs(service) { emit('open-logs', service) }
function openAppSettings(service) {
  closeCardMenu()
  emit('open-settings', service)
}
function openHealthModal() { emit('open-health') }
function refreshDashboard() { return props.refreshDashboard() }

const cpuPercent = computed(() => props.systemInfo?.metrics?.cpu_percent)
const healthTone = computed(() => {
  const metrics = props.systemInfo?.metrics
  const cpu = Number(metrics?.cpu_percent) || 0
  const mem = Number(metrics?.memory?.percent) || 0
  const disk = Number(metrics?.disk?.percent) || 0
  if (cpu >= 90 || mem >= 90 || disk >= 90) return 'warn'
  return 'ok'
})

const route = useRoute()
const router = useRouter()
const catalogState = computed(() =>
  route.name === 'catalog' ? catalogStateFromQuery(route.query) : catalogStateFromQuery({})
)
const catalogCategoriesSelected = computed(() => catalogState.value.cat)
const catalogStatusFilters = computed(() => catalogState.value.status)
const catalogSort = computed({
  get: () => catalogState.value.sort,
  set: (value) => patchCatalogQuery({ sort: value === 'az' ? 'az' : 'popularity' }),
})

function patchCatalogQuery(patch) {
  const next = { ...catalogStateFromQuery(route.name === 'catalog' ? route.query : {}), ...patch }
  const query = catalogQueryFromState(next)
  if (route.name === 'catalog' && sameCatalogQuery(catalogStateFromQuery(route.query), next)) {
    return
  }
  router.replace({ name: 'catalog', query })
}

watch(
  () => (route.name === 'catalog' ? String(route.query.q || '') : ''),
  (q) => {
    if (catalogSearchInput.value !== q) catalogSearchInput.value = q
  },
  { immediate: true }
)
watch(catalogSearchInput, (value) => {
  if (route.name !== 'catalog') return
  clearTimeout(catalogSearchTimer)
  catalogSearchTimer = setTimeout(() => {
    if (route.name !== 'catalog') return
    patchCatalogQuery({ q: value })
  }, 280)
})
// --- Combined Services List ---
const combinedServices = computed(() => {
  const appMap = new Map()
  for (const app of props.applications) {
    appMap.set(app.name, app)
  }

  return props.catalogApps.filter((cat) => cat.current_arch_supported !== false).map(cat => {
    const live = appMap.get(cat.name)
    const port = live?.port || cat.port || cat.default_port
    const webUrl = appWebUrl({
      appName: cat.name,
      port,
      baseDomain: props.systemInfo?.public_app_base_domain || '',
      subdomain: (() => {
        const row = (props.systemInfo?.public_app_hostnames || {})[cat.name]
        return row && row.enabled ? row.subdomain : ''
      })(),
    })
    return {
      name: cat.name,
      displayName: cat.display_name,
      description: cat.description ? t(cat.description) : '',
      category: cat.category,
      iconSrc: appIconSrc(cat.name),
      tier: cat.tier,
      port,
      defaultPort: cat.default_port,
      installed: cat.installed || (live && live.installed) || false,
      installedVersion: cat.installed_version || (live && live.version),
      installJob: cat.install_job,
      installBusy: ['queued', 'installing', 'configuring', 'updating'].includes(cat.install_job),
      installMessage: cat.install_message || cat.install_error || '',
      installUpdatedAt: cat.install_updated_at,
      webUrl,
      state: live ? live.state : (cat.installed ? 'stopped' : 'not_installed'),
      pid: live ? live.pid : null,
      uptime: live ? live.uptime_seconds : null,
      is_crash_loop: live ? live.is_crash_loop : false,
      recent_crashes: live ? live.recent_crashes : 0,
      autostart: live?.autostart ?? cat.daemon !== false,
      daemon: cat.daemon !== false,
      arm64: cat.arm64_supported,
      popularity: cat.popularity ?? 0,
      helpUrl: cat.help_url || '',
      updateAvailable: !!(props.updateStatus.available || []).find(
        (row) => row.kind !== 'appliance' && row.name === cat.name
      ),
      latestVersion: (
        (props.updateStatus.available || []).find(
          (row) => row.kind !== 'appliance' && row.name === cat.name
        ) || {}
      ).latest_version
    }
  })
})

function categoryLabel(name) {
  return t(CATEGORY_LABELS[name] || name)
}

const CATEGORY_LABELS = {
  downloading: 'Downloading',
  automation: 'Automation',
  indexers: 'Indexers',
  subtitles: 'Subtitles',
  media: 'Media',
  requests: 'Requests',
  optimization: 'Optimization',
  maintenance: 'Maintenance'
}

const catalogCategories = computed(() => {
  const names = [...new Set(combinedServices.value.map(s => s.category).filter(Boolean))]
  return names.sort((a, b) => categoryLabel(a).localeCompare(categoryLabel(b), undefined, { sensitivity: 'base' }))
})

function isRunningService(s) {
  return s.state === 'running' || s.state === 'healthy'
}

const discoverSelected = computed(() => !catalogCategoriesSelected.value.length && !catalogStatusFilters.value.length)
const featuredIndex = ref(0)
const featuredPaused = ref(false)
const featuredHovered = ref(false)
const featuredFocused = ref(false)
let featuredTimer = null
let featuredTouch = null
let featuredSwiped = false
function startFeaturedSwipe(event) {
  featuredSwiped = false
  if (event.pointerType === 'touch') featuredTouch = { x: event.clientX, y: event.clientY }
}
function endFeaturedSwipe(event) {
  if (!featuredTouch) return
  const dx = event.clientX - featuredTouch.x
  const dy = event.clientY - featuredTouch.y
  featuredTouch = null
  if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) {
    featuredSwiped = true
    moveFeatured(dx < 0 ? 1 : -1)
  }
}
function openFeatured() {
  if (featuredSwiped) { featuredSwiped = false; return }
  openAppSettings(featuredService.value)
}
const featuredPosition = computed(() => featuredIndex.value % (combinedServices.value.length || 1))
const featuredService = computed(() => combinedServices.value[featuredPosition.value])
const showDiscovery = computed(() => discoverSelected.value && !catalogSearchInput.value.trim())
function moveFeatured(direction) {
  const count = combinedServices.value.length
  if (count) featuredIndex.value = (featuredPosition.value + direction + count) % count
}
function advanceFeatured() {
  if (showDiscovery.value && !featuredPaused.value && !featuredHovered.value && !featuredFocused.value) moveFeatured(1)
}
const catalogHeading = computed(() => {
  if (catalogSearchInput.value.trim()) return t('Search results')
  if (catalogCategoriesSelected.value.length === 1) return categoryLabel(catalogCategoriesSelected.value[0])
  if (catalogStatusFilters.value.length === 1) {
    return t({ installed: 'My apps', active: 'Active', available: 'Available' }[catalogStatusFilters.value[0]])
  }
  return t('Discover')
})
function selectCatalogSection(status = '', category = '') {
  const restoreFocus = categoryFiltersExpanded.value && categoryNavigation.value?.contains(document.activeElement)
  categoryFiltersExpanded.value = false
  if (restoreFocus) nextTick(() => categoryFiltersToggle.value?.focus())
  patchCatalogQuery({ status: status ? [status] : [], cat: category ? [category] : [] })
}
function onAppRowClick(event, service) {
  if (event.target.closest('button, a, input, select, [role="listbox"]')) return
  openAppSettings(service)
}
function primaryAction(service) {
  if (service.is_crash_loop) return resetCrashLoop(service.name)
  if (!service.installed) return installApp(service.name, service.displayName)
  if (!service.daemon) return syncRecyclarr()
  if (!isServiceActive(service)) return startApp(service.name)
}
function primaryActionLabel(service) {
  if (service.is_crash_loop) return t('Reset')
  if (service.installBusy) return t('Installing')
  if (!service.installed) return t('Install')
  if (!service.daemon) return t('Sync')
  return t('Start')
}

const visibleServices = computed(() => {
  let list = combinedServices.value
  if (catalogCategoriesSelected.value.length) {
    const allowed = new Set(catalogCategoriesSelected.value)
    list = list.filter(s => allowed.has(s.category))
  }
  if (catalogStatusFilters.value.length) {
    list = list.filter(s => {
      const matchActive = catalogStatusFilters.value.includes('active') && isRunningService(s)
      const matchInstalled = catalogStatusFilters.value.includes('installed') && s.installed
      const matchAvailable = catalogStatusFilters.value.includes('available') && !s.installed
      return matchActive || matchInstalled || matchAvailable
    })
  }
  const query = catalogSearchInput.value.trim().toLowerCase()
  if (query) {
    list = list.filter(s => {
      const haystack = [
        s.displayName,
        s.name,
        s.description,
        categoryLabel(s.category),
        CATEGORY_LABELS[s.category] || s.category
      ].join(' ').toLowerCase()
      return haystack.includes(query)
    })
  }
  const copy = [...list]
  if (catalogSort.value === 'az') {
    copy.sort((a, b) => a.displayName.localeCompare(b.displayName, undefined, { sensitivity: 'base' }))
  } else {
    copy.sort((a, b) => {
      const pop = (b.popularity || 0) - (a.popularity || 0)
      if (pop !== 0) return pop
      return a.displayName.localeCompare(b.displayName, undefined, { sensitivity: 'base' })
    })
  }
  return copy
})

const activeAppCount = computed(() => {
  return combinedServices.value.filter(s => s.state === 'running' || s.state === 'healthy').length
})

const installedAppCount = computed(() => {
  return combinedServices.value.filter(s => s.installed).length
})

const availableAppCount = computed(() => {
  return combinedServices.value.filter(s => !s.installed).length
})

const vpnUnprotected = computed(() => {
  const vpn = props.systemInfo?.vpn
  if (!vpn) return false
  if (Array.isArray(vpn.unprotected_apps) && vpn.unprotected_apps.length) return true
  return Boolean(vpn.qbittorrent_unprotected || vpn.prowlarr_unprotected || vpn.flaresolverr_unprotected)
})
const cloudflareTunnelIssue = computed(() => {
  const tunnel = props.systemInfo?.cloudflare_tunnel
  return Boolean(tunnel?.enabled && !tunnel?.connected)
})
const hardlinksSupported = computed(() => props.systemInfo?.storage?.download_dir?.hardlinks_supported !== false)

// --- App Control Actions ---
async function startApp(name) {
  actionLoading.value[name] = 'start'
  try {
    const res = await apiRequest(`/api/applications/${name}/start`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok) {
      showToast(t('Started {name}', { name }), 'success')
      await props.fetchApplications()
    } else {
      showToast(apiError(data, t('Failed to start {name}', { name })), 'error')
    }
  } catch (err) {
    showToast(t('Error starting {name}: {message}', { name, message: err.message }), 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function stopApp(name) {
  actionLoading.value[name] = 'stop'
  try {
    const res = await apiRequest(`/api/applications/${name}/stop`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok) {
      showToast(t('Stopped {name}', { name }), 'info')
      await props.fetchApplications()
    } else {
      showToast(apiError(data, t('Failed to stop {name}', { name })), 'error')
    }
  } catch (err) {
    showToast(t('Error stopping {name}: {message}', { name, message: err.message }), 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function restartApp(name) {
  actionLoading.value[name] = 'restart'
  try {
    const res = await apiRequest(`/api/applications/${name}/restart`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok) {
      showToast(t('Restarted {name}', { name }), 'success')
      await props.fetchApplications()
    } else {
      showToast(apiError(data, t('Failed to restart {name}', { name })), 'error')
    }
  } catch (err) {
    showToast(t('Error restarting {name}: {message}', { name, message: err.message }), 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function updateApp(name) {
  if (preflightReview.value && !(await preflightReview.value.review(name, 'update'))) return
  actionLoading.value[name] = 'update'
  try {
    const res = await apiRequest(`/api/applications/${name}/update`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok && data.status === 'updated') {
      showToast(t('Updated {name} to {version}', { name, version: data.version || t('latest') }), 'success')
      await props.refreshDashboard()
    } else {
      showToast(apiError(data, t('Update failed for {name}', { name })), 'error')
    }
  } catch (err) {
    showToast(t('Error updating {name}: {message}', { name, message: err.message }), 'error')
  } finally {
    delete actionLoading.value[name]
    await activity.value?.refresh()
  }
}

async function uninstallApp(name) {
  const removeConfig = window.confirm(
    t('Uninstall {name}?\n\nOK = also remove configuration.\nCancel = keep configuration (binary only).', { name })
  )
  const removeData = removeConfig && window.confirm(t('Also delete {name} application data? Media libraries are never deleted.', { name }))
  actionLoading.value[name] = 'uninstall'
  try {
    const res = await apiRequest(`/api/applications/${name}/uninstall`, {
      method: 'POST',
      body: JSON.stringify({
        remove_application: true,
        remove_config: removeConfig,
        remove_data: !!removeData
      })
    })
    const data = await readJson(res)
    if (res.ok) {
      showToast(t('Uninstalled {name}', { name }), 'info')
      await props.refreshDashboard()
    } else {
      showToast(apiError(data, t('Failed to uninstall {name}', { name })), 'error')
    }
  } catch (err) {
    showToast(t('Error uninstalling {name}: {message}', { name, message: err.message }), 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function installApp(name, displayName) {
  if (preflightReview.value && !(await preflightReview.value.review(name))) return
  actionLoading.value[name] = 'install'
  try {
    const res = await apiRequest(`/api/catalog/${name}/install`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok) {
      activity.value?.show()
      showToast(t('Installing {name}…', { name: displayName || name }), 'success')
      setTimeout(() => props.refreshDashboard(), 3000)
    } else {
      showToast(apiError(data, t('Failed to install {name}', { name })), 'error')
    }
  } catch (err) {
    showToast(t('Error installing {name}: {message}', { name, message: err.message }), 'error')
  } finally {
    delete actionLoading.value[name]
  }
}
async function resetCrashLoop(name) {
  try {
    const res = await apiRequest(`/api/applications/${name}/reset-crash-loop`, { method: 'POST' })
    if (res.ok) {
      showToast(t('Crash loop reset for {name}', { name }), 'success')
      await props.fetchApplications()
    }
  } catch (err) {
    showToast(t('Failed to reset crash loop: {message}', { message: String(err) }), 'error')
  }
}

function isServiceActive(service) {
  return service.state === 'running' || service.state === 'healthy'
}

async function toggleCardMenu(name, event) {
  const wrap = event.currentTarget.parentElement
  openCardMenu.value = openCardMenu.value === name ? '' : name
  await nextTick()
  wrap.querySelector('.card-menu')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}

function closeCardMenu() {
  openCardMenu.value = ''
}
async function syncRecyclarr() {
  closeCardMenu()
  actionLoading.value.recyclarr = 'sync'
  try {
    const res = await apiRequest('/api/recyclarr/sync', { method: 'POST' })
    const data = await readJson(res)
    if (!res.ok) {
      showToast(apiError(data, t('Recyclarr sync failed')), 'error')
      return
    }
    showToast(t('Recyclarr sync finished'), 'success')
  } catch (err) {
    showToast(err.message || t('Recyclarr sync failed'), 'error')
  } finally {
    delete actionLoading.value.recyclarr
  }
}

function statusLabel(service) {
  if (service.installJob === 'restart_required') return t('Restart required')
  const labels = {
    queued: t('Queued'), installing: t('Installing'), configuring: t('Configuring'), updating: t('Updating'),
    failed: t('Failed'), rollback_failed: t('Recovery incomplete'), running: t('Running'),
    healthy: t('Healthy'), stopped: t('Stopped'), starting: t('Starting'), stopping: t('Stopping'),
    not_installed: t('Not installed'), unhealthy: t('Unhealthy'),
  }
  if (service.installBusy || ['failed', 'rollback_failed'].includes(service.installJob)) return labels[service.installJob] || service.installJob
  if (service.is_crash_loop) return t('Crash loop ({count})', { count: service.recent_crashes || 5 })
  if (!service.daemon && !isServiceActive(service)) return 'CLI'
  return labels[service.state || 'stopped'] || String(service.state).replaceAll('_', ' ')
}

function onDocumentClick() {
  closeCardMenu()
}
onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  featuredPaused.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  featuredTimer = setInterval(() => {
    if (!document.hidden) advanceFeatured()
  }, 30000)
})
onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  clearTimeout(catalogSearchTimer)
  clearInterval(featuredTimer)
})
</script>

<template>
  <PreflightReview ref="preflightReview" />
        <div
          v-if="vpnUnprotected"
          class="alert-banner alert-error"
          style="margin-bottom: 1.25rem;"
        >
          {{ $t('A tunneled app (qBittorrent, Prowlarr, or Flaresolverr) is running without an active VPN tunnel while VPN enforcement is enabled. Usenet traffic is not routed through the VPN.') }}
        </div>

        <div
          v-if="cloudflareTunnelIssue"
          class="alert-banner alert-error"
          style="margin-bottom: 1.25rem;"
        >
          {{ $t('Cloudflare Tunnel is enabled but cloudflared is not connected. The manager is still available at http://server-ip:8080.') }}
        </div>

        <div
          v-if="!hardlinksSupported"
          class="alert-banner alert-error"
          style="margin-bottom: 1.25rem;"
        >
          {{ $t('Hardlinks are not available between downloads and media, so *Arr will copy files (extra disk I/O). Put both folders on the same host filesystem and the same btrfs subvolume, then bind-mount one parent as') }} <code>/data</code> {{ $t('with') }} <code>AMM_DOWNLOAD_DIR=/data/downloads</code> {{ $t('and') }} <code>AMM_MEDIA_DIR=/data/media</code>.
        </div>


  <section class="catalog-store glass-card" :aria-label="$t('Catalog')">
    <aside class="catalog-store-sidebar">
      <h2 class="catalog-sidebar-title">{{ $t('Catalog') }}</h2>
      <label class="catalog-search-label" for="catalog-search">{{ $t('Search') }}</label>
      <input id="catalog-search" v-model="catalogSearchInput" type="search" class="ui-input catalog-store-search"
        :placeholder="$t('Search apps…')" autocomplete="off" spellcheck="false" />
      <nav class="catalog-store-nav catalog-status-nav" :aria-label="$t('Catalog')">
        <button type="button" :aria-pressed="discoverSelected" @click="selectCatalogSection()">
          <span aria-hidden="true">✧</span>{{ $t('Discover') }}
        </button>
        <button type="button" :aria-pressed="catalogStatusFilters.includes('installed')" @click="selectCatalogSection('installed')">
          <span aria-hidden="true">▦</span>{{ $t('My apps') }}<small>{{ installedAppCount }}</small>
        </button>
        <button type="button" :aria-pressed="catalogStatusFilters.includes('active')" @click="selectCatalogSection('active')">
          <span aria-hidden="true">▷</span>{{ $t('Active') }}<small>{{ activeAppCount }}</small>
        </button>
        <button type="button" :aria-pressed="catalogStatusFilters.includes('available')" @click="selectCatalogSection('available')">
          <span aria-hidden="true">＋</span>{{ $t('Available') }}<small>{{ availableAppCount }}</small>
        </button>
      </nav>
      <div class="catalog-category-filters">
        <button ref="categoryFiltersToggle" class="ui-btn ui-btn-ghost catalog-filters-toggle" type="button" :aria-expanded="categoryFiltersExpanded" aria-controls="catalog-category-navigation" @click="categoryFiltersExpanded = !categoryFiltersExpanded">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M7 12h10M10 17h4" /></svg>
          <span>{{ $t('Filters') }}</span>
          <small v-if="catalogCategoriesSelected.length">{{ catalogCategoriesSelected.map(categoryLabel).join(', ') }}</small>
          <svg class="catalog-filters-chevron" :class="{ 'is-expanded': categoryFiltersExpanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        </button>
        <nav ref="categoryNavigation" id="catalog-category-navigation" class="catalog-store-nav catalog-category-nav" :class="{ 'is-expanded': categoryFiltersExpanded }" :aria-label="$t('Category')">
        <p class="catalog-sidebar-label">{{ $t('Category') }}</p>
        <button class="catalog-all-categories" type="button" :aria-pressed="!catalogCategoriesSelected.length" @click="selectCatalogSection()">{{ $t('All categories') }}</button>
        <button v-for="category in catalogCategories" :key="category" type="button"
          :aria-pressed="catalogCategoriesSelected.includes(category)" @click="selectCatalogSection('', category)">
          <span aria-hidden="true">{{ { media: '▷', automation: '✧', downloading: '↓', indexers: '⌕', subtitles: '≡', requests: '＋', optimization: '◇', maintenance: '⚙' }[category] || '◇' }}</span>
          {{ categoryLabel(category) }}
        </button>
        </nav>
      </div>
      <button type="button" class="catalog-store-health" :class="{ 'is-warning': healthTone !== 'ok' }" @click="openHealthModal">
        <span>{{ $t('Health') }} · {{ healthTone === 'ok' ? 'OK' : $t('HIGH') }}</span>
        <small>CPU {{ cpuPercent != null ? Math.round(cpuPercent) + '%' : '—' }}</small>
      </button>
    </aside>
    <div class="catalog-store-main">
      <header class="catalog-store-heading">
        <h2>{{ catalogHeading }}</h2>
      <InstallationActivity ref="activity" @retry="retryJob" @logs="openLogs" />
      </header>
      <section v-if="showDiscovery && featuredService" class="catalog-feature-carousel" :aria-label="$t('Featured apps')"
        aria-roledescription="carousel" @mouseenter="featuredHovered = true" @mouseleave="featuredHovered = false"
        @focusin="featuredFocused = true" @focusout="featuredFocused = !!($event.relatedTarget && $event.currentTarget.contains($event.relatedTarget))">
      <button type="button" class="catalog-feature" @click="openFeatured"
        @pointerdown="startFeaturedSwipe" @pointerup="endFeaturedSwipe" @pointercancel="featuredTouch = null">
        <span :key="featuredService.name" class="catalog-feature-copy">
          <span class="catalog-feature-kicker">{{ categoryLabel(featuredService.category) }}</span>
          <strong>{{ featuredService.displayName }}</strong>
          <span>{{ featuredService.description }}</span>
          <span class="catalog-feature-link">{{ $t('Explore {name}', { name: featuredService.displayName }) }} →</span>
        </span>
        <img v-if="featuredService.iconSrc && !iconFailed[featuredService.name]" :src="featuredService.iconSrc" alt="" @error="iconFailed[featuredService.name] = true" />
      </button>
      <div v-if="combinedServices.length > 1" class="catalog-feature-controls">
        <div class="catalog-feature-dots catalog-feature-dots-left">
          <button type="button" class="catalog-feature-arrow" :aria-label="$t('Previous app')" @click="moveFeatured(-1)">
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m7.5 2-4 4 4 4" /></svg>
          </button>
          <button v-for="(service, index) in combinedServices.slice(0, Math.ceil(combinedServices.length / 2))" :key="service.name"
            type="button" class="catalog-feature-dot" :class="{ 'is-current': featuredPosition === index }"
            :aria-label="$t('Explore {name}', { name: service.displayName })" :aria-pressed="featuredPosition === index"
            @click="featuredIndex = index"><span aria-hidden="true"></span></button>
        </div>
        <button type="button" class="catalog-feature-pause" :aria-label="featuredPaused ? $t('Resume rotation') : $t('Pause rotation')"
          :aria-pressed="featuredPaused" @click="featuredPaused = !featuredPaused">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path v-if="featuredPaused" d="M3 1.5 10 6 3 10.5Z" /><path v-else d="M2 1h3v10H2zM7 1h3v10H7z" /></svg>
        </button>
        <div class="catalog-feature-dots catalog-feature-dots-right">
          <button v-for="(service, index) in combinedServices.slice(Math.ceil(combinedServices.length / 2))" :key="service.name"
            type="button" class="catalog-feature-dot" :class="{ 'is-current': featuredPosition === index + Math.ceil(combinedServices.length / 2) }"
            :aria-label="$t('Explore {name}', { name: service.displayName })" :aria-pressed="featuredPosition === index + Math.ceil(combinedServices.length / 2)"
            @click="featuredIndex = index + Math.ceil(combinedServices.length / 2)"><span aria-hidden="true"></span></button>
          <button type="button" class="catalog-feature-arrow" :aria-label="$t('Next app')" @click="moveFeatured(1)">
            <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m4.5 2 4 4-4 4" /></svg>
          </button>
        </div>
      </div>
      </section>
      <div id="catalog-toolbar" class="catalog-store-list-heading">
        <h3>{{ showDiscovery ? $t('For your media server') : $t('Applications') }} <span>{{ visibleServices.length }}</span></h3>
        <UiSelect id="catalog-sort" v-model="catalogSort" variant="inline" :aria-label="$t('Sort')"
          :options="[{ value: 'popularity', label: $t('Popularity') }, { value: 'az', label: $t('A to Z') }]" />
      </div>
      <div class="catalog-store-apps">
        <article v-for="service in visibleServices" :key="service.name" class="catalog-store-app"
          :class="{ 'has-open-menu': openCardMenu === service.name }" @click="onAppRowClick($event, service)">
          <button type="button" class="catalog-app-details" :aria-label="t('Settings for {name}', { name: service.displayName })" @click="openAppSettings(service)">
            <span class="app-badge catalog-store-icon" :class="{ 'has-icon': service.iconSrc && !iconFailed[service.name] }">
              <img v-if="service.iconSrc && !iconFailed[service.name]" :src="service.iconSrc" alt="" class="app-icon" @error="iconFailed[service.name] = true" />
              <span v-else>{{ service.name.substring(0, 2).toUpperCase() }}</span>
            </span>
            <span class="catalog-app-copy">
              <span class="catalog-app-name">{{ service.displayName }}</span>
              <span class="catalog-app-description">{{ service.description }}</span>
              <span class="catalog-app-state" :class="{ 'is-active': isServiceActive(service), 'is-failed': ['failed', 'rollback_failed'].includes(service.installJob) || service.is_crash_loop }">
                <template v-if="service.installed || service.installBusy || ['failed', 'rollback_failed'].includes(service.installJob)">{{ statusLabel(service) }}</template>
                <template v-else>{{ categoryLabel(service.category) }}</template>
                <span v-if="service.updateAvailable" class="catalog-app-update"> · {{ $t('Update available') }}</span>
              </span>
            </span>
          </button>
          <div class="catalog-app-actions">
            <a v-if="service.installed && service.daemon && isServiceActive(service) && !service.installBusy && !service.is_crash_loop"
              :href="service.webUrl" target="_blank" rel="noopener noreferrer" class="catalog-get" @click="openApp($event, service.name, service.webUrl)">{{ $t('Open') }}</a>
            <button v-else type="button" class="catalog-get" :disabled="!!actionLoading[service.name] || service.installBusy" @click="primaryAction(service)">
              <span v-if="actionLoading[service.name] || service.installBusy" class="spinner spinner-sm" :aria-label="$t('Loading…')"></span>
              <template v-else>{{ primaryActionLabel(service) }}</template>
            </button>
            <div class="card-menu-wrap" @click.stop @keydown.esc.stop="closeCardMenu">
              <button type="button" class="catalog-app-more" :aria-label="t('More actions for {name}', { name: service.displayName })"
                :aria-expanded="openCardMenu === service.name" @click="toggleCardMenu(service.name, $event)">⋯</button>
              <div v-if="openCardMenu === service.name" class="card-menu glass-popover">
                <button type="button" @click="openAppSettings(service)">{{ $t('Settings') }}</button>
                <template v-if="service.installed">
                  <button v-if="isServiceActive(service)" type="button" :disabled="!!actionLoading[service.name] || service.installBusy" @click="closeCardMenu(); stopApp(service.name)">{{ $t('Stop') }}</button>
                  <button v-if="isServiceActive(service)" type="button" :disabled="!!actionLoading[service.name] || service.installBusy" @click="closeCardMenu(); restartApp(service.name)">{{ $t('Restart') }}</button>
                  <button type="button" @click="closeCardMenu(); openLogs(service)">{{ $t('Logs') }}</button>
                  <button type="button" :disabled="!!actionLoading[service.name] || service.installBusy" @click="closeCardMenu(); updateApp(service.name)">{{ $t('Update') }}</button>
                  <button type="button" class="danger" :disabled="!!actionLoading[service.name] || service.installBusy" @click="closeCardMenu(); uninstallApp(service.name)">{{ $t('Uninstall') }}</button>
                </template>
                <a v-if="service.helpUrl" :href="service.helpUrl" target="_blank" rel="noopener noreferrer">{{ $t('Guide') }}</a>
              </div>
            </div>
          </div>
          <p v-if="service.installMessage && (service.installBusy || ['failed', 'rollback_failed'].includes(service.installJob))" class="catalog-app-progress" aria-live="polite">
            {{ service.installMessage }}
            <small v-if="service.installBusy && service.installUpdatedAt">{{ $t('Last progress {when} ago', { when: formatUptime(Date.now() / 1000 - service.installUpdatedAt) }) }}</small>
          </p>
        </article>
      </div>
      <p v-if="visibleServices.length === 0" class="catalog-empty">{{ $t('No applications match these filters.') }}</p>
      <section v-if="showDiscovery" class="catalog-collections" :aria-label="$t('Explore categories')">
        <button v-if="catalogCategories.includes('automation')" type="button" @click="selectCatalogSection('', 'automation')">
          <span class="catalog-feature-kicker">{{ $t('Less manual work') }}</span>
          <strong>{{ $t('Your collection grows on its own.') }}</strong>
          <span>{{ $t('Discover automation for films and series.') }}</span>
        </button>
        <button v-if="catalogCategories.includes('media')" type="button" @click="selectCatalogSection('', 'media')">
          <span class="catalog-feature-kicker">{{ $t('Ready to watch') }}</span>
          <strong>{{ $t('Your media, everywhere.') }}</strong>
          <span>{{ $t('Choose a media server that fits you.') }}</span>
        </button>
      </section>
    </div>
  </section>
</template>

<style scoped>
.catalog-search-label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.catalog-store { display: grid; grid-template-columns: 13.5rem minmax(0, 1fr); padding: 0; isolation: isolate; overflow: visible; }
.catalog-store-sidebar { display: flex; flex-direction: column; gap: 1rem; padding: 1.5rem 0.875rem; border-right: 1px solid var(--border-subtle); background: var(--panel-shine); border-radius: var(--radius-glass) 0 0 var(--radius-glass); }
.catalog-sidebar-title { margin: 0 0.5rem; font-size: var(--text-title); letter-spacing: -0.04em; }
.catalog-store-search { width: 100%; min-width: 0; border-radius: var(--radius-inset); }
.catalog-store-nav { display: grid; gap: 0.25rem; }
.catalog-filters-toggle, .catalog-store-nav .catalog-all-categories { display: none; }
.catalog-store-nav button { display: flex; align-items: center; gap: 0.6rem; width: 100%; border: 1px solid transparent; border-radius: 10px; padding: 0.65rem; background: transparent; color: var(--text-muted); font: inherit; font-size: var(--text-body); text-align: left; cursor: pointer; }
.catalog-store-nav button > span { width: 1.1rem; color: var(--color-primary-text); text-align: center; flex-shrink: 0; }
.catalog-store-nav button > small { margin-left: auto; font-size: var(--text-kicker); }
.catalog-store-nav button:hover { background: var(--bg-surface); }
.catalog-store-nav button[aria-pressed='true'] { background: var(--pill-active); color: var(--color-primary-text); }
.catalog-sidebar-label { padding: 1rem 0.65rem 0.35rem; font-size: var(--text-kicker); color: var(--text-dim); }
.catalog-store-health { display: grid; gap: 0.25rem; margin-top: auto; padding: 1.25rem 0.65rem 0; background: transparent; border: 0; border-top: 1px solid var(--border-subtle); font: inherit; font-size: var(--text-body); color: var(--color-success-fg); cursor: pointer; text-align: left; }
.catalog-store-health small { color: var(--text-dim); font-size: var(--text-kicker); }
.catalog-store-health.is-warning { color: var(--color-warning-fg); }
.catalog-store-main { min-width: 0; padding: 1.75rem; }
.catalog-store-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; }
.catalog-store-heading h2 { font-size: var(--text-display); letter-spacing: -0.04em; }
.catalog-feature { display: grid; grid-template-columns: minmax(0, 1fr) 8rem; align-items: center; gap: 1.5rem; width: 100%; padding: 1.75rem; border: 1px solid var(--border-strong); border-radius: var(--radius-tile); background: linear-gradient(125deg, rgb(var(--color-primary-rgb) / 0.19), transparent), var(--bg-surface); color: var(--text-main); text-align: left; cursor: pointer; font: inherit; }
.catalog-feature-carousel { position: relative; }
.catalog-feature-controls { position: absolute; bottom: 0.8rem; left: 1rem; right: 1rem; display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items: center; gap: 0.2rem; }
.catalog-feature-dots { display: flex; flex-wrap: wrap; align-items: center; }
.catalog-feature-dots-left { justify-content: flex-end; }
.catalog-feature-dots-right { justify-content: flex-start; }
.catalog-feature-dot, .catalog-feature-pause, .catalog-feature-arrow { display: inline-flex; justify-content: center; align-items: center; width: 1.5rem; height: 1.5rem; padding: 0; border: 0; border-radius: 50%; background: transparent; color: var(--text-muted); cursor: pointer; }
.catalog-feature-dot span { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: currentColor; opacity: 0.45; }
.catalog-feature-dot.is-current { color: var(--color-primary-text); }
.catalog-feature-dot.is-current span, .catalog-feature-dot:hover span { opacity: 1; }
.catalog-feature-pause svg { width: 0.5rem; height: 0.5rem; fill: currentColor; }
.catalog-feature-arrow svg { width: 0.65rem; height: 0.65rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.catalog-feature-arrow:hover, .catalog-feature-pause:hover { color: var(--text-main); }
.catalog-feature-dot:focus-visible, .catalog-feature-pause:focus-visible, .catalog-feature-arrow:focus-visible { outline: 2px solid var(--color-primary-text); outline-offset: 1px; }
.catalog-feature { min-height: 16rem; padding-bottom: 3.75rem; }
@keyframes catalog-feature-reveal { from { opacity: 0; transform: translateY(0.3rem); } to { opacity: 1; transform: translateY(0); } }
@media (prefers-reduced-motion: no-preference) { .catalog-feature-copy { animation: catalog-feature-reveal 300ms ease-out; } }
.catalog-feature-copy { display: grid; gap: 0.75rem; max-width: 28rem; }
.catalog-feature-kicker { color: var(--color-primary-text); text-transform: uppercase; letter-spacing: 0.1em; font-size: var(--text-kicker); }
.catalog-feature-copy strong { font-size: clamp(1.4rem, 2.5vw, 2rem); line-height: 1.15; letter-spacing: -0.035em; font-weight: 600; }
.catalog-feature-copy > span:not(.catalog-feature-kicker):not(.catalog-feature-link) { color: var(--text-muted); font-size: var(--text-body); }
.catalog-feature-link { color: var(--color-primary-text); font-size: var(--text-body); }
.catalog-feature img { width: 7rem; height: 7rem; object-fit: contain; filter: drop-shadow(0 1rem 1rem rgb(0 0 0 / 0.2)); }
.catalog-store-list-heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; margin: 1.5rem 0 0.25rem; }
.catalog-store-list-heading h3 { font-size: var(--text-strong); font-weight: 600; letter-spacing: -0.02em; }
.catalog-store-list-heading h3 span { margin-left: 0.4rem; font-size: var(--text-kicker); color: var(--text-dim); font-weight: 400; }
.catalog-store-apps { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 1.75rem; }
.catalog-store-app { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 0.5rem; padding: 1.1rem 0; border-bottom: 1px solid var(--border-subtle); position: relative; cursor: pointer; }
.catalog-store-app.has-open-menu { z-index: 5; }
.catalog-app-details { display: flex; align-items: center; gap: 0.8rem; min-width: 0; padding: 0; border: 0; border-radius: var(--radius-sm); background: transparent; color: inherit; text-align: left; font: inherit; cursor: pointer; }
.catalog-store-icon { width: 3rem; height: 3rem; min-width: 3rem; border-radius: 12px; background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); }
.catalog-store-icon .app-icon { width: 2.35rem; height: 2.35rem; }
.catalog-app-copy { display: grid; gap: 0.2rem; min-width: 0; }
.catalog-app-name { font-size: var(--text-body); font-weight: 600; }
.catalog-app-description { font-size: var(--text-kicker); color: var(--text-muted); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.catalog-app-state { color: var(--text-dim); font-size: var(--text-kicker); overflow-wrap: anywhere; }
.catalog-app-state.is-active { color: var(--color-success-fg); }
.catalog-app-state.is-failed, .catalog-app-update { color: var(--color-warning-fg); }
.card-menu a { display: block; padding: 0.55rem 0.75rem; color: var(--text-main); font-size: var(--text-body); text-decoration: none; }
.catalog-app-actions { display: flex; align-items: center; gap: 0.2rem; }
.catalog-get { display: inline-flex; align-items: center; justify-content: center; min-width: 4.3rem; min-height: 2rem; padding: 0.35rem 0.8rem; border: 1px solid var(--border-subtle); border-radius: var(--radius-control); background: var(--pill-active); color: var(--color-primary-text); font: inherit; font-size: var(--text-kicker); font-weight: 600; text-decoration: none; cursor: pointer; }
.catalog-get:hover { background: var(--bg-surface-elevated); }
.catalog-get:disabled { opacity: 0.6; cursor: wait; }
.catalog-app-more { display: grid; place-items: center; width: 1.8rem; min-height: 2rem; padding: 0; border: 0; background: transparent; color: var(--text-dim); font-size: var(--text-strong); cursor: pointer; border-radius: var(--radius-sm); }
.catalog-app-progress { grid-column: 1 / -1; color: var(--text-muted); font-size: var(--text-kicker); overflow-wrap: anywhere; }
.catalog-app-progress small { display: block; font-size: inherit; }
.catalog-collections { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin-top: 1.75rem; }
.catalog-collections button { display: grid; align-content: start; gap: 0.65rem; padding: 1.25rem; border: 1px solid var(--border-subtle); border-radius: var(--radius-tile); background: var(--bg-surface); color: var(--text-main); text-align: left; font: inherit; cursor: pointer; }
.catalog-collections strong { font-size: var(--text-strong); letter-spacing: -0.02em; }
.catalog-collections button > span:last-child { color: var(--text-muted); font-size: var(--text-body); }
@media (max-width: 1100px) { .catalog-store-apps { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 760px) {
  .catalog-store { grid-template-columns: minmax(0, 1fr); }
  .catalog-store-sidebar { border-right: 0; border-bottom: 1px solid var(--border-subtle); padding: 1rem; border-radius: var(--radius-glass) var(--radius-glass) 0 0; }
  .catalog-sidebar-title, .catalog-sidebar-label, .catalog-store-health { display: none; }
  .catalog-status-nav { display: flex; flex-wrap: nowrap; gap: 0.35rem; overflow-x: auto; }
  .catalog-status-nav button { flex: 0 0 auto; white-space: nowrap; }
  .catalog-category-nav { display: none; }
  .catalog-category-nav.is-expanded { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .35rem; margin-top: .75rem; }
  .catalog-category-nav.is-expanded .catalog-all-categories { display: flex; grid-column: 1 / -1; }
  .catalog-filters-toggle { display: flex; width: 100%; min-height: 44px; justify-content: flex-start; gap: .5rem; }
  .catalog-filters-toggle svg { width: 1.1rem; height: 1.1rem; flex-shrink: 0; }
  .catalog-filters-toggle small { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-primary-text); font: inherit; }
  .catalog-filters-chevron { margin-left: auto; }
  .catalog-filters-chevron.is-expanded { transform: rotate(180deg); }
  .catalog-store-nav button { width: auto; padding: 0.5rem 0.65rem; font-size: var(--text-kicker); }
  .catalog-store-nav button > span, .catalog-store-nav button > small { display: none; }
  .catalog-store-main { padding: 1.25rem; }
  .catalog-feature { grid-template-columns: minmax(0, 1fr) 4rem; padding: 1.25rem 1.25rem 3.75rem; gap: 0.75rem; }
  .catalog-feature { touch-action: pan-y; }
  .catalog-feature-dot { display: none; }
  .catalog-feature-controls { display: flex; justify-content: center; gap: 0.75rem; }
  .catalog-feature-arrow, .catalog-feature-pause { width: 44px; height: 44px; }
  .catalog-feature-arrow svg, .catalog-feature-pause svg { width: 1rem; height: 1rem; }
  .catalog-app-actions .card-menu { left: auto; right: 0; width: max-content; min-width: 10.5rem; max-width: calc(100vw - 2rem); max-height: calc(100dvh - 2rem); overflow-y: auto; }
  .catalog-feature img { width: 4rem; height: 4rem; }
  .catalog-collections { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 400px) {
  .catalog-feature { grid-template-columns: minmax(0, 1fr); }
  .catalog-feature img { display: none; }
  .catalog-store-main { padding: 1rem; }
  .catalog-app-details { gap: 0.5rem; }
  .catalog-store-icon { width: 2.25rem; height: 2.25rem; min-width: 2.25rem; }
  .catalog-store-icon .app-icon { width: 1.85rem; height: 1.85rem; }
  .catalog-get { min-width: 3.4rem; padding-inline: 0.5rem; }
}
@media (pointer: coarse) { .catalog-get, .catalog-app-more, .catalog-store-nav button { min-height: 44px; } .catalog-app-more { width: 36px; } }
</style>
