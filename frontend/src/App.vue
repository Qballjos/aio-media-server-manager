<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import WizardPanel from './WizardPanel.vue'
import SettingsPanel from './SettingsPanel.vue'
import HomepagePanel from './HomepagePanel.vue'
import AuthScreens from './AuthScreens.vue'
import CatalogView from './CatalogView.vue'
import LogsModal from './LogsModal.vue'
import HealthModal from './HealthModal.vue'
import AppSettingsModal from './AppSettingsModal.vue'
import WallpaperLayer from './WallpaperLayer.vue'
import AppLoader from './AppLoader.vue'
import { homeEditing } from './homeLayout.js'
import { startGuardedInterval } from './pageVisible.js'
import {
  apiRequest,
  applySession,
  clearSession,
  readJson,
  setUnauthorizedHandler,
} from './api.js'
import { useToasts } from './useToasts.js'
import { canPromptInstall, promptInstall, subscribePwaInstall } from './pwaInstall.js'
import { brandTitle, brandHeaderUrl, loadBranding } from './branding.js'
import { migrateLocalVisualsIfNeeded } from './visualsProfile.js'
import { lockThemeToSystem, unlockTheme } from './theme.js'
import { tunnelChip, vpnChip } from './statusChips.js'

const { toasts, showToast } = useToasts()
const showPwaInstall = ref(false)

const authStatus = ref({
  setup_required: false,
  authenticated: false,
  username: null,
  avatar_url: null,
})
const catalogApps = ref([])
const UPDATE_TOAST_KEY = 'amm-update-notice'
const updateStatus = ref({
  available: [],
  last_check_at: null,
  last_apply_at: null,
  paused: false,
  notify_enabled: false,
})
const backupStatus = ref({})
const applications = ref([])
const systemInfo = ref(null)
const hostArch = ref('')
const isLoadingData = ref(false)
const wizardCompleted = ref(true)
const wizardStatusLoaded = ref(false)
const authStatusKnown = ref(false)
const wiringRunning = ref(false)
const vpnLive = ref({})
const cloudflareLive = ref({})
const showHealthModal = ref(false)
const logApp = ref(null)
const settingsService = ref(null)

let stopLivePoll = null
let stopSlowPoll = null

const route = useRoute()
const router = useRouter()
const currentView = computed(() => {
  if (route.name === 'settings') return 'settings'
  if (route.name === 'catalog') return 'catalog'
  return 'home'
})

const transcodingAvailable = computed(() => systemInfo.value?.transcoding?.available)
const statusChips = computed(() =>
  [
    ['vpn', vpnChip(vpnLive.value)],
    ['tunnel', tunnelChip(cloudflareLive.value)],
  ]
    .filter(([, chip]) => chip)
    .map(([key, chip]) => ({ key, ...chip })),
)
const availableUpdates = computed(() => updateStatus.value.available || [])
const showUpdatesPill = computed(
  () =>
    authStatus.value.authenticated &&
    wizardCompleted.value &&
    !!updateStatus.value.notify_enabled &&
    availableUpdates.value.length > 0,
)
const updatesPillLabel = computed(() => {
  const n = availableUpdates.value.length
  return n === 1 ? '1 update' : `${n} updates`
})

function updateFingerprint(status) {
  return (status?.available || [])
    .map((row) => `${row.kind || 'catalog'}:${row.name}:${row.latest_version || row.latest_sha || ''}`)
    .sort()
    .join('|')
}

function maybeNotifyUpdates(status) {
  if (!status?.notify_enabled) return
  const items = status.available || []
  if (!items.length) return
  const fingerprint = updateFingerprint(status)
  try {
    if (sessionStorage.getItem(UPDATE_TOAST_KEY) === fingerprint) return
    sessionStorage.setItem(UPDATE_TOAST_KEY, fingerprint)
  } catch (_) {}
  const appliance = items.some((row) => row.kind === 'appliance')
  const catalog = items.filter((row) => row.kind !== 'appliance')
  let message = 'Updates available'
  if (catalog.length && appliance) {
    message = `${catalog.length} app update(s) and a newer appliance image are available`
  } else if (appliance) {
    message = 'A newer appliance image is available. Pull and recreate on the host.'
  } else if (catalog.length === 1) {
    const row = catalog[0]
    const version = row.latest_version ? ` ${row.latest_version}` : ''
    message = `${row.display_name || row.name}${version} is available`
  } else {
    message = `${catalog.length} catalog updates are available`
  }
  showToast(message, 'info')
}

setUnauthorizedHandler(() => {
  if (!authStatus.value.authenticated) return
  authStatus.value.authenticated = false
  clearSession()
  showToast('Session expired. Please log in again.', 'warning')
})

function onAuthStatus(data) {
  authStatusKnown.value = true
  authStatus.value = data
  applySession(data)
  if (data?.authenticated) {
    migrateLocalVisualsIfNeeded(data).catch(() => {})
  }
}

async function onAuthSession(data) {
  authStatusKnown.value = true
  authStatus.value = {
    setup_required: false,
    authenticated: true,
    username: data.username,
    avatar_url: data.avatar_url || null,
  }
  applySession(data)
  await migrateLocalVisualsIfNeeded(data).catch(() => {})
  await Promise.all([refreshDashboard(), fetchWizardStatus()])
}

async function handleLogout() {
  try {
    await apiRequest('/api/auth/logout', { method: 'POST' })
  } catch (_) {}
  clearSession()
  authStatus.value.authenticated = false
  authStatus.value.username = null
  authStatus.value.avatar_url = null
  vpnLive.value = {}
  cloudflareLive.value = {}
  router.replace({ name: 'home' })
  showToast('Logged out successfully.', 'info')
}

async function fetchCatalog() {
  try {
    const res = await apiRequest('/api/catalog')
    if (res.ok) {
      const data = await readJson(res)
      catalogApps.value = data.applications || []
      hostArch.value = data.host_architecture || ''
    }
  } catch (err) {
    console.error('Catalog fetch error:', err)
  }
}

async function fetchApplications() {
  try {
    const res = await apiRequest('/api/applications')
    if (res.ok) {
      const data = await readJson(res)
      applications.value = data.applications || []
    }
  } catch (err) {
    console.error('Applications fetch error:', err)
  }
}

async function fetchVpnStatus() {
  if (!authStatus.value.authenticated) return
  try {
    const res = await apiRequest('/api/vpn/status')
    if (res.ok) vpnLive.value = await readJson(res)
  } catch (err) {
    console.error('VPN status error:', err)
  }
}

async function fetchSystemInfo() {
  try {
    const res = await apiRequest('/api/system/info')
    if (res.ok) {
      systemInfo.value = await readJson(res)
      if (systemInfo.value?.vpn) vpnLive.value = systemInfo.value.vpn
      if (systemInfo.value?.cloudflare_tunnel) cloudflareLive.value = systemInfo.value.cloudflare_tunnel
    }
  } catch (err) {
    console.error('System info fetch error:', err)
  }
}

async function fetchWizardStatus() {
  try {
    const res = await apiRequest('/api/wizard/status')
    if (res.ok) {
      const data = await readJson(res)
      wizardCompleted.value = !!data.completed
    } else {
      wizardCompleted.value = true
    }
  } catch (err) {
    console.error('Wizard status error:', err)
    wizardCompleted.value = true
  } finally {
    wizardStatusLoaded.value = true
  }
}

function syncSetupTheme() {
  // Until auth status is known, stay on OS theme (covers first-run + loading).
  if (!authStatusKnown.value) {
    lockThemeToSystem()
    return
  }
  const setup = !!authStatus.value.setup_required
  const auth = !!authStatus.value.authenticated
  const wizardPending = auth && (!wizardStatusLoaded.value || !wizardCompleted.value)
  if (setup || wizardPending) {
    lockThemeToSystem()
    return
  }
  unlockTheme()
}

watch(
  () => [
    authStatusKnown.value,
    authStatus.value.setup_required,
    authStatus.value.authenticated,
    wizardCompleted.value,
    wizardStatusLoaded.value,
  ],
  () => syncSetupTheme(),
  { immediate: true },
)

async function onWizardDone() {
  wizardCompleted.value = true
  unlockTheme()
  await router.replace({ name: 'home' })
  showToast('Setup finished. Catalog installs may continue in the background.', 'success')
  await refreshDashboard()
}

function onSettingsSession(data) {
  applySession(data)
  if (data?.username) authStatus.value.username = data.username
  if (data && 'avatar_url' in data) authStatus.value.avatar_url = data.avatar_url || null
}

function onSettingsVpn(vpn) {
  if (vpn) vpnLive.value = vpn
  else fetchVpnStatus()
}

async function fetchUpdateStatus() {
  try {
    const [res, bak] = await Promise.all([apiRequest('/api/updates/status'), apiRequest('/api/backups')])
    if (res.ok) {
      const data = await readJson(res)
      updateStatus.value = data
      maybeNotifyUpdates(data)
    }
    if (bak.ok) backupStatus.value = (await readJson(bak)).schedule || {}
  } catch (err) {
    console.error('Update status error:', err)
  }
}

async function refreshDashboard() {
  isLoadingData.value = true
  try {
    // system/info already includes vpn — skip a separate vpn round-trip on load
    await Promise.all([fetchCatalog(), fetchApplications(), fetchSystemInfo(), fetchUpdateStatus()])
  } finally {
    isLoadingData.value = false
  }
}

function pollLiveStatus() {
  if (!authStatus.value.authenticated || !wizardCompleted.value) return
  if (currentView.value === 'catalog') {
    fetchApplications()
    fetchCatalog()
  }
  fetchVpnStatus()
}

function pollSlowStatus() {
  if (!authStatus.value.authenticated || !wizardCompleted.value) return
  if (!showHealthModal.value) fetchSystemInfo()
  fetchUpdateStatus()
}

function onHealthSystem(data) {
  systemInfo.value = data
  if (data?.vpn) vpnLive.value = data.vpn
  if (data?.cloudflare_tunnel) cloudflareLive.value = data.cloudflare_tunnel
}

function openCatalog() {
  router.push({ name: 'catalog' })
}

async function runAutomatedWiring() {
  wiringRunning.value = true
  try {
    const res = await apiRequest('/api/integrations/run', { method: 'POST' })
    if (res.ok) {
      const data = await readJson(res)
      showToast(`Auto-Wire finished (${data.steps?.length || 0} tasks)`, 'success')
      await refreshDashboard()
    } else {
      showToast('Auto-Wire failed', 'error')
    }
  } catch (err) {
    showToast(`Auto-Wire error: ${err}`, 'error')
  } finally {
    wiringRunning.value = false
  }
}

watch(currentView, (view) => {
  if (!authStatus.value.authenticated || !wizardCompleted.value) return
  if (view === 'catalog') {
    fetchApplications()
    fetchCatalog()
    fetchUpdateStatus()
  }
})

function refreshPwaInstall() {
  showPwaInstall.value = canPromptInstall()
}

async function installPwa() {
  const ok = await promptInstall()
  if (ok) showToast('App installed on this device.', 'success')
}

let stopPwa = null

// The account menu closes on a click outside it and when the page changes.
function closeAccountMenu(event) {
  const menu = document.querySelector('.nav-account[open]')
  if (menu && !menu.contains(event?.target)) menu.removeAttribute('open')
}
watch(() => route.fullPath, () => closeAccountMenu())

onMounted(() => {
  document.addEventListener('click', closeAccountMenu)
  loadBranding()
  refreshPwaInstall()
  stopPwa = subscribePwaInstall(refreshPwaInstall)
  stopLivePoll = startGuardedInterval(pollLiveStatus, 10000)
  stopSlowPoll = startGuardedInterval(pollSlowStatus, 45000)
})

onUnmounted(() => {
  document.removeEventListener('click', closeAccountMenu)
  if (stopPwa) stopPwa()
  if (stopLivePoll) stopLivePoll()
  if (stopSlowPoll) stopSlowPoll()
})
</script>

<template>
  <div class="app-container">
    <WallpaperLayer />
    <header class="top-nav">
      <div class="nav-brand glass-pill">
        <div class="logo-orb">
          <img
            :src="brandHeaderUrl"
            :alt="brandTitle"
            class="brand-logo"
          />
        </div>
        <div class="brand-titles">
          <h1 class="brand-name" :title="brandTitle">{{ brandTitle }}</h1>
        </div>
      </div>

      <nav v-if="authStatus.authenticated && wizardCompleted" class="nav-tabs glass-pill" aria-label="Pages">
        <RouterLink
          :to="{ name: 'home', query: route.name === 'home' ? route.query : {} }"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'home' }"
          title="Home"
        >
          Home
        </RouterLink>
        <RouterLink
          :to="{ name: 'catalog', query: route.name === 'catalog' ? route.query : {} }"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'catalog' }"
          title="Install and manage applications"
        >
          Catalog
        </RouterLink>
        <RouterLink
          :to="route.name === 'settings'
            ? { name: 'settings', params: { section: route.params.section } }
            : { name: 'settings', params: { section: 'account' } }"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'settings' }"
          title="Appliance settings"
        >
          Settings
        </RouterLink>
        <template v-if="currentView === 'home'">
          <span class="nav-tabs-divider" aria-hidden="true"></span>
          <button
            type="button"
            class="metric-pill metric-pill-action nav-edit-btn"
            :class="{ 'is-active': homeEditing }"
            :aria-pressed="homeEditing"
            :title="homeEditing ? 'Done arranging Home' : 'Edit the Home layout'"
            :aria-label="homeEditing ? 'Done arranging Home' : 'Edit the Home layout'"
            @click="homeEditing = !homeEditing"
          >
            <svg v-if="!homeEditing" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="8" height="9" rx="2" /><rect x="13" y="3" width="8" height="5" rx="2" /><rect x="13" y="12" width="8" height="9" rx="2" /><rect x="3" y="16" width="8" height="5" rx="2" /></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          </button>
        </template>
      </nav>

      <div class="nav-metrics" :class="{ 'nav-metrics-authenticated': authStatus.authenticated }">
        <RouterLink
          v-if="showUpdatesPill"
          :to="{ name: 'settings', params: { section: 'updates' } }"
          class="metric-pill is-updates"
          title="Open Settings → Updates"
        >
          <span class="metric-val font-mono">{{ updatesPillLabel }}</span>
        </RouterLink>
        <button
          v-if="authStatus.authenticated && currentView === 'catalog'"
          @click="runAutomatedWiring"
          class="metric-pill metric-pill-action"
          :disabled="wiringRunning"
          title="Wire installed apps to each other"
        >
          <span v-if="wiringRunning" class="spinner spinner-sm"></span>
          <span v-else>⚡ <span class="hide-compact">Auto-Wire</span></span>
        </button>
      </div>

      <details v-if="authStatus.authenticated" class="nav-account" @keydown.esc="$event.currentTarget.removeAttribute('open')">
        <summary class="glass-pill" :aria-label="`${authStatus.username} account. ${wizardCompleted ? statusChips.map(chip => chip.title).join('. ') : ''}`">
          <span v-if="wizardCompleted && statusChips.length" class="nav-account-status">
            <span v-for="chip in statusChips" :key="chip.key" class="status-chip" :data-tone="chip.tone" :title="chip.title">
              <span class="status-dot" aria-hidden="true"></span>
              <span>{{ chip.label }}</span>
            </span>
          </span>
          <span class="user-avatar" aria-hidden="true">
            <img v-if="authStatus.avatar_url" :src="authStatus.avatar_url" alt="" class="user-avatar-img" />
            <template v-else>{{ authStatus.username?.[0]?.toUpperCase() || 'A' }}</template>
          </span>
          <svg class="nav-account-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </summary>
        <div class="nav-account-menu glass-pill">
          <RouterLink
            v-if="wizardCompleted"
            :to="{ name: 'settings', params: { section: 'account' } }"
            class="metric-pill metric-pill-action"
            @click="$event.currentTarget.closest('details').removeAttribute('open')"
          >{{ authStatus.username }} · Account</RouterLink>
          <template v-if="wizardCompleted">
            <RouterLink
              v-for="chip in statusChips"
              :key="chip.key"
              :to="{ name: 'settings', params: { section: 'network' } }"
              class="metric-pill status-chip"
              :data-tone="chip.tone"
              :title="chip.title"
              :aria-label="chip.title"
              @click="$event.currentTarget.closest('details').removeAttribute('open')"
            >
              <span class="status-dot" aria-hidden="true"></span>
              <span>{{ chip.label }}</span>
            </RouterLink>
          </template>
          <div v-if="transcodingAvailable" class="metric-pill nav-account-info" title="Hardware transcoding available">
            <span class="status-dot" aria-hidden="true"></span>
            <span>GPU · hardware transcoding</span>
          </div>
          <RouterLink
            v-if="showUpdatesPill"
            :to="{ name: 'settings', params: { section: 'updates' } }"
            class="metric-pill is-updates nav-account-phone-only"
            @click="$event.currentTarget.closest('details').removeAttribute('open')"
          >{{ updatesPillLabel }}</RouterLink>
          <button
            v-if="currentView === 'catalog'"
            @click="runAutomatedWiring"
            class="metric-pill metric-pill-action nav-account-phone-only"
            :disabled="wiringRunning"
            title="Wire installed apps to each other"
          >
            <span v-if="wiringRunning" class="spinner spinner-sm"></span>
            <span v-else>⚡</span>
            Auto-Wire
          </button>
          <button v-if="showPwaInstall" type="button" class="metric-pill metric-pill-action" @click="installPwa">Install app</button>
          <button type="button" @click="handleLogout" class="metric-pill metric-pill-action">Log out</button>
        </div>
      </details>
    </header>

    <main class="content-wrapper">
      <AuthScreens
        v-if="!authStatus.authenticated"
        @status="onAuthStatus"
        @session="onAuthSession"
      />
      <section v-else-if="!wizardStatusLoaded" class="auth-card-wrapper animate-fade">
        <AppLoader label="Loading setup" />
      </section>
      <WizardPanel
        v-else-if="!wizardCompleted"
        @done="onWizardDone"
      />
      <div v-else class="dashboard-layout animate-fade">
        <SettingsPanel
          v-if="currentView === 'settings'"
          :system-info="systemInfo"
          :host-arch="hostArch"
          @session="onSettingsSession"
          @updates="fetchUpdateStatus"
          @vpn="onSettingsVpn"
        />
        <HomepagePanel
          v-else-if="currentView === 'home'"
          :system-info="systemInfo"
          :username="authStatus.username || ''"
          @manage="openCatalog"
        />
        <CatalogView
          v-else
          :catalog-apps="catalogApps"
          :applications="applications"
          :system-info="systemInfo"
          :update-status="updateStatus"
          :backup-status="backupStatus"
          :is-loading-data="isLoadingData"
          :refresh-dashboard="refreshDashboard"
          :fetch-applications="fetchApplications"
          :show-health-modal="showHealthModal"
          @open-logs="logApp = $event"
          @open-settings="settingsService = $event"
          @open-health="showHealthModal = true"
        />
      </div>
    </main>

    <LogsModal v-if="logApp" :app="logApp" @close="logApp = null" />
    <HealthModal
      v-if="showHealthModal"
      :system-info="systemInfo"
      :catalog-apps="catalogApps"
      @close="showHealthModal = false"
      @system-info="onHealthSystem"
    />
    <AppSettingsModal
      v-if="settingsService"
      :service="settingsService"
      :system-info="systemInfo"
      @close="settingsService = null"
      @saved="refreshDashboard"
    />

    <div class="toast-container">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast-pill animate-slide-in"
        :class="'toast-' + t.type"
      >
        <span>{{ t.message }}</span>
      </div>
    </div>
  </div>
</template>
