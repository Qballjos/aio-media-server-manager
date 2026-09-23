<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { appIconSrc } from './appIcons.js'

const props = defineProps({
  apiRequest: { type: Function, required: true }
})
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

const TITLE = {
  3: 'Storage',
  4: 'Permissions',
  5: 'Download clients',
  6: 'VPN',
  7: '*Arr apps',
  8: 'Media server',
  9: 'Requests',
  10: 'Recommended tools',
  11: 'Review & install'
}

const flowIndex = computed(() => FLOW.indexOf(step.value) + 1)

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

function clampToFlow(id) {
  if (!FLOW.includes(id)) return FIRST
  return id
}

async function loadStep(id) {
  loading.value = true
  error.value = ''
  try {
    const res = await props.apiRequest(`/api/wizard/step/${id}`)
    if (!res.ok) throw new Error('Could not load wizard step')
    payload.value = await res.json()
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
      selections.qbittorrent_username = data.qbittorrent_username || 'admin'
      selections.qbittorrent_password = ''
    } else if (id === 6) {
      selections.vpn_provider = data.selected || 'none'
      selections.vpn_config_path = data.vpn_config_path || ''
      selections.vpn_protocol = data.vpn_protocol || 'wireguard'
      selections.vpn_enforce = !!data.vpn_enforce
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
      qbittorrent_username: selections.qbittorrent_username
    }
    if (selections.qbittorrent_password) body.qbittorrent_password = selections.qbittorrent_password
    return body
  }
  if (id === 6) {
    return {
      vpn_provider: selections.vpn_provider,
      vpn_config_path: selections.vpn_config_path,
      vpn_protocol: selections.vpn_protocol,
      vpn_enforce: selections.vpn_enforce
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
      const res = await props.apiRequest(`/api/wizard/step/${step.value}`, {
        method: 'POST',
        body: JSON.stringify(bodyForStep(step.value))
      })
      if (!res.ok) throw new Error('Could not save this step')
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
  try {
    const res = await props.apiRequest('/api/wizard/skip', { method: 'POST' })
    if (!res.ok) throw new Error('Could not skip wizard')
    emit('done')
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function finish() {
  installing.value = true
  error.value = ''
  installProgress.value = []
  try {
    const res = await props.apiRequest('/api/wizard/execute', { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Wizard could not finish')
    const apps = data.target_apps || []
    for (const name of apps) {
      installProgress.value.push({ name, status: 'installing' })
      try {
        const inst = await props.apiRequest(`/api/catalog/${name}/install`, { method: 'POST' })
        const last = installProgress.value[installProgress.value.length - 1]
        last.status = inst.ok ? 'started' : 'failed'
      } catch (_) {
        installProgress.value[installProgress.value.length - 1].status = 'failed'
      }
    }
    emit('done')
  } catch (err) {
    error.value = err.message
  } finally {
    installing.value = false
  }
}

const summary = computed(() => payload.value.summary || payload.value.selections || {})
const showPlexClaim = computed(() => (selections.media_servers || []).includes('plex'))
const showQbitCreds = computed(() => (selections.download_clients || []).includes('qbittorrent'))
const showVpnFields = computed(() => selections.vpn_provider && selections.vpn_provider !== 'none')

onMounted(async () => {
  const statusRes = await props.apiRequest('/api/wizard/status')
  if (statusRes.ok) {
    const status = await statusRes.json()
    step.value = clampToFlow(status.current_step || FIRST)
  }
  await loadStep(step.value)
})
</script>

<template>
  <section class="wizard-shell animate-fade">
    <div class="wizard-card">
      <div class="wizard-header">
        <span class="accent-badge">FIRST-RUN SETUP</span>
        <h2>{{ TITLE[step] }}</h2>
        <p>Step {{ flowIndex }} of {{ FLOW.length }} — pick your stack, then save and install.</p>
        <ol class="wizard-progress">
          <li
            v-for="(id, index) in FLOW"
            :key="id"
            :class="{ active: id === step, done: FLOW.indexOf(step) > index }"
          >
            {{ index + 1 }}
          </li>
        </ol>
      </div>

      <p v-if="error" class="alert-banner alert-error">{{ error }}</p>
      <p v-if="loading" class="wizard-muted">Loading…</p>

      <div v-else class="wizard-body">
        <template v-if="step === 3">
          <label class="form-group">
            <span>Media directory</span>
            <input v-model="selections.media_dir" class="input-control font-mono" />
          </label>
          <label class="form-group">
            <span>Download directory</span>
            <input v-model="selections.download_dir" class="input-control font-mono" />
          </label>
          <label class="form-group">
            <span>Config directory</span>
            <input v-model="selections.config_dir" class="input-control font-mono" />
          </label>
          <p class="wizard-muted">{{ payload.hardlink_message }} Put both media and downloads under one host folder (for example <code>/data/media</code> and <code>/data/downloads</code>) so *Arr can hardlink instead of copying.</p>
        </template>

        <template v-else-if="step === 4">
          <p class="wizard-muted">Filled from this host’s PUID/PGID (compose <code>PUID</code>/<code>PGID</code>, otherwise 1000). Change only if the media user is different.</p>
          <label class="form-group">
            <span>PUID</span>
            <input v-model="selections.puid" type="number" min="1" class="input-control font-mono" />
          </label>
          <label class="form-group">
            <span>PGID</span>
            <input v-model="selections.pgid" type="number" min="1" class="input-control font-mono" />
          </label>
        </template>

        <template v-else-if="step === 5">
          <div class="wizard-options">
            <label v-for="option in payload.options || []" :key="option.id" class="wizard-option">
              <input type="checkbox" :checked="isSelected('download_clients', option.id)" @change="toggle('download_clients', option.id)" />
              <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="help-chip" title="Official help">?</a>
            </label>
          </div>
          <template v-if="showQbitCreds">
            <label class="form-group">
              <span>qBittorrent WebUI username</span>
              <input v-model="selections.qbittorrent_username" class="input-control font-mono" />
            </label>
            <label class="form-group">
              <span>qBittorrent WebUI password</span>
              <input v-model="selections.qbittorrent_password" type="password" class="input-control" placeholder="Leave blank to use the manager password" />
            </label>
            <p class="wizard-muted">Blank qBittorrent fields use the same username and password as AIO Media Server Manager.</p>
          </template>
        </template>

        <template v-else-if="step === 6">
          <div class="wizard-options">
            <label v-for="option in payload.options || []" :key="option.id" class="wizard-option">
              <input type="radio" name="vpn" :value="option.id" v-model="selections.vpn_provider" />
              <span>{{ option.name }}</span>
            </label>
          </div>
          <template v-if="showVpnFields">
            <label class="form-group">
              <span>VPN config path</span>
              <input v-model="selections.vpn_config_path" class="input-control font-mono" placeholder="/config/vpn/wg0.conf" />
            </label>
            <label class="form-group">
              <span>Protocol</span>
              <select v-model="selections.vpn_protocol" class="input-control">
                <option value="wireguard">WireGuard</option>
                <option value="openvpn">OpenVPN</option>
              </select>
            </label>
            <label class="wizard-option">
              <input type="checkbox" v-model="selections.vpn_enforce" />
              Enforce kill switch for tunneled apps
            </label>
          </template>
        </template>

        <template v-else-if="step === 7">
          <div class="wizard-options">
            <label v-for="option in payload.options || []" :key="option.id" class="wizard-option">
              <input type="checkbox" :checked="isSelected('arr_apps', option.id)" @change="toggle('arr_apps', option.id)" />
              <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="help-chip" title="Official help">?</a>
            </label>
          </div>
        </template>

        <template v-else-if="step === 8">
          <div class="wizard-options">
            <label v-for="option in payload.options || []" :key="option.id" class="wizard-option">
              <input type="checkbox" :checked="isSelected('media_servers', option.id)" @change="toggle('media_servers', option.id)" />
              <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="help-chip" title="Official help">?</a>
            </label>
          </div>
          <label v-if="showPlexClaim" class="form-group">
            <span>Plex claim token</span>
            <input v-model="selections.plex_claim" class="input-control font-mono" placeholder="claim-…" />
            <span class="wizard-muted">Optional. Get a token from plex.tv/claim, or sign in from the Plex UI later.</span>
          </label>
        </template>

        <template v-else-if="step === 9">
          <div class="wizard-options">
            <label v-for="option in payload.options || []" :key="option.id" class="wizard-option">
              <input type="radio" name="seerr" :value="option.id" v-model="selections.request_system" />
              <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="help-chip" title="Official help">?</a>
            </label>
            <label class="wizard-option">
              <input type="radio" name="seerr" value="none" v-model="selections.request_system" />
              <span>Skip for now</span>
            </label>
          </div>
        </template>

        <template v-else-if="step === 10">
          <div class="wizard-options">
            <label v-for="option in payload.options || []" :key="option.id" class="wizard-option">
              <input type="checkbox" :checked="isSelected('recommended_preview', option.id)" @change="toggle('recommended_preview', option.id)" />
              <img v-if="appIconSrc(option.id)" :src="appIconSrc(option.id)" :alt="option.name" class="wizard-icon" />
              <span>{{ option.name }}</span>
              <a v-if="optionHelp(option)" :href="optionHelp(option)" target="_blank" rel="noopener noreferrer" class="help-chip" title="Official help">?</a>
            </label>
          </div>
        </template>

        <template v-else>
          <dl class="wizard-dl">
            <div><dt>*Arr</dt><dd>{{ (summary.arr_apps || []).join(', ') || '—' }}</dd></div>
            <div><dt>Download</dt><dd>{{ (summary.download_clients || []).join(', ') || '—' }}</dd></div>
            <div><dt>Media</dt><dd>{{ (summary.media_servers || []).join(', ') || '—' }}</dd></div>
            <div><dt>Requests</dt><dd>{{ summary.request_system || '—' }}</dd></div>
            <div><dt>VPN</dt><dd>{{ summary.vpn_provider || 'none' }}</dd></div>
            <div><dt>Recommended</dt><dd>{{ (summary.recommended_preview || []).join(', ') || 'none' }}</dd></div>
          </dl>
          <ul v-if="installProgress.length" class="wizard-install-list">
            <li v-for="item in installProgress" :key="item.name">{{ item.name }} — {{ item.status }}</li>
          </ul>
        </template>
      </div>

      <div class="wizard-actions">
        <button type="button" class="btn-secondary" :disabled="saving || installing" @click="skip">Skip for now</button>
        <div class="wizard-nav">
          <button type="button" class="btn-secondary" :disabled="step === FIRST || saving || installing" @click="back">Back</button>
          <button v-if="step !== LAST" type="button" class="btn-primary" :disabled="saving || loading" @click="next">
            {{ saving ? 'Saving…' : 'Next' }}
          </button>
          <button v-else type="button" class="btn-primary" :disabled="installing" @click="finish">
            {{ installing ? 'Starting installs…' : 'Save & install' }}
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
  padding: 1.5rem 0 3rem;
}
.wizard-card {
  width: min(760px, 100%);
  padding: 2rem 2.1rem 1.75rem;
  background: rgba(22, 30, 46, 0.75);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
}
.wizard-header h2 {
  margin: 0.55rem 0 0.4rem;
  font-size: 1.55rem;
  color: #f8fafc;
}
.wizard-header p,
.wizard-muted {
  color: #94a3b8;
  font-size: 0.92rem;
  line-height: 1.45;
  margin: 0;
}
.accent-badge {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.16);
  border: 1px solid rgba(129, 140, 248, 0.35);
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
}
.wizard-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 1.15rem 0 0;
}
.wizard-progress li {
  width: 2.35rem;
  height: 2.35rem;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 0.92rem;
  font-weight: 700;
  color: #94a3b8;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(15, 23, 42, 0.55);
}
.wizard-progress li.active {
  color: #fff;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border-color: transparent;
  box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);
}
.wizard-progress li.done {
  color: #6ee7b7;
  border-color: rgba(52, 211, 153, 0.5);
  background: rgba(16, 185, 129, 0.12);
}
.wizard-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin: 1.4rem 0 1.5rem;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  font-size: 0.82rem;
  font-weight: 500;
  color: #cbd5e1;
}
.input-control {
  width: 100%;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.12);
  padding: 0.85rem 1rem;
  border-radius: 8px;
  color: #f8fafc;
  font-size: 0.95rem;
  line-height: 1.3;
  box-sizing: border-box;
}
.input-control:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.22);
}
.wizard-options {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.wizard-option {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.8rem 0.95rem;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.07);
  color: #e2e8f0;
  cursor: pointer;
}
.wizard-option:hover {
  border-color: rgba(99, 102, 241, 0.35);
}
.wizard-icon {
  width: 26px;
  height: 26px;
  object-fit: contain;
}
.help-chip {
  margin-left: auto;
  width: 1.55rem;
  height: 1.55rem;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 0.82rem;
  color: #93c5fd;
  border: 1px solid rgba(147, 197, 253, 0.4);
  text-decoration: none;
  background: rgba(59, 130, 246, 0.12);
}
.wizard-dl {
  display: grid;
  gap: 0.75rem;
}
.wizard-dl div {
  display: grid;
  grid-template-columns: 8.5rem 1fr;
  gap: 0.6rem;
  padding: 0.7rem 0.85rem;
  background: rgba(15, 23, 42, 0.45);
  border-radius: 10px;
}
.wizard-dl dt {
  color: #64748b;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.wizard-dl dd {
  margin: 0;
  color: #e2e8f0;
}
.wizard-actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
}
.wizard-nav {
  display: flex;
  gap: 0.65rem;
}
.btn-primary,
.btn-secondary {
  min-height: 2.75rem;
  padding: 0.8rem 1.35rem;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-primary {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border: none;
  color: #fff;
  box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
}
.btn-primary:hover:not(:disabled) {
  filter: brightness(1.08);
}
.btn-secondary {
  background: rgba(30, 41, 59, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e2e8f0;
}
.btn-secondary:hover:not(:disabled) {
  background: rgba(51, 65, 85, 0.9);
  color: #fff;
}
.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.alert-banner {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.85rem;
}
.alert-error {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fca5a5;
}
.wizard-install-list {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.85rem;
  color: #cbd5e1;
  margin: 0;
  padding-left: 1.1rem;
}
</style>
