<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { appIconSrc } from './appIcons.js'
import { apiError, apiRequest, readJson } from './api.js'
import { brandLogoUrl, brandTitle } from './branding.js'
import { formatUptime } from './format.js'
import VpnConfigFields from './VpnConfigFields.vue'

const emit = defineEmits(['done'])

const FLOW = [3, 4, 5, 6, 7, 8, 9, 10, 11]
const FIRST = FLOW[0]
const LAST = FLOW[FLOW.length - 1]

const step = ref(FIRST)
const payload = ref({})
const selections = reactive({})
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const installing = ref(false)
const installProgress = ref([])
const progressNow = ref(Date.now() / 1000)
let finishAborted = false

const TITLE = {
  3: 'Storage',
  4: 'File ownership',
  5: 'Download clients',
  6: 'VPN & remote access',
  7: '*Arr apps',
  8: 'Media server',
  9: 'Requests',
  10: 'Recommended tools',
  11: 'Review & install'
}

const flowIndex = computed(() => FLOW.indexOf(step.value) + 1)

const installTotal = computed(() => installProgress.value.length)
const installDoneCount = computed(() =>
  installProgress.value.filter((item) =>
    ['started', 'failed', 'already_installed'].includes(item.status)
  ).length
)
const installActive = computed(() =>
  installProgress.value.find((item) => ['installing', 'configuring'].includes(item.status))
)
const installPercent = computed(() => {
  if (!installTotal.value) return 0
  return Math.round((installDoneCount.value / installTotal.value) * 100)
})
const headerTitle = computed(() => (installing.value ? 'Installing applications' : TITLE[step.value]))
const headerSubtitle = computed(() => {
  if (installing.value && !installTotal.value) {
    return 'Saving your choices and starting catalog installs.'
  }
  if (installing.value) {
    const current = installActive.value
    if (current) return `${displayName(current.name)}: ${current.message || installStatusLabel(current.status).toLowerCase()}`
    return `Finished ${installDoneCount.value} of ${installTotal.value} selected apps.`
  }
  return `Step ${flowIndex.value} of ${FLOW.length} — pick your stack, then save and install.`
})

function isSelected(listKey, id) {
  const list = selections[listKey]
  return Array.isArray(list) && list.includes(id)
}

function toggle(listKey, id) {
  const current = Array.isArray(selections[listKey]) ? [...selections[listKey]] : []
  const idx = current.indexOf(id)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(id)
  selections[listKey] = current
}

function optionHelp(option) {
  return option.help_url || ''
}

function displayName(id, fallback) {
  const item = installProgress.value.find((row) => row.name === id)
  if (item?.displayName) return item.displayName
  const raw = String(fallback || id || '')
  if (!raw) return '—'
  return raw.charAt(0).toUpperCase() + raw.slice(1)
}

function isInstallTerminal(status) {
  return ['started', 'failed', 'already_installed'].includes(status)
}

function patchInstallItem(name, patch) {
  installProgress.value = installProgress.value.map((item) =>
    item.name === name ? { ...item, ...patch } : item
  )
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function refreshInstallProgress() {
  progressNow.value = Date.now() / 1000
  const res = await apiRequest('/api/catalog')
  if (!res.ok) return
  const data = await readJson(res)
  const byName = Object.fromEntries((data.applications || []).map((row) => [row.name, row]))
  installProgress.value = installProgress.value.map((item) => {
    const row = byName[item.name]
    if (!row) return item
    const next = {
      ...item,
      displayName: row.display_name || item.displayName,
      installed: row.installed,
      message: row.install_message || '',
      updatedAt: row.install_updated_at,
    }
    if (row.install_job === 'failed') {
      next.status = 'failed'
      next.detail = row.install_error || item.detail
    } else if (row.install_job === 'configuring') {
      next.status = 'configuring'
    } else if (row.install_job === 'installing' || row.install_job === 'queued') {
      next.status = row.install_job
    } else if (row.installed || row.install_job === 'started' || row.install_job === 'already_installed') {
      next.status = row.install_job === 'already_installed' ? 'already_installed' : 'started'
    }
    return next
  })
}

async function waitForAppInstall(name) {
  while (!finishAborted) {
    await refreshInstallProgress()
    const item = installProgress.value.find((row) => row.name === name)
    // Configuration can wait for other apps, so keep installing the remaining packages.
    if (!item || item.installed || isInstallTerminal(item.status)) return
    await sleep(1500)
  }
}

function installStatusLabel(status) {
  if (status === 'queued') return 'QUEUED'
  if (status === 'installing') return 'INSTALLING'
  if (status === 'configuring') return 'CONFIGURING'
  if (status === 'started') return 'STARTED'
  if (status === 'already_installed') return 'INSTALLED'
  if (status === 'failed') return 'FAILED'
  return String(status || '').toUpperCase()
}

function installBadgeClass(status) {
  if (status === 'started' || status === 'already_installed') return 'badge-running'
  if (status === 'failed') return 'badge-failed'
  if (status === 'installing' || status === 'configuring') return 'badge-installing'
  return 'badge-inactive'
}

function clampToFlow(id) {
  if (!FLOW.includes(id)) return FIRST
  return id
}

async function loadStep(id) {
  loading.value = true
  error.value = ''
  try {
    const res = await apiRequest(`/api/wizard/step/${id}`)
    if (!res.ok) throw new Error('Could not load wizard step')
    payload.value = await readJson(res)
    const data = payload.value
    if (id === 3) {
      selections.media_dir = data.media_dir || ''
      selections.download_dir = data.download_dir || ''
      selections.config_dir = data.config_dir || ''
    } else if (id === 4) {
      selections.puid = data.puid || data.current_uid || 1000
      selections.pgid = data.pgid || data.current_gid || 1000
    } else if (id === 5) {
      selections.download_clients = [...(data.selected || [])]
      selections.qbittorrent_username = data.qbittorrent_username || ''
      selections.qbittorrent_password = ''
      selections.usenet_host = data.usenet_host || ''
      selections.usenet_port = data.usenet_port || 563
      selections.usenet_ssl = data.usenet_ssl !== false
      selections.usenet_username = data.usenet_username || ''
      selections.usenet_password = ''
      selections.usenet_connections = data.usenet_connections || 8
    } else if (id === 6) {
      selections.vpn_provider = data.selected || 'none'
      selections.vpn_config_path = data.vpn_config_path || ''
      selections.vpn_protocol = data.vpn_protocol || 'wireguard'
      selections.vpn_enforce = !!data.vpn_enforce
      selections.has_vpn_config = !!data.has_vpn_config
      selections.vpn_config_text = ''
      selections.cloudflare_tunnel_enabled = !!data.cloudflare_tunnel_enabled
      selections.has_cloudflare_token = !!data.has_cloudflare_token
      selections.cloudflare_tunnel_token = ''
    } else if (id === 7) {
      selections.arr_apps = [...(data.selected || [])]
    } else if (id === 8) {
      selections.media_servers = [...(data.selected || [])]
      selections.plex_claim = data.plex_claim || ''
    } else if (id === 9) {
      selections.request_system = data.selected || 'seerr'
    } else if (id === 10) {
      selections.recommended_preview = [...(data.selected || [])]
    }
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function bodyForStep(id) {
  if (id === 3) return { media_dir: selections.media_dir, download_dir: selections.download_dir, config_dir: selections.config_dir }
  if (id === 4) return { puid: Number(selections.puid), pgid: Number(selections.pgid) }
  if (id === 5) {
    const body = {
      download_clients: selections.download_clients,
      qbittorrent_username: selections.qbittorrent_username,
      usenet_host: selections.usenet_host,
      usenet_port: Number(selections.usenet_port) || 563,
      usenet_ssl: !!selections.usenet_ssl,
      usenet_username: selections.usenet_username,
      usenet_connections: Number(selections.usenet_connections) || 8
    }
    if (selections.qbittorrent_password) body.qbittorrent_password = selections.qbittorrent_password
    if (selections.usenet_password) body.usenet_password = selections.usenet_password
    return body
  }
  if (id === 6) {
    return {
      vpn_provider: selections.vpn_provider,
      vpn_config_path: selections.vpn_config_path,
      vpn_protocol: selections.vpn_protocol,
      vpn_enforce: selections.vpn_provider !== 'none',
      ...(selections.vpn_config_text ? { vpn_config_text: selections.vpn_config_text } : {}),
      cloudflare_tunnel_enabled: !!selections.cloudflare_tunnel_enabled,
      ...(selections.cloudflare_tunnel_token ? { cloudflare_tunnel_token: selections.cloudflare_tunnel_token } : {})
    }
  }
  if (id === 7) return { arr_apps: selections.arr_apps }
  if (id === 8) return { media_servers: selections.media_servers, plex_claim: selections.plex_claim }
  if (id === 9) return { request_system: selections.request_system }
  if (id === 10) return { recommended_preview: selections.recommended_preview }
  return {}
}

async function next() {
  saving.value = true
  error.value = ''
  try {
    if (step.value >= FIRST && step.value < LAST) {
      const res = await apiRequest(`/api/wizard/step/${step.value}`, {
        method: 'POST',
        body: JSON.stringify(bodyForStep(step.value))
      })
      if (!res.ok) {
        const data = await readJson(res)
        throw new Error(apiError(data, 'Could not save this step'))
      }
    }
    const idx = FLOW.indexOf(step.value)
    if (idx < FLOW.length - 1) {
      step.value = FLOW[idx + 1]
      await loadStep(step.value)
    }
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function back() {
  const idx = FLOW.indexOf(step.value)
  if (idx <= 0) return
  step.value = FLOW[idx - 1]
  await loadStep(step.value)
}

async function skip() {
  saving.value = true
  error.value = ''
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 8000)
  try {
    const res = await apiRequest('/api/wizard/skip', {
      method: 'POST',
      signal: controller.signal
    })
    if (!res.ok) throw new Error('Could not skip wizard')
  } catch (err) {
    if (err.name !== 'AbortError') error.value = err.message
  } finally {
    clearTimeout(timer)
    saving.value = false
    emit('done')
  }
}

async function finish() {
  installing.value = true
  error.value = ''
  installProgress.value = []
  finishAborted = false
  try {
    const res = await apiRequest('/api/wizard/execute', { method: 'POST' })
    const data = await readJson(res)
    if (!res.ok) throw new Error(apiError(data, 'Wizard could not finish'))
    const apps = data.target_apps || []
    const already = new Set(
      (data.installations || [])
        .filter((row) => row.status === 'already_installed')
        .map((row) => row.app)
    )
    installProgress.value = apps.map((name) => ({
      name,
      displayName: displayName(name),
      status: already.has(name) ? 'already_installed' : 'queued'
    }))
    await nextTick()
    await refreshInstallProgress()
    for (const item of [...installProgress.value]) {
      if (finishAborted) return
      if (item.installed || isInstallTerminal(item.status)) continue
      patchInstallItem(item.name, { status: 'installing' })
      try {
        const inst = await apiRequest(`/api/catalog/${item.name}/install`, { method: 'POST' })
        const instData = await readJson(inst)
        if (!inst.ok) {
          patchInstallItem(item.name, {
            status: 'failed',
            detail: apiError(instData, 'Install failed')
          })
          continue
        }
        if (instData.status === 'already_installed') {
          patchInstallItem(item.name, { status: 'already_installed' })
          continue
        }
        await waitForAppInstall(item.name)
      } catch (err) {
        patchInstallItem(item.name, { status: 'failed', detail: err.message })
      }
    }
    if (!finishAborted && installProgress.value.length) {
      await refreshInstallProgress()
      await sleep(800)
    }
    if (!finishAborted) emit('done')
  } catch (err) {
    if (!finishAborted) error.value = err.message
  } finally {
    if (!finishAborted) installing.value = false
  }
}

function leaveToHome() {
  finishAborted = true
  emit('done')
}

const summary = computed(() => payload.value.summary || payload.value.selections || {})
const showPlexClaim = computed(() => (selections.media_servers || []).includes('plex'))
const showQbitCreds = computed(() => (selections.download_clients || []).includes('qbittorrent'))
const showUsenetCreds = computed(() => {
  const clients = selections.download_clients || []
  return clients.includes('sabnzbd') || clients.includes('nzbget')
})
const showVpnFields = computed(() => selections.vpn_provider && selections.vpn_provider !== 'none')

onMounted(async () => {
  const statusRes = await apiRequest('/api/wizard/status')
  if (statusRes.ok) {
    const status = await readJson(statusRes)
    step.value = clampToFlow(status.current_step || FIRST)
  }
  await loadStep(step.value)
})

onUnmounted(() => {
  finishAborted = true
})
</script>

<template>
  <section class="wizard-shell animate-fade">
    <div class="wizard-card glass-card">
      <div class="wizard-glow"></div>
      <div class="wizard-header">
        <img
          :src="brandLogoUrl"
          :alt="brandTitle"
          class="wizard-logo"
        />
        <span class="wizard-badge">FIRST-RUN SETUP</span>
        <h2>{{ headerTitle }}</h2>
        <p>{{ headerSubtitle }}</p>
        <ol class="wizard-steps" aria-label="Setup steps">
          <li
            v-for="(id, index) in FLOW"
            :key="id"
            :class="{
              active: !installing && id === step,
              done: installing || FLOW.indexOf(step) > index
            }"
          >
            {{ index + 1 }}
          </li>
        </ol>
      </div>

      <p v-if="error" class="ui-alert ui-alert-error">{{ error }}</p>
      <p v-if="loading" class="wizard-muted">Loading…</p>

      <div v-else class="wizard-body">
        <template v-if="installing">
          <div class="wizard-install">
            <div class="wizard-install-meta">
              <span>{{ installTotal ? 'Catalog installs' : 'Preparing' }}</span>
              <span class="font-mono">{{ installDoneCount }}/{{ installTotal || 0 }}</span>
            </div>
            <div
              class="wizard-bar"
              role="progressbar"
              :aria-valuemin="0"
              :aria-valuemax="100"
              :aria-valuenow="installTotal ? installPercent : undefined"
              :aria-valuetext="`${installDoneCount} of ${installTotal} apps finished`"
              aria-label="Application setup"
            >
              <div
                class="wizard-bar-fill"
                :class="{ indeterminate: installing && !installTotal }"
                :style="{ width: (installing && !installTotal ? 40 : installPercent) + '%' }"
              ></div>
            </div>
            <ul v-if="installProgress.length" class="wizard-install-list">
              <li v-for="item in installProgress" :key="item.name" class="wizard-install-row">
                <span class="wizard-app-badge">
                  <img
                    v-if="appIconSrc(item.name)"
                    :src="appIconSrc(item.name)"
                    :alt="displayName(item.name)"
                    class="wizard-icon"
                  />
                  <span v-else>{{ displayName(item.name).slice(0, 2).toUpperCase() }}</span>
                </span>
                <span class="wizard-install-name">
                  {{ displayName(item.name) }}
                  <small v-if="item.status === 'failed' && item.detail" class="wizard-install-error">{{ item.detail }}</small>
                  <template v-else-if="['queued', 'installing', 'configuring'].includes(item.status)">
                    <small v-if="item.message" class="wizard-install-detail" aria-live="polite">{{ item.message }}</small>
                    <small v-if="item.updatedAt" class="wizard-install-detail">
                      Last progress {{ formatUptime(progressNow - item.updatedAt) }} ago
                    </small>
                  </template>
                </span>
                <span class="wizard-status" :class="installBadgeClass(item.status)">
                  <span v-if="item.status === 'installing' || item.status === 'configuring'" class="spinner spinner-sm"></span>
                  <span v-else class="wizard-status-dot"></span>
                  {{ installStatusLabel(item.status) }}
                </span>
              </li>
            </ul>
          </div>
        </template>

        <template v-else-if="step === 3">
          <label class="ui-field">
            <span>Media directory</span>
            <input v-model="selections.media_dir" class="ui-input font-mono" />
          </label>
          <label class="ui-field">
            <span>Download directory</span>
            <input v-model="selections.download_dir" class="ui-input font-mono" />
          </label>
          <label class="ui-field">
            <span>Config directory</span>
            <input v-model="selections.config_dir" class="ui-input font-mono" />
          </label>
          <p class="wizard-muted">{{ payload.hardlink_message }} Put both media and downloads under one host folder (for example <code>/data/media</code> and <code>/data/downloads</code>) so *Arr can hardlink instead of copying.</p>
        </template>

        <template v-else-if="step === 4">
          <p class="wizard-muted">Filled from this host’s PUID/PGID (compose <code>PUID</code>/<code>PGID</code>, otherwise 1000). Change only if the media user is different.</p>
          <label class="ui-field">
            <span>PUID</span>
            <input v-model="selections.puid" type="number" min="1" class="ui-input font-mono" />
          </label>
          <label class="ui-field">
            <span>PGID</span>
            <input v-model="selections.pgid" type="number" min="1" class="ui-input font-mono" />
          </label>
        </template>

        <template v-else-if="step === 5">
          <div class="wizard-options">
            <label
              v-for="option in payload.options || []"
              :key="option.id"
              class="wizard-option"
              :class="{ selected: isSelected('download_clients', option.id) }"
            >
              <input type="checkbox" :checked="isSelected('download_clients', option.id)" @change="toggle('download_clients', option.id)" />
              <span class="wizard-app-badge">
                <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              </span>
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="wizard-help" title="Official help">?</a>
            </label>
          </div>
          <template v-if="showQbitCreds">
            <label class="ui-field">
              <span>qBittorrent username</span>
              <input v-model="selections.qbittorrent_username" class="ui-input font-mono" placeholder="Leave blank to use the manager username" />
            </label>
            <label class="ui-field">
              <span>qBittorrent password</span>
              <input v-model="selections.qbittorrent_password" type="password" class="ui-input" placeholder="Leave blank to use the manager password" />
            </label>
            <p class="wizard-muted">Blank qBittorrent username and password use the same login as AIO Media Server Manager.</p>
          </template>
          <template v-if="showUsenetCreds">
            <p class="wizard-muted">Optional. These Usenet provider details are pushed into SABnzbd and/or NZBGet after install.</p>
            <label class="ui-field">
              <span>Usenet server host</span>
              <input v-model="selections.usenet_host" class="ui-input font-mono" placeholder="news.example.com" />
            </label>
            <label class="ui-field">
              <span>Port</span>
              <input v-model.number="selections.usenet_port" type="number" min="1" max="65535" class="ui-input font-mono" />
            </label>
            <label class="wizard-option" :class="{ selected: selections.usenet_ssl }">
              <input type="checkbox" v-model="selections.usenet_ssl" />
              SSL / TLS
            </label>
            <label class="ui-field">
              <span>Usenet username</span>
              <input v-model="selections.usenet_username" class="ui-input font-mono" placeholder="username" autocomplete="off" />
            </label>
            <label class="ui-field">
              <span>Usenet password</span>
              <input v-model="selections.usenet_password" type="password" class="ui-input" :placeholder="payload.has_usenet_password ? 'Saved — leave blank to keep' : ''" />
            </label>
            <label class="ui-field">
              <span>Connections</span>
              <input v-model.number="selections.usenet_connections" type="number" min="1" max="100" class="ui-input font-mono" />
            </label>
          </template>
        </template>

        <template v-else-if="step === 6">
          <div class="wizard-options">
            <label
              v-for="option in payload.options || []"
              :key="option.id"
              class="wizard-option"
              :class="{ selected: selections.vpn_provider === option.id }"
            >
              <input type="radio" name="vpn" :value="option.id" v-model="selections.vpn_provider" />
              <span>{{ option.name }}</span>
            </label>
          </div>
          <template v-if="showVpnFields">
            <VpnConfigFields
              v-model:protocol="selections.vpn_protocol"
              v-model:path="selections.vpn_config_path"
              v-model:text="selections.vpn_config_text"
              :has-config="!!selections.has_vpn_config"
            />
          </template>
          <p class="wizard-muted">Remote access (optional). A Cloudflare Tunnel reaches the dashboard and apps over HTTPS without opening router ports; it starts right after this wizard.</p>
          <label class="wizard-option" :class="{ selected: selections.cloudflare_tunnel_enabled }">
            <input type="checkbox" v-model="selections.cloudflare_tunnel_enabled" />
            Cloudflare Tunnel
          </label>
          <label v-if="selections.cloudflare_tunnel_enabled" class="ui-field">
            <span>Tunnel token</span>
            <input
              v-model="selections.cloudflare_tunnel_token"
              type="password"
              class="ui-input font-mono"
              autocomplete="off"
              :placeholder="selections.has_cloudflare_token ? 'Saved — leave blank to keep' : 'Token from Cloudflare Zero Trust → Tunnels'"
            />
          </label>
        </template>

        <template v-else-if="step === 7">
          <div class="wizard-options">
            <label
              v-for="option in payload.options || []"
              :key="option.id"
              class="wizard-option"
              :class="{ selected: isSelected('arr_apps', option.id) }"
            >
              <input type="checkbox" :checked="isSelected('arr_apps', option.id)" @change="toggle('arr_apps', option.id)" />
              <span class="wizard-app-badge">
                <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              </span>
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="wizard-help" title="Official help">?</a>
            </label>
          </div>
        </template>

        <template v-else-if="step === 8">
          <div class="wizard-options">
            <label
              v-for="option in payload.options || []"
              :key="option.id"
              class="wizard-option"
              :class="{ selected: isSelected('media_servers', option.id) }"
            >
              <input type="checkbox" :checked="isSelected('media_servers', option.id)" @change="toggle('media_servers', option.id)" />
              <span class="wizard-app-badge">
                <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              </span>
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="wizard-help" title="Official help">?</a>
            </label>
          </div>
          <label v-if="showPlexClaim" class="ui-field">
            <span>Plex claim token</span>
            <input v-model="selections.plex_claim" class="ui-input font-mono" placeholder="claim-…" />
            <span class="wizard-muted">Optional. Get a token from plex.tv/claim, or sign in from the Plex UI later.</span>
          </label>
        </template>

        <template v-else-if="step === 9">
          <div class="wizard-options">
            <label
              v-for="option in payload.options || []"
              :key="option.id"
              class="wizard-option"
              :class="{ selected: selections.request_system === option.id }"
            >
              <input type="radio" name="seerr" :value="option.id" v-model="selections.request_system" />
              <span class="wizard-app-badge">
                <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              </span>
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="wizard-help" title="Official help">?</a>
            </label>
            <label class="wizard-option" :class="{ selected: selections.request_system === 'none' }">
              <input type="radio" name="seerr" value="none" v-model="selections.request_system" />
              <span>Skip for now</span>
            </label>
          </div>
        </template>

        <template v-else-if="step === 10">
          <div class="wizard-options">
            <label
              v-for="option in payload.options || []"
              :key="option.id"
              class="wizard-option"
              :class="{ selected: isSelected('recommended_preview', option.id) }"
            >
              <input type="checkbox" :checked="isSelected('recommended_preview', option.id)" @change="toggle('recommended_preview', option.id)" />
              <span class="wizard-app-badge">
                <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              </span>
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="wizard-help" title="Official help">?</a>
            </label>
          </div>
        </template>

        <template v-else>
          <dl class="wizard-dl">
            <div><dt>*Arr</dt><dd>{{ (summary.arr_apps || []).join(', ') || '—' }}</dd></div>
            <div><dt>Download</dt><dd>{{ (summary.download_clients || []).join(', ') || '—' }}</dd></div>
            <div><dt>Usenet</dt><dd>{{ summary.usenet_host || (summary.has_usenet_account ? 'configured' : '—') }}</dd></div>
            <div><dt>Media</dt><dd>{{ (summary.media_servers || []).join(', ') || '—' }}</dd></div>
            <div><dt>Requests</dt><dd>{{ summary.request_system || '—' }}</dd></div>
            <div><dt>VPN</dt><dd>{{ summary.vpn_provider || 'none' }}{{ summary.has_vpn_config ? ' · config saved' : '' }}</dd></div>
            <div><dt>Remote access</dt><dd>{{ summary.cloudflare_tunnel_enabled ? 'Cloudflare Tunnel' : '—' }}</dd></div>
            <div><dt>Recommended</dt><dd>{{ (summary.recommended_preview || []).join(', ') || 'none' }}</dd></div>
          </dl>
        </template>
      </div>

      <div class="wizard-actions">
        <button
          v-if="installing"
          type="button"
          class="ui-btn ui-btn-ghost"
          @click="leaveToHome"
        >Open Home</button>
        <button
          v-else
          type="button"
          class="ui-btn ui-btn-ghost"
          :disabled="saving"
          @click="skip"
        >Skip for now</button>
        <div class="wizard-nav">
          <button type="button" class="ui-btn ui-btn-ghost" :disabled="step === FIRST || saving || installing" @click="back">Back</button>
          <button v-if="step !== LAST" type="button" class="ui-btn ui-btn-primary" :disabled="saving || loading" @click="next">
            {{ saving ? 'Saving…' : 'Next' }}
          </button>
          <button v-else type="button" class="ui-btn ui-btn-primary" :disabled="installing" @click="finish">
            <span v-if="installing" class="spinner spinner-sm"></span>
            {{ installing ? 'Installing…' : 'Save & install' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.wizard-shell {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  min-height: 60vh;
  padding: 0.5rem clamp(0.5rem, 2vw, 0.75rem) 2.5rem;
  min-width: 0;
}
.wizard-card {
  width: min(640px, 100%);
  padding: clamp(1.25rem, 4vw, 2.25rem);
  position: relative;
  overflow: hidden;
  min-width: 0;
}
.wizard-glow {
  position: absolute;
  top: -40px;
  right: -40px;
  width: 120px;
  height: 120px;
  background: radial-gradient(circle, rgba(var(--color-primary-rgb), 0.25) 0%, transparent 70%);
  pointer-events: none;
}
.wizard-header {
  margin-bottom: 1.5rem;
  position: relative;
}
.wizard-logo {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  object-fit: cover;
  display: block;
  margin-bottom: 0.85rem;
  border: none;
  box-shadow: none;
}
.wizard-badge {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  background: rgba(var(--color-primary-rgb), 0.18);
  color: var(--color-primary-soft);
  margin-bottom: 0.5rem;
}
.wizard-header h2 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0.25rem 0 0.5rem;
  color: var(--text-heading);
}
.wizard-header p,
.wizard-muted {
  color: var(--text-muted);
  font-size: 0.85rem;
  line-height: 1.4;
  margin: 0;
}
.wizard-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  list-style: none;
  padding: 0;
  margin: 1.15rem 0 0;
}
.wizard-steps li {
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-muted);
  border: 1px solid var(--border-subtle);
  background: var(--pill-bg);
}
.wizard-steps li.active {
  color: var(--color-primary-contrast);
  background: var(--gradient-primary);
  border-color: transparent;
  box-shadow: 0 4px 14px rgba(var(--color-primary-rgb), 0.35);
}
.wizard-steps li.done {
  color: var(--color-success-fg);
  border-color: color-mix(in srgb, var(--color-success) 35%, transparent);
  background: var(--color-success-bg);
}
.wizard-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin: 0 0 1.5rem;
  position: relative;
}
.wizard-options {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.wizard-option {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.75rem 0.9rem;
  border-radius: 10px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  color: var(--text-main);
  cursor: pointer;
  font-size: 0.9rem;
  min-width: 0;
}
.wizard-option > span:not(.wizard-app-badge) {
  flex: 1 1 8rem;
  min-width: 0;
  overflow-wrap: anywhere;
}
.wizard-option:hover {
  border-color: var(--border-strong);
}
.wizard-option.selected {
  border-color: rgba(var(--color-primary-rgb), 0.45);
  box-shadow: 0 0 0 1px rgba(var(--color-primary-rgb), 0.22);
  background: rgba(var(--color-primary-rgb), 0.08);
}
.wizard-app-badge {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--color-primary-soft);
}
.wizard-icon {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.wizard-help {
  margin-left: auto;
  width: 1.55rem;
  height: 1.55rem;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 0.82rem;
  color: var(--color-info-fg);
  border: 1px solid color-mix(in srgb, var(--color-info) 40%, transparent);
  text-decoration: none;
  background: var(--color-info-bg);
  flex-shrink: 0;
}
.wizard-dl {
  display: grid;
  gap: 0.55rem;
}
.wizard-dl div {
  display: grid;
  grid-template-columns: 7.5rem 1fr;
  gap: 0.6rem;
  padding: 0.75rem 0.9rem;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
}
.wizard-dl dt {
  color: var(--text-dim);
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.wizard-dl dd {
  margin: 0;
  color: var(--text-main);
  font-size: 0.88rem;
  overflow-wrap: anywhere;
}
.wizard-install {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.wizard-install-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-main);
}
.wizard-bar {
  height: 10px;
  border-radius: 999px;
  background: var(--overlay-soft);
  border: 1px solid var(--border-subtle);
  overflow: hidden;
}
.wizard-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--gradient-primary);
  box-shadow: 0 0 12px rgba(var(--color-primary-rgb), 0.45);
  transition: width 0.35s ease;
}
.wizard-bar-fill.indeterminate {
  width: 40% !important;
  animation: wizard-indeterminate 1.2s ease-in-out infinite;
}
@keyframes wizard-indeterminate {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(280%); }
}
.wizard-install-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  max-height: 320px;
  overflow-y: auto;
}
.wizard-install-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.65rem 0.8rem;
  border-radius: 10px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  min-width: 0;
}
.wizard-install-name {
  flex: 1 1 8rem;
  min-width: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-main);
  overflow-wrap: anywhere;
}
.wizard-install-error,
.wizard-install-detail {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-danger-fg);
}
.wizard-install-detail {
  color: var(--text-muted);
}
.wizard-status {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.03em;
}
.wizard-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.badge-running {
  background: var(--color-success-bg);
  color: var(--color-success-fg);
  border: 1px solid color-mix(in srgb, var(--color-success) 35%, transparent);
}
.badge-failed {
  background: var(--color-danger-bg);
  color: var(--color-danger-fg);
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, transparent);
}
.badge-installing {
  background: var(--color-info-bg);
  color: var(--color-info-fg);
  border: 1px solid color-mix(in srgb, var(--color-info) 35%, transparent);
}
.badge-inactive {
  background: color-mix(in srgb, var(--text-dim) 16%, transparent);
  color: var(--text-muted);
  border: 1px solid color-mix(in srgb, var(--text-dim) 25%, transparent);
}
.wizard-actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
  position: relative;
}
.wizard-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}
.ui-alert {
  margin-bottom: 1rem;
}
.spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid var(--spinner-track, rgba(148, 163, 184, 0.35));
  border-radius: 50%;
  border-top-color: var(--color-primary);
  animation: wizard-spin 0.8s linear infinite;
}
.spinner-sm {
  width: 14px;
  height: 14px;
}
@keyframes wizard-spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 560px) {
  .wizard-dl div {
    grid-template-columns: 1fr;
  }
  .wizard-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .wizard-nav {
    width: 100%;
  }
  .wizard-nav .ui-btn,
  .wizard-actions > .ui-btn {
    flex: 1 1 auto;
    width: 100%;
  }
}
</style>
