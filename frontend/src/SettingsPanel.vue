<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  apiRequest: { type: Function, required: true }
})

const loading = ref(false)
const error = ref('')
const share = ref({ active: false, url: '', expires_at: null, ttl_hours: 24 })
const errors = ref([])
const copied = ref(false)

async function loadStatus() {
  loading.value = true
  error.value = ''
  try {
    const res = await props.apiRequest('/api/diagnostics')
    const data = await res.json()
    if (!res.ok) {
      error.value = data.detail || 'Could not load diagnostics.'
      return
    }
    share.value = data.share || share.value
    errors.value = data.errors || []
  } catch (err) {
    error.value = err.message || 'Could not load diagnostics.'
  } finally {
    loading.value = false
  }
}

async function createShare() {
  loading.value = true
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
    loading.value = false
  }
}

async function revokeShare() {
  loading.value = true
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
    loading.value = false
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

onMounted(loadStatus)
</script>

<template>
  <section class="settings-page animate-fade">
    <div class="settings-header">
      <div>
        <h2 class="section-title">Settings</h2>
        <p class="section-subtitle">Testing tools. Turn debug off when you are done sharing a report.</p>
      </div>
    </div>

    <div class="glass-card settings-card">
      <div class="settings-card-head">
        <span class="accent-badge">DEBUG</span>
        <h3>Error manager</h3>
        <p>
          Capture recent errors, catalog install state, and process logs behind a time-limited URL
          you can send for support. Secrets are redacted. The link expires after {{ share.ttl_hours || 24 }} hours.
        </p>
      </div>

      <div v-if="error" class="ui-alert ui-alert-error">{{ error }}</div>

      <div class="ui-switch-row">
        <div class="ui-switch-copy">
          <strong>Debug share URL</strong>
          <span>
            When on, a time-limited link is available for support. Secrets are redacted.
            The link expires after {{ share.ttl_hours || 24 }} hours.
          </span>
        </div>
        <button
          type="button"
          class="ui-switch"
          role="switch"
          :aria-checked="share.active ? 'true' : 'false'"
          :disabled="loading"
          :title="share.active ? 'Turn debug sharing off' : 'Turn debug sharing on'"
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
  </section>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
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
.settings-card {
  padding: 1.4rem 1.5rem;
}
.settings-card-head h3 {
  margin: 0.4rem 0 0.35rem;
  font-size: 1.05rem;
  color: #fff;
}
.settings-card-head p {
  color: #94a3b8;
  margin: 0 0 1rem;
  max-width: 62ch;
}
.share-row {
  display: flex;
  gap: 0.6rem;
}
.share-row .ui-input {
  flex: 1;
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
</style>
