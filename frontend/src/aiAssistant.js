import { apiRequest, readJson } from './api.js'

export const providers = {
  openai: {
    name: 'OpenAI (GPT)', label: 'ChatGPT', console: 'https://platform.openai.com/api-keys',
    models: ['gpt-5.4-mini', 'gpt-5.4-nano'],
  },
  claude: {
    name: 'Anthropic Claude', label: 'Claude', console: 'https://platform.claude.com/settings/keys',
    models: ['claude-haiku-5-5', 'claude-sonnet-5-5'],
  },
  gemini: {
    name: 'Google Gemini', label: 'Gemini', console: 'https://aistudio.google.com/api-keys',
    models: ['gemini-3.5-flash', 'gemini-3.1-flash-lite'],
  },
}

export async function assistantRequest(path, method = 'GET', body, signal) {
  const res = await apiRequest('/api/ai-assistant/' + path, {
    method, signal, body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok && !res.headers.get('content-type')?.includes('application/json')) {
    throw new Error('The AI connection is temporarily unavailable. Try again in a moment.')
  }
  const data = await readJson(res)
  if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : 'AI request failed.')
  return data
}
