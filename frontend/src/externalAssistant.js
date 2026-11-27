import { ref } from 'vue'
import { apiJson } from './api.js'

export const externalChatUrl = ref('')
let revision = 0

export function setExternalChatUrl(value) {
  revision += 1
  externalChatUrl.value = ''
  if (!value) return
  try {
    const url = new URL(value)
    if (['http:', 'https:'].includes(url.protocol) && url.origin !== window.location.origin) {
      externalChatUrl.value = url.href
    }
  } catch {
    // Settings only accept absolute HTTP(S) addresses.
  }
}

export async function loadExternalChatUrl() {
  const operation = ++revision
  try {
    const { res, data } = await apiJson('/api/ai-assistant/arr-mcp/settings')
    if (operation === revision && res.ok) setExternalChatUrl(data.chat_url)
  } catch {
    // The optional launcher stays hidden if the connection could not be loaded.
  }
}
