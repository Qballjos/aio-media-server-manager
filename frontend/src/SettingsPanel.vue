<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import VpnConfigFields from './VpnConfigFields.vue'

const props = defineProps({
  apiRequest: { type: Function, required: true },
  systemInfo: { type: Object, default: null },
  hostArch: { type: String, default: '' }
})
const emit = defineEmits(['session'])

const section = ref('account')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const share = ref({ active: false, url: '', expires_at: null, ttl_hours: 24 })
const errors = ref([])
const copied = ref(false)
const backups = ref([])
const form = ref({
  username: '',
  email: '',
  current_password: '',
  new_password: '',
  timezone: 'UTC',
  log_level: 'INFO',
  puid: 1000,
  pgid: 1000,
  backup_retention: 7,
  vpn_enabled: false,
  vpn_enforce: false,
  vpn_provider: 'privadovpn',
  vpn_protocol: 'wireguard',
  vpn_config_path: '',
  vpn_config_text: '',
  cloudflare_tunnel_enabled: false,
  cloudflare_tunnel_token: '',
  trusted_proxies: '',
  github_token: '',
  jellyfin_api_key: '',
  update_check_schedule: 'off',
  update_apply_schedule: 'off',
  update_time: '04:00',
  update_weekday: 0,
  update_day_of_month: 1
})
const snapshot = ref({})
const vpnLive = ref({})
const tunnelLive = ref({})
const githubConfigured = ref(false)
const jellyfinConfigured = ref(false)

const metrics = computed(() => props.systemInfo?.metrics || {})
const storage = computed(() => snapshot.value.storage || props.systemInfo?.storage || {})
const transcoding = computed(() => props.systemInfo?.transcoding || {})
const storageRows = computed(() =>
  Object.entries(storage.value).map(([label, info]) => ({ label, ...info }))
)
const hardlinks = computed(() => storage.value?.download_dir?.hardlinks_supported !== false)

function formatBytes(n) {
  const v = Number(n) || 0
  if (!v) return '—'
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

function prettyLabel(key) {
  return String(key || '').replace(/_/g, ' ')
}

function apiError(data, fallback) {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return fallback
}

function applySettingsPayload(data) {
  snapshot.value = data || {}
  form.value.timezone = data.timezone || 'UTC'
  form.value.log_level = data.log_level || 'INFO'
  form.value.puid = data.puid || 1000
  form.value.pgid = data.pgid || 1000
  form.value.backup_retention = data.backup_retention || 7
  form.value.trusted_proxies = data.trusted_proxies || ''
  const vpn = data.vpn || {}
  vpnLive.value = vpn
  form.value.vpn_enabled = !!vpn.enabled
  form.value.vpn_enforce = !!vpn.enforce
  form.value.vpn_provider = vpn.provider || 'privadovpn'
  form.value.vpn_protocol = vpn.protocol || 'wireguard'
  form.value.vpn_config_path = vpn.config_path || ''
  form.value.vpn_config_text = ''
  const tunnel = data.cloudflare_tunnel || {}
  tunnelLive.value = tunnel
  form.value.cloudflare_tunnel_enabled = !!tunnel.enabled
  form.value.cloudflare_tunnel_token = ''
  githubConfigured.value = !!data.github_token_configured
  form.value.github_token = ''
  jellyfinConfigured.value = !!data.jellyfin_api_key_configured
  form.value.jellyfin_api_key = ''
  const updates = data.updates || {}
  form.value.update_check_schedule = updates.check_schedule || 'off'
  form.value.update_apply_schedule = updates.apply_schedule || 'off'
  form.value.update_time = updates.time || '04:00'
  form.value.update_weekday = updates.weekday ?? 0
  form.value.update_day_of_month = updates.day_of_month || 1
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [meRes, setRes, bakRes, diagRes] = await Promise.all([
      props.apiRequest('/api/auth/me'),
      props.apiRequest('/api/settings'),
      props.apiRequest('/api/backups'),
      props.apiRequest('/api/diagnostics')
    ])
    if (meRes.ok) {
      const me = await meRes.json()
      form.value.username = me.username || 'admin'
      form.value.email = me.email || ''
    }
    if (setRes.ok) applySettingsPayload(await setRes.json())
    else error.value = 'Could not load settings.'
    if (bakRes.ok) {
      const bak = await bakRes.json()
      backups.value = bak.backups || []
    }
    if (diagRes.ok) {
      const diag = await diagRes.json()
      share.value = diag.share || share.value
      errors.value = diag.errors || []
    }
  } catch (err) {
    error.value = err.message || 'Could not load settings.'
  } finally {
    loading.value = false
  }
}

async function patchSettings(payload) {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await props.apiRequest('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
    const data = await res.json()
    if (!res.ok) {
      error.value = apiError(data, 'Could not save settings.')
      return
    }
    applySettingsPayload(data)
    notice.value = (data.notes && data.notes.join(' ')) || 'Saved.'
  } catch (err) {
    error.value = err.message || 'Could not save settings.'
  } finally {
    saving.value = false
  }
}

async function saveVpn() {
  const payload = {
    vpn_enabled: form.value.vpn_enabled,
    vpn_enforce: form.value.vpn_enforce,
    vpn_provider: form.value.vpn_provider,
    vpn_protocol: form.value.vpn_protocol,
    vpn_config_path: form.value.vpn_config_path
  }
  if (form.value.vpn_config_text) payload.vpn_config_text = form.value.vpn_config_text
  await patchSettings(payload)
}

async function saveAccount() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const body = {
      current_password: form.value.current_password,
      username: form.value.username,
      email: form.value.email
    }
    if (form.value.new_password) body.new_password = form.value.new_password
    const res = await props.apiRequest('/api/auth/account', {
      method: 'PATCH',
      body: JSON.stringify(body)
    })
    const data = await res.json()
    if (!res.ok) {
      error.value = apiError(data, 'Could not update account.')
      return
    }
    form.value.current_password = ''
    form.value.new_password = ''
    emit('session', data)
    notice.value = 'Account updated.'
  } catch (err) {
    error.value = err.message || 'Could not update account.'
  } finally {
    saving.value = false
  }
}

async function runUpdateCheck() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await props.apiRequest('/api/updates/check', { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      error.value = apiError(data, 'Update check failed.')
      return
    }
    const count = (data.available || []).length
    notice.value = count ? `${count} update(s) available.` : 'No updates found.'
    await loadAll()
  } catch (err) {
    error.value = err.message || 'Update check failed.'
  } finally {
    saving.value = false
  }
}

async function createBackup() {
  saving.value = true
  error.value = ''
  try {
    const res = await props.apiRequest('/api/backups', { method: 'POST', body: JSON.stringify({ label: 'manual' }) })
    const data = await res.json()
    if (!res.ok) {
      error.value = data.detail || 'Backup failed.'
      return
    }
    notice.value = `Created ${data.name}`
    await loadAll()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function restoreBackup(name) {
  if (!window.confirm(`Restore ${name}? This replaces manager config files.`)) return
  saving.value = true
  error.value = ''
  try {
    const res = await props.apiRequest(`/api/backups/${encodeURIComponent(name)}/restore`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      error.value = data.detail || 'Restore failed.'
      return
    }
    notice.value = 'Backup restored. Restart the manager container if processes look stale.'
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function deleteBackup(name) {
  if (!window.confirm(`Delete ${name}?`)) return
  const res = await props.apiRequest(`/api/backups/${encodeURIComponent(name)}`, { method: 'DELETE' })
  if (res.ok) await loadAll()
}

async function loadStatus() {
  const res = await props.apiRequest('/api/diagnostics')
  if (!res.ok) return
  const data = await res.json()
  share.value = data.share || share.value
  errors.value = data.errors || []
}

async function createShare() {
  saving.value = true
  error.value = ''
  copied.value = false
  try {
    const res = await props.apiRequest('/api/diagnostics/share', { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      error.value = data.detail || 'Could not create debug link.'
      return
    }
    share.value = {
      active: true,
      url: data.url,
      token: data.token,
      expires_at: data.expires_at,
      ttl_hours: data.ttl_hours
    }
    await loadStatus()
  } catch (err) {
    error.value = err.message || 'Could not create debug link.'
  } finally {
    saving.value = false
  }
}

async function revokeShare() {
  saving.value = true
  error.value = ''
  try {
    const res = await props.apiRequest('/api/diagnostics/share', { method: 'DELETE' })
    if (!res.ok) {
      const data = await res.json()
      error.value = data.detail || 'Could not revoke debug link.'
      return
    }
    share.value = { active: false, url: '', expires_at: null, ttl_hours: 24 }
    copied.value = false
  } catch (err) {
    error.value = err.message || 'Could not revoke debug link.'
  } finally {
    saving.value = false
  }
}

async function setDebugEnabled(enabled) {
  if (enabled === share.value.active) return
  if (enabled) await createShare()
  else await revokeShare()
}

async function copyUrl() {
  if (!share.value.url) return
  try {
    await navigator.clipboard.writeText(share.value.url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch (err) {
    error.value = 'Copy failed. Select the URL manually.'
  }
}

function formatExpiry(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch (err) {
    return iso
  }
}

function formatWhen(ts) {
  if (!ts) return '—'
  const ms = ts > 1e12 ? ts : ts * 1000
  return new Date(ms).toLocaleString()
}

watch(section, () => {
  error.value = ''
  notice.value = ''
})

onMounted(loadAll)
</script>

<template>
  <section class="settings-page animate-fade">
    <div class="settings-header">
      <div>
        <h2 class="section-title">Settings</h2>
        <p class="section-subtitle">Manage this appliance after first-run. Bind mounts and the manager port stay in compose/env.</p>
      </div>
    </div>

    <nav class="settings-nav" aria-label="Settings sections">
      <button v-for="item in [
        ['account', 'Account'],
        ['general', 'General'],
        ['updates', 'Updates'],
        ['storage', 'Storage'],
        ['permissions', 'Permissions'],
        ['backups', 'Backups'],
        ['vpn', 'VPN'],
        ['remote', 'Remote access'],
        ['integrations', 'Integrations'],
        ['github', 'GitHub'],
        ['debug', 'Debug']
      ]" :key="item[0]" type="button" class="settings-nav-btn" :class="{ active: section === item[0] }" @click="section = item[0]">
        {{ item[1] }}
      </button>
    </nav>

    <div v-if="error" class="ui-alert ui-alert-error">{{ error }}</div>
    <p v-if="notice" class="share-meta">{{ notice }}</p>

    <template v-if="section === 'account'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">ACCOUNT</span>
          <h3>Administrator</h3>
          <p>Current password is required for any change. Email is used for Seerr wiring.</p>
        </div>
        <form class="form-stack" @submit.prevent="saveAccount">
          <label class="ui-field">Username
            <input v-model="form.username" class="ui-input" required />
          </label>
          <label class="ui-field">Email
            <input v-model="form.email" type="email" class="ui-input" required />
          </label>
          <label class="ui-field">Current password
            <input v-model="form.current_password" type="password" class="ui-input" required autocomplete="current-password" />
          </label>
          <label class="ui-field">New password (optional)
            <input v-model="form.new_password" type="password" class="ui-input" minlength="8" autocomplete="new-password" />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">{{ saving ? 'Saving…' : 'Save account' }}</button>
        </form>
      </div>
    </template>

    <template v-else-if="section === 'general'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>General</h3>
          <p>Timezone for logs and later update schedules. Log level applies immediately.</p>
        </div>
        <form class="form-stack" @submit.prevent="patchSettings({ timezone: form.timezone, log_level: form.log_level })">
          <label class="ui-field">Timezone
            <input v-model="form.timezone" class="ui-input font-mono" list="tz-list" />
            <datalist id="tz-list">
              <option value="UTC" />
              <option value="Europe/Amsterdam" />
              <option value="Europe/London" />
              <option value="America/New_York" />
              <option value="America/Los_Angeles" />
              <option value="Australia/Sydney" />
            </datalist>
          </label>
          <label class="ui-field">Log level
            <select v-model="form.log_level" class="ui-input">
              <option>DEBUG</option>
              <option>INFO</option>
              <option>WARNING</option>
              <option>ERROR</option>
            </select>
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save</button>
        </form>
        <p class="share-idle">Manager listen address {{ snapshot.api_host }}:{{ snapshot.api_port }} is compose/env only.</p>
      </div>
    </template>

    <template v-else-if="section === 'updates'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Updates</h3>
          <p>Check GitHub in the host timezone. Apply can stay off (notify only) or match the check schedule.</p>
        </div>
        <p class="share-meta" v-if="snapshot.updates">
          Last check {{ formatWhen(snapshot.updates.last_check_at) }}
          · last apply {{ formatWhen(snapshot.updates.last_apply_at) }}
          · {{ (snapshot.updates.available || []).length }} waiting
          <span v-if="snapshot.updates.paused"> · paused ({{ snapshot.updates.paused_reason }})</span>
        </p>
        <form class="form-stack" @submit.prevent="patchSettings({
          update_check_schedule: form.update_check_schedule,
          update_apply_schedule: form.update_apply_schedule,
          update_time: form.update_time,
          update_weekday: Number(form.update_weekday),
          update_day_of_month: Number(form.update_day_of_month)
        })">
          <label class="ui-field">Check schedule
            <select v-model="form.update_check_schedule" class="ui-input">
              <option value="off">Off</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          <label class="ui-field">Apply schedule
            <select v-model="form.update_apply_schedule" class="ui-input">
              <option value="off">Off (notify only)</option>
              <option value="same">Same as check</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          <label class="ui-field">Time of day
            <input v-model="form.update_time" type="time" class="ui-input font-mono" />
          </label>
          <label v-if="form.update_check_schedule === 'weekly' || form.update_apply_schedule === 'weekly'" class="ui-field">Weekday
            <select v-model.number="form.update_weekday" class="ui-input">
              <option :value="0">Monday</option>
              <option :value="1">Tuesday</option>
              <option :value="2">Wednesday</option>
              <option :value="3">Thursday</option>
              <option :value="4">Friday</option>
              <option :value="5">Saturday</option>
              <option :value="6">Sunday</option>
            </select>
          </label>
          <label v-if="form.update_check_schedule === 'monthly' || form.update_apply_schedule === 'monthly'" class="ui-field">Day of month
            <input v-model.number="form.update_day_of_month" type="number" min="1" max="28" class="ui-input font-mono" />
          </label>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save schedule</button>
            <button type="button" class="ui-btn ui-btn-ghost" :disabled="saving" @click="runUpdateCheck">Check now</button>
          </div>
        </form>
        <ul v-if="(snapshot.updates?.available || []).length" class="backup-list">
          <li v-for="item in snapshot.updates.available" :key="item.name">
            <div>
              <strong>{{ item.name }}</strong>
              <span class="path-line font-mono">{{ item.installed_version || '—' }} → {{ item.latest_version }}</span>
            </div>
          </li>
        </ul>
      </div>
    </template>

    <template v-else-if="section === 'storage'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">HOST</span>
          <h3>System info</h3>
          <p>Read-only. Changing bind mounts is a host/compose job; this UI does not remount disks.</p>
        </div>
        <dl class="info-grid">
          <div>
            <dt>Architecture</dt>
            <dd class="font-mono">{{ hostArch ? hostArch.toUpperCase() : '—' }}</dd>
          </div>
          <div>
            <dt>CPU</dt>
            <dd class="font-mono">
              {{ metrics.cpu_count || '—' }} cores
              · {{ metrics.cpu_percent != null ? Math.round(metrics.cpu_percent) + '%' : '—' }}
            </dd>
          </div>
          <div>
            <dt>Memory</dt>
            <dd class="font-mono">
              {{ formatBytes((metrics.memory?.total || 0) - (metrics.memory?.available || 0)) }}
              / {{ formatBytes(metrics.memory?.total) }}
            </dd>
          </div>
          <div>
            <dt>Hardlinks</dt>
            <dd>{{ hardlinks ? 'Supported between downloads and media' : 'Not available — *Arr will copy' }}</dd>
          </div>
          <div>
            <dt>Transcoding</dt>
            <dd>{{ transcoding.available ? 'Hardware GPU available' : 'Software only' }}</dd>
          </div>
        </dl>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Storage paths</h3>
          <p>Filesystem format and capacity. Edit mounts in docker-compose, not here.</p>
        </div>
        <div class="storage-table-wrap">
          <table class="storage-table">
            <thead>
              <tr><th>Path</th><th>Format</th><th>Capacity</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in storageRows" :key="row.label">
                <td>
                  <strong>{{ prettyLabel(row.label) }}</strong>
                  <span class="path-line font-mono">{{ row.path }}</span>
                </td>
                <td class="font-mono">{{ row.fs_type || '—' }}</td>
                <td class="font-mono">
                  {{ formatBytes(row.disk_used) }} / {{ formatBytes(row.disk_total) }}
                </td>
              </tr>
              <tr v-if="!storageRows.length">
                <td colspan="3" class="share-idle">System info is not loaded yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <template v-else-if="section === 'permissions'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Permissions</h3>
          <p>Saving PUID/PGID restarts running child processes so new files stay owned correctly.</p>
        </div>
        <form class="form-stack" @submit.prevent="patchSettings({ puid: Number(form.puid), pgid: Number(form.pgid) })">
          <label class="ui-field">PUID
            <input v-model.number="form.puid" type="number" min="1" class="ui-input font-mono" required />
          </label>
          <label class="ui-field">PGID
            <input v-model.number="form.pgid" type="number" min="1" class="ui-input font-mono" required />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save and restart children</button>
        </form>
      </div>
    </template>

    <template v-else-if="section === 'backups'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Backups</h3>
          <p>Config, secrets, and databases only — never media libraries. Stored in {{ snapshot.backup_dir }}.</p>
        </div>
        <form class="form-stack" @submit.prevent="patchSettings({ backup_retention: Number(form.backup_retention) })">
          <label class="ui-field">Keep last N backups
            <input v-model.number="form.backup_retention" type="number" min="1" max="90" class="ui-input font-mono" />
          </label>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-ghost" :disabled="saving">Save retention</button>
            <button type="button" class="ui-btn ui-btn-primary" :disabled="saving" @click="createBackup">Backup now</button>
          </div>
        </form>
        <ul class="backup-list">
          <li v-for="item in backups" :key="item.name">
            <div>
              <strong class="font-mono">{{ item.name }}</strong>
              <span class="path-line">{{ formatWhen(item.modified_at) }} · {{ formatBytes(item.size_bytes) }}</span>
            </div>
            <div class="share-row">
              <button type="button" class="ui-btn ui-btn-ghost" @click="restoreBackup(item.name)">Restore</button>
              <button type="button" class="ui-btn ui-btn-ghost" @click="deleteBackup(item.name)">Delete</button>
            </div>
          </li>
          <li v-if="!backups.length" class="share-idle">No backups yet.</li>
        </ul>
      </div>
    </template>

    <template v-else-if="section === 'vpn'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>VPN</h3>
          <p>qBittorrent, Prowlarr, and Flaresolverr. Usenet always bypasses the tunnel.</p>
        </div>
        <p class="share-meta">Tunnel {{ vpnLive.tunnel_up ? 'up' : 'down' }} · config {{ vpnLive.config_present ? 'present' : 'missing' }}</p>
        <form class="form-stack" @submit.prevent="saveVpn">
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>Enable VPN</strong>
              <span>Starts or stops the tunnel when you save.</span>
            </div>
            <button type="button" class="ui-switch" role="switch" :aria-checked="form.vpn_enabled ? 'true' : 'false'" @click="form.vpn_enabled = !form.vpn_enabled">
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>Kill switch / enforce</strong>
              <span>Block tunneled apps when the tunnel is down.</span>
            </div>
            <button type="button" class="ui-switch" role="switch" :aria-checked="form.vpn_enforce ? 'true' : 'false'" @click="form.vpn_enforce = !form.vpn_enforce">
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <label class="ui-field">Provider
            <select v-model="form.vpn_provider" class="ui-input">
              <option v-for="p in (vpnLive.supported_providers || ['privadovpn','custom'])" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
          <VpnConfigFields
            v-model:protocol="form.vpn_protocol"
            v-model:path="form.vpn_config_path"
            v-model:text="form.vpn_config_text"
            :has-config="!!vpnLive.config_present"
          />
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save VPN</button>
        </form>
      </div>
    </template>

    <template v-else-if="section === 'remote'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Remote access</h3>
          <p>Cloudflare Tunnel token is stored on disk and never shown again. Trusted proxies are comma-separated IPs/CIDRs.</p>
        </div>
        <p class="share-meta">
          Tunnel {{ tunnelLive.connected ? 'connected' : 'not connected' }}
          · token {{ tunnelLive.token_present ? 'present' : 'missing' }}
          · binary {{ tunnelLive.binary_present ? 'found' : 'not found' }}
        </p>
        <form class="form-stack" @submit.prevent="patchSettings({
          cloudflare_tunnel_enabled: form.cloudflare_tunnel_enabled,
          cloudflare_tunnel_token: form.cloudflare_tunnel_token || undefined,
          trusted_proxies: form.trusted_proxies
        })">
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>Cloudflare Tunnel</strong>
              <span>Requires cloudflared in the image and a tunnel token.</span>
            </div>
            <button type="button" class="ui-switch" role="switch" :aria-checked="form.cloudflare_tunnel_enabled ? 'true' : 'false'" @click="form.cloudflare_tunnel_enabled = !form.cloudflare_tunnel_enabled">
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <label class="ui-field">Tunnel token (leave blank to keep)
            <input v-model="form.cloudflare_tunnel_token" type="password" class="ui-input font-mono" autocomplete="off" />
          </label>
          <label class="ui-field">Trusted reverse-proxy IPs
            <input v-model="form.trusted_proxies" class="ui-input font-mono" placeholder="10.0.0.1,10.0.0.0/8" />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save</button>
        </form>
      </div>
    </template>

    <template v-else-if="section === 'integrations'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Jellyfin API key</h3>
          <p>
            Homepage Recently added uses this key. Create one in Jellyfin Dashboard → API Keys
            (or paste the access token). Leave blank and save to clear it.
          </p>
        </div>
        <p class="share-meta">{{ jellyfinConfigured ? 'A Jellyfin API key is saved.' : 'No Jellyfin API key saved yet.' }}</p>
        <form class="form-stack" @submit.prevent="patchSettings({ jellyfin_api_key: form.jellyfin_api_key })">
          <label class="ui-field">API key
            <input v-model="form.jellyfin_api_key" type="password" class="ui-input font-mono" autocomplete="off" />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save API key</button>
        </form>
      </div>
    </template>

    <template v-else-if="section === 'github'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>GitHub</h3>
          <p>Optional token so catalog installs and later scheduled updates stay under the authenticated rate limit.</p>
        </div>
        <p class="share-meta">{{ githubConfigured ? 'A token is saved.' : 'No token configured.' }}</p>
        <form class="form-stack" @submit.prevent="patchSettings({ github_token: form.github_token })">
          <label class="ui-field">Personal access token (blank clears it)
            <input v-model="form.github_token" type="password" class="ui-input font-mono" autocomplete="off" />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save token</button>
        </form>
      </div>
    </template>

    <template v-else>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">DEBUG</span>
          <h3>Error manager</h3>
          <p>
            Capture recent errors behind a time-limited URL for support. Secrets are redacted.
            The link expires after {{ share.ttl_hours || 24 }} hours.
          </p>
        </div>
        <div class="ui-switch-row">
          <div class="ui-switch-copy">
            <strong>Debug share URL</strong>
            <span>When on, a time-limited link is available for support.</span>
          </div>
          <button
            type="button"
            class="ui-switch"
            role="switch"
            :aria-checked="share.active ? 'true' : 'false'"
            :disabled="loading || saving"
            @click="setDebugEnabled(!share.active)"
          >
            <span class="ui-switch-thumb"></span>
          </button>
        </div>
        <div v-if="share.active && share.url" class="share-box">
          <label class="ui-field" for="debug-share-url">Share URL</label>
          <div class="share-row">
            <input id="debug-share-url" class="ui-input font-mono" :value="share.url" readonly />
            <button type="button" class="ui-btn ui-btn-ghost" @click="copyUrl">{{ copied ? 'Copied' : 'Copy' }}</button>
          </div>
          <p class="share-meta font-mono">Expires {{ formatExpiry(share.expires_at) }}</p>
        </div>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Recent errors</h3>
          <p>Last captured ERROR+ events from this manager process.</p>
        </div>
        <div v-if="!errors.length" class="share-idle">No errors captured since startup.</div>
        <pre v-else class="error-log font-mono">{{ errors.map(e => `[${e.timestamp}] ${e.level} ${e.source}\n${e.message}`).join('\n\n') }}</pre>
      </div>
    </template>
  </section>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  min-width: 0;
}
.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 0.75rem;
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
.settings-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.settings-nav-btn {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}
.settings-nav-btn.active {
  color: #e0f2fe;
  background: rgba(14, 165, 233, 0.18);
  border-color: rgba(56, 189, 248, 0.45);
}
.settings-card {
  padding: 1.4rem 1.5rem;
  min-width: 0;
}
.settings-card-head h3 {
  margin: 0.4rem 0 0.35rem;
  font-size: 1.05rem;
  color: #fff;
}
.settings-card-head p {
  color: #94a3b8;
  margin: 0 0 1rem;
  max-width: min(62ch, 100%);
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
}
.form-stack {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  max-width: 36rem;
}
.info-grid {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}
.info-grid div {
  padding: 0.75rem 0.85rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.08);
  min-width: 0;
}
.info-grid dt {
  color: #64748b;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.info-grid dd {
  margin: 0.3rem 0 0;
  color: #e2e8f0;
  font-size: 0.9rem;
  overflow-wrap: anywhere;
}
.storage-table-wrap {
  overflow-x: auto;
  min-width: 0;
}
.storage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.storage-table th {
  text-align: left;
  color: #64748b;
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.4rem 0.6rem 0.65rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.storage-table td {
  padding: 0.75rem 0.6rem;
  color: #cbd5e1;
  vertical-align: top;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.storage-table strong {
  display: block;
  color: #f8fafc;
  text-transform: capitalize;
  margin-bottom: 0.15rem;
}
.path-line {
  display: block;
  color: #64748b;
  font-size: 0.75rem;
  overflow-wrap: anywhere;
}
.share-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.share-row .ui-input {
  flex: 1 1 12rem;
  min-width: 0;
}
.share-meta,
.share-idle {
  color: #94a3b8;
  font-size: 0.85rem;
  margin-top: 0.55rem;
}
.share-box {
  margin-top: 1rem;
}
.backup-list {
  list-style: none;
  margin: 1rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}
.backup-list li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 0.85rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.error-log {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 1rem;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 0.78rem;
  color: #cbd5e1;
}
@media (max-width: 640px) {
  .settings-card {
    padding: 1.1rem;
  }
  .share-row .ui-btn {
    width: 100%;
  }
}
</style>
