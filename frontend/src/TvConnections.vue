<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { apiRequest, apiError, readJson } from './api.js'
import { copyText } from './clipboard.js'

const devices = ref([])
const link = ref('')
const error = ref('')
const busy = ref(false)
const copied = ref(false)
let expiry
onBeforeUnmount(() => clearTimeout(expiry))

async function load() {
  const response = await apiRequest('/api/tv/devices')
  if (!response.ok) throw new Error(await apiError(response))
  devices.value = (await readJson(response)).devices || []
}
async function invite() {
  busy.value = true
  error.value = ''
  try {
    const response = await apiRequest('/api/tv/pairings', { method: 'POST' })
    if (!response.ok) throw new Error(await apiError(response))
    const data = await readJson(response)
    link.value = `${window.location.origin}/#tv-pair=${encodeURIComponent(data.pairingCode)}`
    copied.value = false
    clearTimeout(expiry)
    expiry = setTimeout(() => { link.value = '' }, data.expiresIn * 1000)
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function copy() {
  try { await copyText(link.value); copied.value = true }
  catch (e) { error.value = e.message }
}
async function revoke(id) {
  busy.value = true
  error.value = ''
  try {
    const response = await apiRequest(`/api/tv/devices/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!response.ok) throw new Error(await apiError(response))
    await load()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
onMounted(() => load().catch(e => { error.value = e.message }))
</script>

<template>
  <div class="glass-card settings-card">
    <div class="settings-card-head">
      <h3>{{ $t('TV connections') }}</h3>
      <p>{{ $t('Connect TV Thuis without entering passwords or API keys on your TV.') }}</p>
    </div>
    <p>{{ $t('On the TV, choose AIO Media → Connect with AIO and scan the QR code. Create a link here and paste it on that phone page.') }}</p>
    <button class="ui-btn ui-btn-primary" :disabled="busy" @click="invite">{{ $t('Create pairing link') }}</button>
    <div v-if="link" class="form-stack">
      <p>{{ $t('This link works once for five minutes. A new link replaces the previous one. It allows media browsing and requests, not server administration.') }}</p>
      <label class="ui-field">{{ $t('Pairing link') }}<textarea class="ui-input" :value="link" readonly rows="3" autocomplete="off" spellcheck="false" /></label>
      <button class="ui-btn" @click="copy">{{ copied ? $t('Copied') : $t('Copy link') }}</button>
      <button class="ui-btn ui-btn-ghost" :disabled="busy" @click="load().catch(e => { error = e.message })">{{ $t('Refresh') }}</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <ul v-if="devices.length">
      <li v-for="device in devices" :key="device.id">
        {{ device.name }}
        <button class="ui-btn ui-btn-ghost" :disabled="busy" @click="revoke(device.id)">{{ $t('Disconnect') }}</button>
      </li>
    </ul>
  </div>
</template>
