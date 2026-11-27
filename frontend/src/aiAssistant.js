import { apiJson } from './api.js'

export const providers = {
  openai: { name: 'OpenAI (GPT)', console: 'https://platform.openai.com/api-keys' },
  claude: { name: 'Anthropic Claude', console: 'https://platform.claude.com/settings/keys' },
  gemini: { name: 'Google Gemini', console: 'https://aistudio.google.com/api-keys' },
}

export async function assistantRequest(path, method = 'GET', body, signal) {
  const { res, data } = await apiJson('/api/ai-assistant/' + path, {
    method, signal, body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'AI request failed.')
  return data
}
