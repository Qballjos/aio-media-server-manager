<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { apiRequest, readJson, apiError } from './api.js'
const form = ref({ enabled: false, url: '', username: '', password: '', encryption_password: '' })
const saved = ref({}), busy = ref(false), error = ref(''), job = ref(null), name = ref('')
let timer
async function call(path, options = {}) {
  const response = await apiRequest(path, options), data = await readJson(response)
  if (!response.ok) throw new Error(apiError(data))
  return data
}
async function load() {
  saved.value = await call('/api/backups/external/config')
  form.value = { ...saved.value, password: '', encryption_password: '' }
}
async function save() {
  busy.value = true; error.value = ''
  try {
    await call('/api/backups/external/config', { method: 'PUT', body: JSON.stringify({ enabled: form.value.enabled, url: form.value.url, username: form.value.username, password: form.value.password || null, encryption_password: form.value.encryption_password || null }) })
    await load()
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function refresh() {
  try {
    const data = await call('/api/backups/job')
    job.value = data.job
    if (job.value?.status !== 'running') { clearInterval(timer); timer = null; busy.value = false; saved.value = await call('/api/backups/external/config') }
  } catch (err) { error.value = err.message; busy.value = false; clearInterval(timer) }
}
async function run(action) {
  busy.value = true; error.value = ''
  try {
    const data = await call(`/api/backups/external/${action}`, { method: 'POST', body: JSON.stringify({ name: name.value.trim() }) })
    job.value = data.job
    clearInterval(timer); timer = setInterval(refresh, 2000)
  } catch (err) { error.value = err.message; busy.value = false }
}
onMounted(async () => { try { await load(); await refresh(); if (job.value?.status === 'running') { busy.value = true; timer = setInterval(refresh, 2000) } } catch (err) { error.value = err.message } })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <section class="glass-card settings-card">
    <h3>{{ $t('Encrypted external backups') }}</h3>
    <p>{{ $t('Store a verified encrypted copy over HTTPS/WebDAV. Keep the encryption password somewhere outside this server; it is required for recovery.') }}</p>
    <form class="form-stack" @submit.prevent="save">
      <label><input type="checkbox" v-model="form.enabled" /> {{ $t('Automatically export new backups') }}</label>
      <label class="ui-field">{{ $t('WebDAV folder URL') }}<input class="ui-input" type="url" v-model="form.url" placeholder="https://cloud.example/remote.php/dav/files/user/backups" /></label>
      <label class="ui-field">{{ $t('Username') }}<input class="ui-input" v-model="form.username" autocomplete="off" /></label>
      <label class="ui-field">{{ $t('WebDAV password') }}<input class="ui-input" type="password" v-model="form.password" autocomplete="new-password" :placeholder="saved.password_saved ? $t('Saved — leave blank to keep') : ''" /></label>
      <label class="ui-field">{{ $t('Backup encryption password') }}<input class="ui-input" type="password" v-model="form.encryption_password" minlength="16" autocomplete="new-password" :placeholder="saved.encryption_password_saved ? $t('Saved — leave blank to keep') : $t('At least 16 characters')" /></label>
      <button class="ui-btn ui-btn-primary" :disabled="busy">{{ $t('Save') }}</button>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="saved.last_transfer">{{ $t('Last external copy') }}: {{ saved.last_transfer.status }} {{ saved.last_transfer.name || saved.last_transfer.error }}</p>
    <p v-if="saved.last_drill">{{ $t('Last restore test') }}: {{ saved.last_drill.status }} — {{ saved.last_drill.name }}</p>
    <label class="ui-field">{{ $t('Backup filename') }}<input class="ui-input" v-model="name" :placeholder="$t('amm-….tar.gz (or .tar.gz.aioenc for import)')" /></label>
    <div class="share-row"><button class="ui-btn ui-btn-ghost" :disabled="busy || !name" @click="run('export')">{{ $t('Export encrypted copy') }}</button><button class="ui-btn ui-btn-ghost" :disabled="busy || !name" @click="run('import')">{{ $t('Import external copy') }}</button><button class="ui-btn ui-btn-ghost" :disabled="busy || !name" @click="run('drill')">{{ $t('Test restore safely') }}</button></div>
    <p>{{ $t('Import first, then test the imported filename. A restore test uses a temporary folder and leaves running apps untouched. To restore for real, choose the imported backup in the backup list.') }}</p>
    <div v-if="job" aria-live="polite"><strong>{{ job.kind }}: {{ job.stage }}</strong><p v-if="job.error" role="alert">{{ job.error }}</p><p v-if="job.result">{{ job.result.status }} — {{ job.result.name }}</p></div>
  </section>
</template>
