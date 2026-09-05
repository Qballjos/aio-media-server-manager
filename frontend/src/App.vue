<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

// --- State Variables ---
const authStatus = ref({
  setup_required: false,
  authenticated: false,
  username: null
})

const csrfToken = ref('')
const authToken = ref(localStorage.getItem('amm_token') || '')

const authForm = ref({
  username: 'admin',
  password: '',
  confirmPassword: ''
})
const authError = ref('')
const authLoading = ref(false)

// Dashboard data
const catalogApps = ref([])
const applications = ref([])
const systemInfo = ref(null)
const hostArch = ref('')
const isLoadingData = ref(false)
const actionLoading = ref({}) // map appName -> action ("start", "stop", etc.)

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
const logLines = ref([])
const logLoading = ref(false)
const autoScrollLogs = ref(true)
const logContainerRef = ref(null)
let logPollInterval = null

// Live Clock
const currentTime = ref(new Date().toLocaleTimeString())
let clockInterval = null
let pollInterval = null

// --- API Helper ---
async function apiRequest(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }

  if (csrfToken.value) {
    headers['X-CSRF-Token'] = csrfToken.value
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
      if (data.authenticated) {
        await refreshDashboard()
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
      csrfToken.value = data.csrf_token
    }

    authStatus.value = {
      setup_required: false,
      authenticated: true,
      username: data.username
    }
    showToast('Admin setup completed successfully! Welcome to AIO Media Manager.', 'success')
    authForm.value.password = ''
    authForm.value.confirmPassword = ''
    await refreshDashboard()
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
      csrfToken.value = data.csrf_token
    }

    authStatus.value = {
      setup_required: false,
      authenticated: true,
      username: data.username
    }
    showToast(`Welcome back, ${data.username}!`, 'success')
    authForm.value.password = ''
    await refreshDashboard()
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
  localStorage.removeItem('amm_token')
  authStatus.value.authenticated = false
  authStatus.value.username = null
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
    }
  } catch (err) {
    console.error('System info fetch error:', err)
  }
}

async function refreshDashboard() {
  isLoadingData.value = true
  await Promise.all([fetchCatalog(), fetchApplications(), fetchSystemInfo()])
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
      tier: cat.tier,
      port: cat.port || cat.default_port,
      installed: cat.installed || (live && live.installed) || false,
      installedVersion: cat.installed_version || (live && live.version),
      webUrl: `http://${host}:${cat.port || cat.default_port}`,
      state: live ? live.state : (cat.installed ? 'stopped' : 'not_installed'),
      pid: live ? live.pid : null,
      uptime: live ? live.uptime_seconds : null,
      arm64: cat.arm64_supported
    }
  })
})

const activeAppCount = computed(() => {
  return combinedServices.value.filter(s => s.state === 'running' || s.state === 'healthy').length
})

const installedAppCount = computed(() => {
  return combinedServices.value.filter(s => s.installed).length
})

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
  await fetchLogs(app.name)
  startLogPolling(app.name)
}

function closeLogs() {
  showLogModal.value = false
  activeLogApp.value = null
  if (logPollInterval) {
    clearInterval(logPollInterval)
    logPollInterval = null
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

function statusBadgeClass(state) {
  switch (state) {
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
})
</script>

<template>
  <div class="app-container">
    <!-- Header -->
    <header class="top-nav">
      <div class="nav-brand">
        <div class="logo-orb">
          <span class="logo-icon">⚡</span>
        </div>
        <div class="brand-titles">
          <h1 class="brand-name">AIO Media Manager</h1>
          <span class="brand-tagline">Unified Media Automation Stack</span>
        </div>
      </div>

      <div class="nav-metrics">
        <div class="metric-pill">
          <span class="pulse-dot"></span>
          <span class="metric-label">TIME</span>
          <span class="metric-val font-mono">{{ currentTime }}</span>
        </div>
        <div v-if="hostArch" class="metric-pill">
          <span class="metric-label">ARCH</span>
          <span class="metric-val font-mono">{{ hostArch.toUpperCase() }}</span>
        </div>
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
            <span class="accent-badge">INITIAL SETUP</span>
            <h2>Create Administrator</h2>
            <p>Welcome! Set up the initial administrator account to protect and manage your server.</p>
          </div>

          <form @submit.prevent="handleSetup" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label>Administrator Username</label>
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                class="input-control font-mono"
              />
            </div>

            <div class="form-group">
              <label>Admin Password (minimum 8 characters)</label>
              <input
                v-model="authForm.password"
                type="password"
                placeholder="••••••••••••"
                required
                class="input-control"
              />
            </div>

            <div class="form-group">
              <label>Confirm Password</label>
              <input
                v-model="authForm.confirmPassword"
                type="password"
                placeholder="••••••••••••"
                required
                class="input-control"
              />
            </div>

            <button type="submit" :disabled="authLoading" class="btn-primary btn-block">
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
            <span class="accent-badge">SIGN IN</span>
            <h2>Manager Access</h2>
            <p>Enter your administrator credentials to manage services and server config.</p>
          </div>

          <form @submit.prevent="handleLogin" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label>Username</label>
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                autofocus
                class="input-control font-mono"
              />
            </div>

            <div class="form-group">
              <label>Password</label>
              <input
                v-model="authForm.password"
                type="password"
                placeholder="••••••••••••"
                required
                class="input-control"
              />
            </div>

            <button type="submit" :disabled="authLoading" class="btn-primary btn-block">
              <span v-if="authLoading" class="spinner"></span>
              <span v-else>Authenticate Session</span>
            </button>
          </form>
        </div>
      </section>

      <!-- 3. Dashboard View -->
      <div v-else class="dashboard-layout animate-fade">
        <!-- Metric Cards -->
        <section class="metrics-grid">
          <div class="stat-card glass-card">
            <div class="stat-icon-wrapper active-color">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="5 3 19 12 5 21 5 3"></polygon>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">ACTIVE SERVICES</div>
              <div class="stat-value font-mono">
                <span class="text-glow-cyan">{{ activeAppCount }}</span>
                <span class="stat-sub"> / {{ combinedServices.length }}</span>
              </div>
            </div>
          </div>

          <div class="stat-card glass-card">
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
                <span class="stat-sub"> / {{ combinedServices.length }}</span>
              </div>
            </div>
          </div>

          <div class="stat-card glass-card">
            <div class="stat-icon-wrapper storage-color">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">STORAGE ATOMICITY</div>
              <div class="stat-value font-mono">
                <span class="status-indicator-tag">SINGLE-VOLUME</span>
              </div>
            </div>
          </div>

          <div class="stat-card glass-card">
            <div class="stat-icon-wrapper refresh-color" @click="refreshDashboard" style="cursor: pointer;" title="Refresh now">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': isLoadingData }">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
            </div>
            <div class="stat-content">
              <div class="stat-label">SUPERVISOR HEALTH</div>
              <div class="stat-value font-mono text-emerald">
                ONLINE
              </div>
            </div>
          </div>
        </section>

        <!-- Services Section Header -->
        <div class="section-title-row">
          <div>
            <h2 class="section-title">Core Applications Stack</h2>
            <p class="section-subtitle">Supervised media pipeline components running bare-metal inside a unified container.</p>
          </div>
          <button @click="refreshDashboard" class="btn-secondary" :disabled="isLoadingData">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': isLoadingData }">
              <polyline points="23 4 23 10 17 10"></polyline>
              <polyline points="1 20 1 14 7 14"></polyline>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            <span>Sync Status</span>
          </button>
        </div>

        <!-- Services Grid -->
        <div class="services-grid">
          <div
            v-for="service in combinedServices"
            :key="service.name"
            class="service-card glass-card"
            :class="{ 'is-running': service.state === 'running' || service.state === 'healthy' }"
          >
            <!-- Card Header -->
            <div class="service-header">
              <div class="service-ident">
                <div class="app-badge" :class="service.category">
                  {{ service.name.substring(0, 2).toUpperCase() }}
                </div>
                <div>
                  <div class="service-name-row">
                    <h3 class="service-name">{{ service.displayName }}</h3>
                    <span class="category-pill">{{ service.category }}</span>
                  </div>
                  <div class="service-port font-mono">
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
              <span class="status-badge" :class="statusBadgeClass(service.state)">
                <span class="badge-dot"></span>
                {{ service.state.toUpperCase().replace('_', ' ') }}
              </span>
            </div>

            <!-- Description -->
            <p class="service-desc">{{ service.description }}</p>

            <!-- Metadata footer -->
            <div class="service-meta font-mono">
              <span v-if="service.installedVersion">v{{ service.installedVersion }}</span>
              <span v-else-if="service.installed">Installed</span>
              <span v-else class="text-dim">Not Installed</span>

              <span v-if="service.uptime" class="uptime-text">
                up {{ formatUptime(service.uptime) }}
              </span>
              <span v-if="service.pid" class="pid-text">PID: {{ service.pid }}</span>
            </div>

            <!-- Action Controls -->
            <div class="service-actions">
              <!-- Not installed -> Install button -->
              <template v-if="!service.installed">
                <button
                  @click="installApp(service.name, service.displayName)"
                  class="btn-action btn-install"
                  :disabled="actionLoading[service.name] === 'install'"
                >
                  <span v-if="actionLoading[service.name] === 'install'" class="spinner spinner-sm"></span>
                  <span v-else>Download & Install</span>
                </button>
              </template>

              <!-- Installed -> Lifecycle buttons -->
              <template v-else>
                <div class="action-btn-group">
                  <!-- Start button -->
                  <button
                    v-if="service.state === 'stopped' || service.state === 'not_installed' || service.state === 'crashed'"
                    @click="startApp(service.name)"
                    class="btn-action btn-start"
                    :disabled="!!actionLoading[service.name]"
                    title="Start Process"
                  >
                    <span v-if="actionLoading[service.name] === 'start'" class="spinner spinner-sm"></span>
                    <span v-else>Start</span>
                  </button>

                  <!-- Stop button -->
                  <button
                    v-if="service.state === 'running' || service.state === 'healthy'"
                    @click="stopApp(service.name)"
                    class="btn-action btn-stop"
                    :disabled="!!actionLoading[service.name]"
                    title="Stop Process"
                  >
                    <span v-if="actionLoading[service.name] === 'stop'" class="spinner spinner-sm"></span>
                    <span v-else>Stop</span>
                  </button>

                  <!-- Restart button -->
                  <button
                    v-if="service.state === 'running' || service.state === 'healthy'"
                    @click="restartApp(service.name)"
                    class="btn-action btn-restart"
                    :disabled="!!actionLoading[service.name]"
                    title="Restart Process"
                  >
                    <span v-if="actionLoading[service.name] === 'restart'" class="spinner spinner-sm"></span>
                    <span v-else>Restart</span>
                  </button>

                  <!-- Web UI button -->
                  <a
                    :href="service.webUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="btn-action btn-webui"
                    title="Open in new tab"
                  >
                    Open UI
                  </a>

                  <!-- Logs button -->
                  <button
                    @click="openLogs(service)"
                    class="btn-action btn-logs"
                    title="View Process Logs"
                  >
                    Logs
                  </button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Log Viewer Modal -->
    <div v-if="showLogModal" class="modal-backdrop" @click.self="closeLogs">
      <div class="log-modal glass-card animate-scale">
        <div class="modal-header">
          <div class="modal-title-group">
            <span class="modal-dot"></span>
            <h3>{{ activeLogApp?.displayName }} Process Logs</h3>
            <span class="font-mono text-dim">({{ activeLogApp?.name }})</span>
          </div>

          <div class="modal-controls">
            <label class="toggle-control font-mono">
              <input type="checkbox" v-model="autoScrollLogs" />
              <span>Auto-Scroll</span>
            </label>
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
          <div v-if="logLines.length === 0" class="log-empty">
            <span v-if="logLoading">Streaming output buffer...</span>
            <span v-else>No output received yet for this process.</span>
          </div>
          <div
            v-for="(line, idx) in logLines"
            :key="idx"
            class="log-line"
          >
            <span class="line-num">{{ idx + 1 }}</span>
            <span class="line-content">{{ line }}</span>
          </div>
        </div>
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
  background: radial-gradient(circle at 10% 20%, rgba(18, 20, 32, 1) 0%, rgba(10, 11, 16, 1) 90%);
  color: #e2e8f0;
  font-family: 'Inter', sans-serif;
  display: flex;
  flex-direction: column;
}

.top-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: rgba(15, 17, 26, 0.7);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  position: sticky;
  top: 0;
  z-index: 50;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.logo-orb {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  box-shadow: 0 0 16px rgba(99, 102, 241, 0.35);
}

.brand-titles {
  display: flex;
  flex-direction: column;
}

.brand-name {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  background: linear-gradient(90deg, #ffffff, #cbd5e1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.brand-tagline {
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 400;
}

.nav-metrics {
  display: flex;
  align-items: center;
  gap: 0.75rem;
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
  max-width: 1360px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
  width: 100%;
  box-sizing: border-box;
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
}

.auth-card {
  width: 100%;
  max-width: 440px;
  padding: 2.25rem;
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

.form-group label {
  font-size: 0.8rem;
  font-weight: 500;
  color: #cbd5e1;
}

.input-control {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0.7rem 0.9rem;
  border-radius: 8px;
  color: #fff;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.input-control:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
}

.alert-banner {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.82rem;
  line-height: 1.4;
}

.alert-error {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}

.btn-primary {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border: none;
  color: #fff;
  font-weight: 600;
  padding: 0.8rem 1.2rem;
  border-radius: 8px;
  font-size: 0.92rem;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
}

.btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.btn-block {
  width: 100%;
}

/* Dashboard Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}

.stat-card {
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
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

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 0.7rem;
  color: #64748b;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: #f1f5f9;
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

.btn-secondary {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  padding: 0.5rem 0.9rem;
  border-radius: 8px;
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(51, 65, 85, 0.8);
  color: #fff;
}

.services-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 1.25rem;
}

.service-card {
  padding: 1.4rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.service-card.is-running {
  border-color: rgba(99, 102, 241, 0.35);
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.08);
}

.service-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.85rem;
}

.service-ident {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.app-badge {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #1e293b;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.85rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.app-badge.indexers { color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); background: rgba(56, 189, 248, 0.1); }
.app-badge.automation { color: #818cf8; border-color: rgba(129, 140, 248, 0.3); background: rgba(129, 140, 248, 0.1); }
.app-badge.downloading { color: #34d399; border-color: rgba(52, 211, 153, 0.3); background: rgba(52, 211, 153, 0.1); }
.app-badge.media { color: #f472b6; border-color: rgba(244, 114, 182, 0.3); background: rgba(244, 114, 182, 0.1); }
.app-badge.requests { color: #fbbf24; border-color: rgba(251, 191, 36, 0.3); background: rgba(251, 191, 36, 0.1); }

.service-name-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.service-name {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0;
  color: #f8fafc;
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
  margin: 0 0 1rem 0;
  line-height: 1.45;
  min-height: 2.4rem;
}

.service-meta {
  display: flex;
  align-items: center;
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
  align-items: center;
}

.action-btn-group {
  display: flex;
  gap: 0.4rem;
  width: 100%;
}

.btn-action {
  flex: 1;
  padding: 0.45rem 0.6rem;
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
  width: 100%;
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
  padding: 1.5rem;
}

.log-modal {
  width: 100%;
  max-width: 900px;
  height: 80vh;
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
  padding: 1rem 1.5rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.modal-title-group {
  display: flex;
  align-items: center;
  gap: 0.6rem;
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

.modal-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
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
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  z-index: 200;
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
</style>
