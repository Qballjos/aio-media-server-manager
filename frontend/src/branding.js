/** Shared appliance branding (title, accent, custom images). */

import { ref } from 'vue'
import { apiRequest, readJson } from './api.js'

const DEFAULT_TITLE = 'AIO Media Server Manager'
const DEFAULT_LOGO = '/logo-aio-media-manager.png'
export const DEFAULT_ACCENT = '#f97316'
const ACCENT_CACHE_KEY = 'amm-accent'

export const brandTitle = ref(DEFAULT_TITLE)
export const brandHeaderUrl = ref(DEFAULT_LOGO)
export const brandLogoUrl = ref(DEFAULT_LOGO)
export const brandFaviconUrl = ref(DEFAULT_LOGO)
export const brandAccent = ref(DEFAULT_ACCENT)
export const brandSlots = ref({})

export const ACCENT_PRESETS = [
  ['#f97316', 'Orange'],
  ['#f59e0b', 'Amber'],
  ['#ef4444', 'Red'],
  ['#ec4899', 'Pink'],
  ['#8b5cf6', 'Violet'],
  ['#3b82f6', 'Blue'],
  ['#06b6d4', 'Cyan'],
  ['#10b981', 'Emerald'],
]

function ensureLink(rel, attrs = {}) {
  if (typeof document === 'undefined') return null
  let el = document.querySelector(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  Object.entries(attrs).forEach(([key, value]) => {
    if (value == null) el.removeAttribute(key)
    else el.setAttribute(key, value)
  })
  return el
}

function normalizeHex(value) {
  let text = String(value || '').trim()
  if (!text) return DEFAULT_ACCENT
  if (!text.startsWith('#')) text = `#${text}`
  if (!/^#[0-9a-fA-F]{6}$/.test(text)) return DEFAULT_ACCENT
  return text.toLowerCase()
}

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16)
  return {
    r: (n >> 16) & 255,
    g: (n >> 8) & 255,
    b: n & 255,
  }
}

function toHex(r, g, b) {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')}`
}

function mixChannel(from, to, amount) {
  return from + (to - from) * amount
}

export function deriveAccent(hex) {
  const primary = normalizeHex(hex)
  const { r, g, b } = hexToRgb(primary)
  const hover = toHex(mixChannel(r, 0, 0.18), mixChannel(g, 0, 0.18), mixChannel(b, 0, 0.18))
  const soft = toHex(mixChannel(r, 255, 0.28), mixChannel(g, 255, 0.28), mixChannel(b, 255, 0.28))
  return {
    primary,
    hover,
    soft,
    rgb: `${r}, ${g}, ${b}`,
    gradient: `linear-gradient(135deg, ${hover} 0%, ${soft} 100%)`,
  }
}

export function applyAccentColor(hex) {
  const accent = deriveAccent(hex)
  brandAccent.value = accent.primary
  try {
    localStorage.setItem(ACCENT_CACHE_KEY, accent.primary)
  } catch (_) {}

  if (typeof document === 'undefined') return accent.primary
  const root = document.documentElement
  root.style.setProperty('--color-primary', accent.primary)
  root.style.setProperty('--color-primary-hover', accent.hover)
  root.style.setProperty('--color-primary-soft', accent.soft)
  root.style.setProperty('--color-primary-rgb', accent.rgb)
  root.style.setProperty('--gradient-primary', accent.gradient)
  root.style.setProperty('--border-active', accent.primary)
  root.style.setProperty('--border-hover', `rgba(${accent.rgb}, 0.35)`)
  root.style.setProperty('--shadow-glow', `0 0 20px rgba(${accent.rgb}, 0.28)`)
  root.style.setProperty('--glow-orb', `rgba(${accent.rgb}, 0.18)`)
  root.style.setProperty(
    '--brand-title-gradient',
    `linear-gradient(90deg, var(--text-heading), ${accent.soft})`,
  )
  return accent.primary
}

export function initAccentFromCache() {
  try {
    const cached = localStorage.getItem(ACCENT_CACHE_KEY)
    if (cached) applyAccentColor(cached)
  } catch (_) {}
}

export function applyBranding(data) {
  const title = (data?.title || DEFAULT_TITLE).trim() || DEFAULT_TITLE
  // Each Settings slot has its own built-in placeholder; do not cascade a custom
  // header into logo/favicon (or vice versa) when that slot is still default.
  const header = data?.header_url || data?.slots?.header?.url || DEFAULT_LOGO
  const logo = data?.logo_url || data?.slots?.logo?.url || DEFAULT_LOGO
  const favicon = data?.favicon_url || data?.slots?.favicon?.url || DEFAULT_LOGO
  const accent = normalizeHex(data?.accent_color || DEFAULT_ACCENT)

  brandTitle.value = title
  brandHeaderUrl.value = header
  brandLogoUrl.value = logo
  brandFaviconUrl.value = favicon
  brandSlots.value = data?.slots || {}
  applyAccentColor(accent)

  if (typeof document === 'undefined') return

  document.title = title
  const appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]')
  if (appleTitle) appleTitle.setAttribute('content', title.slice(0, 12))

  // Tab icon + Apple touch icon follow the favicon slot (placeholder or custom upload).
  ensureLink('icon', { type: favicon.endsWith('.ico') ? 'image/x-icon' : 'image/png', href: favicon })
  ensureLink('apple-touch-icon', { href: favicon })
}

export async function loadBranding() {
  try {
    const res = await apiRequest('/api/branding')
    if (!res.ok) return applyBranding(null)
    applyBranding(await readJson(res))
  } catch (_) {
    applyBranding(null)
  }
}
