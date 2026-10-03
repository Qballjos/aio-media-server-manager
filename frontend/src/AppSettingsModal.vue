<script setup>
import { computed, ref, watch } from 'vue'
import { apiError, apiRequest, readJson } from './api.js'
import { useToasts } from './useToasts.js'

const props = defineProps({
  service: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved'])
const { showToast } = useToasts()

const settingsApp = computed(() => props.service)
const settingsForm = ref({
  port: 0,
  autostart: true,
  vuetorrent: false,
  apiKey: '',
  recyclarrYaml: '',
  recyclarrOriginalYaml: '',
  recyclarrNaming: 'plex',
  recyclarrPrefs: {}
})
const settingsMeta = ref(null)
const recyclarrMeta = ref(null)
const settingsLoading = ref(false)
const settingsError = ref('')

const actionLoading = ref({})

async function loadSettings(service) {
  settingsError.value = ''
  settingsLoading.value = true
  try {
    const res = await apiRequest(`/api/applications/${service.name}/settings`)
    const data = await readJson(res)
    if (!res.ok) {
      settingsError.value = apiError(data, 'Could not load settings.')
      settingsMeta.value = null
      settingsForm.value = { port: service.port, autostart: service.autostart }
      return
    }
    settingsMeta.value = data
    settingsForm.value = {
      port: data.port,
      autostart: data.autostart,
      vuetorrent: !!data.vuetorrent,
      apiKey: '',
      recyclarrYaml: '',
      recyclarrOriginalYaml: '',
      recyclarrNaming: 'plex',
      recyclarrPrefs: {}
    }
    recyclarrMeta.value = null
    if (service.name === 'recyclarr') {
      const rec = await apiRequest('/api/recyclarr')
      const recData = await readJson(rec)
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
  settingsMeta.value = null
  recyclarrMeta.value = null
  settingsError.value = ''
  emit('close')
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
        const recData = await readJson(rec)
        if (!rec.ok) {
          settingsError.value = apiError(recData, 'Could not save Recyclarr YAML.')
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
        const recData = await readJson(rec)
        if (!rec.ok) {
          settingsError.value = apiError(recData, 'Could not save Recyclarr profiles.')
          return
        }
      }
      showToast('Saved Recyclarr TRaSH config', 'success')
      closeAppSettings()
      emit('saved')
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
    if (['jellyfin', 'seerr'].includes(settingsApp.value.name) && String(settingsForm.value.apiKey || '').trim()) {
      payload.api_key = String(settingsForm.value.apiKey).trim()
    }
    const res = await apiRequest(`/api/applications/${settingsApp.value.name}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
    const data = await readJson(res)
    if (!res.ok) {
      settingsError.value = apiError(data, 'Could not save settings.')
      return
    }
    showToast(
      data.restarted
        ? `Saved ${data.display_name} and restarted on port ${data.port}`
        : `Saved ${data.display_name} settings`,
      'success'
    )
    closeAppSettings()
    emit('saved')
  } catch (err) {
    settingsError.value = err.message || 'Could not save settings.'
  } finally {
    settingsLoading.value = false
  }
}

async function resetRecyclarrDefaults() {
  settingsLoading.value = true
  settingsError.value = ''
  try {
    const rec = await apiRequest('/api/recyclarr/reset', { method: 'POST' })
    const recData = await readJson(rec)
    if (!rec.ok) {
      settingsError.value = apiError(recData, 'Could not reset Recyclarr.')
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


watch(
  () => props.service,
  (service) => {
    if (service) loadSettings(service)
  },
  { immediate: true }
)
</script>

<template>
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
          <div v-if="settingsApp.name === 'jellyfin' || settingsApp.name === 'seerr'" class="ui-field-block">
            <label class="ui-field">
              {{ settingsApp.name === 'seerr' ? 'Seerr' : 'Jellyfin' }} API key
              <input
                v-model="settingsForm.apiKey"
                class="ui-input font-mono"
                type="password"
                autocomplete="off"
                :placeholder="settingsMeta.api_key_configured
                  ? 'Saved — paste a new key to replace'
                  : (settingsApp.name === 'seerr' ? 'Settings → General → API Key' : 'Dashboard → API Keys')"
              />
            </label>
            <p class="settings-hint">
              Optional. Saved keys are used for
              {{ settingsApp.name === 'seerr' ? 'Home search and requests' : 'Recently added' }}.
              Leave empty to keep the current key.
            </p>
          </div>
          <div v-if="settingsApp.name === 'qbittorrent'" class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>VueTorrent WebUI</strong>
              <span>
                On by default. Uses
                <a href="https://github.com/VueTorrent/VueTorrent" target="_blank" rel="noopener noreferrer">VueTorrent</a>
                instead of the stock qBittorrent WebUI. Turn off for the stock UI. *Arr still uses the same WebAPI.
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
</template>
