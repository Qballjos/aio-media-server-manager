/** Sync visual preferences with the admin profile API. */

import { apiError, apiRequest, readJson } from './api.js'
import {
  applyVisualsFromProfile,
  clearWallpaperImage,
  encodeWallpaperFile,
  getWallpaperImage,
  getWallpaperPreference,
  shouldMigrateLocalVisuals,
  setWallpaperPreference,
} from './background.js'
import { getThemePreference, setThemePreference } from './theme.js'
import {
  cacheHomepageWidgetDebug,
  readHomepageWidgetDebug,
} from './homepageDebug.js'

export { applyVisualsFromProfile, shouldMigrateLocalVisuals }

async function patchVisuals(body) {
  const res = await apiRequest('/api/auth/visuals', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await readJson(res)
  if (!res.ok) throw new Error(apiError(data, 'Could not save visual preferences.'))
  applyVisualsFromProfile(data)
  return data
}

export async function saveThemeToProfile(theme) {
  setThemePreference(theme)
  return patchVisuals({ theme })
}

export async function saveWallpaperToProfile(wallpaper) {
  setWallpaperPreference(wallpaper)
  return patchVisuals({ wallpaper })
}

export async function saveHomepageWidgetDebugToProfile(enabled) {
  cacheHomepageWidgetDebug(enabled)
  return patchVisuals({ homepage_widget_debug: !!enabled })
}

export async function uploadWallpaperToProfile(file) {
  const blob = await encodeWallpaperFile(file)
  const res = await apiRequest('/api/auth/wallpaper', {
    method: 'PUT',
    headers: { 'Content-Type': blob.type || 'image/jpeg' },
    body: blob,
  })
  const data = await readJson(res)
  if (!res.ok) throw new Error(apiError(data, 'Could not save background image.'))
  applyVisualsFromProfile(data)
  return data
}

export async function removeWallpaperFromProfile() {
  const res = await apiRequest('/api/auth/wallpaper', { method: 'DELETE' })
  const data = await readJson(res)
  if (!res.ok) throw new Error(apiError(data, 'Could not remove background image.'))
  clearWallpaperImage()
  applyVisualsFromProfile(data)
  return data
}

export async function migrateLocalVisualsIfNeeded(payload) {
  if (!payload || typeof payload !== 'object') return payload
  if (!shouldMigrateLocalVisuals(payload)) {
    applyVisualsFromProfile(payload)
    return payload
  }
  const theme = getThemePreference()
  const wallpaper = getWallpaperPreference()
  const localImage = getWallpaperImage()
  const localDebug = readHomepageWidgetDebug()
  const profileDebug = !!payload.homepage_widget_debug
  try {
    const nextWallpaper =
      wallpaper === 'personal' && (!localImage || !localImage.startsWith('data:image/'))
        ? 'default'
        : wallpaper
    const patchBody = { theme, wallpaper: nextWallpaper }
    if (localDebug && !profileDebug) {
      patchBody.homepage_widget_debug = true
    }
    // Only push theme/wallpaper when profile is still at defaults; otherwise just debug.
    const themeDefault = (payload.theme || 'dark') === 'dark'
    const wallpaperDefault = (payload.wallpaper || 'default') === 'default' && !payload.has_wallpaper_image
    if (!(themeDefault && wallpaperDefault)) {
      delete patchBody.theme
      delete patchBody.wallpaper
    }
    if (Object.keys(patchBody).length) {
      await patchVisuals(patchBody)
    }
    if (
      themeDefault &&
      wallpaperDefault &&
      wallpaper === 'personal' &&
      localImage &&
      localImage.startsWith('data:image/')
    ) {
      const resBlob = await fetch(localImage)
      const blob = await resBlob.blob()
      const put = await apiRequest('/api/auth/wallpaper', {
        method: 'PUT',
        headers: { 'Content-Type': blob.type || 'image/jpeg' },
        body: blob,
      })
      const data = await readJson(put)
      if (put.ok) {
        applyVisualsFromProfile(data)
        return data
      }
    }
  } catch (_) {
    applyVisualsFromProfile(payload)
  }
  return payload
}
