<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { appIconSrc } from './appIcons.js'

const props = defineProps({
  apiRequest: { type: Function, required: true }
})
const emit = defineEmits(['done'])

const step = ref(1)
const steps = ref([])
const payload = ref({})
const selections = reactive({})
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const installing = ref(false)
const installProgress = ref([])

const TITLE = {
  1: 'Welcome',
  2: 'Platform',
  3: 'Storage',
  4: 'Permissions',
  5: 'Download clients',
  6: 'VPN',
  7: '*Arr apps',
  8: 'Media server',
  9: 'Requests',
  10: 'Recommended tools',
  11: 'Review',
  12: 'Install'
}

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
      selections.config_dir = data.config_dir || ''
    } else if (id === 4) {
      selections.puid = data.puid
      selections.pgid = data.pgid
    } else if (id === 5) {
      selections.download_clients = [...(data.selected || [])]
      selections.preferred_download_client = data.preferred_download_client || 'qbittorrent'
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
  if (id === 3) return { media_dir: selections.media_dir, config_dir: selections.config_dir }
  if (id === 4) return { puid: Number(selections.puid), pgid: Number(selections.pgid) }
  if (id === 5) {
    const body = {
      download_clients: selections.download_clients,
      preferred_download_client: selections.preferred_download_client,
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
    if (step.value >= 3 && step.value <= 10) {
      const res = await props.apiRequest(`/api/wizard/step/${step.value}`, {
        method: 'POST',
        body: JSON.stringify(bodyForStep(step.value))
      })
      if (!res.ok) throw new Error('Could not save this step')
    }
    step.value += 1
    await loadStep(step.value)
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function back() {
  if (step.value <= 1) return
  step.value -= 1
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
    steps.value = status.steps || []
    step.value = Math.min(status.current_step || 1, 12)
  }
  await loadStep(step.value)
})
</script>

<template>
  <section class="wizard-shell animate-fade">
    <div class="glass-card wizard-card">
      <div class="wizard-header">
        <span class="accent-badge">FIRST-RUN SETUP</span>
        <h2>{{ TITLE[step] }}</h2>
        <p>Step {{ step }} of 12 — pick your stack, then we will save settings and start installs.</p>
        <ol class="wizard-progress">
          <li
            v-for="item in (steps.length ? steps : Array.from({ length: 12 }, (_, i) => ({ id: i + 1 })))"
            :key="item.id"
            :class="{ active: item.id === step, done: item.id < step }"
          >
            {{ item.id }}
          </li>
        </ol>
      </div>

      <p v-if="error" class="alert-banner alert-error">{{ error }}</p>
      <p v-if="loading" class="wizard-muted">Loading…</p>

      <div v-else class="wizard-body">
        <template v-if="step === 1">
          <p>{{ payload.description }}</p>
          <p class="wizard-muted">You can skip and install apps later from the catalog. Help links stay available on every app card.</p>
        </template>

        <template v-else-if="step === 2">
          <dl class="wizard-dl">
            <div><dt>OS</dt><dd>{{ payload.platform?.system }} {{ payload.platform?.release }}</dd></div>
            <div><dt>Arch</dt><dd>{{ payload.platform?.machine }}</dd></div>
            <div><dt>Container</dt><dd>{{ payload.platform?.is_container ? 'Yes' : 'No' }}</dd></div>
          </dl>
        </template>

        <template v-else-if="step === 3">
          <label class="form-group">
            Media directory
            <input v-model="selections.media_dir" class="input-control font-mono" />
          </label>
          <label class="form-group">
            Config directory
            <input v-model="selections.config_dir" class="input-control font-mono" />
          </label>
          <p class="wizard-muted">{{ payload.hardlink_message }}</p>
        </template>

        <template v-else-if="step === 4">
          <label class="form-group">
            PUID
            <input v-model="selections.puid" type="number" min="1" class="input-control font-mono" />
          </label>
          <label class="form-group">
            PGID
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
          <label class="form-group">
            Preferred download client
            <select v-model="selections.preferred_download_client" class="input-control">
              <option v-for="id in selections.download_clients" :key="id" :value="id">{{ id }}</option>
            </select>
          </label>
          <template v-if="showQbitCreds">
            <label class="form-group">
              qBittorrent WebUI username
              <input v-model="selections.qbittorrent_username" class="input-control font-mono" />
            </label>
            <label class="form-group">
              qBittorrent WebUI password
              <input v-model="selections.qbittorrent_password" type="password" class="input-control" placeholder="Leave blank to keep existing" />
            </label>
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
              VPN config path
              <input v-model="selections.vpn_config_path" class="input-control font-mono" placeholder="/config/vpn/wg0.conf" />
            </label>
            <label class="form-group">
              Protocol
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
            Plex claim token
            <input v-model="selections.plex_claim" class="input-control font-mono" placeholder="claim-…" />
            <span class="wizard-muted">Get a token from plex.tv/claim. Optional if you will sign in from the Plex UI.</span>
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

        <template v-else-if="step === 11">
          <dl class="wizard-dl">
            <div><dt>*Arr</dt><dd>{{ (summary.arr_apps || []).join(', ') || '—' }}</dd></div>
            <div><dt>Download</dt><dd>{{ (summary.download_clients || []).join(', ') || '—' }} (preferred: {{ summary.preferred_download_client || '—' }})</dd></div>
            <div><dt>Media</dt><dd>{{ (summary.media_servers || []).join(', ') || '—' }}</dd></div>
            <div><dt>Requests</dt><dd>{{ summary.request_system || '—' }}</dd></div>
            <div><dt>VPN</dt><dd>{{ summary.vpn_provider || 'none' }}</dd></div>
            <div><dt>Recommended</dt><dd>{{ (summary.recommended_preview || []).join(', ') || 'none' }}</dd></div>
          </dl>
        </template>

        <template v-else>
          <p>Save paths, credentials, and VPN options, then start catalog installs for the apps you picked. Wiring runs after processes come up.</p>
          <ul v-if="installProgress.length" class="wizard-install-list">
            <li v-for="item in installProgress" :key="item.name">{{ item.name }} — {{ item.status }}</li>
          </ul>
        </template>
      </div>

      <div class="wizard-actions">
        <button type="button" class="btn-secondary" :disabled="saving || installing" @click="skip">Skip for now</button>
        <div class="wizard-nav">
          <button type="button" class="btn-secondary" :disabled="step === 1 || saving || installing" @click="back">Back</button>
          <button v-if="step < 12" type="button" class="btn-primary" :disabled="saving || loading" @click="next">
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
  padding: 1.75rem;
}
.wizard-header h2 {
  margin: 0.4rem 0 0.35rem;
}
.wizard-header p,
.wizard-muted {
  color: #94a3b8;
  font-size: 0.9rem;
}
.wizard-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  list-style: none;
  padding: 0;
  margin: 1rem 0 0;
}
.wizard-progress li {
  width: 1.6rem;
  height: 1.6rem;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 0.7rem;
  color: #64748b;
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.wizard-progress li.active {
  color: #fff;
  background: #6366f1;
  border-color: #6366f1;
}
.wizard-progress li.done {
  color: #6ee7b7;
  border-color: rgba(52, 211, 153, 0.45);
}
.wizard-body {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  margin: 1.25rem 0;
}
.wizard-options {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.wizard-option {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 0.7rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}
.wizard-icon {
  width: 22px;
  height: 22px;
  object-fit: contain;
}
.help-chip {
  margin-left: auto;
  width: 1.35rem;
  height: 1.35rem;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 0.75rem;
  color: #93c5fd;
  border: 1px solid rgba(147, 197, 253, 0.4);
  text-decoration: none;
}
.wizard-dl {
  display: grid;
  gap: 0.6rem;
}
.wizard-dl div {
  display: grid;
  grid-template-columns: 8rem 1fr;
  gap: 0.5rem;
}
.wizard-dl dt {
  color: #64748b;
}
.wizard-actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
}
.wizard-nav {
  display: flex;
  gap: 0.5rem;
}
.wizard-install-list {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: #cbd5e1;
}
</style>
