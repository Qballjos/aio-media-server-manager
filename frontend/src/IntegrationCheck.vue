<script setup>
import { ref, onMounted } from 'vue'
import { apiRequest, readJson, apiError } from './api.js'
const report = ref(null), busy = ref(false), error = ref(''), message = ref(''), choice = ref({ enabled: false, indexers: [] })
async function call(path, options = {}) {
  const response = await apiRequest(path, options), data = await readJson(response)
  if (!response.ok) throw new Error(apiError(data))
  return data
}
async function verify() {
  busy.value = true; error.value = ''; message.value = ''
  try { report.value = await call('/api/integrations/verify', { method: 'POST' }) }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function repair() {
  busy.value = true; error.value = ''
  try { await call('/api/integrations/run', { method: 'POST' }); message.value = 'Auto-Wire has started. Check again when setup has finished.' }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function saveChoice() {
  busy.value = true; error.value = ''
  try { choice.value = await call('/api/integrations/public-indexers', { method: 'PUT', body: JSON.stringify({ enabled: choice.value.enabled }) }); message.value = 'Choice saved. Run Auto-Wire to add selected public indexers. Existing indexers are kept.' }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(async () => { try { choice.value = await call('/api/integrations/public-indexers') } catch (err) { error.value = err.message } })
</script>
<template>
  <section class="glass-card settings-card">
    <h3>{{ $t('Check my installation') }}</h3>
    <p>{{ $t('Read back library folders, download clients, indexer synchronization and request connections. No settings are changed by this check.') }}</p>
    <div class="share-row"><button class="ui-btn ui-btn-primary" :disabled="busy" @click="verify">{{ $t('Check connections') }}</button><button class="ui-btn ui-btn-ghost" :disabled="busy" @click="repair">Auto-Wire</button></div>
    <p v-if="busy" aria-live="polite">{{ $t('Working…') }}</p><p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ $t(message) }}</p>
    <ul v-if="report"><li v-for="(check, index) in report.checks" :key="index"><strong>{{ check.app }} — {{ check.name }}: {{ check.status }}</strong><p>{{ check.detail }} {{ check.hint }}</p></li></ul>
    <p v-if="report && !report.checks.length">{{ $t('Install supported apps to check their connections.') }}</p>
    <h3>{{ $t('Public torrent indexers') }}</h3>
    <label><input type="checkbox" v-model="choice.enabled" :disabled="busy" /> {{ $t('Add the starter set of public torrent indexers (optional)') }}</label>
    <p>{{ $t('Off by default. You can add your own sources in Prowlarr.') }}</p><p>{{ choice.indexers.join(', ') }}</p>
    <button class="ui-btn ui-btn-ghost" :disabled="busy" @click="saveChoice">{{ $t('Save') }}</button>
  </section>
</template>
