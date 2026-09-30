/** Shared fetch helper: CSRF, bearer token, JSON vs binary, FastAPI error bodies. */

const CSRF_COOKIE = 'amm_csrf'
const TOKEN_KEY = 'amm_token'
const CSRF_KEY = 'amm_csrf'

let onUnauthorized = null

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

export function getAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch (_) {
    return ''
  }
}

export function setAuthToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch (_) {
    /* ignore quota / private mode */
  }
}

function readCookie(name) {
  if (typeof document === 'undefined') return ''
  const prefix = `${name}=`
  const parts = document.cookie.split(';')
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }
  return ''
}

export function getCsrfToken() {
  try {
    return sessionStorage.getItem(CSRF_KEY) || readCookie(CSRF_COOKIE) || ''
  } catch (_) {
    return readCookie(CSRF_COOKIE)
  }
}

export function setCsrfToken(token) {
  try {
    if (token) sessionStorage.setItem(CSRF_KEY, token)
    else sessionStorage.removeItem(CSRF_KEY)
  } catch (_) {
    /* ignore */
  }
}

export function applySession(data) {
  if (data?.access_token) setAuthToken(data.access_token)
  if (data?.csrf_token) setCsrfToken(data.csrf_token)
  else if (!getCsrfToken()) {
    const fromCookie = readCookie(CSRF_COOKIE)
    if (fromCookie) setCsrfToken(fromCookie)
  }
}

export function clearSession() {
  setAuthToken('')
  setCsrfToken('')
}

function headerHas(headers, name) {
  const want = name.toLowerCase()
  return Object.keys(headers).some((key) => key.toLowerCase() === want)
}

function isBinaryBody(body) {
  if (body == null) return false
  if (typeof Blob !== 'undefined' && body instanceof Blob) return true
  if (typeof FormData !== 'undefined' && body instanceof FormData) return true
  return false
}

export async function apiRequest(endpoint, options = {}) {
  const { json, headers: extra = {}, ...rest } = options
  const headers = { ...extra }

  const binary = json === false || isBinaryBody(rest.body)
  if (!binary && rest.body != null && !headerHas(headers, 'Content-Type')) {
    headers['Content-Type'] = 'application/json'
  }

  const csrf = getCsrfToken()
  if (csrf) headers['X-CSRF-Token'] = csrf
  const token = getAuthToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(endpoint, {
    ...rest,
    headers,
    credentials: 'include',
  })

  if (response.status === 401 && onUnauthorized) onUnauthorized()
  return response
}

export async function readJson(response) {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text)
  } catch (_) {
    const snippet = text
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 180)
    return { detail: snippet || `HTTP ${response.status} (not JSON)` }
  }
}

export function apiError(data, fallback = 'Request failed') {
  const detail = data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  if (typeof data?.error === 'string' && data.error) return data.error
  return fallback
}

export async function apiJson(endpoint, options) {
  const res = await apiRequest(endpoint, options)
  const data = await readJson(res)
  return { res, data }
}
