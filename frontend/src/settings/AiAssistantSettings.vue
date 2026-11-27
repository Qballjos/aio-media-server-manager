<script setup>
import { onMounted, ref } from 'vue'
import { apiJson } from '../api.js'
import AiProvidersSettings from './AiProvidersSettings.vue'

const endpoint = ref('')
const savedEndpoint = ref('')
const token = ref('')
const busy = ref(false)
const status = ref(null)

async function request(path, method = 'GET', body) {
  const { res, data } = await apiJson('/api/ai-assistant/arr-mcp/' + path, {
    method, body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error('arr-mcp request failed')
  return data
}

async function run(action) {
  busy.value = true
  status.value = null
  try {
    await action()
  } catch {
    status.value = 'error'
  } finally {
    busy.value = false
  }
}

function applySettings(data) {
  savedEndpoint.value = data.endpoint || ''
  endpoint.value = savedEndpoint.value
  token.value = ''
}

onMounted(() => run(async () => applySettings(await request('settings'))))

function save() {
  return run(async () => {
    applySettings(await request('settings', 'PUT', { endpoint: endpoint.value.trim() || null, token: token.value || null }))
    status.value = 'saved'
  })
}

function check() {
  return run(async () => {
    await request('check', 'POST')
    status.value = 'connected'
  })
}

function disconnect() {
  return run(async () => {
    await request('settings', 'DELETE')
    applySettings({})
  })
}
</script>

<template>
  <AiProvidersSettings />
  <section class="glass-card connection-card" :aria-busy="busy">
    <h3>arr-mcp</h3>
    <form class="connection-card connection-form" @submit.prevent="save">
      <label>
        {{ $t('arr-mcp address') }}
        <input v-model="endpoint" class="ui-input" maxlength="128" :disabled="busy" placeholder="http://192.168.1.10:6060/mcp" />
      </label>
      <label>
        {{ $t('arr-mcp read token') }}
        <input v-model="token" class="ui-input" type="password" autocomplete="off" maxlength="2048" :required="!!endpoint.trim() && endpoint.trim() !== savedEndpoint" :disabled="busy" />
      </label>
      <div class="connection-actions">
        <button class="ui-btn ui-btn-primary" :disabled="busy">{{ $t('Save') }}</button>
        <button v-if="savedEndpoint" type="button" class="ui-btn" :disabled="busy || endpoint.trim() !== savedEndpoint || !!token" @click="check">
          {{ $t('Check connection') }}
        </button>
        <button v-if="savedEndpoint" type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="disconnect">
          {{ $t('Remove connection') }}
        </button>
      </div>
    </form>
    <p v-if="status === 'saved'" role="status">{{ $t('Connection settings saved.') }}</p>
    <p v-if="status === 'connected'" role="status">{{ $t('arr-mcp connection verified.') }}</p>
    <p v-if="status === 'error'" role="alert">{{ $t('Check the MCP address and read token.') }}</p>
  </section>
</template>

<style scoped>
.connection-card, label { display: grid; gap: 0.75rem; min-width: 0; }
.connection-card { padding: 1rem; }
.connection-form { padding: 0; }
.connection-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
</style>
