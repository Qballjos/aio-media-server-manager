<script setup>
import { computed, onMounted, ref } from 'vue'
import { assistantRequest, providers } from '../aiAssistant.js'

const selected = ref('openai')
const saved = ref({})
const model = ref('')
const key = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const configured = computed(() => !!saved.value[selected.value])

function resetForm() {
  model.value = saved.value[selected.value] || ''
  key.value = ''
  error.value = ''
  notice.value = ''
}

async function run(action) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}

onMounted(() => run(async () => {
  saved.value = await assistantRequest('providers')
  resetForm()
}))

function save() {
  return run(async () => {
    const result = await assistantRequest('providers/' + selected.value, 'PUT', {
      model: model.value.trim(), api_key: key.value.trim() || null,
    })
    saved.value[selected.value] = result.model
    resetForm()
    notice.value = 'Provider settings saved.'
  })
}

function remove() {
  return run(async () => {
    await assistantRequest('providers/' + selected.value, 'DELETE')
    delete saved.value[selected.value]
    resetForm()
    notice.value = 'Provider removed.'
  })
}
</script>

<template>
  <section class="glass-card provider-card" :aria-busy="busy">
    <form class="provider-form" @submit.prevent="save">
      <label>
        {{ $t('AI provider') }}
        <select v-model="selected" class="ui-input" :disabled="busy" @change="resetForm">
          <option v-for="(provider, id) in providers" :key="id" :value="id">
            {{ provider.name }}{{ saved[id] ? ' · ' + $t('Configured') : '' }}
          </option>
        </select>
      </label>
      <label>
        {{ $t('Model ID') }}
        <input v-model="model" class="ui-input" maxlength="120" required :disabled="busy" />
      </label>
      <label>
        {{ $t('API key') }}
        <input v-model="key" class="ui-input" type="password" autocomplete="new-password" maxlength="2048"
          :required="!configured" :disabled="busy" :placeholder="configured ? $t('API key saved') : ''" />
      </label>
      <a :href="providers[selected].console" target="_blank" rel="noopener noreferrer">{{ $t('Get an API key') }}</a>
      <div class="provider-actions">
        <button class="ui-btn ui-btn-primary" :disabled="busy">{{ $t('Save') }}</button>
        <button v-if="configured" type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="remove">
          {{ $t('Remove connection') }}
        </button>
      </div>
    </form>
    <p v-if="notice" role="status">{{ $t(notice) }}</p>
    <p v-if="error" role="alert">{{ $t(error) }}</p>
  </section>
</template>

<style scoped>
.provider-card { padding: 1rem; }
.provider-card, .provider-form, label { display: grid; gap: 0.75rem; min-width: 0; }
.provider-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
</style>
