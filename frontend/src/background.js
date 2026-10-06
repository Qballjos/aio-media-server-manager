/** Personal wallpaper — localStorage cache + profile sync. */

import { setThemePreference } from './theme.js'
import { applyHomepageWidgetDebugFromProfile, readHomepageWidgetDebug } from './homepageDebug.js'

const PREF_KEY = 'amm-wallpaper'
const IMAGE_KEY = 'amm-wallpaper-image'
const IMAGE_URL_KEY = 'amm-wallpaper-image-url'
const PRESETS = new Set(['default', 'jellyfin', 'plex', 'personal'])

export const WALLPAPER_OPTIONS = [
  ['default', 'App default', 'Warm orange glow on deep slate'],
  ['jellyfin', 'Jellyfin', 'Purple and cyan media glow'],
  ['plex', 'Plex', 'Amber gold on charcoal'],
  ['personal', 'Personal', 'Your own uploaded image'],
]

function normalizePreference(value) {
  return PRESETS.has(value) ? value : 'default'
}

export function getWallpaperPreference() {
  try {
    return normalizePreference(localStorage.getItem(PREF_KEY))
  } catch (_) {
    return 'default'
  }
}

export function getWallpaperImage() {
  try {
    return localStorage.getItem(IMAGE_URL_KEY) || localStorage.getItem(IMAGE_KEY) || ''
  } catch (_) {
    return ''
  }
}

export function cacheWallpaperPreference(preference) {
  const pref = normalizePreference(preference)
  try {
    localStorage.setItem(PREF_KEY, pref)
  } catch (_) {}
  return pref
}

export function cacheWallpaperImageUrl(url) {
  try {
    if (url) localStorage.setItem(IMAGE_URL_KEY, url)
    else localStorage.removeItem(IMAGE_URL_KEY)
  } catch (_) {}
  return url || ''
}

export function applyWallpaper(preference = getWallpaperPreference(), imageSrc = getWallpaperImage()) {
  if (typeof document === 'undefined') return preference
  const pref = normalizePreference(preference)
  const root = document.documentElement
  root.setAttribute('data-wallpaper', pref)
  if (pref === 'personal' && imageSrc) {
    const cssUrl = imageSrc.startsWith('url(') ? imageSrc : `url("${imageSrc}")`
    root.style.setProperty('--wallpaper-image', cssUrl)
    root.classList.add('has-wallpaper-image')
  } else {
    root.style.removeProperty('--wallpaper-image')
    root.classList.remove('has-wallpaper-image')
  }
  return pref
}

export function setWallpaperPreference(preference) {
  const pref = cacheWallpaperPreference(preference)
  return applyWallpaper(pref, getWallpaperImage())
}

export function clearWallpaperImage() {
  try {
    localStorage.removeItem(IMAGE_KEY)
    localStorage.removeItem(IMAGE_URL_KEY)
  } catch (_) {}
  const pref = getWallpaperPreference() === 'personal' ? 'default' : getWallpaperPreference()
  cacheWallpaperPreference(pref)
  return applyWallpaper(pref, '')
}

/** Resize and JPEG-compress an image file for upload (~1.2MB budget). */
export function encodeWallpaperFile(file) {
  return new Promise((resolve, reject) => {
    if (!file || !String(file.type || '').startsWith('image/')) {
      reject(new Error('Choose an image file (JPEG, PNG, or WebP).'))
      return
    }
    if (file.size > 12 * 1024 * 1024) {
      reject(new Error('Image is too large (max 12 MB before compression).'))
      return
    }
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      const maxW = 1920
      const maxH = 1200
      let { width, height } = img
      const scale = Math.min(1, maxW / width, maxH / height)
      width = Math.max(1, Math.round(width * scale))
      height = Math.max(1, Math.round(height * scale))
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reject(new Error('Could not process image.'))
        return
      }
      ctx.drawImage(img, 0, 0, width, height)
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error('Could not process image.'))
            return
          }
          resolve(blob)
        },
        'image/jpeg',
        0.82,
      )
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not read that image.'))
    }
    img.src = url
  })
}

export async function setWallpaperImageFromFile(file) {
  const blob = await encodeWallpaperFile(file)
  cacheWallpaperPreference('personal')
  // Temporary object URL until the profile upload returns a stable URL.
  const tempUrl = URL.createObjectURL(blob)
  applyWallpaper('personal', tempUrl)
  return { blob, tempUrl }
}

export function initWallpaper() {
  return applyWallpaper(getWallpaperPreference(), getWallpaperImage())
}

/** Apply visuals returned from /api/auth/status, /me, login, or visuals PATCH. */
export function applyVisualsFromProfile(payload = {}) {
  if (!payload || typeof payload !== 'object') return
  if (payload.theme) {
    setThemePreference(payload.theme)
  }
  if (payload.wallpaper) {
    cacheWallpaperPreference(payload.wallpaper)
  }
  if (payload.wallpaper_url) {
    cacheWallpaperImageUrl(payload.wallpaper_url)
    try {
      localStorage.removeItem(IMAGE_KEY)
    } catch (_) {}
  } else if (payload.has_wallpaper_image === false) {
    cacheWallpaperImageUrl('')
    try {
      localStorage.removeItem(IMAGE_KEY)
    } catch (_) {}
  }
  applyWallpaper(getWallpaperPreference(), getWallpaperImage())
  applyHomepageWidgetDebugFromProfile(payload)
}

/** One-time migrate browser-only prefs into the profile when the profile is still default. */
export function shouldMigrateLocalVisuals(payload = {}) {
  const theme = payload.theme || 'dark'
  const wallpaper = payload.wallpaper || 'default'
  const hasImage = !!payload.has_wallpaper_image
  const profileDebug = !!payload.homepage_widget_debug
  const localDebug = readHomepageWidgetDebug()
  if (localDebug && !profileDebug) return true
  if (theme !== 'dark' || wallpaper !== 'default' || hasImage) return false
  const localTheme = getThemePreference()
  const localWallpaper = getWallpaperPreference()
  const localImage = getWallpaperImage()
  return localTheme !== 'dark' || localWallpaper !== 'default' || !!localImage
}
