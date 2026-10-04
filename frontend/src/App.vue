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
const wiringRunning = ref(false)
const currentTime = ref(new Date().toLocaleTimeString())
const vpnLive = ref({})
const cloudflareLive = ref({})
const showHealthModal = ref(false)
const logApp = ref(null)
const settingsService = ref(null)

let stopClock = null
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
const showVpnPill = computed(
  () => authStatus.value.authenticated && wizardCompleted.value && !!vpnLive.value.enabled,
)
const vpnTunnelUp = computed(() => !!vpnLive.value.tunnel_up)
const showCloudflarePill = computed(
  () => authStatus.value.authenticated && wizardCompleted.value && !!cloudflareLive.value.enabled,
)
const cloudflareUp = computed(() => !!cloudflareLive.value.connected)
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
  authStatus.value = data
  applySession(data)
}

async function onAuthSession(data) {
  authStatus.value = {
    setup_required: false,
    authenticated: true,
    username: data.username,
    avatar_url: data.avatar_url || null,
  }
  applySession(data)
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

async function onWizardDone() {
  wizardCompleted.value = true
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
  if (currentView.value === 'catalog') fetchApplications()
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

onMounted(() => {
  loadBranding()
  refreshPwaInstall()
  stopPwa = subscribePwaInstall(refreshPwaInstall)
  stopClock = startGuardedInterval(() => {
    currentTime.value = new Date().toLocaleTimeString()
  }, 1000)
  stopLivePoll = startGuardedInterval(pollLiveStatus, 10000)
  stopSlowPoll = startGuardedInterval(pollSlowStatus, 45000)
})

onUnmounted(() => {
  if (stopPwa) stopPwa()
  if (stopClock) stopClock()
  if (stopLivePoll) stopLivePoll()
  if (stopSlowPoll) stopSlowPoll()
})
</script>

<template>
  <div class="app-container">
    <header class="top-nav">
      <div class="nav-brand">
        <div class="logo-orb">
          <img
            :src="brandHeaderUrl"
            :alt="brandTitle"
            class="brand-logo"
          />
        </div>
        <div class="brand-titles">
          <h1 class="brand-name">{{ brandTitle }}</h1>
        </div>
      </div>

      <div class="nav-metrics">
        <div class="metric-pill hide-compact" :title="currentTime">
          <span class="pulse-dot"></span>
          <span class="metric-val font-mono">{{ currentTime }}</span>
        </div>
        <div
          v-if="showVpnPill"
          class="metric-pill"
          :class="vpnTunnelUp ? 'is-vpn-up' : 'is-vpn-down'"
          :title="vpnTunnelUp ? 'VPN tunnel up' : 'VPN tunnel down'"
        >
          <span class="pulse-dot"></span>
          <span class="metric-val font-mono">VPN</span>
        </div>
        <RouterLink
          v-if="showCloudflarePill"
          :to="{ name: 'settings', params: { section: 'network' } }"
          class="metric-pill"
          :class="cloudflareUp ? 'is-cf-up' : 'is-cf-down'"
          :title="cloudflareUp
            ? (cloudflareLive.token_saved || cloudflareLive.token_present
              ? 'Cloudflare Tunnel up · token saved'
              : 'Cloudflare Tunnel up')
            : (cloudflareLive.summary || 'Cloudflare Tunnel down — open Settings → Network')"
        >
          <span class="pulse-dot"></span>
          <span class="metric-val font-mono">CF</span>
        </RouterLink>
        <RouterLink
          v-if="showUpdatesPill"
          :to="{ name: 'settings', params: { section: 'updates' } }"
          class="metric-pill is-updates"
          title="Open Settings → Updates"
        >
          <span class="pulse-dot"></span>
          <span class="metric-val font-mono">{{ updatesPillLabel }}</span>
        </RouterLink>
        <div v-if="transcodingAvailable" class="metric-pill hide-narrow" title="Hardware transcoding available">
          <span class="metric-label">GPU</span>
          <span class="metric-val font-mono">HW</span>
        </div>
        <RouterLink
          v-if="authStatus.authenticated && wizardCompleted"
          :to="{ name: 'home', query: route.name === 'home' ? route.query : {} }"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'home' }"
          title="Home"
        >
          Home
        </RouterLink>
        <RouterLink
          v-if="authStatus.authenticated && wizardCompleted"
          :to="{ name: 'catalog', query: route.name === 'catalog' ? route.query : {} }"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'catalog' }"
          title="Install and manage applications"
        >
          Catalog
        </RouterLink>
        <RouterLink
          v-if="authStatus.authenticated && wizardCompleted"
          :to="route.name === 'settings'
            ? { name: 'settings', params: { section: route.params.section } }
            : { name: 'settings', params: { section: 'account' } }"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'settings' }"
          title="Appliance settings"
        >
          Settings
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
        <button
          v-if="showPwaInstall"
          type="button"
          class="metric-pill metric-pill-action"
          title="Install this manager as an app"
          @click="installPwa"
        >
          Install
        </button>
        <div v-if="authStatus.authenticated" class="user-pill">
          <span class="user-avatar" aria-hidden="true">
            <img
              v-if="authStatus.avatar_url"
              :src="authStatus.avatar_url"
              alt=""
              class="user-avatar-img"
            />
            <template v-else>{{ authStatus.username?.[0]?.toUpperCase() || 'A' }}</template>
          </span>
          <span class="user-name">{{ authStatus.username }}</span>
          <button @click="handleLogout" class="btn-logout" title="Log out">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
          </button>
        </div>
      </div>
    </header>

    <main class="content-wrapper">
      <AuthScreens
        v-if="!authStatus.authenticated"
        @status="onAuthStatus"
        @session="onAuthSession"
      />
      <section v-else-if="!wizardStatusLoaded" class="auth-card-wrapper animate-fade">
        <p class="wizard-muted" style="text-align:center;">Loading setup…</p>
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
