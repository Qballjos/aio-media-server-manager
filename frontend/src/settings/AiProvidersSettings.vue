<script setup>
import { computed, onMounted, ref } from 'vue'
import { assistantRequest, providers } from '../aiAssistant.js'

const selected = ref('openai')
const saved = ref({})
const active = ref(null)
const shareLocalStatus = ref(false)
const model = ref('')
const customModel = ref('')
const advanced = ref(false)
const key = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const current = computed(() => providers[selected.value])
const configured = computed(() => !!saved.value[selected.value])

function resetForm() {
  const previous = saved.value[selected.value]
  model.value = !previous || current.value.models.includes(previous) ? (previous || current.value.models[0]) : 'custom'
  customModel.value = model.value === 'custom' ? previous : ''
  advanced.value = false
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
  const [models, preferences] = await Promise.all([
    assistantRequest('providers'), assistantRequest('preferences'),
  ])
  saved.value = models
  active.value = preferences.provider
  shareLocalStatus.value = preferences.share_local_status
  if (active.value) selected.value = active.value
  resetForm()
}))

function save() {
  return run(async () => {
    const result = await assistantRequest('providers/' + selected.value, 'PUT', {
      model: (model.value === 'custom' ? customModel.value : model.value).trim(), api_key: key.value.trim() || null,
    })
    saved.value[selected.value] = result.model
    const preferences = await assistantRequest('preferences', 'PUT', {
      provider: selected.value, share_local_status: shareLocalStatus.value,
    })
    active.value = preferences.provider
    resetForm()
    notice.value = 'Provider settings saved.'
  })
}

function remove() {
  return run(async () => {
    await assistantRequest('providers/' + selected.value, 'DELETE')
    delete saved.value[selected.value]
    if (active.value === selected.value) {
      const preferences = await assistantRequest('preferences', 'PUT', { provider: null, share_local_status: false })
      active.value = preferences.provider
      shareLocalStatus.value = preferences.share_local_status
    }
    resetForm()
    notice.value = 'Provider removed.'
  })
}
</script>

<template>
  <section class="glass-card provider-card" :aria-busy="busy">
    <form class="provider-form" @submit.prevent="save">
      <fieldset class="provider-options" :disabled="busy">
        <legend>{{ $t('Choose an AI provider') }}</legend>
        <label v-for="(provider, id) in providers" :key="id" class="provider-option">
          <input v-model="selected" type="radio" name="ai-provider" :value="id" @change="resetForm" />
          <span>{{ provider.label }}</span>
          <small v-if="active === id">{{ $t('Active') }}</small>
          <small v-else-if="saved[id]">{{ $t('Configured') }}</small>
        </label>
      </fieldset>

      <p>{{ $t('Sign in on the provider’s site to create an API key, then paste it here.') }}</p>
      <a :href="current.console" target="_blank" rel="noopener noreferrer">
        {{ $t('Get an API key from {provider}', { provider: current.label }) }}
      </a>
      <label class="provider-field">
        {{ $t('API key') }}
        <input v-model="key" class="ui-input" type="password" autocomplete="new-password" maxlength="2048"
          :required="!configured" :disabled="busy" :placeholder="configured ? $t('API key saved') : ''" />
      </label>
      <details :open="advanced" @toggle="advanced = $event.target.open">
        <summary>{{ $t('Advanced model settings') }}</summary>
        <div class="provider-model">
          <label class="provider-field">
            {{ $t('Model') }}
            <select v-model="model" class="ui-input" :disabled="busy">
              <option v-for="id in current.models" :key="id" :value="id">{{ id }}</option>
              <option value="custom">{{ $t('Custom model ID') }}</option>
            </select>
          </label>
          <label v-if="model === 'custom'" class="provider-field">
            {{ $t('Model ID') }}
            <input v-model="customModel" class="ui-input" maxlength="120" :required="advanced" :disabled="busy" />
          </label>
        </div>
      </details>
      <div class="provider-model">
        <label class="provider-consent">
          <input v-model="shareLocalStatus" type="checkbox" :disabled="busy" aria-describedby="ai-status-consent" />
          {{ $t('Share local app status with the active AI') }}
        </label>
        <p id="ai-status-consent">{{ $t('Without permission, the AI cannot see or diagnose your installed apps. You can still ask general questions.') }}</p>
      </div>
      <div class="provider-actions">
        <button class="ui-btn ui-btn-primary" :disabled="busy || (model === 'custom' && !customModel.trim())">
          {{ $t(active === selected ? 'Save' : 'Connect') }}
        </button>
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
.provider-card, .provider-form, .provider-field, .provider-model { display: grid; gap: 0.75rem; min-width: 0; }
p { margin: 0; }
.provider-options { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0; padding: 0; border: 0; }
legend { margin-bottom: 0.5rem; font-weight: 600; }
.provider-option {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  min-height: 44px;
  padding: 0.25rem 0.65rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-control);
  cursor: pointer;
}
.provider-consent { display: flex; align-items: center; gap: 0.5rem; min-height: 44px; }
.provider-option small { color: var(--text-muted); }
.provider-option input { accent-color: var(--color-primary); }
summary { min-height: 44px; align-content: center; cursor: pointer; }
.provider-model { padding-bottom: 0.75rem; }
.provider-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
</style>
