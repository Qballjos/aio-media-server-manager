<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { assistantRequest, providers } from './aiAssistant.js'

const model = ref('')
const shareLocalStatus = ref(false)
const provider = ref('')
const messages = ref([])
const draft = ref('')
const loading = ref(true)
const pendingText = ref('')
const sending = computed(() => !!pendingText.value)
const error = ref('')
const transcript = ref(null)
const controller = new AbortController()
const props = defineProps({
  active: Boolean,
})
const emit = defineEmits(['close'])

watch(() => props.active, async (active) => {
  if (!active) return
  loading.value = true
  if (!sending.value) error.value = ''
  try {
    const [models, preferences] = await Promise.all([
      assistantRequest('providers', 'GET', undefined, controller.signal),
      assistantRequest('preferences', 'GET', undefined, controller.signal),
    ])
    const nextProvider = preferences.provider || ''
    const nextModel = models[nextProvider] || ''
    if (provider.value !== nextProvider || model.value !== nextModel || shareLocalStatus.value !== preferences.share_local_status) {
      messages.value = []
    }
    shareLocalStatus.value = preferences.share_local_status
    provider.value = nextProvider
    model.value = nextModel
  } catch (failure) {
    if (!controller.signal.aborted) error.value = failure.message
  } finally {
    loading.value = false
  }
}, { immediate: true })
onUnmounted(() => controller.abort())

async function send() {
  const content = draft.value.trim()
  if (!content || !provider.value || sending.value) return
  const pending = [...messages.value.slice(-8), { role: 'user', content }]
  while (pending.length > 1 && pending.reduce((total, message) => total + message.content.length, 0) > 24000) {
    pending.splice(0, 2)
  }
  pendingText.value = content
  error.value = ''
  void scrollToLatest()
  try {
    const { reply } = await assistantRequest('chat', 'POST', {
      messages: pending,
    }, controller.signal)
    messages.value = [...messages.value, { role: 'user', content }, { role: 'assistant', content: reply }]
    if (draft.value.trim() === content) draft.value = ''
    void scrollToLatest()
  } catch (failure) {
    if (!controller.signal.aborted) error.value = failure.message
  } finally {
    pendingText.value = ''
  }
}
async function scrollToLatest() {
  await nextTick()
  if (transcript.value) transcript.value.scrollTop = transcript.value.scrollHeight
}

function sendOnEnter(event) {
  if (event.shiftKey || event.isComposing) return
  event.preventDefault()
  void send()
}
</script>

<template>
  <section class="ai-chat" :aria-label="$t('AI chat')">
    <div ref="transcript" class="chat-transcript" role="log" :aria-label="$t('Messages')">
      <p v-if="loading" role="status" class="chat-empty">{{ $t('Loading AI providers…') }}</p>
      <p v-else-if="!provider && !error" class="chat-empty">
        <RouterLink to="/settings/ai-assistant" @click="emit('close')">{{ $t('Configure an AI provider') }}</RouterLink>
      </p>
      <p v-else-if="provider && !messages.length && !pendingText" class="chat-empty">
        {{ $t('Ask about your media server, configuration or an error.') }}
      </p>
      <p v-for="(message, i) in messages" :key="i" class="chat-message" :data-role="message.role">
        <span class="chat-sr">{{ message.role === 'user' ? $t('You') : providers[provider]?.label }}</span>
        {{ message.content }}
      </p>
      <template v-if="pendingText">
        <p class="chat-message" data-role="user">{{ pendingText }}</p>
        <p class="chat-message chat-pending" role="status">{{ $t('Waiting for a reply…') }}</p>
      </template>
      <p v-if="error" class="chat-error" role="alert">{{ $t(error) }}</p>
    </div>

    <footer v-if="provider && !loading" class="chat-footer">
      <form v-if="provider" class="chat-form" :aria-busy="sending" @submit.prevent="send">
        <textarea v-model="draft" class="ui-input" rows="1" maxlength="4000" required :disabled="sending"
          :aria-label="$t('Message')" :placeholder="$t('Message')" @keydown.enter="sendOnEnter" />
        <button type="submit" class="ui-btn ui-btn-primary chat-send" :aria-label="$t('Send')" :title="$t('Send')"
          :disabled="sending || !draft.trim()">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </form>
    </footer>
  </section>
</template>

<style scoped>
.ai-chat { display: grid; grid-template-rows: minmax(0, 1fr) auto; height: 100%; min-width: 0; gap: 0.5rem; }
.ai-chat p { margin: 0; }
.chat-form { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
.chat-form textarea { flex: 1; min-width: 0; }
.chat-transcript { display: flex; flex-direction: column; gap: 0.5rem; overflow: auto; padding: 0.25rem; }
.chat-empty { margin: auto !important; text-align: center; color: var(--text-muted); }
.chat-message {
  align-self: flex-start;
  max-width: 88%;
  padding: 0.55rem 0.85rem;
  border-radius: 1rem 1rem 1rem 0.3rem;
  background: var(--border-subtle);
  color: var(--text-main);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.chat-message[data-role='user'] {
  align-self: flex-end;
  border-radius: 1rem 1rem 0.3rem 1rem;
  background: color-mix(in srgb, var(--color-primary) 20%, transparent);
}
.chat-pending { color: var(--text-muted); font-size: var(--text-small, 0.85rem); }
.chat-error { color: var(--color-danger); overflow-wrap: anywhere; }
.chat-footer { display: grid; gap: 0.4rem; min-width: 0; }
.chat-form textarea { resize: none; min-height: 44px; }
.chat-send { flex: 0 0 44px; min-height: 44px; padding: 0; }
.chat-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
