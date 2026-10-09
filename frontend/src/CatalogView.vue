<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { appIconSrc } from './appIcons.js'
import { catalogQueryFromState, catalogStateFromQuery, sameCatalogQuery } from './catalogQuery.js'
import { appWebUrl } from './appWebUrl.js'
import { openSeerr } from './seerrOpen.js'
import { apiError, apiRequest, readJson } from './api.js'
import { formatUpdateWhen, formatUptime } from './format.js'
import { useToasts } from './useToasts.js'

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
let catalogSearchTimer = null
const actionLoading = ref({})
const iconFailed = ref({})
const openCardMenu = ref('')

function openLogs(service) { emit('open-logs', service) }
function openAppSettings(service) { emit('open-settings', service) }
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
      description: cat.description,
      category: cat.category,
      iconSrc: appIconSrc(cat.name),
      tier: cat.tier,
      port,
      defaultPort: cat.default_port,
      installed: cat.installed || (live && live.installed) || false,
      installedVersion: cat.installed_version || (live && live.version),
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

const catalogUpdateCount = computed(
  () => (props.updateStatus.available || []).filter((row) => row.kind !== 'appliance').length
)
const applianceUpdate = computed(
  () => (props.updateStatus.available || []).find((row) => row.kind === 'appliance')
)

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
  return names.sort((a, b) => (CATEGORY_LABELS[a] || a).localeCompare(CATEGORY_LABELS[b] || b))
})

function isRunningService(s) {
  return s.state === 'running' || s.state === 'healthy'
}

function toggleCategoryFilter(category) {
  if (category === 'all') {
    patchCatalogQuery({ cat: [] })
    return
  }
  const current = [...catalogCategoriesSelected.value]
  const idx = current.indexOf(category)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(category)
  patchCatalogQuery({ cat: current })
}

function removeCategoryFilter(category) {
  patchCatalogQuery({ cat: catalogCategoriesSelected.value.filter((c) => c !== category) })
}

function toggleStatusFilter(key) {
  const current = [...catalogStatusFilters.value]
  const idx = current.indexOf(key)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(key)
  patchCatalogQuery({ status: current })
}

function removeStatusFilter(key) {
  patchCatalogQuery({ status: catalogStatusFilters.value.filter((k) => k !== key) })
}

function scrollToCatalog() {
  document.getElementById('catalog-toolbar')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function openCatalog() {
  router.push({ name: 'catalog' })
}

function filterByActiveServices() {
  toggleStatusFilter('active')
  scrollToCatalog()
}

function filterByInstalledPlugins() {
  toggleStatusFilter('installed')
  scrollToCatalog()
}

function filterByAvailablePlugins() {
  toggleStatusFilter('available')
  scrollToCatalog()
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

const catalogSize = computed(() => combinedServices.value.length)
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
const transcodingAvailable = computed(() => props.systemInfo?.transcoding?.available)
const hardlinksSupported = computed(() => props.systemInfo?.storage?.download_dir?.hardlinks_supported !== false)

// --- App Control Actions ---
async function startApp(name) {
  actionLoading.value[name] = 'start'
  try {
    const res = await apiRequest(`/api/applications/${name}/start`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok) {
      showToast(`Started ${name}`, 'success')
      await props.fetchApplications()
    } else {
      showToast(apiError(data, `Failed to start ${name}`), 'error')
    }
  } catch (err) {
    showToast(`Error starting ${name}: ${err.message}`, 'error')
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
      showToast(`Stopped ${name}`, 'info')
      await props.fetchApplications()
    } else {
      showToast(apiError(data, `Failed to stop ${name}`), 'error')
    }
  } catch (err) {
    showToast(`Error stopping ${name}: ${err.message}`, 'error')
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
      showToast(`Restarted ${name}`, 'success')
      await props.fetchApplications()
    } else {
      showToast(apiError(data, `Failed to restart ${name}`), 'error')
    }
  } catch (err) {
    showToast(`Error restarting ${name}: ${err.message}`, 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function updateApp(name) {
  actionLoading.value[name] = 'update'
  try {
    const res = await apiRequest(`/api/applications/${name}/update`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok && data.status !== 'rolled_back') {
      showToast(`Updated ${name} to ${data.version || 'latest'}`, 'success')
      await props.refreshDashboard()
    } else {
      showToast(apiError(data, `Update failed for ${name}`), 'error')
    }
  } catch (err) {
    showToast(`Error updating ${name}: ${err.message}`, 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function uninstallApp(name) {
  const removeConfig = window.confirm(
    `Uninstall ${name}?\n\nOK = also remove configuration.\nCancel = keep configuration (binary only).`
  )
  const removeData = removeConfig && window.confirm(`Also delete ${name} application data? Media libraries are never deleted.`)
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
      showToast(`Uninstalled ${name}`, 'info')
      await props.refreshDashboard()
    } else {
      showToast(apiError(data, `Failed to uninstall ${name}`), 'error')
    }
  } catch (err) {
    showToast(`Error uninstalling ${name}: ${err.message}`, 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

async function installApp(name, displayName) {
  actionLoading.value[name] = 'install'
  try {
    const res = await apiRequest(`/api/catalog/${name}/install`, { method: 'POST' })
    const data = await readJson(res)
    if (res.ok) {
      showToast(`Installing ${displayName || name}…`, 'success')
      setTimeout(() => props.refreshDashboard(), 3000)
    } else {
      showToast(apiError(data, `Failed to install ${name}`), 'error')
    }
  } catch (err) {
    showToast(`Error installing ${name}: ${err.message}`, 'error')
  } finally {
    delete actionLoading.value[name]
  }
}
async function resetCrashLoop(name) {
  try {
    const res = await apiRequest(`/api/applications/${name}/reset-crash-loop`, { method: 'POST' })
    if (res.ok) {
      showToast(`Crash loop reset for ${name}`, 'success')
      await props.fetchApplications()
    }
  } catch (err) {
    showToast(`Failed to reset crash loop: ${err}`, 'error')
  }
}

function isServiceActive(service) {
  return service.state === 'running' || service.state === 'healthy'
}

function toggleCardMenu(name) {
  openCardMenu.value = openCardMenu.value === name ? '' : name
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
      showToast(apiError(data, 'Recyclarr sync failed'), 'error')
      return
    }
    showToast('Recyclarr sync finished', 'success')
  } catch (err) {
    showToast(err.message || 'Recyclarr sync failed', 'error')
  } finally {
    delete actionLoading.value.recyclarr
  }
}

function statusLabel(service) {
  if (service.is_crash_loop) return `CRASH LOOP (${service.recent_crashes || 5})`
  if (!service.daemon && !isServiceActive(service)) return 'CLI'
  return String(service.state || 'stopped').toUpperCase().replace('_', ' ')
}

function statusBadgeClass(service) {
  if (service.is_crash_loop || service.state === 'crash_loop') return 'badge-failed font-bold'
  if (!service.daemon && !isServiceActive(service)) return 'badge-inactive'
  switch (service.state) {
    case 'healthy':
    case 'running':
      return 'badge-running'
    case 'stopped':
      return 'badge-stopped'
    case 'crashed':
    case 'failed':
      return 'badge-failed'
    default:
      return 'badge-inactive'
  }
}


function onDocumentClick() {
  closeCardMenu()
}
onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  clearTimeout(catalogSearchTimer)
})
</script>

<template>
        <!-- Metric Cards -->
        <section class="metrics-grid">
          <div
            class="stat-card glass-card stat-card-filter"
            :class="{ 'is-filter-on': catalogStatusFilters.includes('active') }"
            role="button"
            tabindex="0"
            :aria-pressed="catalogStatusFilters.includes('active')"
            title="Show only running apps"
            @click="filterByActiveServices"
            @keydown.enter.prevent="filterByActiveServices"
            @keydown.space.prevent="filterByActiveServices"
          >
            <div class="stat-icon-wrapper active-color">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">ACTIVE</div>
              <div class="stat-value font-mono">
                <span class="text-glow-cyan">{{ activeAppCount }}</span>
                <span class="stat-sub"> running</span>
              </div>
            </div>
          </div>

          <div
            class="stat-card glass-card stat-card-filter"
            :class="{ 'is-filter-on': catalogStatusFilters.includes('installed') }"
            role="button"
            tabindex="0"
            :aria-pressed="catalogStatusFilters.includes('installed')"
            title="Show only installed applications"
            @click="filterByInstalledPlugins"
            @keydown.enter.prevent="filterByInstalledPlugins"
            @keydown.space.prevent="filterByInstalledPlugins"
          >
            <div class="stat-icon-wrapper installed-color">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">INSTALLED</div>
              <div class="stat-value font-mono">
                <span class="text-glow-purple">{{ installedAppCount }}</span>
                <span class="stat-sub"> of {{ catalogSize }}</span>
              </div>
            </div>
          </div>

          <div
            class="stat-card glass-card stat-card-filter"
            :class="{ 'is-filter-on': catalogStatusFilters.includes('available') }"
            role="button"
            tabindex="0"
            :aria-pressed="catalogStatusFilters.includes('available')"
            title="Show applications that are not installed yet"
            @click="filterByAvailablePlugins"
            @keydown.enter.prevent="filterByAvailablePlugins"
            @keydown.space.prevent="filterByAvailablePlugins"
          >
            <div class="stat-icon-wrapper storage-color">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7"></rect>
                <rect x="14" y="3" width="7" height="7"></rect>
                <rect x="14" y="14" width="7" height="7"></rect>
                <rect x="3" y="14" width="7" height="7"></rect>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">AVAILABLE</div>
              <div class="stat-value font-mono">
                <span class="text-glow-cyan">{{ availableAppCount }}</span>
                <span class="stat-sub"> of {{ catalogSize }}</span>
              </div>
            </div>
          </div>

          <div
            class="stat-card glass-card stat-card-filter"
            :class="{ 'is-filter-on': showHealthModal }"
            role="button"
            tabindex="0"
            title="Host health"
            @click="openHealthModal"
            @keydown.enter.prevent="openHealthModal"
            @keydown.space.prevent="openHealthModal"
          >
            <div class="stat-icon-wrapper refresh-color">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">HEALTH</div>
              <div class="stat-value font-mono">
                <span :class="healthTone === 'ok' ? 'text-emerald' : 'text-warn'">{{ healthTone === 'ok' ? 'OK' : 'HIGH' }}</span>
                <span class="stat-sub"> · CPU {{ cpuPercent != null ? Math.round(cpuPercent) + '%' : '—' }}</span>
              </div>
            </div>
          </div>
        </section>

        <div
          v-if="vpnUnprotected"
          class="alert-banner alert-error"
          style="margin-bottom: 1.25rem;"
        >
          A tunneled app (qBittorrent, Prowlarr, or Flaresolverr) is running without an active VPN tunnel while VPN enforcement is enabled. Usenet traffic is not routed through the VPN.
        </div>

        <div
          v-if="cloudflareTunnelIssue"
          class="alert-banner alert-error"
          style="margin-bottom: 1.25rem;"
        >
          Cloudflare Tunnel is enabled but cloudflared is not connected. The manager is still available at http://server-ip:8080.
        </div>

        <div
          v-if="!hardlinksSupported"
          class="alert-banner alert-error"
          style="margin-bottom: 1.25rem;"
        >
          Hardlinks are not available between downloads and media, so *Arr will copy files (extra disk I/O). Put both folders on the same host filesystem and the same btrfs subvolume, then bind-mount one parent as <code>/data</code> with <code>AMM_DOWNLOAD_DIR=/data/downloads</code> and <code>AMM_MEDIA_DIR=/data/media</code>.
        </div>


        <!-- Services Section Header -->
        <div class="section-title-row">
          <div>
            <h2 class="section-title">Applications</h2>
            <p class="section-subtitle">
              Install, start, and manage apps in this appliance.
              <span v-if="updateStatus.last_check_at || (updateStatus.available || []).length">
                Last update check {{ formatUpdateWhen(updateStatus.last_check_at) }}
                · last apply {{ formatUpdateWhen(updateStatus.last_apply_at) }}
                · {{ catalogUpdateCount }} waiting
                <span v-if="applianceUpdate"> · appliance image update</span>
              </span>
              <span v-if="backupStatus.schedule">
                · last backup {{ formatUpdateWhen(backupStatus.last_backup_at) }}
                <span v-if="backupStatus.last_error" class="text-warn">(last attempt failed)</span>
              </span>
            </p>
          </div>
          <button @click="refreshDashboard" class="ui-btn ui-btn-ghost" :disabled="isLoadingData">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': isLoadingData }">
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            <span>Refresh</span>
          </button>
        </div>

        <div id="catalog-toolbar" class="catalog-toolbar glass-card">
          <div class="catalog-filter-group catalog-search-group">
            <label class="catalog-filter-label" for="catalog-search">Search</label>
            <input
              id="catalog-search"
              v-model="catalogSearchInput"
              type="search"
              class="ui-input catalog-search-input"
              placeholder="Search apps…"
              autocomplete="off"
              spellcheck="false"
            />
          </div>
          <div class="catalog-filter-group">
            <span class="catalog-filter-label">Status</span>
            <div class="catalog-chips" role="group" aria-label="Filter by status">
              <button
                type="button"
                class="catalog-chip"
                :class="{ active: catalogStatusFilters.includes('active') }"
                @click="toggleStatusFilter('active')"
              >
                Active
                <span
                  v-if="catalogStatusFilters.includes('active')"
                  class="chip-clear"
                  role="button"
                  aria-label="Remove active filter"
                  @click.stop="removeStatusFilter('active')"
                >×</span>
              </button>
              <button
                type="button"
                class="catalog-chip"
                :class="{ active: catalogStatusFilters.includes('installed') }"
                @click="toggleStatusFilter('installed')"
              >
                Installed
                <span
                  v-if="catalogStatusFilters.includes('installed')"
                  class="chip-clear"
                  role="button"
                  aria-label="Remove installed filter"
                  @click.stop="removeStatusFilter('installed')"
                >×</span>
              </button>
              <button
                type="button"
                class="catalog-chip"
                :class="{ active: catalogStatusFilters.includes('available') }"
                @click="toggleStatusFilter('available')"
              >
                Available
                <span
                  v-if="catalogStatusFilters.includes('available')"
                  class="chip-clear"
                  role="button"
                  aria-label="Remove available filter"
                  @click.stop="removeStatusFilter('available')"
                >×</span>
              </button>
            </div>
          </div>
          <div class="catalog-filter-group">
            <span class="catalog-filter-label">Category</span>
            <div class="catalog-chips" role="group" aria-label="Filter by category">
              <button
                type="button"
                class="catalog-chip"
                :class="{ active: catalogCategoriesSelected.length === 0 }"
                @click="toggleCategoryFilter('all')"
              >
                All
              </button>
              <button
                v-for="category in catalogCategories"
                :key="category"
                type="button"
                class="catalog-chip"
                :class="{ active: catalogCategoriesSelected.includes(category) }"
                @click="toggleCategoryFilter(category)"
              >
                {{ CATEGORY_LABELS[category] || category }}
                <span
                  v-if="catalogCategoriesSelected.includes(category)"
                  class="chip-clear"
                  role="button"
                  :aria-label="'Remove ' + (CATEGORY_LABELS[category] || category) + ' filter'"
                  @click.stop="removeCategoryFilter(category)"
                >×</span>
              </button>
            </div>
          </div>
          <div class="catalog-filter-group catalog-sort-group">
            <label class="catalog-filter-label" for="catalog-sort">Sort</label>
            <select id="catalog-sort" v-model="catalogSort" class="ui-input catalog-sort-select">
              <option value="popularity">Popularity</option>
              <option value="az">A to Z</option>
            </select>
          </div>
          <span class="catalog-count font-mono">{{ visibleServices.length }} shown · {{ installedAppCount }} installed · {{ availableAppCount }} available</span>
        </div>

        <!-- Services Grid -->
        <div class="services-grid">
          <div
            v-for="service in visibleServices"
            :key="service.name"
            class="service-card glass-card"
            :class="{ 'is-running': service.state === 'running' || service.state === 'healthy' }"
          >
            <!-- Card Header -->
            <div class="service-header">
              <div class="service-ident">
                <div class="app-badge" :class="service.category">
                  <img
                    v-if="service.iconSrc && !iconFailed[service.name]"
                    :src="service.iconSrc"
                    :alt="service.displayName"
                    class="app-icon"
                    @error="iconFailed[service.name] = true"
                  />
                  <span v-else>{{ service.name.substring(0, 2).toUpperCase() }}</span>
                </div>
                <div>
                  <div class="service-name-row">
                    <h3 class="service-name">{{ service.displayName }}</h3>
                    <a
                      v-if="service.helpUrl"
                      :href="service.helpUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="help-btn"
                      :title="'Help / wiki for ' + service.displayName"
                    >?</a>
                    <span class="category-pill">{{ CATEGORY_LABELS[service.category] || service.category }}</span>
                    <span v-if="service.updateAvailable" class="update-pill">Update available</span>
                  </div>
                  <div v-if="service.daemon" class="service-port font-mono">
                    <span class="port-label">PORT:</span>
                    <a
                      :href="service.webUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="port-link"
                      @click="service.name === 'seerr' && openSeerr($event, service.webUrl)"
                      title="Open UI"
                    >
                      :{{ service.port }}
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                        <polyline points="15 3 21 3 21 9"></polyline>
                        <line x1="10" y1="14" x2="21" y2="3"></line>
                      </svg>
                    </a>
                  </div>
                </div>
              </div>

              <!-- Status Badge -->
              <span class="status-badge" :class="statusBadgeClass(service)">
                <span class="badge-dot"></span>
                <span>{{ statusLabel(service) }}</span>
              </span>
            </div>

            <!-- Description -->
            <p class="service-desc">{{ service.description }}</p>

            <!-- Metadata footer -->
            <div class="service-meta font-mono">
              <span v-if="service.installedVersion">v{{ service.installedVersion }}<template v-if="service.latestVersion"> → {{ service.latestVersion }}</template></span>
              <span v-else-if="service.installed">Installed</span>
              <span v-else class="text-dim">Not installed</span>

              <span v-if="service.uptime" class="uptime-text">
                up {{ formatUptime(service.uptime) }}
              </span>
              <span v-if="service.pid" class="pid-text">PID: {{ service.pid }}</span>
            </div>

            <!-- Action Controls -->
            <div class="service-actions">
              <template v-if="!service.installed">
                <button
                  @click="installApp(service.name, service.displayName)"
                  class="btn-action btn-install"
                  :disabled="actionLoading[service.name] === 'install'"
                >
                  <span v-if="actionLoading[service.name] === 'install'" class="spinner spinner-sm"></span>
                  <span v-else>Install</span>
                </button>
                <button type="button" class="btn-action btn-logs" @click.stop="openAppSettings(service)">
                  Settings
                </button>
              </template>

              <template v-else>
                <button
                  v-if="service.is_crash_loop"
                  @click="resetCrashLoop(service.name)"
                  class="btn-action btn-stop"
                  title="Clear crash history and unlock auto-restart"
                >
                  Reset
                </button>
                <button
                  v-else-if="!isServiceActive(service) && service.daemon"
                  @click="startApp(service.name)"
                  class="btn-action btn-start"
                  :disabled="!!actionLoading[service.name]"
                >
                  <span v-if="actionLoading[service.name] === 'start'" class="spinner spinner-sm"></span>
                  <span v-else>Start</span>
                </button>
                <button
                  v-else-if="isServiceActive(service)"
                  @click="stopApp(service.name)"
                  class="btn-action btn-stop"
                  :disabled="!!actionLoading[service.name]"
                >
                  <span v-if="actionLoading[service.name] === 'stop'" class="spinner spinner-sm"></span>
                  <span v-else>Stop</span>
                </button>
                <button
                  v-else-if="!service.daemon"
                  type="button"
                  class="btn-action btn-start"
                  :disabled="!!actionLoading[service.name]"
                  @click="syncRecyclarr"
                >
                  <span v-if="actionLoading[service.name] === 'sync'" class="spinner spinner-sm"></span>
                  <span v-else>Sync</span>
                </button>
                <a
                  v-if="service.daemon"
                  :href="service.webUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="btn-action btn-webui"
                  @click="service.name === 'seerr' && openSeerr($event, service.webUrl)"
                >
                  Open UI
                </a>
                <div class="card-menu-wrap" @click.stop>
                  <button
                    type="button"
                    class="btn-action btn-more"
                    :class="{ open: openCardMenu === service.name }"
                    title="More actions"
                    @click="toggleCardMenu(service.name)"
                  >
                    More
                  </button>
                  <div v-if="openCardMenu === service.name" class="card-menu">
                    <button
                      v-if="isServiceActive(service)"
                      type="button"
                      @click="closeCardMenu(); restartApp(service.name)"
                    >
                      Restart
                    </button>
                    <button type="button" @click="closeCardMenu(); openLogs(service)">Logs</button>
                    <button type="button" @click="openAppSettings(service)">Settings</button>
                    <button
                      type="button"
                      :disabled="!!actionLoading[service.name]"
                      @click="closeCardMenu(); updateApp(service.name)"
                    >
                      {{ actionLoading[service.name] === 'update' ? 'Updating…' : 'Update' }}
                    </button>
                    <button
                      type="button"
                      class="danger"
                      :disabled="!!actionLoading[service.name]"
                      @click="closeCardMenu(); uninstallApp(service.name)"
                    >
                      Uninstall
                    </button>
                  </div>
                </div>
              </template>
            </div>
          </div>
          <p v-if="visibleServices.length === 0" class="catalog-empty">No applications match these filters.</p>
        </div>

</template>
