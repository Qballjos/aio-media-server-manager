<script setup>
import { ref } from 'vue'
import { assistantRequest } from './aiAssistant.js'

const clients = { qbittorrent: 'qBittorrent', sabnzbd: 'SABnzbd', nzbget: 'NZBGet', transmission: 'Transmission' }
const service = ref('qbittorrent')
const action = ref('pause')
const preview = ref(null)
const busy = ref(false)
const error = ref('')

async function run(confirm = null) {
  error.value = ''
  preview.value = null
  busy.value = true
  try {
    preview.value = await assistantRequest('arr-mcp/downloads', 'POST', {
      service: service.value, action: action.value, confirm,
    })
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <details>
    <summary>{{ $t('Download actions') }}</summary>
    <form class="download-action" @submit.prevent="run()">
      <label>
        {{ $t('Download client') }}
        <select v-model="service" class="ui-input" :disabled="busy" @change="preview = null">
          <option v-for="(name, id) in clients" :key="id" :value="id">{{ name }}</option>
        </select>
      </label>
      <label>
        {{ $t('Action') }}
        <select v-model="action" class="ui-input" :disabled="busy" @change="preview = null">
          <option value="pause">{{ $t('Pause downloads') }}</option>
          <option value="resume">{{ $t('Resume downloads') }}</option>
        </select>
      </label>
      <button class="ui-btn" :disabled="busy">{{ $t('Preview change') }}</button>
    </form>
    <p v-if="preview" role="status">{{ preview.summary }}</p>
    <p v-if="error" role="alert">{{ $t(error) }}</p>
    <button v-if="preview?.confirm" type="button" class="ui-btn ui-btn-primary" :disabled="busy" @click="run(preview.confirm)">
      {{ $t('Confirm change') }}
    </button>
  </details>
</template>

<style scoped>
summary { cursor: pointer; min-height: 44px; align-content: center; }
.download-action { display: flex; flex-wrap: wrap; align-items: end; gap: 0.5rem; }
label { display: grid; gap: 0.25rem; flex: 1 1 8rem; }
</style>
