/** Personal wallpaper / background presets (browser-local, like color theme). */

const PREF_KEY = 'amm-wallpaper'
const IMAGE_KEY = 'amm-wallpaper-image'
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
    return localStorage.getItem(IMAGE_KEY) || ''
  } catch (_) {
    return ''
  }
}

export function applyWallpaper(preference = getWallpaperPreference(), imageDataUrl = getWallpaperImage()) {
  if (typeof document === 'undefined') return preference
  const pref = normalizePreference(preference)
  const root = document.documentElement
  root.setAttribute('data-wallpaper', pref)
  if (pref === 'personal' && imageDataUrl) {
    root.style.setProperty('--wallpaper-image', `url("${imageDataUrl}")`)
    root.classList.add('has-wallpaper-image')
  } else {
    root.style.removeProperty('--wallpaper-image')
    root.classList.remove('has-wallpaper-image')
  }
  return pref
}

export function setWallpaperPreference(preference) {
  const pref = normalizePreference(preference)
  try {
    localStorage.setItem(PREF_KEY, pref)
  } catch (_) {}
  return applyWallpaper(pref, getWallpaperImage())
}

export function clearWallpaperImage() {
  try {
    localStorage.removeItem(IMAGE_KEY)
  } catch (_) {}
  return applyWallpaper(getWallpaperPreference(), '')
}

/** Resize and JPEG-compress an image file for localStorage (~1.2MB budget). */
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
      let quality = 0.82
      let dataUrl = canvas.toDataURL('image/jpeg', quality)
      while (dataUrl.length > 1_400_000 && quality > 0.45) {
        quality -= 0.08
        dataUrl = canvas.toDataURL('image/jpeg', quality)
      }
      if (dataUrl.length > 1_800_000) {
        reject(new Error('Could not compress image enough for this browser. Try a smaller photo.'))
        return
      }
      resolve(dataUrl)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not read that image.'))
    }
    img.src = url
  })
}

export async function setWallpaperImageFromFile(file) {
  const dataUrl = await encodeWallpaperFile(file)
  try {
    localStorage.setItem(IMAGE_KEY, dataUrl)
  } catch (_) {
    throw new Error('Browser storage is full. Clear site data or use a smaller image.')
  }
  try {
    localStorage.setItem(PREF_KEY, 'personal')
  } catch (_) {}
  applyWallpaper('personal', dataUrl)
  return dataUrl
}

export function initWallpaper() {
  return applyWallpaper(getWallpaperPreference(), getWallpaperImage())
}
