import { createI18n } from 'vue-i18n'
import { TABLE } from './locales/table.js'

function catalog(index) {
  const messages = {}
  for (const [key, values] of Object.entries(TABLE)) {
    messages[key] = index == null ? key : values[index]
  }
  return messages
}

export const LOCALES = [
  { code: 'en', label: 'English' },
  { code: 'nl', label: 'Nederlands' },
  { code: 'de', label: 'Deutsch' },
  { code: 'fr', label: 'Français' },
]

const STORAGE_KEY = 'amm-locale'
const KNOWN = new Set(LOCALES.map((item) => item.code))

export function isLocale(value) {
  return KNOWN.has(value)
}

/** Primary system language when it is one we ship; otherwise English. */
export function localeFromLanguage(language) {
  const code = String(language || '').split(/[-_]/)[0].toLowerCase()
  return isLocale(code) ? code : 'en'
}

export function browserLocale() {
  const language = typeof navigator === 'undefined' ? '' : navigator.language
  return localeFromLanguage(language)
}

export function readStoredLocale() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return isLocale(stored) ? stored : ''
  } catch (_) {
    return ''
  }
}

function startingLocale() {
  return readStoredLocale() || browserLocale()
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: startingLocale(),
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: catalog(null), nl: catalog(0), de: catalog(1), fr: catalog(2) },
})

export function setLocale(code) {
  if (!isLocale(code)) return
  i18n.global.locale.value = code
  if (typeof document !== 'undefined') document.documentElement.lang = code
  try {
    localStorage.setItem(STORAGE_KEY, code)
  } catch (_) {}
}

export function applyLocaleFromProfile(code) {
  if (isLocale(code)) setLocale(code)
}

export function initLocale() {
  const code = startingLocale()
  i18n.global.locale.value = code
  if (typeof document !== 'undefined') document.documentElement.lang = code
}

export function t(key, params) {
  return i18n.global.t(key, params || {})
}
