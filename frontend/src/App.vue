<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { appIconSrc } from './appIcons.js'
import WizardPanel from './WizardPanel.vue'
import SettingsPanel from './SettingsPanel.vue'
import HomepagePanel from './HomepagePanel.vue'

// --- State Variables ---
const authStatus = ref({
  setup_required: false,
  authenticated: false,
  username: null
})

const CSRF_COOKIE = 'amm_csrf'
const csrfToken = ref(sessionStorage.getItem('amm_csrf') || '')
const authToken = ref(localStorage.getItem('amm_token') || '')

const authForm = ref({
  username: 'admin',
  email: '',
  password: '',
  confirmPassword: ''
})
const authError = ref('')
const authLoading = ref(false)

// Dashboard data
const catalogApps = ref([])
const updateStatus = ref({ available: [], last_check_at: null, last_apply_at: null, paused: false })
const catalogCategoriesSelected = ref([])
const catalogStatusFilters = ref([])
const catalogSort = ref('popularity')
const catalogSearch = ref('')
const applications = ref([])
const systemInfo = ref(null)
const hostArch = ref('')
const isLoadingData = ref(false)
const actionLoading = ref({}) // map appName -> action ("start", "stop", etc.)
const iconFailed = ref({})
const wizardCompleted = ref(true)
const wizardStatusLoaded = ref(false)
const currentView = ref('home')

// Toast messages
const toasts = ref([])
let toastId = 0
function showToast(message, type = 'info') {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 4500)
}

// Logs Modal
const showLogModal = ref(false)
const activeLogApp = ref(null)
const openCardMenu = ref('')
const settingsApp = ref(null)
const settingsForm = ref({
  port: 0,
  autostart: true,
  vuetorrent: false,
  jellyfinApiKey: '',
  recyclarrYaml: '',
  recyclarrOriginalYaml: '',
  recyclarrNaming: 'plex',
  recyclarrPrefs: {}
})
const settingsMeta = ref(null)
const recyclarrMeta = ref(null)
const settingsLoading = ref(false)
const settingsError = ref('')
const logLines = ref([])
const logLoading = ref(false)
const autoScrollLogs = ref(true)
const logFilter = ref('')
const logOnlyErrors = ref(false)
const logContainerRef = ref(null)
let logPollInterval = null
let logWs = null

const filteredLogLines = computed(() => {
  let lines = logLines.value
  if (logOnlyErrors.value) {
    lines = lines.filter(l => /error|fatal|fail|exception/i.test(l))
  }
  if (logFilter.value) {
    const q = logFilter.value.toLowerCase()
    lines = lines.filter(l => l.toLowerCase().includes(q))
  }
  return lines
})

const wiringRunning = ref(false)

// Live Clock
const currentTime = ref(new Date().toLocaleTimeString())
let clockInterval = null
let pollInterval = null

function readCookie(name) {
  const prefix = `${name}=`
  const parts = document.cookie.split(';')
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }
  return ''
}

function currentCsrfToken() {
  return csrfToken.value || readCookie(CSRF_COOKIE) || sessionStorage.getItem('amm_csrf') || ''
}

function storeCsrf(token) {
  csrfToken.value = token || ''
  if (token) {
    sessionStorage.setItem('amm_csrf', token)
  } else {
    sessionStorage.removeItem('amm_csrf')
  }
}

// --- API Helper ---
async function apiRequest(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }

  const csrf = currentCsrfToken()
  if (csrf) {
    headers['X-CSRF-Token'] = csrf
  }
  if (authToken.value) {
    headers['Authorization'] = `Bearer ${authToken.value}`
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
    credentials: 'include'
  })

  if (response.status === 401 && authStatus.value.authenticated) {
    authStatus.value.authenticated = false
    authToken.value = ''
    localStorage.removeItem('amm_token')
    showToast('Session expired. Please log in again.', 'warning')
  }

  return response
}

// --- Auth Functions ---
async function checkAuthStatus() {
  try {
    const res = await apiRequest('/api/auth/status')
    if (res.ok) {
      const data = await res.json()
      authStatus.value = data
      if (data.csrf_token) {
        storeCsrf(data.csrf_token)
      } else if (!csrfToken.value) {
        const fromCookie = readCookie(CSRF_COOKIE)
        if (fromCookie) storeCsrf(fromCookie)
      }
      if (data.authenticated) {
        await Promise.all([refreshDashboard(), fetchWizardStatus()])
      }
    }
  } catch (err) {
    console.error('Failed to check auth status:', err)
  }
}

async function handleSetup() {
  authError.value = ''
  if (authForm.value.password.length < 8) {
    authError.value = 'Password must be at least 8 characters long.'
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(authForm.value.email.trim())) {
    authError.value = 'A valid email address is required.'
    return
  }
  if (authForm.value.password !== authForm.value.confirmPassword) {
    authError.value = 'Passwords do not match.'
    return
  }

  authLoading.value = true
  try {
    const res = await fetch('/api/auth/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        username: authForm.value.username,
        email: authForm.value.email.trim(),
        password: authForm.value.password
      })
    })

    const data = await res.json()
    if (!res.ok) {
      authError.value = data.detail || 'Setup failed.'
      return
    }

    if (data.access_token) {
      authToken.value = data.access_token
      localStorage.setItem('amm_token', data.access_token)
    }
    if (data.csrf_token) {
      storeCsrf(data.csrf_token)
    }

    authStatus.value = {
      setup_required: false,
      authenticated: true,
      username: data.username
    }
    showToast('Admin setup completed successfully! Welcome to AIO Media Manager.', 'success')
    authForm.value.password = ''
    authForm.value.confirmPassword = ''
    await Promise.all([refreshDashboard(), fetchWizardStatus()])
  } catch (err) {
    authError.value = 'Network error during setup: ' + err.message
  } finally {
    authLoading.value = false
  }
}

async function handleLogin() {
  authError.value = ''
  authLoading.value = true
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        username: authForm.value.username,
        password: authForm.value.password
      })
    })

    const data = await res.json()
    if (!res.ok) {
      authError.value = data.detail || 'Invalid username or password.'
      return
    }

    if (data.access_token) {
      authToken.value = data.access_token
      localStorage.setItem('amm_token', data.access_token)
    }
    if (data.csrf_token) {
      storeCsrf(data.csrf_token)
    }

    authStatus.value = {
      setup_required: false,
      authenticated: true,
      username: data.username
    }
    showToast(`Welcome back, ${data.username}!`, 'success')
    authForm.value.password = ''
    await Promise.all([refreshDashboard(), fetchWizardStatus()])
  } catch (err) {
    authError.value = 'Login error: ' + err.message
  } finally {
    authLoading.value = false
  }
}

async function handleLogout() {
  try {
    await apiRequest('/api/auth/logout', { method: 'POST' })
  } catch (_) {}
  authToken.value = ''
  storeCsrf('')
  localStorage.removeItem('amm_token')
  authStatus.value.authenticated = false
  authStatus.value.username = null
  currentView.value = 'home'
  showToast('Logged out successfully.', 'info')
}

// --- Data Fetching ---
async function fetchCatalog() {
  try {
    const res = await apiRequest('/api/catalog')
    if (res.ok) {
      const data = await res.json()
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
      const data = await res.json()
      applications.value = data.applications || []
    }
  } catch (err) {
    console.error('Applications fetch error:', err)
  }
}

async function fetchSystemInfo() {
  try {
    const res = await apiRequest('/api/system/info')
    if (res.ok) {
      systemInfo.value = await res.json()
      recordHealthSample()
    }
  } catch (err) {
    console.error('System info fetch error:', err)
  }
}

async function fetchWizardStatus() {
  try {
    const res = await apiRequest('/api/wizard/status')
    if (res.ok) {
      const data = await res.json()
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
    currentView.value = 'home'
    showToast('Setup wizard finished. Catalog installs may continue in the background.', 'success')
  await refreshDashboard()
}

function onSettingsSession(data) {
  if (data?.access_token) {
    authToken.value = data.access_token
    localStorage.setItem('amm_token', data.access_token)
  }
  if (data?.csrf_token) storeCsrf(data.csrf_token)
  if (data?.username) authStatus.value.username = data.username
}

async function fetchUpdateStatus() {
  try {
    const res = await apiRequest('/api/updates/status')
    if (res.ok) updateStatus.value = await res.json()
  } catch (err) {
    console.error('Update status error:', err)
  }
}

function formatUpdateWhen(ts) {
  if (!ts) return 'never'
  const ms = ts > 1e12 ? ts : ts * 1000
  return new Date(ms).toLocaleString()
}

async function refreshDashboard() {
  isLoadingData.value = true
  await Promise.all([fetchCatalog(), fetchApplications(), fetchSystemInfo(), fetchUpdateStatus()])
  isLoadingData.value = false
}

// --- Combined Services List ---
const combinedServices = computed(() => {
  const appMap = new Map()
  for (const app of applications.value) {
    appMap.set(app.name, app)
  }

  return catalogApps.value.map(cat => {
    const live = appMap.get(cat.name)
    const host = window.location.hostname || 'localhost'
    return {
      name: cat.name,
      displayName: cat.display_name,
      description: cat.description,
      category: cat.category,
      iconSrc: appIconSrc(cat.name),
      tier: cat.tier,
      port: live?.port || cat.port || cat.default_port,
      defaultPort: cat.default_port,
      installed: cat.installed || (live && live.installed) || false,
      installedVersion: cat.installed_version || (live && live.version),
      webUrl: `http://${host}:${live?.port || cat.port || cat.default_port}`,
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
      updateAvailable: !!(updateStatus.value.available || []).find((row) => row.name === cat.name),
      latestVersion: ((updateStatus.value.available || []).find((row) => row.name === cat.name) || {}).latest_version
    }
  })
})

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
    catalogCategoriesSelected.value = []
    return
  }
  const current = [...catalogCategoriesSelected.value]
  const idx = current.indexOf(category)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(category)
  catalogCategoriesSelected.value = current
}

function removeCategoryFilter(category) {
  catalogCategoriesSelected.value = catalogCategoriesSelected.value.filter(c => c !== category)
}

function toggleStatusFilter(key) {
  const current = [...catalogStatusFilters.value]
  const idx = current.indexOf(key)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(key)
  catalogStatusFilters.value = current
}

function removeStatusFilter(key) {
  catalogStatusFilters.value = catalogStatusFilters.value.filter(k => k !== key)
}

function scrollToCatalog() {
  document.getElementById('catalog-toolbar')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
  const query = catalogSearch.value.trim().toLowerCase()
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

const cpuPercent = computed(() => systemInfo.value?.metrics?.cpu_percent)
const memPercent = computed(() => systemInfo.value?.metrics?.memory?.percent)
const diskPercent = computed(() => systemInfo.value?.metrics?.disk?.percent)
const showHealthModal = ref(false)
const healthHistory = ref([])
const HEALTH_MAX_SAMPLES = 60
let healthPoll = null

function formatBytes(n) {
  const v = Number(n) || 0
  if (v < 1024) return `${Math.round(v)} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let x = v
  let i = -1
  do {
    x /= 1024
    i += 1
  } while (x >= 1024 && i < units.length - 1)
  return `${x >= 10 ? x.toFixed(0) : x.toFixed(1)} ${units[i]}`
}

function formatCpu(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toFixed(1)}%`
}

function formatMemShare(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return `${n < 10 ? n.toFixed(1) : Math.round(n)}%`
}

function recordHealthSample() {
  const metrics = systemInfo.value?.metrics
  if (!metrics) return
  healthHistory.value = [
    ...healthHistory.value,
    {
      t: Date.now(),
      cpu: Number(metrics.cpu_percent) || 0,
      mem: Number(metrics.memory?.percent) || 0,
      disk: Number(metrics.disk?.percent) || 0
    }
  ].slice(-HEALTH_MAX_SAMPLES)
}

function chartPath(values) {
  const w = 320
  const h = 88
  const pad = 6
  const series = values.length ? values : [0]
  const pts = series.length === 1 ? [series[0], series[0]] : series
  const n = Math.max(pts.length - 1, 1)
  const coords = pts.map((v, i) => {
    const x = pad + (i / n) * (w - pad * 2)
    const y = pad + (1 - Math.min(100, Math.max(0, Number(v) || 0)) / 100) * (h - pad * 2)
    return [x, y]
  })
  const line = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const last = coords[coords.length - 1]
  const first = coords[0]
  const fill = `${line} L${last[0].toFixed(1)} ${(h - pad).toFixed(1)} L${first[0].toFixed(1)} ${(h - pad).toFixed(1)} Z`
  return { line, fill, w, h }
}

const cpuChart = computed(() => chartPath(healthHistory.value.map(s => s.cpu)))
const memChart = computed(() => chartPath(healthHistory.value.map(s => s.mem)))
const diskChart = computed(() => chartPath(healthHistory.value.map(s => s.disk)))

const healthProcesses = computed(() => {
  const rows = systemInfo.value?.metrics?.processes
  if (!Array.isArray(rows)) return []
  const labels = new Map(combinedServices.value.map((s) => [s.name, s.displayName]))
  return rows.map((row) => ({
    ...row,
    displayName: labels.get(row.name) || row.name
  }))
})

const healthTone = computed(() => {
  const cpu = Number(cpuPercent.value) || 0
  const mem = Number(memPercent.value) || 0
  const disk = Number(diskPercent.value) || 0
  if (cpu >= 90 || mem >= 90 || disk >= 90) return 'warn'
  return 'ok'
})

function openHealthModal() {
  showHealthModal.value = true
  fetchSystemInfo()
  if (healthPoll) clearInterval(healthPoll)
  healthPoll = setInterval(() => {
    fetchSystemInfo()
  }, 2000)
}

function closeHealthModal() {
  showHealthModal.value = false
  if (healthPoll) {
    clearInterval(healthPoll)
    healthPoll = null
  }
}

const vpnUnprotected = computed(() => {
  const vpn = systemInfo.value?.vpn
  if (!vpn) return false
  if (Array.isArray(vpn.unprotected_apps) && vpn.unprotected_apps.length) return true
  return Boolean(vpn.qbittorrent_unprotected || vpn.prowlarr_unprotected || vpn.flaresolverr_unprotected)
})
const cloudflareTunnelIssue = computed(() => {
  const tunnel = systemInfo.value?.cloudflare_tunnel
  return Boolean(tunnel?.enabled && !tunnel?.connected)
})
const transcodingAvailable = computed(() => systemInfo.value?.transcoding?.available)
const hardlinksSupported = computed(() => systemInfo.value?.storage?.download_dir?.hardlinks_supported !== false)

// --- App Control Actions ---
async function startApp(name) {
  actionLoading.value[name] = 'start'
  try {
    const res = await apiRequest(`/api/applications/${name}/start`, { method: 'POST' })
    const data = await res.json()
    if (res.ok) {
      showToast(`Started ${name}`, 'success')
      await refreshDashboard()
    } else {
      showToast(data.detail || `Failed to start ${name}`, 'error')
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
    const data = await res.json()
    if (res.ok) {
      showToast(`Stopped ${name}`, 'info')
      await refreshDashboard()
    } else {
      showToast(data.detail || `Failed to stop ${name}`, 'error')
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
    const data = await res.json()
    if (res.ok) {
      showToast(`Restarted ${name}`, 'success')
      await refreshDashboard()
    } else {
      showToast(data.detail || `Failed to restart ${name}`, 'error')
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
    const data = await res.json()
    if (res.ok && data.status !== 'rolled_back') {
      showToast(`Updated ${name} to ${data.version || 'latest'}`, 'success')
      await refreshDashboard()
    } else {
      showToast(data.error || data.detail || `Update failed for ${name}`, 'error')
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
    const data = await res.json()
    if (res.ok) {
      showToast(`Uninstalled ${name}`, 'info')
      await refreshDashboard()
    } else {
      showToast(data.detail || `Failed to uninstall ${name}`, 'error')
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
    const data = await res.json()
    if (res.ok) {
      showToast(`Installation initiated for ${displayName || name}...`, 'success')
      setTimeout(refreshDashboard, 3000)
    } else {
      showToast(data.detail || `Failed to install ${name}`, 'error')
    }
  } catch (err) {
    showToast(`Error installing ${name}: ${err.message}`, 'error')
  } finally {
    delete actionLoading.value[name]
  }
}

// --- Log Modal Functions ---
async function openLogs(app) {
  activeLogApp.value = app
  showLogModal.value = true
  logLines.value = []
  logFilter.value = ''
  logOnlyErrors.value = false
  await fetchLogs(app.name)
  startLiveWebSocket(app.name)
}

function closeLogs() {
  showLogModal.value = false
  activeLogApp.value = null
  if (logWs) {
    logWs.close()
    logWs = null
  }
  if (logPollInterval) {
    clearInterval(logPollInterval)
    logPollInterval = null
  }
}

function startLiveWebSocket(name) {
  if (logWs) {
    logWs.close()
    logWs = null
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = authToken.value ? `?token=${encodeURIComponent(authToken.value)}` : ''
  const wsUrl = `${protocol}//${window.location.host}/api/logs/ws/${encodeURIComponent(name)}${token}`
  try {
    logWs = new WebSocket(wsUrl)
    logWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data && data.line) {
          logLines.value.push(data.line)
          if (autoScrollLogs.value) {
            nextTick(() => {
              if (logContainerRef.value) {
                logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
              }
            })
          }
        }
      } catch (e) {}
    }
    logWs.onerror = () => {
      startLogPolling(name)
    }
  } catch (e) {
    startLogPolling(name)
  }
}

function downloadLogs(name) {
  if (!name) return
  window.open(`/api/logs/download?app=${encodeURIComponent(name)}`, '_blank')
}

async function resetCrashLoop(name) {
  try {
    const res = await apiRequest(`/api/applications/${name}/reset-crash-loop`, { method: 'POST' })
    if (res.ok) {
      showToast(`Crash loop reset for ${name}`, 'success')
      await refreshDashboard()
    }
  } catch (err) {
    showToast(`Failed to reset crash loop: ${err}`, 'error')
  }
}

async function runAutomatedWiring() {
  wiringRunning.value = true
  try {
    const res = await apiRequest('/api/integrations/run', { method: 'POST' })
    if (res.ok) {
      const data = await res.json()
      showToast(`Auto-wiring completed (${data.steps?.length || 0} tasks executed)`, 'success')
      await refreshDashboard()
    } else {
      showToast('Automated wiring failed', 'error')
    }
  } catch (err) {
    showToast(`Wiring error: ${err}`, 'error')
  } finally {
    wiringRunning.value = false
  }
}

async function fetchLogs(name) {
  logLoading.value = true
  try {
    const res = await apiRequest(`/api/applications/${name}/logs`)
    if (res.ok) {
      const data = await res.json()
      logLines.value = data.lines || []
      if (autoScrollLogs.value) {
        await nextTick()
        if (logContainerRef.value) {
          logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
        }
      }
    }
  } catch (err) {
    console.error('Failed to fetch logs:', err)
  } finally {
    logLoading.value = false
  }
}

function startLogPolling(name) {
  if (logPollInterval) clearInterval(logPollInterval)
  logPollInterval = setInterval(() => {
    fetchLogs(name)
  }, 2500)
}

function formatUptime(seconds) {
  if (!seconds || seconds < 0) return '0s'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
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

async function openAppSettings(service) {
  closeCardMenu()
  settingsError.value = ''
  settingsApp.value = service
  settingsLoading.value = true
  try {
    const res = await apiRequest(`/api/applications/${service.name}/settings`)
    const data = await res.json()
    if (!res.ok) {
      settingsError.value = data.detail || 'Could not load settings.'
      settingsMeta.value = null
      settingsForm.value = { port: service.port, autostart: service.autostart }
      return
    }
    settingsMeta.value = data
    settingsForm.value = {
      port: data.port,
      autostart: data.autostart,
      vuetorrent: !!data.vuetorrent,
      jellyfinApiKey: '',
      recyclarrYaml: '',
      recyclarrOriginalYaml: '',
      recyclarrNaming: 'plex',
      recyclarrPrefs: {}
    }
    recyclarrMeta.value = null
    if (service.name === 'recyclarr') {
      const rec = await apiRequest('/api/recyclarr')
      const recData = await rec.json()
      if (rec.ok) {
        recyclarrMeta.value = recData
        settingsForm.value.recyclarrYaml = recData.yaml || ''
        settingsForm.value.recyclarrOriginalYaml = recData.yaml || ''
        settingsForm.value.recyclarrNaming = recData.prefs?.naming || 'plex'
        settingsForm.value.recyclarrPrefs = { ...(recData.prefs || {}) }
      }
    }
  } catch (err) {
    settingsError.value = err.message || 'Could not load settings.'
  } finally {
    settingsLoading.value = false
  }
}

function closeAppSettings() {
  settingsApp.value = null
  settingsMeta.value = null
  recyclarrMeta.value = null
  settingsError.value = ''
}

async function saveAppSettings() {
  if (!settingsApp.value) return
  settingsLoading.value = true
  settingsError.value = ''
  try {
    if (settingsApp.value.name === 'recyclarr') {
      if (!recyclarrMeta.value) {
        settingsError.value = 'Could not load Recyclarr config.'
        return
      }
      const yamlChanged = settingsForm.value.recyclarrYaml !== settingsForm.value.recyclarrOriginalYaml
      if (yamlChanged) {
        const rec = await apiRequest('/api/recyclarr', {
          method: 'PUT',
          body: JSON.stringify({ yaml: settingsForm.value.recyclarrYaml })
        })
        const recData = await rec.json()
        if (!rec.ok) {
          settingsError.value = recData.detail || 'Could not save Recyclarr YAML.'
          return
        }
      } else {
        const rec = await apiRequest('/api/recyclarr', {
          method: 'PATCH',
          body: JSON.stringify({
            sonarr_web_1080p: !!settingsForm.value.recyclarrPrefs.sonarr_web_1080p,
            sonarr_web_2160p: !!settingsForm.value.recyclarrPrefs.sonarr_web_2160p,
            sonarr_anime: !!settingsForm.value.recyclarrPrefs.sonarr_anime,
            radarr_hd: !!settingsForm.value.recyclarrPrefs.radarr_hd,
            radarr_uhd: !!settingsForm.value.recyclarrPrefs.radarr_uhd,
            naming: settingsForm.value.recyclarrNaming
          })
        })
        const recData = await rec.json()
        if (!rec.ok) {
          settingsError.value = recData.detail || 'Could not save Recyclarr profiles.'
          return
        }
      }
      showToast('Saved Recyclarr TRaSH config', 'success')
      closeAppSettings()
      return
    }
    const payload = {
      port: Number(settingsForm.value.port),
      autostart: settingsForm.value.autostart,
      restart: true
    }
    if (settingsApp.value.name === 'qbittorrent') {
      payload.vuetorrent = !!settingsForm.value.vuetorrent
    }
    if (settingsApp.value.name === 'jellyfin' && String(settingsForm.value.jellyfinApiKey || '').trim()) {
      payload.api_key = String(settingsForm.value.jellyfinApiKey).trim()
    }
    const res = await apiRequest(`/api/applications/${settingsApp.value.name}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
    const data = await res.json()
    if (!res.ok) {
      settingsError.value = data.detail || 'Could not save settings.'
      return
    }
    showToast(
      data.restarted
        ? `Saved ${data.display_name} and restarted on port ${data.port}`
        : `Saved ${data.display_name} settings`,
      'success'
    )
    closeAppSettings()
    await refreshDashboard()
  } catch (err) {
    settingsError.value = err.message || 'Could not save settings.'
  } finally {
    settingsLoading.value = false
  }
}

function onDocumentClick() {
  closeCardMenu()
}

async function resetRecyclarrDefaults() {
  settingsLoading.value = true
  settingsError.value = ''
  try {
    const rec = await apiRequest('/api/recyclarr/reset', { method: 'POST' })
    const recData = await rec.json()
    if (!rec.ok) {
      settingsError.value = recData.detail || 'Could not reset Recyclarr.'
      return
    }
    recyclarrMeta.value = recData
    settingsForm.value.recyclarrYaml = recData.yaml || ''
    settingsForm.value.recyclarrOriginalYaml = recData.yaml || ''
    settingsForm.value.recyclarrNaming = recData.prefs?.naming || 'plex'
    settingsForm.value.recyclarrPrefs = { ...(recData.prefs || {}) }
    showToast('Restored TRaSH Recyclarr defaults', 'success')
  } catch (err) {
    settingsError.value = err.message || 'Could not reset Recyclarr.'
  } finally {
    settingsLoading.value = false
  }
}

async function syncRecyclarr() {
  closeCardMenu()
  actionLoading.value.recyclarr = 'sync'
  try {
    const res = await apiRequest('/api/recyclarr/sync', { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      showToast(data.detail || 'Recyclarr sync failed', 'error')
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

// Lifecycle
onMounted(async () => {
  clockInterval = setInterval(() => {
    currentTime.value = new Date().toLocaleTimeString()
  }, 1000)
  document.addEventListener('click', onDocumentClick)

  await checkAuthStatus()

  pollInterval = setInterval(() => {
    if (authStatus.value.authenticated) {
      refreshDashboard()
    }
  }, 5000)
})

onUnmounted(() => {
  if (clockInterval) clearInterval(clockInterval)
  if (pollInterval) clearInterval(pollInterval)
  if (logPollInterval) clearInterval(logPollInterval)
  if (healthPoll) clearInterval(healthPoll)
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div class="app-container">
    <!-- Header -->
    <header class="top-nav">
      <div class="nav-brand">
        <div class="logo-orb">
          <img
            src="/logo-aio-media-manager.png"
            alt="AIO Media Server Manager"
            class="brand-logo"
          />
        </div>
        <div class="brand-titles">
          <h1 class="brand-name">AIO Media Manager</h1>
          <span class="brand-tagline">Unified Media Automation Stack</span>
        </div>
      </div>

      <div class="nav-metrics">
        <div class="metric-pill hide-compact" :title="currentTime">
          <span class="pulse-dot"></span>
          <span class="metric-val font-mono">{{ currentTime }}</span>
        </div>
        <div v-if="transcodingAvailable" class="metric-pill hide-narrow">
          <span class="metric-label">GPU</span>
          <span class="metric-val font-mono">HW</span>
        </div>
        <button
          v-if="authStatus.authenticated && wizardCompleted"
          @click="currentView = 'home'"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'home' }"
          title="Household homepage"
        >
          Home
        </button>
        <button
          v-if="authStatus.authenticated && wizardCompleted"
          @click="currentView = 'catalog'"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'catalog' }"
          title="Install and manage applications"
        >
          Catalog
        </button>
        <button
          v-if="authStatus.authenticated && wizardCompleted"
          @click="currentView = 'settings'"
          class="metric-pill metric-pill-action"
          :class="{ 'is-active': currentView === 'settings' }"
          title="Settings and debug share link"
        >
          Settings
        </button>
        <button
          v-if="authStatus.authenticated && currentView === 'catalog'"
          @click="runAutomatedWiring"
          class="metric-pill metric-pill-action"
          :disabled="wiringRunning"
          title="Trigger automatic integration wiring across applications"
        >
          <span v-if="wiringRunning" class="spinner spinner-sm"></span>
          <span v-else>⚡ <span class="hide-compact">Auto-Wire</span></span>
        </button>
        <div v-if="authStatus.authenticated" class="user-pill">
          <span class="user-avatar">{{ authStatus.username?.[0]?.toUpperCase() || 'A' }}</span>
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

    <!-- Main Content Area -->
    <main class="content-wrapper">
      <!-- 1. First-run Admin Setup View -->
      <section v-if="authStatus.setup_required" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-glow"></div>
          <div class="card-header-accent">
            <img
              src="/logo-aio-media-manager.png"
              alt="AIO Media Server Manager"
              class="auth-logo"
            />
            <span class="accent-badge">INITIAL SETUP</span>
            <h2>Create Administrator</h2>
            <p>Welcome! Set up the initial administrator account to protect and manage your server.</p>
          </div>

          <form @submit.prevent="handleSetup" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label class="ui-field">Administrator Username
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                class="ui-input font-mono"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">Email address
              <input
                v-model="authForm.email"
                type="email"
                placeholder="you@example.com"
                required
                autocomplete="email"
                class="ui-input"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">Admin Password (minimum 8 characters)
              <input
                v-model="authForm.password"
                type="password"
                placeholder="••••••••••••"
                required
                class="ui-input"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">Confirm Password
              <input
                v-model="authForm.confirmPassword"
                type="password"
                placeholder="••••••••••••"
                required
                class="ui-input"
              />
              </label>
            </div>

            <button type="submit" :disabled="authLoading" class="ui-btn ui-btn-primary btn-block">
              <span v-if="authLoading" class="spinner"></span>
              <span v-else>Initialize System & Log In</span>
            </button>
          </form>
        </div>
      </section>

      <!-- 2. Login View (when not authenticated & setup done) -->
      <section v-else-if="!authStatus.authenticated" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-glow"></div>
          <div class="card-header-accent">
            <img
              src="/logo-aio-media-manager.png"
              alt="AIO Media Server Manager"
              class="auth-logo"
            />
            <span class="accent-badge">SIGN IN</span>
            <h2>Manager Access</h2>
            <p>Enter your administrator credentials to manage services and server config.</p>
          </div>

          <form @submit.prevent="handleLogin" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label class="ui-field">Username
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                autofocus
                class="ui-input font-mono"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">Password
              <input
                v-model="authForm.password"
                type="password"
                placeholder="••••••••••••"
                required
                class="ui-input"
              />
              </label>
            </div>

            <button type="submit" :disabled="authLoading" class="ui-btn ui-btn-primary btn-block">
              <span v-if="authLoading" class="spinner"></span>
              <span v-else>Authenticate Session</span>
            </button>
          </form>
        </div>
      </section>

      <!-- 3. First-run stack wizard -->
      <section v-else-if="!wizardStatusLoaded" class="auth-card-wrapper animate-fade">
        <p class="wizard-muted" style="text-align:center;color:#94a3b8;">Loading setup…</p>
      </section>
      <WizardPanel
        v-else-if="!wizardCompleted"
        :api-request="apiRequest"
        @done="onWizardDone"
      />

      <!-- 4. Dashboard View -->
      <div v-else class="dashboard-layout animate-fade">
        <SettingsPanel
          v-if="currentView === 'settings'"
          :api-request="apiRequest"
          :system-info="systemInfo"
          :host-arch="hostArch"
          @session="onSettingsSession"
        />
        <HomepagePanel
          v-else-if="currentView === 'home'"
          :api-request="apiRequest"
          @manage="currentView = 'catalog'"
        />
        <template v-else>
        <!-- Metric Cards -->
        <section class="metrics-grid">
          <div
            class="stat-card glass-card stat-card-filter"
            :class="{ 'is-filter-on': catalogStatusFilters.includes('active') }"
            role="button"
            tabindex="0"
            :aria-pressed="catalogStatusFilters.includes('active')"
            title="Show only running services"
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
              <div class="stat-label">ACTIVE SERVICES</div>
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
              <div class="stat-label">INSTALLED PLUGINS</div>
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
              <div class="stat-label">AVAILABLE TO INSTALL</div>
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
            title="Open host health graphs"
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
            <h2 class="section-title">Core Applications Stack</h2>
            <p class="section-subtitle">
              Supervised media pipeline components running bare-metal inside a unified container.
              <span v-if="updateStatus.last_check_at || (updateStatus.available || []).length">
                Last update check {{ formatUpdateWhen(updateStatus.last_check_at) }}
                · last apply {{ formatUpdateWhen(updateStatus.last_apply_at) }}
                · {{ (updateStatus.available || []).length }} waiting
              </span>
            </p>
          </div>
          <button @click="refreshDashboard" class="ui-btn ui-btn-ghost" :disabled="isLoadingData">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': isLoadingData }">
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            <span>Sync Status</span>
          </button>
        </div>

        <div id="catalog-toolbar" class="catalog-toolbar glass-card">
          <div class="catalog-filter-group catalog-search-group">
            <label class="catalog-filter-label" for="catalog-search">Search</label>
            <input
              id="catalog-search"
              v-model="catalogSearch"
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
                    <span class="category-pill">{{ service.category }}</span>
                    <span v-if="service.updateAvailable" class="update-pill">Update available</span>
                  </div>
                  <div v-if="service.daemon" class="service-port font-mono">
                    <span class="port-label">PORT:</span>
                    <a
                      :href="service.webUrl"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="port-link"
                      title="Open WebUI"
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
              <span v-else class="text-dim">Not Installed</span>

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
      </div>
    </main>

    <!-- Log Viewer Modal -->
    <div v-if="showLogModal" class="modal-backdrop" @click.self="closeLogs">
      <div class="log-modal glass-card animate-scale">
        <div class="modal-header">
          <div class="modal-title-group">
            <span class="modal-dot"></span>
            <img
              v-if="activeLogApp?.iconSrc && !iconFailed[activeLogApp.name]"
              :src="activeLogApp.iconSrc"
              :alt="activeLogApp.displayName"
              class="app-icon app-icon-sm"
            />
            <h3>{{ activeLogApp?.displayName }} Process Logs</h3>
            <span class="font-mono text-dim">({{ activeLogApp?.name }})</span>
          </div>

          <div class="modal-controls">
            <input
              type="text"
              v-model="logFilter"
              placeholder="Search logs..."
              class="ui-input font-mono log-search"
            />
            <label class="toggle-control font-mono">
              <input type="checkbox" v-model="logOnlyErrors" />
              <span>Errors Only</span>
            </label>
            <label class="toggle-control font-mono">
              <input type="checkbox" v-model="autoScrollLogs" />
              <span>Auto-Scroll</span>
            </label>
            <button @click="downloadLogs(activeLogApp?.name)" class="btn-icon" title="Download Logs">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </button>
            <button @click="fetchLogs(activeLogApp?.name)" class="btn-icon" title="Refresh">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': logLoading }">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
            </button>
            <button @click="closeLogs" class="btn-icon btn-close" title="Close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>

        <div class="log-console font-mono" ref="logContainerRef">
          <div v-if="filteredLogLines.length === 0" class="log-empty">
            <span v-if="logLoading">Streaming output buffer...</span>
            <span v-else-if="logLines.length > 0">No logs matching filter criteria.</span>
            <span v-else>No output received yet for this process.</span>
          </div>
          <div
            v-for="(line, idx) in filteredLogLines"
            :key="idx"
            class="log-line"
            :style="/error|fatal|fail|exception/i.test(line) ? 'color: #f87171;' : ''"
          >
            <span class="line-num">{{ idx + 1 }}</span>
            <span class="line-content">{{ line }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showHealthModal" class="modal-backdrop" @click.self="closeHealthModal">
      <div class="health-modal glass-card animate-scale" @click.stop>
        <div class="modal-header">
          <div class="modal-title-group">
            <h3>Host health</h3>
            <span class="font-mono" :class="healthTone === 'ok' ? 'text-emerald' : 'text-warn'">
              {{ healthTone === 'ok' ? 'OK' : 'HIGH LOAD' }}
            </span>
          </div>
          <button type="button" class="btn-icon" title="Close" @click="closeHealthModal">×</button>
        </div>
        <div class="health-body">
          <article class="health-chart-card">
            <div class="health-chart-head">
              <span>CPU</span>
              <strong class="font-mono">{{ cpuPercent != null ? Math.round(cpuPercent) + '%' : '—' }}</strong>
            </div>
            <p class="health-chart-meta">{{ systemInfo?.metrics?.cpu_count || '—' }} cores</p>
            <svg class="health-svg" :viewBox="`0 0 ${cpuChart.w} ${cpuChart.h}`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="cpuChart.fill" class="health-fill cpu"></path>
              <path :d="cpuChart.line" class="health-line cpu"></path>
            </svg>
          </article>
          <article class="health-chart-card">
            <div class="health-chart-head">
              <span>RAM</span>
              <strong class="font-mono">{{ memPercent != null ? Math.round(memPercent) + '%' : '—' }}</strong>
            </div>
            <p class="health-chart-meta">
              {{ formatBytes((systemInfo?.metrics?.memory?.total || 0) - (systemInfo?.metrics?.memory?.available || 0)) }}
              used of {{ formatBytes(systemInfo?.metrics?.memory?.total) }}
            </p>
            <svg class="health-svg" :viewBox="`0 0 ${memChart.w} ${memChart.h}`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="memChart.fill" class="health-fill mem"></path>
              <path :d="memChart.line" class="health-line mem"></path>
            </svg>
          </article>
          <article class="health-chart-card">
            <div class="health-chart-head">
              <span>Disk</span>
              <strong class="font-mono">{{ diskPercent != null ? Math.round(diskPercent) + '%' : '—' }}</strong>
            </div>
            <p class="health-chart-meta">
              {{ formatBytes(systemInfo?.metrics?.disk?.used) }}
              used of {{ formatBytes(systemInfo?.metrics?.disk?.total) }}
            </p>
            <svg class="health-svg" :viewBox="`0 0 ${diskChart.w} ${diskChart.h}`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="diskChart.fill" class="health-fill disk"></path>
              <path :d="diskChart.line" class="health-line disk"></path>
            </svg>
          </article>
          <article class="health-apps-card">
            <div class="health-chart-head">
              <span>Applications</span>
              <strong class="font-mono">{{ healthProcesses.length }}</strong>
            </div>
            <p class="health-chart-meta">CPU and RAM include child processes for each supervised app.</p>
            <p v-if="!healthProcesses.length" class="health-chart-meta">No supervised processes yet. Start apps from Catalog.</p>
            <div v-else class="health-apps-table-wrap">
              <table class="health-apps-table">
                <thead>
                  <tr>
                    <th>App</th>
                    <th>CPU</th>
                    <th>RAM</th>
                    <th class="hide-narrow">Share</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in healthProcesses" :key="row.name">
                    <td>
                      <span class="health-app-name">{{ row.displayName }}</span>
                      <span class="health-app-state">{{ row.state || 'stopped' }}</span>
                    </td>
                    <td class="font-mono">{{ formatCpu(row.cpu_percent) }}</td>
                    <td class="font-mono">{{ row.memory_rss != null ? formatBytes(row.memory_rss) : '—' }}</td>
                    <td class="font-mono hide-narrow">{{ formatMemShare(row.memory_percent) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </div>
    </div>

    <div v-if="settingsApp" class="modal-backdrop" @click.self="closeAppSettings">
      <div
        class="settings-modal glass-card animate-scale"
        :class="{ 'settings-modal-wide': settingsApp.name === 'recyclarr' }"
      >
        <div class="modal-header">
          <div class="modal-title-group">
            <h3>{{ settingsApp.displayName }} settings</h3>
            <span class="font-mono text-dim">({{ settingsApp.name }})</span>
          </div>
          <button type="button" class="btn-icon btn-close" title="Close" @click="closeAppSettings">×</button>
        </div>
        <div v-if="settingsError" class="ui-alert ui-alert-error">{{ settingsError }}</div>
        <form class="app-settings-form" @submit.prevent="saveAppSettings">
          <div class="app-settings-body">
          <template v-if="settingsApp.name === 'recyclarr' && recyclarrMeta">
            <p class="settings-hint">
              Official TRaSH Guides profiles via Recyclarr v8. HD is on by default; 4K is opt-in.
              Saving profile checkboxes regenerates YAML. Editing YAML marks the file as custom until you reset.
            </p>
            <p v-if="recyclarrMeta.yaml_path" class="settings-hint font-mono">{{ recyclarrMeta.yaml_path }}</p>
            <label v-for="profile in recyclarrMeta.profiles" :key="profile.id" class="ui-switch-row">
              <div class="ui-switch-copy">
                <strong>{{ profile.label }}</strong>
                <a :href="profile.guide" target="_blank" rel="noopener noreferrer" class="link-btn">Guide</a>
              </div>
              <button
                type="button"
                class="ui-switch"
                role="switch"
                :aria-checked="settingsForm.recyclarrPrefs[profile.id] ? 'true' : 'false'"
                @click="settingsForm.recyclarrPrefs[profile.id] = !settingsForm.recyclarrPrefs[profile.id]"
              >
                <span class="ui-switch-thumb"></span>
              </button>
            </label>
            <label class="ui-field">
              Folder naming
              <select v-model="settingsForm.recyclarrNaming" class="ui-input">
                <option v-for="opt in recyclarrMeta.naming_options" :key="opt.id" :value="opt.id">{{ opt.label }}</option>
              </select>
            </label>
            <label class="ui-field">
              recyclarr.yml
              <textarea v-model="settingsForm.recyclarrYaml" class="ui-input font-mono recyclarr-yaml" spellcheck="false" />
            </label>
            <p v-if="recyclarrMeta.user_edited || settingsForm.recyclarrYaml !== settingsForm.recyclarrOriginalYaml" class="settings-hint">
              Custom YAML is kept as-is on Save. Profile checkboxes apply only when the YAML is unchanged.
            </p>
          </template>
          <template v-else>
          <label class="ui-field">
            Listen port
            <input
              v-model.number="settingsForm.port"
              class="ui-input font-mono"
              type="number"
              min="1024"
              max="65535"
              required
            />
          </label>
          <p v-if="settingsMeta?.default_port" class="settings-hint">
            Default is {{ settingsMeta.default_port }}.
            <button
              type="button"
              class="link-btn"
              @click="settingsForm.port = settingsMeta.default_port"
            >
              Reset
            </button>
          </p>
          <div v-if="settingsMeta?.daemon !== false" class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>Start with the manager</strong>
              <span>When on, this app starts after the appliance boots if it is installed.</span>
            </div>
            <button
              type="button"
              class="ui-switch"
              role="switch"
              :aria-checked="settingsForm.autostart ? 'true' : 'false'"
              @click="settingsForm.autostart = !settingsForm.autostart"
            >
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <div v-if="settingsApp.name === 'jellyfin'" class="ui-field-block">
            <label class="ui-field">
              Jellyfin API key
              <input
                v-model="settingsForm.jellyfinApiKey"
                class="ui-input font-mono"
                type="password"
                autocomplete="off"
                :placeholder="settingsMeta.api_key_configured ? 'Saved — paste a new key to replace' : 'Dashboard → API Keys'"
              />
            </label>
            <p class="settings-hint">
              Optional. Saved keys are used for Recently added. Leave empty to keep the current key.
            </p>
          </div>
          <div v-if="settingsApp.name === 'qbittorrent'" class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>VueTorrent WebUI</strong>
              <span>
                Use
                <a href="https://github.com/VueTorrent/VueTorrent" target="_blank" rel="noopener noreferrer">VueTorrent</a>
                instead of the stock qBittorrent WebUI. *Arr still uses the same WebAPI.
              </span>
              <span v-if="settingsMeta.vuetorrent_version" class="settings-hint">
                Installed {{ settingsMeta.vuetorrent_version }}
              </span>
            </div>
            <button
              type="button"
              class="ui-switch"
              role="switch"
              :aria-checked="settingsForm.vuetorrent ? 'true' : 'false'"
              @click="settingsForm.vuetorrent = !settingsForm.vuetorrent"
            >
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <dl v-if="settingsMeta" class="app-settings-dl font-mono">
            <div><dt>Config</dt><dd>{{ settingsMeta.config_dir }}</dd></div>
            <div><dt>Install</dt><dd>{{ settingsMeta.install_dir }}</dd></div>
            <div><dt>Health</dt><dd>{{ settingsMeta.health_url }}</dd></div>
          </dl>
          <ul v-if="settingsMeta?.notes?.length" class="app-settings-notes">
            <li v-for="note in settingsMeta.notes" :key="note">{{ note }}</li>
          </ul>
          </template>
          </div>
          <div class="wizard-nav app-settings-actions">
            <button type="button" class="ui-btn ui-btn-ghost" @click="closeAppSettings">Cancel</button>
            <button
              v-if="settingsApp.name === 'recyclarr'"
              type="button"
              class="ui-btn ui-btn-ghost"
              :disabled="settingsLoading"
              @click="resetRecyclarrDefaults"
            >
              Restore TRaSH defaults
            </button>
            <button
              v-if="settingsApp.name === 'recyclarr'"
              type="button"
              class="ui-btn ui-btn-ghost"
              :disabled="settingsLoading || !!actionLoading.recyclarr"
              @click="syncRecyclarr"
            >
              Sync now
            </button>
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="settingsLoading">
              {{ settingsLoading ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Toast Notifications -->
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

<style scoped>
/* Main Layout */
.app-container {
  min-height: 100vh;
  min-height: 100dvh;
  background: radial-gradient(circle at 10% 20%, rgba(18, 20, 32, 1) 0%, rgba(10, 11, 16, 1) 90%);
  color: #e2e8f0;
  font-family: 'Inter', sans-serif;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: hidden;
}

.top-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem 1rem;
  padding: 0.85rem clamp(0.85rem, 3vw, 2rem);
  background: rgba(15, 17, 26, 0.7);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  top: 0;
  z-index: 50;
  min-width: 0;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  min-width: 0;
  flex: 1 1 auto;
}

.logo-orb {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #05070c;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 0 16px rgba(56, 189, 248, 0.2);
  flex-shrink: 0;
}

.brand-logo {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.auth-logo {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  object-fit: cover;
  display: block;
  margin-bottom: 0.85rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}

.brand-titles {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-name {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  background: linear-gradient(90deg, #ffffff, #cbd5e1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  overflow-wrap: anywhere;
}

.brand-tagline {
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 400;
}

.nav-metrics {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  min-width: 0;
  flex: 1 1 auto;
}

.metric-pill {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.75rem;
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  font-size: 0.75rem;
  color: #94a3b8;
  flex-shrink: 0;
  max-width: 100%;
}

.metric-pill-action {
  cursor: pointer;
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.4);
  color: #60a5fa;
  font: inherit;
}

.metric-pill-action.is-active {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.45);
  color: #c7d2fe;
}

.metric-pill-action:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
}

.metric-label {
  color: #64748b;
  font-weight: 600;
}

.metric-val {
  color: #94a3b8;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.75rem;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 8px;
  font-size: 0.8rem;
}

.user-avatar {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #6366f1;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.7rem;
}

.user-name {
  color: #c7d2fe;
  font-weight: 500;
}

.btn-logout {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-logout:hover {
  color: #f87171;
}

/* Content */
.content-wrapper {
  flex: 1;
  width: min(1360px, 100%);
  max-width: 100%;
  margin: 0 auto;
  padding: clamp(1rem, 2.5vw, 2rem) clamp(0.85rem, 3vw, 1.5rem);
  box-sizing: border-box;
  min-width: 0;
}

/* Glass Card */
.glass-card {
  background: rgba(19, 23, 34, 0.65);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  position: relative;
  overflow: hidden;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.service-card.glass-card,
.catalog-toolbar.glass-card {
  overflow: visible;
}

.glass-card:hover {
  border-color: rgba(255, 255, 255, 0.15);
}

/* Auth Cards */
.auth-card-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
  padding: 0 0.25rem;
  min-width: 0;
}

.auth-card {
  width: 100%;
  max-width: min(440px, 100%);
  padding: clamp(1.15rem, 4vw, 2.25rem);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
}

.card-glow {
  position: absolute;
  top: -40px;
  right: -40px;
  width: 120px;
  height: 120px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.25) 0%, transparent 70%);
  pointer-events: none;
}

.card-header-accent {
  margin-bottom: 1.75rem;
}

.accent-badge {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
  margin-bottom: 0.5rem;
}

.card-header-accent h2 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0.25rem 0 0.5rem;
  color: #fff;
}

.card-header-accent p {
  color: #94a3b8;
  font-size: 0.85rem;
  margin: 0;
  line-height: 1.4;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

/* Dashboard Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}

.stat-card {
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  min-width: 0;
}

.stat-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1 1 8rem;
}

.stat-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: #f1f5f9;
  overflow-wrap: anywhere;
}

.stat-card-filter {
  cursor: pointer;
  user-select: none;
}

.stat-card-filter:hover {
  border-color: rgba(255, 255, 255, 0.16);
}

.stat-card-filter.is-filter-on {
  border-color: rgba(56, 189, 248, 0.45);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.25);
}

.stat-icon-wrapper {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.active-color {
  background: rgba(6, 182, 212, 0.15);
  color: #06b6d4;
  border: 1px solid rgba(6, 182, 212, 0.3);
}

.installed-color {
  background: rgba(168, 85, 247, 0.15);
  color: #c084fc;
  border: 1px solid rgba(168, 85, 247, 0.3);
}

.storage-color {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.refresh-color {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.stat-label {
  font-size: 0.7rem;
  color: #64748b;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.stat-sub {
  font-size: 0.9rem;
  color: #64748b;
  font-weight: 400;
}

.text-glow-cyan {
  color: #22d3ee;
  text-shadow: 0 0 10px rgba(34, 211, 238, 0.4);
}

.text-glow-purple {
  color: #c084fc;
  text-shadow: 0 0 10px rgba(192, 132, 252, 0.4);
}

.text-emerald {
  color: #34d399;
}

.text-warn {
  color: #fbbf24;
}

.status-indicator-tag {
  font-size: 0.85rem;
  color: #fbbf24;
  letter-spacing: 0.02em;
}

/* Services Section */
.section-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 0.85rem 1rem;
  margin-bottom: 1.25rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.section-title {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0;
  color: #fff;
}

.section-subtitle {
  font-size: 0.82rem;
  color: #64748b;
  margin: 0.2rem 0 0;
}

.catalog-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 1rem 1.25rem;
  padding: 0.9rem 1.1rem;
  margin-bottom: 1.15rem;
}

.catalog-filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-width: 0;
  flex: 1 1 auto;
}

.catalog-sort-group {
  flex: 1 1 10rem;
  min-width: 0;
}

.catalog-search-group {
  flex: 1 1 14rem;
  max-width: 22rem;
  min-width: 0;
}

.catalog-filter-label {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.catalog-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.catalog-chip {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  padding: 0.3rem 0.7rem;
  border-radius: 999px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.catalog-chip:hover {
  color: #e2e8f0;
  border-color: rgba(56, 189, 248, 0.4);
}

.catalog-chip.active {
  color: #e0f2fe;
  background: rgba(14, 165, 233, 0.18);
  border-color: rgba(56, 189, 248, 0.45);
}

.chip-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.05rem;
  height: 1.05rem;
  border-radius: 999px;
  font-size: 0.95rem;
  line-height: 1;
  color: #e0f2fe;
  background: rgba(15, 23, 42, 0.55);
}

.chip-clear:hover {
  background: rgba(239, 68, 68, 0.35);
  color: #fecaca;
}

.catalog-sort-select {
  min-width: 0;
  width: 100%;
}

.catalog-count {
  margin-left: auto;
  font-size: 0.75rem;
  color: #64748b;
  align-self: center;
}

@media (max-width: 720px) {
  .catalog-count {
    margin-left: 0;
    width: 100%;
  }

  .catalog-sort-select,
  .catalog-search-group {
    min-width: 0;
    width: 100%;
    max-width: none;
  }
}

.catalog-empty {
  grid-column: 1 / -1;
  color: #64748b;
  font-size: 0.9rem;
  margin: 0.5rem 0 0;
}

.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
  gap: 1.1rem;
}

.service-card {
  padding: 1.4rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: visible;
  min-width: 0;
}

.service-card.is-running {
  border-color: rgba(99, 102, 241, 0.35);
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.08);
}

.service-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-bottom: 0.85rem;
}

.service-ident {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  min-width: 0;
  flex: 1 1 12rem;
}

.app-badge {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: #1e293b;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.85rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
  flex-shrink: 0;
}

.app-icon {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.app-icon-sm {
  width: 22px;
  height: 22px;
  border-radius: 5px;
}

.app-badge.indexers { color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); background: rgba(56, 189, 248, 0.1); }
.app-badge.automation { color: #818cf8; border-color: rgba(129, 140, 248, 0.3); background: rgba(129, 140, 248, 0.1); }
.app-badge.downloading { color: #34d399; border-color: rgba(52, 211, 153, 0.3); background: rgba(52, 211, 153, 0.1); }
.app-badge.media { color: #f472b6; border-color: rgba(244, 114, 182, 0.3); background: rgba(244, 114, 182, 0.1); }
.app-badge.requests { color: #fbbf24; border-color: rgba(251, 191, 36, 0.3); background: rgba(251, 191, 36, 0.1); }
.app-badge.subtitles { color: #c084fc; border-color: rgba(192, 132, 252, 0.3); background: rgba(192, 132, 252, 0.1); }
.app-badge.optimization { color: #22d3ee; border-color: rgba(34, 211, 238, 0.3); background: rgba(34, 211, 238, 0.1); }
.app-badge.maintenance { color: #fb923c; border-color: rgba(251, 146, 60, 0.3); background: rgba(251, 146, 60, 0.1); }

.service-name-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  min-width: 0;
}

.service-name {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0;
  color: #f8fafc;
  overflow-wrap: anywhere;
}

.update-pill {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #86efac;
  border: 1px solid rgba(134, 239, 172, 0.35);
  background: rgba(22, 163, 74, 0.15);
  border-radius: 999px;
  padding: 0.15rem 0.45rem;
  white-space: nowrap;
}

.help-btn {
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 700;
  color: #93c5fd;
  border: 1px solid rgba(147, 197, 253, 0.35);
  text-decoration: none;
  background: rgba(59, 130, 246, 0.12);
}

.help-btn:hover {
  color: #fff;
  border-color: #93c5fd;
}

.category-pill {
  font-size: 0.65rem;
  text-transform: uppercase;
  color: #64748b;
  background: rgba(255, 255, 255, 0.05);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
}

.service-port {
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.2rem;
}

.port-label {
  color: #64748b;
  font-size: 0.7rem;
}

.port-link {
  color: #38bdf8;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  transition: color 0.15s;
}

.port-link:hover {
  color: #7dd3fc;
  text-decoration: underline;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.badge-running {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-stopped {
  background: rgba(100, 116, 139, 0.15);
  color: #94a3b8;
  border: 1px solid rgba(100, 116, 139, 0.3);
}

.badge-failed {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.badge-inactive {
  background: rgba(71, 85, 105, 0.15);
  color: #64748b;
  border: 1px solid rgba(71, 85, 105, 0.2);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.service-desc {
  font-size: 0.82rem;
  color: #94a3b8;
  margin: 0 0 0.85rem 0;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.service-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: #64748b;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  margin-bottom: 0.9rem;
}

.uptime-text {
  color: #10b981;
}

.service-actions {
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.action-btn-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  width: 100%;
  min-width: 0;
}

.btn-action {
  flex: 1 1 5.5rem;
  min-width: 0;
  padding: 0.45rem 0.55rem;
  border-radius: 6px;
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  transition: all 0.2s;
}

.btn-install {
  flex: 2;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  font-weight: 600;
}

.btn-start {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.3);
}

.btn-start:hover {
  background: rgba(16, 185, 129, 0.25);
}

.btn-stop {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.3);
}

.btn-stop:hover {
  background: rgba(239, 68, 68, 0.25);
}

.btn-restart {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border-color: rgba(245, 158, 11, 0.3);
}

.btn-restart:hover {
  background: rgba(245, 158, 11, 0.25);
}

.btn-webui {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  border-color: rgba(99, 102, 241, 0.3);
}

.btn-webui:hover {
  background: rgba(99, 102, 241, 0.25);
}

.btn-logs {
  background: rgba(51, 65, 85, 0.4);
  color: #cbd5e1;
  border-color: rgba(255, 255, 255, 0.1);
}

.btn-logs:hover {
  background: rgba(51, 65, 85, 0.7);
}

.btn-more {
  width: 100%;
  height: 100%;
  background: rgba(30, 41, 59, 0.7);
  color: #cbd5e1;
  border-color: rgba(255, 255, 255, 0.1);
}

.btn-more.open,
.btn-more:hover {
  color: #fff;
  background: rgba(51, 65, 85, 0.9);
}

.card-menu-wrap {
  position: relative;
  flex: 1 1 5.5rem;
  min-width: 0;
  display: flex;
}

.card-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 0.35rem);
  min-width: 10.5rem;
  max-width: min(16rem, calc(100vw - 2rem));
  padding: 0.35rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  z-index: 5;
  display: flex;
  flex-direction: column;
}

.card-menu button {
  background: transparent;
  border: none;
  color: #e2e8f0;
  text-align: left;
  padding: 0.45rem 0.65rem;
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
}

.card-menu button:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.2);
}

.card-menu button.danger {
  color: #fca5a5;
}

.card-menu button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.settings-modal {
  display: flex;
  flex-direction: column;
  width: min(520px, 100%);
  max-width: 100%;
  max-height: min(90dvh, calc(100dvh - 1.25rem), 900px);
  overflow: hidden;
  padding: clamp(0.85rem, 2.5vw, 1.25rem);
  box-sizing: border-box;
}

.settings-modal .modal-header {
  flex: 0 0 auto;
  padding: 0 0 0.75rem;
  margin: 0;
}

.settings-modal-wide {
  width: min(760px, 100%);
}

.app-settings-form {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  gap: 0.75rem;
}

.app-settings-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  padding-right: 0.15rem;
}

.app-settings-actions {
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
  margin: 0;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.recyclarr-yaml {
  min-height: 8rem;
  max-height: min(28vh, 18rem);
  overflow: auto;
  font-size: 0.75rem;
  line-height: 1.45;
  resize: vertical;
}

.health-modal {
  width: min(860px, 100%);
  max-height: min(90dvh, 900px);
  overflow: auto;
}

.health-body {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
  gap: 0.85rem;
  padding: 1rem 1.15rem 1.25rem;
}

.health-chart-card {
  min-width: 0;
  padding: 0.85rem 0.9rem 0.7rem;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.health-chart-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #94a3b8;
}

.health-chart-head strong {
  font-size: 1.15rem;
  letter-spacing: 0;
  text-transform: none;
  color: #f8fafc;
}

.health-chart-meta {
  margin: 0.2rem 0 0.55rem;
  font-size: 0.75rem;
  color: #64748b;
}

.health-svg {
  display: block;
  width: 100%;
  height: 72px;
}

.health-fill {
  fill-opacity: 0.22;
  stroke: none;
}

.health-line {
  fill: none;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.health-fill.cpu { fill: #22d3ee; }
.health-line.cpu { stroke: #22d3ee; }
.health-fill.mem { fill: #c084fc; }
.health-line.mem { stroke: #c084fc; }
.health-fill.disk { fill: #fbbf24; }
.health-line.disk { stroke: #fbbf24; }

.health-apps-card {
  grid-column: 1 / -1;
  min-width: 0;
  padding: 0.85rem 0.9rem 0.7rem;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.health-apps-table-wrap {
  overflow-x: auto;
  margin-top: 0.35rem;
}

.health-apps-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.health-apps-table th,
.health-apps-table td {
  text-align: left;
  padding: 0.45rem 0.35rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  vertical-align: top;
}

.health-apps-table th {
  color: #64748b;
  font-weight: 600;
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.health-apps-table td:nth-child(n + 2) {
  white-space: nowrap;
}

.health-app-name {
  display: block;
  color: #f8fafc;
}

.health-app-state {
  display: block;
  color: #64748b;
  font-size: 0.72rem;
  text-transform: lowercase;
}

.app-settings-dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  font-size: 0.72rem;
  color: #94a3b8;
}

.app-settings-dl div {
  display: grid;
  grid-template-columns: 4.5rem 1fr;
  gap: 0.5rem;
}

.app-settings-dl dt {
  color: #64748b;
}

.app-settings-dl dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: #cbd5e1;
}

.app-settings-notes {
  margin: 0;
  padding-left: 1.1rem;
  color: #94a3b8;
  font-size: 0.78rem;
  line-height: 1.45;
}

.link-btn {
  background: none;
  border: none;
  color: #93c5fd;
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.settings-hint {
  color: #94a3b8;
  font-size: 0.8rem;
  margin: 0;
  overflow-wrap: anywhere;
}

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: clamp(0.6rem, 3vw, 1.5rem);
}

.log-modal {
  width: 100%;
  max-width: 900px;
  height: min(80vh, 80dvh);
  max-height: calc(100dvh - 1.5rem);
  display: flex;
  flex-direction: column;
  background: #0f121b;
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.modal-title-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
  min-width: 0;
}

.modal-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.log-search {
  padding: 4px 8px;
  font-size: 11px;
  width: min(140px, 100%);
  height: 28px;
}

.modal-title-group h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.modal-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6366f1;
}

.toggle-control {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  color: #94a3b8;
  cursor: pointer;
}

.btn-icon {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-icon:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.log-console {
  flex: 1;
  background: #090a10;
  padding: 1rem 1.25rem;
  overflow-y: auto;
  font-size: 0.8rem;
  line-height: 1.55;
  color: #a5b4fc;
}

.log-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #475569;
}

.log-line {
  display: flex;
  gap: 1rem;
  min-width: 0;
}

.line-num {
  color: #334155;
  user-select: none;
  min-width: 2.5rem;
  text-align: right;
}

.line-content {
  color: #cbd5e1;
  word-break: break-all;
  white-space: pre-wrap;
}

/* Toast */
.toast-container {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  left: auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  z-index: 200;
  width: min(24rem, calc(100vw - 1.5rem));
  max-width: calc(100vw - 1.5rem);
  pointer-events: none;
}

.toast-container > * {
  pointer-events: auto;
}

.toast-pill {
  padding: 0.65rem 1.1rem;
  border-radius: 8px;
  font-size: 0.85rem;
  backdrop-filter: blur(12px);
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
}

.toast-info {
  background: rgba(30, 41, 59, 0.9);
  color: #e2e8f0;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.toast-success {
  background: rgba(6, 95, 70, 0.9);
  color: #6ee7b7;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.toast-error {
  background: rgba(153, 27, 27, 0.9);
  color: #fca5a5;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.toast-warning {
  background: rgba(146, 64, 14, 0.9);
  color: #fcd34d;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

/* Helpers */
.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border-width: 2px;
}

.spin-anim {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.animate-fade {
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 960px) {
  .hide-narrow {
    display: none;
  }
}

@media (max-width: 720px) {
  .hide-compact {
    display: none;
  }

  .brand-tagline {
    display: none;
  }

  .user-name {
    display: none;
  }

  .catalog-count {
    margin-left: 0;
    width: 100%;
  }

  .catalog-sort-select,
  .catalog-search-group,
  .catalog-filter-group {
    min-width: 0;
    width: 100%;
    max-width: none;
    flex: 1 1 100%;
  }

  .section-title-row .ui-btn {
    width: 100%;
  }

  .stat-card {
    padding: 1rem 1.1rem;
  }

  .service-card {
    padding: 1.1rem;
  }

  .service-actions .btn-action,
  .service-actions .card-menu-wrap {
    flex: 1 1 calc(50% - 0.4rem);
  }

  .card-menu {
    top: calc(100% + 0.35rem);
    bottom: auto;
  }

  .app-settings-dl div {
    grid-template-columns: 1fr;
    gap: 0.15rem;
  }

  .modal-header {
    padding: 0.85rem 1rem;
  }

  .log-search {
    width: 100%;
  }
}

@media (max-width: 480px) {
  .brand-name {
    font-size: 1rem;
  }

  .logo-orb {
    width: 36px;
    height: 36px;
  }

  .metrics-grid,
  .services-grid {
    grid-template-columns: 1fr;
  }

  .service-actions .btn-action,
  .service-actions .btn-install,
  .service-actions .card-menu-wrap {
    flex: 1 1 100%;
  }

  .toast-container {
    right: 0.75rem;
    bottom: 0.75rem;
    width: calc(100vw - 1.5rem);
  }
}
</style>
