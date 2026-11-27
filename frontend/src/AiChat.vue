<script setup>
import { nextTick, onUnmounted, ref, watch } from 'vue'
import AiDownloadActions from './AiDownloadActions.vue'
import { RouterLink } from 'vue-router'
import { assistantRequest, providers } from './aiAssistant.js'

const configured = ref({})
const provider = ref('')
const mcpConnected = ref(false)
const includeHealth = ref(false)
const messages = ref([])
const draft = ref('')
const loading = ref(true)
const sending = ref(false)
const error = ref('')
const transcript = ref(null)
const controller = new AbortController()
const props = defineProps({
  active: Boolean,
  prompt: { type: Object, default: null },
})
const emit = defineEmits(['close'])

watch(() => props.prompt, (prompt) => {
  if (prompt) draft.value = prompt.question
}, { immediate: true })

watch(() => props.active, async (active) => {
  if (!active) return
  loading.value = true
  if (!sending.value) error.value = ''
  try {
    const [models, mcp] = await Promise.all([
      assistantRequest('providers', 'GET', undefined, controller.signal),
      assistantRequest('arr-mcp/settings', 'GET', undefined, controller.signal),
    ])
    const configuredModel = configured.value[provider.value]
    configured.value = models
    if (!models[provider.value] || (configuredModel && models[provider.value] !== configuredModel)) {
      reset()
      provider.value = models[provider.value] ? provider.value : Object.keys(models)[0] || ''
    }
    mcpConnected.value = !!mcp.endpoint
  } catch (failure) {
    if (!controller.signal.aborted) error.value = failure.message
  } finally {
    loading.value = false
  }
}, { immediate: true })
onUnmounted(() => controller.abort())

function reset() {
  messages.value = []
  error.value = ''
  includeHealth.value = false
}

async function send() {
  const content = draft.value.trim()
  if (!content || !provider.value || sending.value) return
  const pending = [...messages.value.slice(-8), { role: 'user', content }]
  while (pending.length > 1 && pending.reduce((total, message) => total + message.content.length, 0) > 24000) {
    pending.splice(0, 2)
  }
  sending.value = true
  error.value = ''
  try {
    const { reply } = await assistantRequest('chat', 'POST', {
      provider: provider.value, messages: pending, include_health: includeHealth.value,
    }, controller.signal)
    messages.value = [...messages.value, { role: 'user', content }, { role: 'assistant', content: reply }]
    if (draft.value.trim() === content) draft.value = ''
    await nextTick()
    if (transcript.value) transcript.value.scrollTop = transcript.value.scrollHeight
  } catch (failure) {
    if (!controller.signal.aborted) error.value = failure.message
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <p v-if="loading" role="status">{{ $t('Loading AI providers…') }}</p>
  <p v-if="error" role="alert">{{ $t(error) }}</p>
  <p v-if="!loading && !provider && !error">
    <RouterLink to="/settings/ai-assistant" @click="emit('close')">
      {{ $t('Configure an AI provider') }}
    </RouterLink>
  </p>
  <section v-if="provider && !loading" class="ai-chat">
    <div class="chat-controls">
      <label>
        {{ $t('AI provider') }}
        <select v-model="provider" class="ui-input" :disabled="sending" @change="reset">
          <option v-for="(model, id) in configured" :key="id" :value="id">{{ providers[id].name }} · {{ model }}</option>
        </select>
      </label>
      <button type="button" class="ui-btn" :disabled="sending || !messages.length" @click="reset">{{ $t('New chat') }}</button>
    </div>
    <div v-if="messages.length" ref="transcript" role="log" :aria-label="$t('AI chat')" class="chat-transcript">
      <div v-for="(message, i) in messages" :key="i" class="chat-message">
        <strong>{{ message.role === 'user' ? $t('You') : providers[provider].name }}</strong>
        <p>{{ message.content }}</p>
      </div>
    </div>
    <p v-else>{{ $t('Ask about your media server, configuration or an error.') }}</p>
    <p>{{ $t('Messages and any included stack status are sent to the selected AI provider.') }}</p>
    <form class="chat-form" :aria-busy="sending" @submit.prevent="send">
      <label v-if="mcpConnected" class="chat-health">
        <input v-model="includeHealth" type="checkbox" :disabled="sending" />
        {{ $t('Include live app status from arr-mcp') }}
      </label>
      <label>
        {{ $t('Message') }}
        <textarea v-model="draft" class="ui-input" rows="3" maxlength="4000" required :disabled="sending" />
      </label>
      <button class="ui-btn ui-btn-primary" :disabled="sending || !draft.trim()">
        {{ $t(sending ? 'Sending…' : 'Send') }}
      </button>
    </form>
  </section>
  <AiDownloadActions v-if="mcpConnected && !loading" />
</template>

<style scoped>
.ai-chat, .chat-form, label { display: grid; min-width: 0; gap: 0.6rem; }
.ai-chat { margin-top: 1rem; }
.ai-chat p { margin: 0; }
.chat-controls { display: flex; flex-wrap: wrap; align-items: end; gap: 0.6rem; }
.chat-controls label { flex: 1 1 14rem; }
.chat-transcript { max-height: 32dvh; overflow: auto; display: grid; gap: 0.6rem; }
.chat-message { padding: 0.6rem 0.8rem; border-radius: var(--radius-tile); background: rgb(127 127 127 / 0.12); }
.chat-message p { white-space: pre-wrap; overflow-wrap: anywhere; }
.chat-health { display: flex; align-items: center; }
.chat-form button { justify-self: end; }
textarea { resize: vertical; }
</style>
