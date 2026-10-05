<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { resolveSettingsSection, SETTINGS_NAV } from './router'
import { apiError, apiRequest, readJson } from './api.js'
import { startGuardedInterval } from './pageVisible.js'
import { readHomepageWidgetDebug, writeHomepageWidgetDebug } from './homepageDebug.js'
import VpnConfigFields from './VpnConfigFields.vue'
import {
  canPromptInstall,
  isIosDevice,
  isStandaloneDisplay,
  promptInstall,
  subscribePwaInstall,
} from './pwaInstall.js'
import {
  THEME_OPTIONS,
  getThemePreference,
  setThemePreference,
} from './theme.js'
import {
  ACCENT_PRESETS,
  DEFAULT_ACCENT,
  applyBranding,
} from './branding.js'
import { copyText } from './clipboard.js'

const props = defineProps({
  systemInfo: { type: Object, default: null },
  hostArch: { type: String, default: '' }
})
const emit = defineEmits(['session', 'updates', 'vpn'])
const route = useRoute()
const section = computed(() => resolveSettingsSection(route.params.section))
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const share = ref({ active: false, url: '', expires_at: null, ttl_hours: 24 })
const errors = ref([])
const copied = ref(false)
const backups = ref([])
const backupInfo = ref({ backup_dir: '', legacy_dir: '', schedule: {} })
const backupJob = ref(null)
const restoreTarget = ref(null)
const uploading = ref(false)
let stopJobPollFn = null
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
  backup_schedule: 'daily',
  backup_time: '03:30',
  backup_weekday: 0,
  backup_day_of_month: 1,
  vpn_enabled: false,
  vpn_provider: 'privadovpn',
  vpn_protocol: 'wireguard',
  vpn_config_path: '',
  vpn_config_text: '',
  cloudflare_tunnel_enabled: false,
  cloudflare_tunnel_token: '',
  cloudflare_api_token: '',
  trusted_proxies: '',
  public_app_base_domain: '',
  github_token: '',
  jellyfin_api_key: '',
  seerr_api_key: '',
  update_check_schedule: 'off',
  update_apply_schedule: 'off',
  update_time: '04:00',
  update_weekday: 0,
  update_day_of_month: 1,
  brand_title: 'AIO Media Server Manager',
  accent_color: DEFAULT_ACCENT,
})
const branding = ref({
  title: 'AIO Media Server Manager',
  accent_color: DEFAULT_ACCENT,
  default_accent: DEFAULT_ACCENT,
  accent_custom: false,
  slots: {},
})
const brandUploading = ref('')
const profileAvatar = ref({
  avatar_url: null,
  has_avatar: false,
  recommended: '512 × 512 px (square)',
  help: 'Shown in the top bar instead of your username initial.',
})
const avatarUploading = ref(false)
const snapshot = ref({})
const vpnLive = ref({})
const vpnBusy = ref(false)
const tunnelLive = ref({})
const hostnameRoutes = ref([])
const apiTokenConfigured = ref(false)
const hostnameBusy = ref(false)
const hostnameMeta = ref({ tunnel_id: '', tunnel_account_id: '', tunnel_decode_error: '' })
const githubConfigured = ref(false)
const jellyfinConfigured = ref(false)
const seerrConfigured = ref(false)
const widgetDebug = ref(false)
const pwaStandalone = ref(false)
const pwaCanInstall = ref(false)
const pwaIos = ref(false)
const themePreference = ref(getThemePreference())
let stopPwa = null

function refreshPwaInstall() {
  pwaStandalone.value = isStandaloneDisplay()
  pwaCanInstall.value = canPromptInstall()
  pwaIos.value = isIosDevice()
}

function chooseTheme(pref) {
  setThemePreference(pref)
  themePreference.value = getThemePreference()
  notice.value = `Theme set to ${themePreference.value}.`
}

function applyBrandingPayload(data) {
  const payload = data || {}
  branding.value = {
    title: payload.title || 'AIO Media Server Manager',
    accent_color: payload.accent_color || DEFAULT_ACCENT,
    default_accent: payload.default_accent || DEFAULT_ACCENT,
    accent_custom: !!payload.accent_custom,
    slots: payload.slots || {},
  }
  form.value.brand_title = branding.value.title
  form.value.accent_color = branding.value.accent_color
  applyBranding(payload)
}

function normalizeAccentInput(value) {
  let text = String(value || '').trim()
  if (!text) return DEFAULT_ACCENT
  if (!text.startsWith('#')) text = `#${text}`
  return text.toLowerCase()
}

async function saveBrandTitle() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest('/api/branding', {
      method: 'PATCH',
      body: JSON.stringify({ title: form.value.brand_title }),
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not save title.')
      return
    }
    applyBrandingPayload(data)
    notice.value = 'Brand title saved.'
  } catch (err) {
    error.value = err.message || 'Could not save title.'
  } finally {
    saving.value = false
  }
}

async function saveAccentColor(next) {
  const raw = String(next != null ? next : (form.value.accent_color || '')).trim()
  const reset = !raw || raw.toLowerCase() === 'default'
  let accent = DEFAULT_ACCENT
  if (!reset) {
    accent = normalizeAccentInput(raw)
    if (!/^#[0-9a-f]{6}$/.test(accent)) {
      error.value = 'Accent must be a hex color like #f97316.'
      return
    }
  }
  form.value.accent_color = accent
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest('/api/branding', {
      method: 'PATCH',
      body: JSON.stringify({ accent_color: reset ? 'default' : accent }),
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not save accent color.')
      return
    }
    applyBrandingPayload(data)
    notice.value = reset ? 'Accent color reset to default.' : 'Accent color saved.'
  } catch (err) {
    error.value = err.message || 'Could not save accent color.'
  } finally {
    saving.value = false
  }
}

function resetAccentColor() {
  return saveAccentColor('default')
}

async function uploadBrandSlot(slot, event) {
  const file = event?.target?.files?.[0]
  if (!file) return
  brandUploading.value = slot
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest(`/api/branding/${slot}`, {
      method: 'PUT',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not upload image.')
      return
    }
    applyBrandingPayload(data)
    notice.value = `${branding.value.slots?.[slot]?.label || 'Image'} updated.`
  } catch (err) {
    error.value = err.message || 'Could not upload image.'
  } finally {
    brandUploading.value = ''
    if (event?.target) event.target.value = ''
  }
}

async function resetBrandSlot(slot) {
  brandUploading.value = slot
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest(`/api/branding/${slot}`, { method: 'DELETE' })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not reset image.')
      return
    }
    applyBrandingPayload(data)
    notice.value = `${data.slots?.[slot]?.label || 'Image'} reset to default.`
  } catch (err) {
    error.value = err.message || 'Could not reset image.'
  } finally {
    brandUploading.value = ''
  }
}

async function installPwaFromSettings() {
  const ok = await promptInstall()
  if (ok) notice.value = 'App installed on this device.'
  refreshPwaInstall()
}

function toggleHomepageWidgetDebug() {
  widgetDebug.value = !widgetDebug.value
  writeHomepageWidgetDebug(widgetDebug.value)
}

const jellyfinKey = computed(() => snapshot.value.homepage_keys?.jellyfin || { configured: jellyfinConfigured.value })
const seerrKey = computed(() => snapshot.value.homepage_keys?.seerr || { configured: seerrConfigured.value })

function credentialChip(status) {
  const s = status || {}
  if (s.working) return { label: 'Working', cls: 'is-on' }
  if (s.configured && s.running) return { label: 'Saved, not working', cls: 'is-bad' }
  if (s.configured && s.installed && !s.running) return { label: 'Saved · app stopped', cls: 'is-warn' }
  if (s.configured) return { label: 'Saved', cls: 'is-on' }
  if (s.running) return { label: 'Running, no key', cls: 'is-warn' }
  return { label: 'Not saved', cls: 'is-off' }
}

async function refreshSettings() {
  try {
    const res = await apiRequest('/api/settings')
    if (res.ok) applySettingsPayload(await readJson(res))
  } catch (err) {
    console.error('Settings refresh error:', err)
  }
}

async function refreshTunnelStatus() {
  try {
    const res = await apiRequest('/api/cloudflare/tunnel/status')
    if (res.ok) tunnelLive.value = await readJson(res)
  } catch (err) {
    console.error('Cloudflare tunnel status error:', err)
  }
}

async function pollTunnelUntilSettled(attempts = 8, delayMs = 1000) {
  for (let i = 0; i < attempts; i += 1) {
    await refreshTunnelStatus()
    const t = tunnelLive.value || {}
    if (!t.enabled) return
    if (t.connected || (!t.token_present && !t.token_saved)) return
    if (t.process && t.process !== 'running' && t.process !== 'starting' && i >= 2) return
    await new Promise((r) => setTimeout(r, delayMs))
  }
}

async function saveCloudflare() {
  const ok = await patchSettings({
    cloudflare_tunnel_enabled: form.value.cloudflare_tunnel_enabled,
    cloudflare_tunnel_token: form.value.cloudflare_tunnel_token || undefined,
    trusted_proxies: form.value.trusted_proxies,
    public_app_base_domain: form.value.public_app_base_domain
  })
  if (!ok) return
  await pollTunnelUntilSettled()
  await refreshHostnames()
  const t = tunnelLive.value || {}
  if (form.value.cloudflare_tunnel_enabled && !t.connected) {
    error.value = t.summary || 'Tunnel is enabled but not connected yet. Check cloudflared logs.'
  } else if (form.value.cloudflare_tunnel_enabled && t.connected) {
    notice.value = 'Cloudflare Tunnel connected. Token saved on disk.'
  }
}

function hostnamePayload() {
  const hostnames = {}
  for (const row of hostnameRoutes.value || []) {
    hostnames[row.name] = {
      subdomain: String(row.subdomain || row.default_subdomain || row.name).trim().toLowerCase(),
      enabled: !!row.enabled,
    }
  }
  return hostnames
}

async function refreshHostnames() {
  try {
    const res = await apiRequest('/api/cloudflare/hostnames')
    if (!res.ok) return
    const data = await readJson(res)
    hostnameRoutes.value = (data.routes || []).map((row) => ({ ...row }))
    apiTokenConfigured.value = !!data.api_token_configured
    hostnameMeta.value = {
      tunnel_id: data.tunnel_id || '',
      tunnel_account_id: data.tunnel_account_id || '',
      tunnel_decode_error: data.tunnel_decode_error || '',
    }
    if (data.public_app_base_domain != null) {
      form.value.public_app_base_domain = data.public_app_base_domain || ''
    }
  } catch (err) {
    console.error('Hostname list error:', err)
  }
}

async function saveHostnames() {
  hostnameBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    const body = {
      hostnames: hostnamePayload(),
      public_app_base_domain: form.value.public_app_base_domain,
    }
    if (form.value.cloudflare_api_token) {
      body.cloudflare_api_token = form.value.cloudflare_api_token
    }
    const res = await apiRequest('/api/cloudflare/hostnames', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not save subdomains.')
      return
    }
    hostnameRoutes.value = (data.routes || []).map((row) => ({ ...row }))
    apiTokenConfigured.value = !!data.api_token_configured
    form.value.cloudflare_api_token = ''
    form.value.public_app_base_domain = data.public_app_base_domain || form.value.public_app_base_domain
    notice.value = 'Subdomains saved. Open UI will use them on HTTPS / public access.'
  } catch (err) {
    error.value = err?.message || 'Could not save subdomains.'
  } finally {
    hostnameBusy.value = false
  }
}

async function clearCloudflareApiToken() {
  hostnameBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest('/api/cloudflare/hostnames', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hostnames: hostnamePayload(),
        cloudflare_api_token: '',
      }),
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not clear API token.')
      return
    }
    apiTokenConfigured.value = !!data.api_token_configured
    form.value.cloudflare_api_token = ''
    notice.value = 'Cloudflare API token cleared.'
  } catch (err) {
    error.value = err?.message || 'Could not clear API token.'
  } finally {
    hostnameBusy.value = false
  }
}

async function publishHostnames() {
  const enabled = (hostnameRoutes.value || []).filter((row) => row.enabled)
  const count = enabled.length
  const preview = enabled
    .slice(0, 6)
    .map((row) => previewHostnameUrl(row))
    .filter((u) => u && u !== '—')
    .join('\n')
  const okConfirm = window.confirm(
    [
      count
        ? `Publish ${count} hostname${count === 1 ? '' : 's'} to Cloudflare?`
        : 'Disable previously published hostnames in the tunnel?',
      preview ? `\n${preview}${count > 6 ? '\n…' : ''}` : '',
      '\nThese URLs are reachable from the internet unless you add Cloudflare Access.',
      'Dashboard-only routes you never published from AIO are left alone.',
    ].join('\n'),
  )
  if (!okConfirm) return
  hostnameBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    if (form.value.cloudflare_api_token) {
      const saveRes = await apiRequest('/api/cloudflare/hostnames', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hostnames: hostnamePayload(),
          public_app_base_domain: form.value.public_app_base_domain,
          cloudflare_api_token: form.value.cloudflare_api_token,
        }),
      })
      const saveData = await readJson(saveRes)
      if (!saveRes.ok) {
        error.value = apiError(saveData, 'Could not save API token before publish.')
        return
      }
      form.value.cloudflare_api_token = ''
      apiTokenConfigured.value = !!saveData.api_token_configured
    }
    const res = await apiRequest('/api/cloudflare/hostnames/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hostnames: hostnamePayload(),
        public_app_base_domain: form.value.public_app_base_domain,
      }),
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Publish to Cloudflare failed.')
      return
    }
    await refreshHostnames()
    const published = (data.published || []).length
    const removed = (data.removed || []).length
    const bits = [`Published ${published} hostname${published === 1 ? '' : 's'} to Cloudflare`]
    if (removed) bits.push(`removed ${removed} from the tunnel`)
    notice.value = `${bits.join('; ')}.${data.warning ? ` ${data.warning}` : ''}`
  } catch (err) {
    error.value = err?.message || 'Publish to Cloudflare failed.'
  } finally {
    hostnameBusy.value = false
  }
}

function previewHostnameUrl(row) {
  const base = String(form.value.public_app_base_domain || '')
    .trim()
    .replace(/^\.+|\.+$/g, '')
    .toLowerCase()
  const sub = String(row.subdomain || row.default_subdomain || row.name || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '')
  if (!base || !sub) return '—'
  return `https://${sub}.${base}`
}

async function saveHomepageKey(field) {
  const value = String(form.value[field] || '').trim()
  if (!value) {
    error.value = 'Paste a key to save it, or use Clear key.'
    notice.value = ''
    return
  }
  await patchSettings({ [field]: value })
}

async function clearHomepageKey(field) {
  await patchSettings({ [field]: '' })
}

const metrics = computed(() => props.systemInfo?.metrics || {})
const diskRemaining = computed(() => {
  const disk = metrics.value.disk || {}
  if (disk.free != null) return Number(disk.free) || 0
  const total = Number(disk.total) || 0
  const used = Number(disk.used) || 0
  return Math.max(0, total - used)
})
const storage = computed(() => snapshot.value.storage || props.systemInfo?.storage || {})
const transcoding = computed(() => props.systemInfo?.transcoding || {})
const storageRows = computed(() =>
  Object.entries(storage.value).map(([label, info]) => ({ label, ...info }))
)
const hardlinks = computed(() => {
  const flag = storage.value?.download_dir?.hardlinks_supported
  if (flag === undefined) return null
  return flag !== false
})

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

function applySettingsPayload(data) {
  snapshot.value = data || {}
  form.value.timezone = data.timezone || 'UTC'
  form.value.log_level = data.log_level || 'INFO'
  form.value.puid = data.puid || 1000
  form.value.pgid = data.pgid || 1000
  form.value.backup_retention = data.backup_retention || 7
  form.value.trusted_proxies = data.trusted_proxies || ''
  form.value.public_app_base_domain = data.public_app_base_domain || ''
  const vpn = data.vpn || {}
  vpnLive.value = vpn
  form.value.vpn_enabled = !!vpn.enabled
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
  jellyfinConfigured.value = !!(data.homepage_keys?.jellyfin?.configured ?? data.jellyfin_api_key_configured)
  form.value.jellyfin_api_key = ''
  seerrConfigured.value = !!(data.homepage_keys?.seerr?.configured ?? data.seerr_api_key_configured)
  form.value.seerr_api_key = ''
  const updates = data.updates || {}
  form.value.update_check_schedule = updates.check_schedule || 'off'
  form.value.update_apply_schedule = updates.apply_schedule || 'off'
  form.value.update_time = updates.time || '04:00'
  form.value.update_weekday = updates.weekday ?? 0
  form.value.update_day_of_month = updates.day_of_month || 1
  const bak = data.backups || {}
  form.value.backup_schedule = bak.schedule || 'off'
  form.value.backup_time = bak.time || '03:30'
  form.value.backup_weekday = bak.weekday ?? 0
  form.value.backup_day_of_month = bak.day_of_month || 1
  if (data.branding) applyBrandingPayload(data.branding)
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [meRes, setRes, bakRes, diagRes] = await Promise.all([
      apiRequest('/api/auth/me'),
      apiRequest('/api/settings'),
      apiRequest('/api/backups'),
      apiRequest('/api/diagnostics')
    ])
    if (meRes.ok) {
      const me = await readJson(meRes)
      form.value.username = me.username || 'admin'
      form.value.email = me.email || ''
      applyProfileAvatar(me)
    }
    if (setRes.ok) applySettingsPayload(await readJson(setRes))
    else error.value = 'Could not load settings.'
    if (bakRes.ok) {
      const bak = await readJson(bakRes)
      backups.value = bak.backups || []
      backupInfo.value = bak
      if (bak.job?.status === 'running' && !stopJobPollFn) watchJob(bak.job)
      else if (!stopJobPollFn) backupJob.value = bak.job
    }
    if (diagRes.ok) {
      const diag = await readJson(diagRes)
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
    const res = await apiRequest('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not save settings.')
      return false
    }
    applySettingsPayload(data)
    const notes = (data.notes && data.notes.join(' ')) || ''
    if (Object.prototype.hasOwnProperty.call(payload, 'vpn_enabled')) {
      emit('vpn', data.vpn)
      if (payload.vpn_enabled && !data.vpn?.tunnel_up) {
        error.value = notes || data.vpn?.last_error || 'VPN tunnel did not come up.'
      } else {
        notice.value = notes || (payload.vpn_enabled ? 'VPN started.' : 'VPN stopped.')
      }
    } else {
      notice.value = notes || 'Saved.'
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'update_check_schedule')) emit('updates')
    return true
  } catch (err) {
    error.value = err.message || 'Could not save settings.'
    return false
  } finally {
    saving.value = false
  }
}

async function toggleVpn() {
  if (saving.value || vpnBusy.value) return
  saving.value = true
  const next = !form.value.vpn_enabled
  form.value.vpn_enabled = next
  const ok = await patchSettings({ vpn_enabled: next })
  if (!ok) form.value.vpn_enabled = !next
}

async function saveVpn() {
  // Do not resend vpn_enabled here — that would stop qBittorrent/Prowlarr and
  // bounce the tunnel. Enable/disable is only via the switch (toggleVpn).
  const payload = {
    vpn_provider: form.value.vpn_provider,
    vpn_protocol: form.value.vpn_protocol,
    vpn_config_path: form.value.vpn_config_path
  }
  if (form.value.vpn_config_text) payload.vpn_config_text = form.value.vpn_config_text
  await patchSettings(payload)
}

async function controlVpn(action) {
  if (vpnBusy.value || saving.value) return
  if (!['start', 'stop', 'restart'].includes(action)) return
  vpnBusy.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest(`/api/vpn/${action}`, { method: 'POST' })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, `Could not ${action} VPN.`)
      return
    }
    vpnLive.value = data
    form.value.vpn_enabled = !!data.enabled
    emit('vpn', data)
    const apps = (data.started_apps || []).join(', ')
    if (action === 'start' || action === 'restart') {
      if (data.tunnel_up) {
        notice.value = apps
          ? `VPN ${action === 'restart' ? 'restarted' : 'started'}. Started ${apps} on the tunnel.`
          : `VPN ${action === 'restart' ? 'restarted' : 'started'}.`
      } else {
        error.value = data.detail || data.last_error || 'VPN tunnel did not come up.'
      }
    } else if (data.enabled) {
      notice.value = 'VPN tunnel stopped. Kill switch stays on until you turn Enable VPN off.'
    } else {
      notice.value = apps
        ? `VPN stopped. Started ${apps} on the house network.`
        : 'VPN stopped.'
    }
  } catch (err) {
    error.value = err.message || `Could not ${action} VPN.`
  } finally {
    vpnBusy.value = false
  }
}

function applyProfileAvatar(data) {
  const payload = data || {}
  profileAvatar.value = {
    avatar_url: payload.avatar_url || null,
    has_avatar: !!payload.has_avatar || !!payload.avatar_url,
    recommended: payload.recommended || '512 × 512 px (square)',
    help:
      payload.help ||
      'Shown in the top bar instead of your username initial.',
  }
}

async function uploadProfileAvatar(event) {
  const file = event?.target?.files?.[0]
  if (!file) return
  avatarUploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest('/api/auth/avatar', {
      method: 'PUT',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not upload profile image.')
      return
    }
    applyProfileAvatar(data)
    emit('session', data)
    notice.value = 'Profile image updated.'
  } catch (err) {
    error.value = err.message || 'Could not upload profile image.'
  } finally {
    avatarUploading.value = false
    if (event?.target) event.target.value = ''
  }
}

async function resetProfileAvatar() {
  avatarUploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest('/api/auth/avatar', { method: 'DELETE' })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not remove profile image.')
      return
    }
    applyProfileAvatar(data)
    emit('session', { ...data, avatar_url: null })
    notice.value = 'Profile image removed.'
  } catch (err) {
    error.value = err.message || 'Could not remove profile image.'
  } finally {
    avatarUploading.value = false
  }
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
    const res = await apiRequest('/api/auth/account', {
      method: 'PATCH',
      body: JSON.stringify(body)
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not update account.')
      return
    }
    form.value.current_password = ''
    form.value.new_password = ''
    if (data.avatar_url !== undefined) applyProfileAvatar(data)
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
    const res = await apiRequest('/api/updates/check', { method: 'POST' })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Update check failed.')
      return
    }
    const count = (data.available || []).length
    notice.value = count ? `${count} update(s) available.` : 'No updates found.'
    await loadAll()
    emit('updates')
  } catch (err) {
    error.value = err.message || 'Update check failed.'
  } finally {
    saving.value = false
  }
}

const backupJobRunning = computed(() => backupJob.value?.status === 'running')
const backupOnConfigVolume = computed(() => {
  const dir = backupInfo.value.backup_dir || ''
  const config = snapshot.value.config_dir || ''
  return !!dir && !!config && (dir === config || dir.startsWith(`${config}/`))
})
const backupJobPercent = computed(() => {
  const job = backupJob.value
  if (!job || !job.total) return 0
  return Math.min(100, Math.round((job.done / job.total) * 100))
})

function stopJobPoll() {
  if (stopJobPollFn) stopJobPollFn()
  stopJobPollFn = null
}

function describeJob(job) {
  const result = job.result || {}
  if (job.status === 'error') return `${job.kind} failed: ${job.error}`
  if (job.kind === 'backup') {
    const warn = (result.warnings || []).length
    return `Created ${result.name}${warn ? ` with ${warn} warning(s)` : ''}.`
  }
  if (job.kind === 'verify') {
    return result.ok
      ? `${result.name} is intact (${result.checked} files checked).`
      : `${result.name} failed verification: ${result.error}`
  }
  if (job.kind === 'restore') {
    const parts = [`Restored ${result.files} files (${(result.sections || []).join(', ')}).`]
    if (result.safety_backup) parts.push(`Previous state saved as ${result.safety_backup}.`)
    if ((result.restarted || []).length) parts.push(`Restarted ${result.restarted.join(', ')}.`)
    if ((result.restart_failed || []).length) parts.push(`Could not restart ${result.restart_failed.join(', ')}.`)
    return parts.join(' ')
  }
  return 'Done.'
}

function watchJob(job) {
  backupJob.value = job
  stopJobPoll()
  if (!job || job.status !== 'running') return
  stopJobPollFn = startGuardedInterval(async () => {
    try {
      const res = await apiRequest('/api/backups/job')
      if (!res.ok) return
      const data = await readJson(res)
      backupJob.value = data.job
      if (!data.job || data.job.status !== 'running') {
        stopJobPoll()
        if (data.job?.status === 'error' || (data.job?.kind === 'verify' && !data.job?.result?.ok)) {
          error.value = describeJob(data.job)
        } else if (data.job) {
          notice.value = describeJob(data.job)
        }
        await loadAll()
      }
    } catch (_) {
      /* keep polling */
    }
  }, 1000)
}

async function startBackupJob(endpoint, body) {
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest(endpoint, { method: 'POST', body: JSON.stringify(body || {}) })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Backup action failed.')
      return
    }
    watchJob(data.job)
  } catch (err) {
    error.value = err.message
  }
}

function createBackup() {
  return startBackupJob('/api/backups', { label: 'manual' })
}

function verifyBackup(name) {
  return startBackupJob(`/api/backups/${encodeURIComponent(name)}/verify`)
}

async function openRestore(name) {
  error.value = ''
  const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}`)
  const data = await readJson(res)
  if (!res.ok) {
    error.value = apiError(data, 'Could not read backup.')
    return
  }
  restoreTarget.value = { name, sections: data.sections || [], selected: ['all'] }
}

function toggleRestoreSection(value) {
  const target = restoreTarget.value
  if (!target) return
  if (value === 'all') {
    target.selected = ['all']
    return
  }
  const picked = new Set(target.selected.filter((item) => item !== 'all'))
  if (picked.has(value)) picked.delete(value)
  else picked.add(value)
  target.selected = picked.size ? [...picked] : ['all']
}

async function confirmRestore() {
  const target = restoreTarget.value
  if (!target) return
  const scope = target.selected.includes('all') ? 'everything' : target.selected.join(', ')
  if (!window.confirm(`Restore ${scope} from ${target.name}? Affected apps are stopped, the current state is saved first, then apps restart.`)) return
  restoreTarget.value = null
  await startBackupJob(`/api/backups/${encodeURIComponent(target.name)}/restore`, {
    sections: target.selected.includes('all') ? null : target.selected,
  })
}

async function downloadBackup(name) {
  error.value = ''
  try {
    const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}/download`)
    if (!res.ok) {
      const data = await readJson(res)
      error.value = apiError(data, `Download failed (HTTP ${res.status}).`)
      return
    }
    const url = URL.createObjectURL(await res.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = name
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    error.value = err.message
  }
}

async function uploadBackup(event) {
  const file = event.target?.files?.[0]
  if (event.target) event.target.value = ''
  if (!file) return
  uploading.value = true
  error.value = ''
  notice.value = ''
  try {
    const res = await apiRequest(`/api/backups/upload?filename=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      body: file,
      json: false,
      headers: { 'Content-Type': 'application/octet-stream' },
    })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Upload failed.')
      return
    }
    notice.value = `Uploaded ${data.backup?.name || file.name}. Verify it, then restore when ready.`
    await loadAll()
  } catch (err) {
    error.value = err.message
  } finally {
    uploading.value = false
  }
}

async function deleteBackup(name) {
  if (!window.confirm(`Delete ${name}?`)) return
  const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}`, { method: 'DELETE' })
  if (res.ok) await loadAll()
}

function backupKindLabel(item) {
  return {
    manual: 'Manual',
    scheduled: 'Scheduled',
    'pre-restore': 'Before restore',
    uploaded: 'Uploaded',
  }[item.kind] || item.kind
}

async function loadStatus() {
  const res = await apiRequest('/api/diagnostics')
  if (!res.ok) return
  const data = await readJson(res)
  share.value = data.share || share.value
  errors.value = data.errors || []
}

async function createShare() {
  saving.value = true
  error.value = ''
  copied.value = false
  try {
    const res = await apiRequest('/api/diagnostics/share', { method: 'POST' })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not create debug link.')
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
    const res = await apiRequest('/api/diagnostics/share', { method: 'DELETE' })
    if (!res.ok) {
      const data = await readJson(res)
      error.value = apiError(data, 'Could not revoke debug link.')
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
  error.value = ''
  try {
    await copyText(share.value.url)
    copied.value = true
    notice.value = 'Support share URL copied.'
    setTimeout(() => { copied.value = false }, 2500)
  } catch (err) {
    // Last resort: select the readonly field so the user can Cmd/Ctrl+C.
    const field = document.getElementById('debug-share-url')
    if (field && typeof field.select === 'function') {
      field.focus()
      field.select()
    }
    error.value = 'Copy failed. The URL is selected — press Cmd/Ctrl+C.'
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

watch(section, (s, prev) => {
  error.value = ''
  notice.value = ''
  if (prev && (s === 'network' || s === 'homepage' || s === 'visuals')) refreshSettings()
  if (s === 'network') {
    refreshTunnelStatus()
    refreshHostnames()
  }
})

onMounted(() => {
  widgetDebug.value = readHomepageWidgetDebug()
  refreshPwaInstall()
  stopPwa = subscribePwaInstall(refreshPwaInstall)
  loadAll()
})
onBeforeUnmount(() => {
  if (stopPwa) stopPwa()
  stopJobPoll()
})
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
      <RouterLink
        v-for="item in SETTINGS_NAV"
        :key="item[0]"
        :to="{ name: 'settings', params: { section: item[0] } }"
        class="settings-nav-btn"
        :class="{ active: section === item[0] }"
      >
        {{ item[1] }}
      </RouterLink>
    </nav>

    <div v-if="error" class="ui-alert ui-alert-error">{{ error }}</div>
    <p v-if="notice" class="share-meta">{{ notice }}</p>

    <template v-if="section === 'visuals'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">THEME</span>
          <h3>Color mode</h3>
          <p>Dark, light, or follow the system preference. Saved in this browser.</p>
        </div>
        <div class="theme-picker" role="group" aria-label="Color theme">
          <button
            v-for="item in THEME_OPTIONS"
            :key="item[0]"
            type="button"
            class="theme-option"
            :class="{ 'is-active': themePreference === item[0] }"
            :aria-pressed="themePreference === item[0]"
            @click="chooseTheme(item[0])"
          >
            {{ item[1] }}
          </button>
        </div>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">ACCENT</span>
          <h3>Accent color</h3>
          <p>Highlight color for buttons, switches, and active states. Saved on this appliance for every browser.</p>
        </div>
        <div class="accent-picker">
          <label class="accent-swatch-input" title="Pick a color">
            <input
              v-model="form.accent_color"
              type="color"
              @change="saveAccentColor(form.accent_color)"
            />
          </label>
          <label class="ui-field accent-hex-field">Hex
            <input
              v-model="form.accent_color"
              class="ui-input font-mono"
              maxlength="7"
              placeholder="#f97316"
              @change="saveAccentColor(form.accent_color)"
            />
          </label>
          <button type="button" class="ui-btn ui-btn-primary" :disabled="saving" @click="saveAccentColor(form.accent_color)">
            {{ saving ? 'Saving…' : 'Save accent' }}
          </button>
          <button
            v-if="branding.accent_custom"
            type="button"
            class="ui-btn ui-btn-ghost"
            :disabled="saving"
            @click="resetAccentColor"
          >
            Reset
          </button>
        </div>
        <div class="accent-presets" role="group" aria-label="Accent presets">
          <button
            v-for="item in ACCENT_PRESETS"
            :key="item[0]"
            type="button"
            class="accent-preset"
            :class="{ 'is-active': form.accent_color === item[0] }"
            :style="{ '--preset': item[0] }"
            :title="item[1]"
            :aria-label="item[1]"
            @click="saveAccentColor(item[0])"
          ></button>
        </div>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">BRANDING</span>
          <h3>Name and icons</h3>
          <p>Rename the header title and replace the header icon, login logo, and favicon. Images are stored on this appliance.</p>
        </div>
        <form class="form-stack" @submit.prevent="saveBrandTitle">
          <label class="ui-field">Header title
            <input
              v-model="form.brand_title"
              class="ui-input"
              maxlength="64"
              required
              placeholder="AIO Media Server Manager"
            />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">
            {{ saving ? 'Saving…' : 'Save title' }}
          </button>
        </form>
        <div class="brand-asset-list">
          <div
            v-for="(slot, key) in branding.slots"
            :key="key"
            class="brand-asset-row"
          >
            <img :src="slot.url" :alt="slot.label" class="brand-asset-preview" />
            <div class="brand-asset-copy">
              <strong>{{ slot.label }}</strong>
              <span>{{ slot.help }}</span>
              <span class="brand-asset-size">Required / recommended: {{ slot.recommended }}</span>
              <span class="share-idle">{{ slot.custom ? 'Custom image in use.' : 'Built-in placeholder — upload to replace.' }}</span>
            </div>
            <div class="brand-asset-actions">
              <label class="ui-btn ui-btn-ghost brand-upload-btn">
                {{ brandUploading === key ? 'Uploading…' : 'Upload' }}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif,image/x-icon,.ico"
                  :disabled="brandUploading === key"
                  @change="uploadBrandSlot(key, $event)"
                />
              </label>
              <button
                v-if="slot.custom"
                type="button"
                class="ui-btn ui-btn-ghost"
                :disabled="brandUploading === key"
                @click="resetBrandSlot(key)"
              >
                Reset
              </button>
            </div>
          </div>
          <p v-if="!Object.keys(branding.slots || {}).length" class="share-idle">
            Loading branding options…
          </p>
        </div>
      </div>
    </template>

    <template v-else-if="section === 'account'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <span class="accent-badge">ACCOUNT</span>
          <h3>Administrator</h3>
          <p>Current password is required for any change. Email is used for Seerr wiring.</p>
        </div>
        <div class="brand-asset-list account-avatar-block">
          <div class="brand-asset-row">
            <div class="account-avatar-preview" aria-hidden="true">
              <img
                v-if="profileAvatar.has_avatar && profileAvatar.avatar_url"
                :src="profileAvatar.avatar_url"
                alt=""
              />
              <span v-else>{{ (form.username || 'A').charAt(0).toUpperCase() }}</span>
            </div>
            <div class="brand-asset-copy">
              <strong>Profile image</strong>
              <span>{{ profileAvatar.help }}</span>
              <span class="brand-asset-size">Required / recommended: {{ profileAvatar.recommended }}</span>
              <span class="share-idle">
                {{ profileAvatar.has_avatar ? 'Custom image in use.' : 'Using your username initial.' }}
              </span>
            </div>
            <div class="brand-asset-actions">
              <label class="ui-btn ui-btn-ghost brand-upload-btn">
                {{ avatarUploading ? 'Uploading…' : 'Upload' }}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  :disabled="avatarUploading"
                  @change="uploadProfileAvatar($event)"
                />
              </label>
              <button
                v-if="profileAvatar.has_avatar"
                type="button"
                class="ui-btn ui-btn-ghost"
                :disabled="avatarUploading"
                @click="resetProfileAvatar"
              >
                Remove
              </button>
            </div>
          </div>
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
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Install on this device</h3>
          <p>Add the manager to the home screen like a phone or tablet app.</p>
        </div>
        <p v-if="pwaStandalone" class="share-idle">This browser is already running as an installed app.</p>
        <template v-else>
          <button
            v-if="pwaCanInstall"
            type="button"
            class="ui-btn ui-btn-primary"
            @click="installPwaFromSettings"
          >
            Install app
          </button>
          <p v-else-if="pwaIos" class="share-idle">
            iPhone/iPad: open this page in Safari, tap Share, then Add to Home Screen.
          </p>
          <p v-else class="share-idle">
            Chrome or Edge: menu → Install app / Add to Home Screen.
            Android’s install prompt needs HTTPS (Cloudflare Tunnel or a reverse proxy).
            On a plain LAN HTTP URL, use the browser menu if Install is offered.
          </p>
        </template>
      </div>
    </template>

    <template v-else-if="section === 'system'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Clock and logs</h3>
          <p>Timezone for backups, updates, and logs. Log level applies immediately.</p>
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
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>File ownership</h3>
          <p>Saving PUID/PGID restarts running apps so new files stay owned correctly.</p>
        </div>
        <form class="form-stack" @submit.prevent="patchSettings({ puid: Number(form.puid), pgid: Number(form.pgid) })">
          <label class="ui-field">PUID
            <input v-model.number="form.puid" type="number" min="1" class="ui-input font-mono" required />
          </label>
          <label class="ui-field">PGID
            <input v-model.number="form.pgid" type="number" min="1" class="ui-input font-mono" required />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save and restart apps</button>
        </form>
      </div>
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
            <dt>Disk</dt>
            <dd class="font-mono">
              <template v-if="metrics.disk?.total">
                {{ formatBytes(metrics.disk.used) }} used
                · {{ formatBytes(diskRemaining) }} free
                / {{ formatBytes(metrics.disk.total) }}
                <span v-if="metrics.disk.percent != null"> ({{ Math.round(metrics.disk.percent) }}%)</span>
              </template>
              <template v-else>—</template>
            </dd>
          </div>
          <div>
            <dt>Hardlinks</dt>
            <dd>{{ hardlinks == null ? '—' : hardlinks ? 'Supported between downloads and media' : 'Not available — *Arr will copy' }}</dd>
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
          <p>Filesystem format and capacity for config, downloads, and media. Edit mounts in docker-compose, not here.</p>
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
                <td colspan="3" class="share-idle">Storage details unavailable. Check that config, downloads, and media mounts are readable, then reload Settings.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <template v-else-if="section === 'updates'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Updates</h3>
          <p>Check GitHub in the host timezone (System). Apply can stay off (header notice only) or match the check schedule. Catalog apps can be applied in-place. A newer appliance image is notified only — pull and recreate on the host.</p>
        </div>
        <p class="share-meta" v-if="snapshot.updates">
          Last check {{ formatWhen(snapshot.updates.last_check_at) }}
          · last apply {{ formatWhen(snapshot.updates.last_apply_at) }}
          · {{ (snapshot.updates.available || []).length }} waiting
          <span v-if="snapshot.updates.paused"> · paused ({{ snapshot.updates.paused_reason }})</span>
        </p>
        <p class="share-meta" v-if="snapshot.updates?.appliance">
          Appliance {{ snapshot.updates.appliance.installed_version }}
          <span v-if="!snapshot.updates.appliance.running_sha"> · local build (no image SHA)</span>
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
              <strong>{{ item.display_name || item.name }}</strong>
              <span class="path-line font-mono">{{ item.installed_version || '—' }} → {{ item.latest_version }}</span>
              <span v-if="item.kind === 'appliance'" class="path-line">{{ item.apply_hint }}</span>
            </div>
          </li>
        </ul>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>GitHub token</h3>
          <p>Optional. Catalog installs and scheduled update checks stay under the authenticated rate limit.</p>
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

    <template v-else-if="section === 'backups'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Backups</h3>
          <p>
            Manager settings, secrets, app config and databases. Media, downloads, caches, logs and artwork
            caches are never included. Databases are copied safely while apps keep running.
          </p>
        </div>
        <p class="share-meta">
          Stored in <span class="font-mono">{{ backupInfo.backup_dir || snapshot.backup_dir }}</span>
          · last backup {{ formatWhen(backupInfo.schedule?.last_backup_at) }}
          <span v-if="backupInfo.schedule?.last_error" class="backup-warn"> · last attempt failed: {{ backupInfo.schedule.last_error }}</span>
        </p>
        <p v-if="backupOnConfigVolume" class="settings-hint">
          Backups sit on the same volume as /config. Map a separate disk or NAS share to <code>/backups</code>
          (or set <code>AMM_BACKUP_DIR</code>) so a failed disk does not take the backups with it, or download them regularly.
        </p>

        <div v-if="backupJob && (backupJobRunning || backupJob.status === 'error')" class="backup-job">
          <strong>{{ backupJob.kind }} · {{ backupJob.stage }}</strong>
          <div v-if="backupJobRunning" class="backup-progress"><span :style="{ width: `${backupJobPercent}%` }"></span></div>
          <span v-if="backupJobRunning && backupJob.total" class="path-line">{{ backupJob.done }} / {{ backupJob.total }} files</span>
          <span v-if="backupJob.status === 'error'" class="backup-warn">{{ backupJob.error }}</span>
        </div>

        <form class="form-stack" @submit.prevent="patchSettings({
          backup_retention: Number(form.backup_retention),
          backup_schedule: form.backup_schedule,
          backup_time: form.backup_time,
          backup_weekday: Number(form.backup_weekday),
          backup_day_of_month: Number(form.backup_day_of_month)
        })">
          <label class="ui-field">Automatic backups
            <select v-model="form.backup_schedule" class="ui-input">
              <option value="off">Off</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          <label v-if="form.backup_schedule !== 'off'" class="ui-field">Time of day
            <input v-model="form.backup_time" type="time" class="ui-input font-mono" />
          </label>
          <label v-if="form.backup_schedule === 'weekly'" class="ui-field">Weekday
            <select v-model.number="form.backup_weekday" class="ui-input">
              <option :value="0">Monday</option>
              <option :value="1">Tuesday</option>
              <option :value="2">Wednesday</option>
              <option :value="3">Thursday</option>
              <option :value="4">Friday</option>
              <option :value="5">Saturday</option>
              <option :value="6">Sunday</option>
            </select>
          </label>
          <label v-if="form.backup_schedule === 'monthly'" class="ui-field">Day of month
            <input v-model.number="form.backup_day_of_month" type="number" min="1" max="28" class="ui-input font-mono" />
          </label>
          <label class="ui-field">Keep last N backups
            <input v-model.number="form.backup_retention" type="number" min="1" max="90" class="ui-input font-mono" />
          </label>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-ghost" :disabled="saving">Save</button>
            <button type="button" class="ui-btn ui-btn-primary" :disabled="backupJobRunning" @click="createBackup">Backup now</button>
            <label class="ui-btn ui-btn-ghost backup-upload" :class="{ 'is-disabled': uploading || backupJobRunning }">
              {{ uploading ? 'Uploading…' : 'Upload backup' }}
              <input type="file" accept=".tar.gz,.tgz,application/gzip" :disabled="uploading || backupJobRunning" @change="uploadBackup" />
            </label>
          </div>
        </form>

        <div v-if="restoreTarget" class="backup-restore glass-card">
          <strong>Restore from <span class="font-mono">{{ restoreTarget.name }}</span></strong>
          <p class="settings-hint">
            Pick everything or only some apps. The current state is backed up first, affected apps are stopped
            during the restore and started again afterwards.
          </p>
          <div class="backup-sections">
            <label class="backup-chip">
              <input type="checkbox" :checked="restoreTarget.selected.includes('all')" @change="toggleRestoreSection('all')" />
              Everything
            </label>
            <label v-for="item in restoreTarget.sections" :key="item" class="backup-chip">
              <input
                type="checkbox"
                :checked="restoreTarget.selected.includes(item)"
                @change="toggleRestoreSection(item)"
              />
              {{ item === 'manager' ? 'Manager settings & secrets' : item }}
            </label>
          </div>
          <div class="share-row">
            <button type="button" class="ui-btn ui-btn-primary" @click="confirmRestore">Restore</button>
            <button type="button" class="ui-btn ui-btn-ghost" @click="restoreTarget = null">Cancel</button>
          </div>
        </div>

        <ul class="backup-list">
          <li v-for="item in backups" :key="item.name">
            <div>
              <strong class="font-mono">{{ item.name }}</strong>
              <span class="path-line">
                {{ backupKindLabel(item) }} · {{ formatWhen(item.created_at) }} · {{ formatBytes(item.size_bytes) }}
                <template v-if="item.file_count"> · {{ item.file_count }} files</template>
                <template v-if="item.location === 'legacy'"> · old location</template>
                <template v-if="item.format < 2"> · old format</template>
              </span>
              <span v-if="item.warnings.length" class="path-line backup-warn" :title="item.warnings.join('\n')">
                {{ item.warnings.length }} warning(s): {{ item.warnings[0] }}
              </span>
            </div>
            <div class="share-row">
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="backupJobRunning" @click="openRestore(item.name)">Restore</button>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="backupJobRunning" @click="verifyBackup(item.name)">Verify</button>
              <button type="button" class="ui-btn ui-btn-ghost" @click="downloadBackup(item.name)">Download</button>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="backupJobRunning" @click="deleteBackup(item.name)">Delete</button>
            </div>
          </li>
          <li v-if="!backups.length" class="share-idle">No backups yet.</li>
        </ul>
      </div>
    </template>

    <template v-else-if="section === 'network'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>VPN</h3>
          <p>qBittorrent, Prowlarr, and Flaresolverr. Usenet always bypasses the tunnel.</p>
        </div>
        <p class="share-meta">{{ vpnLive.enabled ? 'VPN is on' : 'VPN is off' }}{{ vpnLive.provider ? ` · ${vpnLive.provider}` : '' }}{{ vpnLive.protocol ? ` · ${vpnLive.protocol}` : '' }}</p>
        <div class="setting-status">
          <span class="setting-chip" :class="vpnLive.enabled ? 'is-on' : 'is-off'">{{ vpnLive.enabled ? 'Enabled' : 'Off' }}</span>
          <span class="setting-chip" :class="vpnLive.config_present ? 'is-on' : 'is-warn'">{{ vpnLive.config_present ? 'Config saved' : 'No config' }}</span>
          <span class="setting-chip" :class="vpnLive.tunnel_up ? 'is-on' : (vpnLive.enabled ? 'is-bad' : 'is-off')">{{ vpnLive.tunnel_up ? 'Tunnel up' : 'Tunnel down' }}</span>
        </div>
        <p v-if="vpnLive.config_present" class="share-meta font-mono">{{ vpnLive.config_path }}</p>
        <div class="share-row" style="margin: 0.75rem 0 1rem;">
          <button
            type="button"
            class="ui-btn ui-btn-primary"
            :disabled="saving || vpnBusy || !vpnLive.config_present || !!vpnLive.tunnel_up"
            @click="controlVpn('start')"
          >{{ vpnBusy ? 'Working…' : 'Start' }}</button>
          <button
            type="button"
            class="ui-btn ui-btn-ghost"
            :disabled="saving || vpnBusy || (!vpnLive.tunnel_up && !vpnLive.enabled)"
            @click="controlVpn('stop')"
          >Stop</button>
          <button
            type="button"
            class="ui-btn ui-btn-ghost"
            :disabled="saving || vpnBusy || !vpnLive.config_present"
            @click="controlVpn('restart')"
          >Restart</button>
        </div>
        <form class="form-stack" @submit.prevent="saveVpn">
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>Enable VPN</strong>
              <span>On: kill switch — qBittorrent, Prowlarr, and Flaresolverr only run when the tunnel is up. Off: those apps can start on the house network. Use Start / Stop / Restart for the tunnel.</span>
            </div>
            <button
              type="button"
              class="ui-switch"
              role="switch"
              :aria-checked="form.vpn_enabled ? 'true' : 'false'"
              :disabled="saving || vpnBusy"
              @click="toggleVpn"
            >
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
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Cloudflare Tunnel</h3>
          <p>
            In Cloudflare: Networking → Tunnels → create a Cloudflared tunnel → copy only the
            <code>eyJ…</code> token from the install command (do not run that command on this NAS).
            Paste it below, enable the tunnel, and Save. Token is stored on disk and never shown again.
            Full walkthrough: project file <code>deploy/CLOUDFLARE.md</code>.
          </p>
        </div>
        <div class="setting-status" aria-live="polite">
          <span class="setting-chip" :class="tunnelLive.enabled ? 'is-on' : 'is-off'">
            {{ tunnelLive.enabled ? 'Enabled' : 'Off' }}
          </span>
          <span
            class="setting-chip"
            :class="(tunnelLive.token_saved || tunnelLive.token_present) ? 'is-on' : (tunnelLive.enabled ? 'is-bad' : 'is-warn')"
          >
            {{ (tunnelLive.token_saved || tunnelLive.token_present) ? 'Token saved' : 'No token' }}
          </span>
          <span
            class="setting-chip"
            :class="tunnelLive.connected ? 'is-on' : (tunnelLive.enabled ? (tunnelLive.running ? 'is-warn' : 'is-bad') : 'is-off')"
          >
            {{ tunnelLive.connected ? 'Tunnel up' : (tunnelLive.running ? 'Connecting…' : 'Tunnel down') }}
          </span>
          <span class="setting-chip" :class="tunnelLive.binary_present ? 'is-on' : 'is-bad'">
            {{ tunnelLive.binary_present ? 'cloudflared ready' : 'cloudflared missing' }}
          </span>
        </div>
        <p class="share-meta">{{ tunnelLive.summary || 'Status loads when you open Network.' }}</p>
        <p v-if="tunnelLive.token_saved || tunnelLive.token_present" class="share-meta font-mono">
          Stored at {{ tunnelLive.token_file || '/config/cloudflare/tunnel.token' }}
        </p>
        <form class="form-stack" @submit.prevent="saveCloudflare">
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>Enable tunnel</strong>
              <span>Requires cloudflared in the image and a tunnel token.</span>
            </div>
            <button type="button" class="ui-switch" role="switch" :aria-checked="form.cloudflare_tunnel_enabled ? 'true' : 'false'" @click="form.cloudflare_tunnel_enabled = !form.cloudflare_tunnel_enabled">
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <label class="ui-field">
            Tunnel token
            <span class="ui-field-hint">
              {{ (tunnelLive.token_saved || tunnelLive.token_present)
                ? 'A token is already saved. Leave blank to keep it, or paste a new eyJ… token to replace it.'
                : 'Paste the eyJ… token from Cloudflare. It is stored on disk and never shown again.' }}
            </span>
            <input
              v-model="form.cloudflare_tunnel_token"
              type="password"
              class="ui-input font-mono"
              autocomplete="off"
              :placeholder="(tunnelLive.token_saved || tunnelLive.token_present) ? '•••• token saved — paste to replace' : 'eyJ…'"
            />
          </label>
          <label class="ui-field">Trusted reverse-proxy IPs
            <span class="ui-field-hint">
              Leave empty for LAN-only or Cloudflare Tunnel (tunnel auto-trusts 127.0.0.1).
              Only list IPs/CIDRs of a reverse proxy you run in front of this app (nginx, Caddy, …).
              Comma-separated. Do not use Cloudflare edge IPs here.
            </span>
            <input v-model="form.trusted_proxies" class="ui-input font-mono" placeholder="172.17.0.1,10.0.0.0/8" />
          </label>
          <label class="ui-field">Public app domain (Open UI over tunnel)
            <span class="ui-field-hint">
              DNS zone for Catalog Open UI when you use HTTPS / Cloudflare, e.g. <code>example.com</code>
              or <code>example.co.uk</code>
              → links become <code>https://sonarr.example.com</code>.
              Leave empty to derive from the current host
              (<code>media.example.com</code> → <code>example.com</code>,
              <code>media.example.co.uk</code> → <code>example.co.uk</code>).
              LAN IP access still uses <code>http://nas-ip:port</code>.
            </span>
            <input
              v-model="form.public_app_base_domain"
              class="ui-input font-mono"
              placeholder="example.com"
              autocomplete="off"
            />
          </label>
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save</button>
        </form>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Public subdomains</h3>
          <p>
            Choose a subdomain per app for Catalog Open UI. With a Cloudflare API token, this page can
            create the tunnel routes and DNS CNAMEs for you — no Cloudflare dashboard hop required
            after the initial tunnel + API token.
            API token needs <strong>Account → Cloudflare Tunnel → Edit</strong> and
            <strong>Zone → DNS → Edit</strong> on your domain.
          </p>
        </div>
        <div class="setting-status" aria-live="polite">
          <span class="setting-chip" :class="apiTokenConfigured ? 'is-on' : 'is-warn'">
            {{ apiTokenConfigured ? 'API token saved' : 'API token optional' }}
          </span>
          <span
            class="setting-chip"
            :class="hostnameMeta.tunnel_id ? 'is-on' : 'is-warn'"
          >
            {{ hostnameMeta.tunnel_id ? 'Tunnel id ready' : 'Need connector token' }}
          </span>
        </div>
        <p v-if="hostnameMeta.tunnel_decode_error" class="share-meta">{{ hostnameMeta.tunnel_decode_error }}</p>
        <form class="form-stack" @submit.prevent="saveHostnames">
          <label class="ui-field">
            Cloudflare API token
            <span class="ui-field-hint">
              Different from the tunnel <code>eyJ…</code> connector token. Create under
              My Profile → API Tokens. Leave blank to keep a saved token.
            </span>
            <input
              v-model="form.cloudflare_api_token"
              type="password"
              class="ui-input font-mono"
              autocomplete="off"
              :placeholder="apiTokenConfigured ? '•••• token saved — paste to replace' : 'Cloudflare API token'"
            />
          </label>
          <div class="hostname-table-wrap">
            <table class="storage-table hostname-table">
              <thead>
                <tr>
                  <th>Expose</th>
                  <th>App</th>
                  <th>Subdomain</th>
                  <th>Public URL</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in hostnameRoutes" :key="row.name">
                  <td>
                    <button
                      type="button"
                      class="ui-switch"
                      role="switch"
                      :aria-checked="row.enabled ? 'true' : 'false'"
                      :aria-label="`Expose ${row.display_name}`"
                      @click="row.enabled = !row.enabled"
                    >
                      <span class="ui-switch-thumb"></span>
                    </button>
                  </td>
                  <td>
                    <strong>{{ row.display_name }}</strong>
                    <span class="path-line">{{ row.name }} · port {{ row.port }}{{ row.installed ? '' : ' · not installed' }}</span>
                  </td>
                  <td>
                    <input
                      v-model="row.subdomain"
                      class="ui-input font-mono"
                      :placeholder="row.default_subdomain"
                      autocomplete="off"
                      :disabled="!row.enabled"
                    />
                  </td>
                  <td class="font-mono hostname-preview">{{ previewHostnameUrl(row) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving || hostnameBusy">
              Save subdomains
            </button>
            <button
              type="button"
              class="ui-btn ui-btn-primary"
              :disabled="saving || hostnameBusy || (!apiTokenConfigured && !form.cloudflare_api_token)"
              @click="publishHostnames"
            >
              Publish to Cloudflare
            </button>
            <button
              v-if="apiTokenConfigured"
              type="button"
              class="ui-btn ui-btn-ghost"
              :disabled="saving || hostnameBusy"
              @click="clearCloudflareApiToken"
            >
              Clear API token
            </button>
          </div>
          <p class="share-meta">
            Save updates Open UI links only. Publish writes enabled hostnames into your tunnel config
            and creates proxied DNS CNAMEs under the public app domain.
            Changing an exposed app’s listen port updates the tunnel service and recreates its DNS
            CNAME automatically (API token required). Disabling an app removes its tunnel route but
            leaves the DNS CNAME (safe no-op / 404). LAN browsing still uses
            <code>http://nas-ip:port</code> even when a public domain is set.
            For zones like <code>example.co.uk</code>, set Public app domain to that full zone.
            Secure public hostnames with
            <code>deploy/CLOUDFLARE_ACCESS.md</code>.
          </p>
        </form>
      </div>
    </template>

    <template v-else-if="section === 'homepage'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Jellyfin API key</h3>
          <p>
            Home → Recently added uses this key. Create one in Jellyfin Dashboard → API Keys
            (or paste the access token). Paste a new key to replace it.
          </p>
        </div>
        <div class="setting-status">
          <span class="setting-chip" :class="credentialChip(jellyfinKey).cls">{{ credentialChip(jellyfinKey).label }}</span>
        </div>
        <p class="share-meta">{{ jellyfinKey.detail || (jellyfinKey.configured ? 'A Jellyfin API key is saved.' : 'No Jellyfin API key saved yet.') }}</p>
        <form class="form-stack" @submit.prevent="saveHomepageKey('jellyfin_api_key')">
          <label class="ui-field">API key
            <input
              v-model="form.jellyfin_api_key"
              type="password"
              class="ui-input font-mono"
              autocomplete="off"
              :placeholder="jellyfinKey.configured ? 'Saved — paste a new key to replace' : 'Paste API key'"
            />
          </label>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save API key</button>
            <button v-if="jellyfinKey.configured" type="button" class="ui-btn ui-btn-ghost" :disabled="saving" @click="clearHomepageKey('jellyfin_api_key')">Clear key</button>
          </div>
        </form>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Seerr API key</h3>
          <p>
            Home search and requests use this key. The manager reads it from Seerr's settings.json when it can;
            otherwise copy it from Seerr Settings → General. Paste a new key to replace it.
          </p>
        </div>
        <div class="setting-status">
          <span class="setting-chip" :class="credentialChip(seerrKey).cls">{{ credentialChip(seerrKey).label }}</span>
        </div>
        <p class="share-meta">{{ seerrKey.detail || (seerrKey.configured ? 'A Seerr API key is saved.' : 'No Seerr API key saved yet.') }}</p>
        <form class="form-stack" @submit.prevent="saveHomepageKey('seerr_api_key')">
          <label class="ui-field">API key
            <input
              v-model="form.seerr_api_key"
              type="password"
              class="ui-input font-mono"
              autocomplete="off"
              :placeholder="seerrKey.configured ? 'Saved — paste a new key to replace' : 'Paste API key'"
            />
          </label>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">Save API key</button>
            <button v-if="seerrKey.configured" type="button" class="ui-btn ui-btn-ghost" :disabled="saving" @click="clearHomepageKey('seerr_api_key')">Clear key</button>
          </div>
        </form>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Widget debug</h3>
          <p>
            Show empty calendar, downloads, and recently added tiles plus per-source skip notes.
            API keys are never shown.
          </p>
        </div>
        <div class="ui-switch-row">
          <div class="ui-switch-copy">
            <strong>Explain empty widgets</strong>
            <span>When on, Home explains why a widget is empty or failing. You can also add <code>?debug=1</code> to the Home URL.</span>
          </div>
          <button
            type="button"
            class="ui-switch"
            role="switch"
            :aria-checked="widgetDebug ? 'true' : 'false'"
            @click="toggleHomepageWidgetDebug"
          >
            <span class="ui-switch-thumb"></span>
          </button>
        </div>
      </div>
    </template>

    <template v-else-if="section === 'diagnostics'">
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>Support share</h3>
          <p>
            Capture recent errors behind a time-limited URL for support. Secrets are redacted.
            The link expires after {{ share.ttl_hours || 24 }} hours. Host dumps and process logs
            use the same switch, except from localhost which is always allowed for troubleshooting.
          </p>
        </div>
        <div class="ui-switch-row">
          <div class="ui-switch-copy">
            <strong>Support share URL</strong>
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
          <p>Last captured ERROR+ events. Shown from localhost, or while Support share is on.</p>
        </div>
        <div v-if="!errors.length" class="share-idle">{{ share.active ? 'No errors captured since startup.' : 'Turn on Support share, or open Settings from localhost, to view captured errors.' }}</div>
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
  color: var(--text-heading);
}
.section-subtitle {
  font-size: 0.82rem;
  color: var(--text-dim);
  margin: 0.2rem 0 0;
}
.settings-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.settings-nav-btn {
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  color: var(--text-muted);
  padding: 0.4rem 0.85rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}
.settings-nav-btn.active {
  color: var(--color-primary-soft);
  background: rgba(var(--color-primary-rgb), 0.16);
  border-color: rgba(var(--color-primary-rgb), 0.45);
}
.settings-card {
  padding: 1.4rem 1.5rem;
  min-width: 0;
}
.settings-card-head h3 {
  margin: 0.4rem 0 0.35rem;
  font-size: 1.05rem;
  color: var(--text-heading);
}
.settings-card-head p {
  color: var(--text-muted);
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
  background: rgba(var(--color-primary-rgb), 0.18);
  color: var(--color-primary-soft);
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
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  min-width: 0;
}
.info-grid dt {
  color: var(--text-dim);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.info-grid dd {
  margin: 0.3rem 0 0;
  color: var(--text-main);
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
  color: var(--text-dim);
  font-size: 0.68rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.4rem 0.6rem 0.65rem;
  border-bottom: 1px solid var(--border-subtle);
}
.storage-table td {
  padding: 0.75rem 0.6rem;
  color: var(--text-main);
  vertical-align: top;
  border-bottom: 1px solid var(--border-subtle);
}
.storage-table strong {
  display: block;
  color: var(--text-heading);
  text-transform: capitalize;
  margin-bottom: 0.15rem;
}
.path-line {
  display: block;
  color: var(--text-dim);
  font-size: 0.75rem;
  overflow-wrap: anywhere;
}
.hostname-table-wrap {
  overflow-x: auto;
  margin: 0.35rem 0 0.25rem;
}
.hostname-table th:first-child,
.hostname-table td:first-child {
  width: 4.5rem;
}
.hostname-table .ui-input {
  min-width: 7rem;
  max-width: 12rem;
}
.hostname-preview {
  font-size: 0.8rem;
  color: var(--text-muted);
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
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 0.55rem;
}
.setting-status {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.65rem 0 0.35rem;
}
.setting-chip {
  display: inline-flex;
  align-items: center;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  background: var(--pill-bg);
  color: var(--text-main);
}
.setting-chip.is-on {
  color: #047857;
  border-color: rgba(16, 185, 129, 0.45);
  background: rgba(16, 185, 129, 0.14);
}
.setting-chip.is-warn {
  color: #b45309;
  border-color: rgba(245, 158, 11, 0.45);
  background: rgba(245, 158, 11, 0.14);
}
.setting-chip.is-bad {
  color: #b91c1c;
  border-color: rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
}
.setting-chip.is-off {
  color: var(--text-muted);
}
[data-theme="dark"] .setting-chip.is-on {
  color: #bbf7d0;
  border-color: rgba(52, 211, 153, 0.35);
  background: rgba(6, 78, 59, 0.45);
}
[data-theme="dark"] .setting-chip.is-warn {
  color: #fde68a;
  border-color: rgba(251, 191, 36, 0.35);
  background: rgba(120, 53, 15, 0.4);
}
[data-theme="dark"] .setting-chip.is-bad {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.4);
  background: rgba(127, 29, 29, 0.45);
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
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
}
.backup-warn {
  color: #fbbf24;
}
.backup-job {
  display: grid;
  gap: 0.35rem;
  margin: 0.75rem 0;
  padding: 0.75rem 0.85rem;
  border-radius: 10px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  text-transform: capitalize;
}
.backup-progress {
  height: 6px;
  border-radius: 999px;
  background: var(--border-subtle);
  overflow: hidden;
}
.backup-progress span {
  display: block;
  height: 100%;
  background: var(--color-primary, #f97316);
  transition: width 0.3s ease;
}
.backup-upload {
  position: relative;
  overflow: hidden;
  cursor: pointer;
}
.backup-upload input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.backup-upload.is-disabled {
  opacity: 0.5;
  pointer-events: none;
}
.backup-restore {
  display: grid;
  gap: 0.6rem;
  margin-top: 1rem;
  padding: 0.9rem 1rem;
}
.backup-sections {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.backup-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  font-size: 0.85rem;
  text-transform: capitalize;
}
.error-log {
  background: var(--overlay-soft);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 1rem;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 0.78rem;
  color: var(--text-main);
}
.brand-asset-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 1.25rem;
}
.brand-asset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.85rem 1rem;
  align-items: flex-start;
  padding: 0.9rem;
  border-radius: 12px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
}
.brand-asset-preview {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  object-fit: cover;
  background: var(--bg-input);
  border: 1px solid var(--border-subtle);
  flex-shrink: 0;
}
.brand-asset-copy {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  flex: 1 1 14rem;
}
.brand-asset-copy strong {
  color: var(--text-heading);
  font-size: 0.92rem;
}
.brand-asset-copy span {
  color: var(--text-muted);
  font-size: 0.8rem;
  line-height: 1.4;
}
.brand-asset-size {
  color: var(--color-primary-soft) !important;
  font-weight: 600;
}
.brand-asset-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  align-items: center;
}
.account-avatar-block {
  margin-bottom: 1.25rem;
}
.account-avatar-preview {
  width: 4.5rem;
  height: 4.5rem;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--color-primary);
  color: var(--color-primary-contrast);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1.5rem;
  line-height: 1;
}
.account-avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.brand-upload-btn {
  position: relative;
  overflow: hidden;
  cursor: pointer;
}
.brand-upload-btn input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.accent-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem;
}
.accent-swatch-input {
  width: 3rem;
  height: 2.6rem;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--pill-bg);
  cursor: pointer;
  flex-shrink: 0;
}
.accent-swatch-input input {
  width: 140%;
  height: 140%;
  margin: -20%;
  border: none;
  padding: 0;
  cursor: pointer;
  background: transparent;
}
.accent-hex-field {
  flex: 1 1 8rem;
  min-width: 8rem;
  max-width: 12rem;
  margin: 0;
}
.accent-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 0.9rem;
}
.accent-preset {
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 999px;
  border: 2px solid transparent;
  background: var(--preset);
  cursor: pointer;
  padding: 0;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.15);
}
.accent-preset.is-active {
  border-color: var(--text-heading);
  box-shadow: 0 0 0 2px rgba(var(--color-primary-rgb), 0.35);
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
