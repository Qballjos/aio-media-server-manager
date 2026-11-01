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
  const response = await apiRequest('/api/homey/devices')
  if (!response.ok) throw new Error(await apiError(response))
  devices.value = (await readJson(response)).devices || []
}
async function invite() {
  busy.value = true
  error.value = ''
  try {
    const response = await apiRequest('/api/homey/pairings', { method: 'POST' })
    if (!response.ok) throw new Error(await apiError(response))
    const data = await readJson(response)
    link.value = data.pairingCode
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
    const response = await apiRequest(`/api/homey/devices/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!response.ok) throw new Error(await apiError(response))
    await load()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
onMounted(() => load().catch(e => { error.value = e.message }))
</script>

<template>
  <div class="glass-card settings-card tv-connections">
    <header class="tv-connections-head">
      <h3>{{ $t('Homey connections') }}</h3>
      <p>{{ $t('Connect Homey with a one-use code. Homey can only read dashboard data.') }}</p>
    </header>
    <div class="tv-pairing">
      <ol class="tv-pairing-steps">
        <li>{{ $t('In Homey, add AIO Media Server Manager and enter this server address.') }}</li>
        <li>{{ $t('Create a code here and paste it in the Homey pairing screen.') }}</li>
      </ol>
      <div class="tv-connection-actions">
        <button class="ui-btn ui-btn-primary" :disabled="busy" @click="invite">{{ $t('Create Homey code') }}</button>
      </div>
      <div v-if="link" class="tv-pairing-link">
        <label class="ui-field">
          {{ $t('Homey pairing code') }}
          <input class="ui-input" :value="link" readonly autocomplete="off" spellcheck="false" />
        </label>
        <p class="ui-field-hint">{{ $t('Valid for 5 minutes and one use. A new link cancels the previous one.') }}</p>
        <div class="tv-connection-actions">
          <button class="ui-btn" @click="copy">{{ copied ? $t('Copied') : $t('Copy code') }}</button>
        </div>
      </div>
      <p class="ui-field-hint">{{ $t('Homey can read what is playing and recently added titles. It cannot change settings or control playback.') }}</p>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <section class="tv-devices">
      <div class="tv-devices-head">
        <h4>{{ $t('Connected Homeys') }}</h4>
        <button class="ui-btn ui-btn-ghost" :disabled="busy" @click="load().catch(e => { error = e.message })">{{ $t('Refresh') }}</button>
      </div>
      <ul v-if="devices.length" class="tv-device-list">
        <li v-for="device in devices" :key="device.id">
          <span>{{ device.name }}</span>
          <button class="ui-btn ui-btn-ghost" :disabled="busy" @click="revoke(device.id)">{{ $t('Disconnect') }}</button>
        </li>
      </ul>
      <p v-else class="ui-field-hint">{{ $t('No Homeys connected yet.') }}</p>
    </section>
  </div>
</template>

<style scoped>
.tv-connections,
.tv-pairing,
.tv-pairing-link,
.tv-devices {
  display: grid;
  gap: 1.25rem;
  min-width: 0;
}
.tv-connections {
  gap: 1.75rem;
}
.tv-connections p,
.tv-connections h4 {
  margin: 0;
}
.tv-connections-head h3 {
  margin: 0.4rem 0 0.5rem;
  font-size: var(--text-strong);
  color: var(--text-heading);
}
.tv-connections-head p,
.tv-pairing-steps {
  max-width: 62ch;
  color: var(--text-muted);
  line-height: 1.6;
}
.tv-pairing,
.tv-devices {
  max-width: 42rem;
}
.tv-pairing-steps {
  display: grid;
  gap: 0.65rem;
  margin: 0;
  padding-left: 1.4rem;
}
.tv-pairing-link,
.tv-devices {
  padding-top: 1.25rem;
  border-top: 1px solid var(--border-subtle);
}
.tv-pairing-link {
  gap: 0.85rem;
}
.tv-connection-actions,
.tv-devices-head,
.tv-device-list li {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.tv-devices-head,
.tv-device-list li {
  justify-content: space-between;
}
.tv-device-list {
  display: grid;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tv-device-list span {
  overflow-wrap: anywhere;
}
</style>
