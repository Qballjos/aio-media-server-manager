/** Wallpaper presets and the personal image — localStorage cache + profile sync. */

import { ref } from 'vue'
import { applyLocaleFromProfile } from './i18n/index.js'
import { getThemePreference, setThemePreference } from './theme.js'
import { applyHomepageWidgetDebugFromProfile, readHomepageWidgetDebug } from './homepageDebug.js'
import { applyHomeLayoutFromProfile } from './homeLayout.js'
import { applyGlassFromProfile } from './glass.js'

const PREF_KEY = 'amm-wallpaper'
const IMAGE_KEY = 'amm-wallpaper-image'
const IMAGE_URL_KEY = 'amm-wallpaper-image-url'
const PRESETS = new Set([
  'default', 'aurora', 'candy', 'mono', 'jellyfin', 'plex',
  'forest', 'northern', 'city', 'ocean', 'alpine', 'dunes', 'lavender', 'starry', 'sunset', 'nebula',
  'tide', 'retrowave', 'personal',
])

export const WALLPAPER_OPTIONS = [
  ['aurora', 'Aurora', 'Soft drifting colour fields'],
  ['forest', 'Forest', 'Sunbeams through a green wood'],
  ['ocean', 'Ocean', 'Turquoise sea below a cliff'],
  ['alpine', 'Alpine', 'A still mountain lake'],
  ['dunes', 'Dunes', 'Red sand at sunrise'],
  ['lavender', 'Lavender', 'Rows of lavender in Provence'],
  ['sunset', 'Sunset beach', 'Pink dusk over granite and sea'],
  ['city', 'City', 'Tokyo at night'],
  ['northern', 'Northern lights', 'Aurora over a snowy road'],
  ['starry', 'Starry night', 'The Milky Way over a lake'],
  ['nebula', 'Nebula', 'The Carina Nebula, by Hubble'],
  ['tide', 'Tide', 'Line-art waves'],
  ['retrowave', 'Retrowave', 'Sun, grid and neon'],
  ['candy', 'Candy', 'Pastel bubbles'],
  ['mono', 'Mono', 'One quiet spotlight, no colour'],
  ['jellyfin', 'Jellyfin', 'A violet-to-cyan beam'],
  ['plex', 'Plex', 'An amber glow on charcoal'],
  ['personal', 'Personal', 'Your own image'],
]

// A blob is a soft radial colour field: position, size and colour; three layers give depth. The
// layers are 14% larger than the window on every side, so y 11% is the top edge and 89% the bottom.
// Each preset has its own shape — waves, a horizon, light shafts, stars — not just other colours.
const B = (x, y, w, h, color) => ({ x, y, w, h, color })
const PALETTES = {
  aurora: {
    day: { base: '#E6EEFF', far: [B('20%', '25%', '60%', '70%', '#7FC8FF'), B('82%', '12%', '56%', '62%', '#CDBBFF')], mid: [B('34%', '92%', '52%', '58%', '#9BF1D6'), B('84%', '66%', '44%', '52%', '#FFC6AE')], near: [B('62%', '36%', '26%', '32%', '#FFEFA3')] },
    night: { base: '#090D1F', far: [B('20%', '25%', '60%', '70%', '#2F52FF'), B('82%', '12%', '56%', '62%', '#9A47FF')], mid: [B('34%', '92%', '52%', '58%', '#16CFC2'), B('84%', '66%', '44%', '52%', '#FF5B8C')], near: [B('62%', '36%', '26%', '32%', 'rgba(255,176,74,0.55)')] },
  },
  candy: {
    day: { base: '#FFF2F7', far: [B('20%', '30%', '52%', '52%', '#FFD3E6'), B('80%', '22%', '46%', '46%', '#D4F5E9')], mid: [B('62%', '72%', '32%', '32%', '#FFF3B5'), B('28%', '80%', '28%', '28%', '#D8E7FF'), B('90%', '62%', '22%', '22%', '#FFD9C2')], near: [B('45%', '36%', '14%', '14%', '#FFFFFF'), B('84%', '84%', '12%', '12%', '#FFFFFF'), B('10%', '60%', '10%', '10%', '#FFFFFF')] },
    night: { base: '#190E1F', far: [B('20%', '30%', '52%', '52%', '#7A2F5E'), B('80%', '22%', '46%', '46%', '#1F6B5E')], mid: [B('62%', '72%', '32%', '32%', '#8A6A1F'), B('28%', '80%', '28%', '28%', '#2C3F7A'), B('90%', '62%', '22%', '22%', '#8A4A2F')], near: [B('45%', '36%', '14%', '14%', 'rgba(255,255,255,0.22)'), B('84%', '84%', '12%', '12%', 'rgba(255,255,255,0.18)'), B('10%', '60%', '10%', '10%', 'rgba(255,255,255,0.16)')] },
  },
  mono: {
    day: { base: '#ECEEF3', far: [B('24%', '16%', '96%', '96%', '#FFFFFF')], mid: [B('86%', '90%', '74%', '74%', '#D3D8E2')], near: [B('60%', '48%', '26%', '26%', 'rgba(255,255,255,0.7)')] },
    night: { base: '#0C0F15', far: [B('24%', '16%', '96%', '96%', '#2A3140')], mid: [B('86%', '90%', '74%', '74%', '#151A23')], near: [B('60%', '48%', '26%', '26%', 'rgba(90,100,120,0.45)')] },
  },
  jellyfin: {
    day: { base: 'linear-gradient(115deg, #ECE6FF 0%, #ECE6FF 36%, #D4C4FF 50%, #CBF1FF 64%, #E8F7FF 100%)', far: [B('14%', '18%', '54%', '62%', '#B79CFF')], mid: [B('86%', '82%', '54%', '62%', '#8FE8FF')], near: [B('50%', '50%', '18%', '18%', 'rgba(255,255,255,0.8)')] },
    night: { base: 'linear-gradient(115deg, #0B0618 0%, #0B0618 36%, #2A1566 50%, #0A3B4C 64%, #070C1A 100%)', far: [B('14%', '18%', '54%', '62%', 'rgba(124,77,255,0.75)')], mid: [B('86%', '82%', '54%', '62%', 'rgba(0,200,220,0.6)')], near: [B('50%', '50%', '18%', '18%', 'rgba(179,136,255,0.35)')] },
  },
  plex: {
    day: { base: 'linear-gradient(180deg, #FBF6EC 0%, #F5E6CC 100%)', far: [B('50%', '96%', '170%', '62%', '#FFD27A')], mid: [B('14%', '12%', '54%', '54%', 'rgba(255,255,255,0.9)')], near: [B('82%', '32%', '30%', '30%', 'rgba(255,220,150,0.6)')] },
    night: { base: 'linear-gradient(180deg, #0E0E0E 0%, #1B1B1B 100%)', far: [B('50%', '98%', '170%', '62%', 'rgba(229,160,13,0.8)')], mid: [B('14%', '12%', '54%', '54%', 'rgba(70,70,70,0.6)')], near: [B('82%', '32%', '30%', '30%', 'rgba(255,190,80,0.25)')] },
  },
}
// Photos (see public/wallpapers/CREDITS.md) and the drawn SVG scenes. Photos are blurred behind the
// glass (Settings → Glass → Wallpaper blur); the drawn scenes stay crisp. The tint keeps text readable.
const PHOTO = (file, base) => ({ day: { base, image: `/wallpapers/${file}`, blur: true }, night: { base, image: `/wallpapers/${file}`, blur: true } })
Object.assign(PALETTES, {
  forest: PHOTO('forest.webp', '#3E5A2E'),
  ocean: PHOTO('ocean.webp', '#2F7FA6'),
  alpine: PHOTO('alpine.webp', '#5E7591'),
  dunes: PHOTO('dunes.webp', '#B9643A'),
  lavender: PHOTO('lavender.webp', '#6E6AA3'),
  sunset: PHOTO('sunset.webp', '#C98B86'),
  city: PHOTO('city.webp', '#15223A'),
  northern: PHOTO('northern.webp', '#1B3A4A'),
  starry: PHOTO('starry.webp', '#141A2C'),
  nebula: PHOTO('nebula.webp', '#2A3A52'),
  tide: { day: { base: '#E8EEF8', image: '/wallpapers/tide-day.svg' }, night: { base: '#0B1630', image: '/wallpapers/tide-night.svg' } },
  retrowave: { day: { base: '#F0E4F8', image: '/wallpapers/retrowave-day.svg' }, night: { base: '#1A0B3A', image: '/wallpapers/retrowave-night.svg' } },
})
const IMAGE_TINT = {
  day: 'linear-gradient(180deg, rgba(255,255,255,0.25) 0%, rgba(230,238,255,0.45) 100%)',
  night: 'linear-gradient(180deg, rgba(9,13,31,0.35) 0%, rgba(9,13,31,0.6) 100%)',
}

/** CSS for a list of blobs — the wallpaper layers and the Settings swatches paint with it. */
export function blobsCss(list) {
  return list.map((b) => `radial-gradient(ellipse ${b.w} ${b.h} at ${b.x} ${b.y}, ${b.color} 0%, transparent 66%)`).join(', ')
}

/** A one-layer preview of a preset (Settings → Background swatches); blobs are stretched to the swatch's wide box. */
export function wallpaperCss(preset, theme, stretch = 2.3) {
  const p = paletteFor(preset, theme)
  if (p.image) return `url("${p.image}") center / cover no-repeat, ${p.base}`
  const tall = (b) => ({ ...b, h: `${parseFloat(b.h) * stretch}%` })
  return [blobsCss([...p.near, ...p.mid, ...p.far].map(tall)), p.base].filter(Boolean).join(', ')
}

/** The colour fields for a preset in a theme; a personal image when one is set. */
export function paletteFor(preset, theme, image = '') {
  const tone = theme === 'light' ? 'day' : 'night'
  if (preset === 'personal' && image) {
    return { base: PALETTES.aurora[tone].base, image, blur: true, tint: IMAGE_TINT[tone], far: [], mid: [], near: [] }
  }
  const name = preset === 'default' || preset === 'personal' || !PALETTES[preset] ? 'aurora' : preset
  const p = PALETTES[name][tone]
  if (p.image) return { base: p.base, image: p.image, blur: !!p.blur, tint: IMAGE_TINT[tone], far: [], mid: [], near: [] }
  return { ...p, image: '' }
}

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

/** What WallpaperLayer renders; applyWallpaper keeps it current. */
export const wallpaperState = ref({ preset: getWallpaperPreference(), image: getWallpaperImage() })

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
  const pref = normalizePreference(preference)
  const image = pref === 'personal' && imageSrc ? imageSrc : ''
  wallpaperState.value = { preset: pref, image }
  if (typeof document !== 'undefined') {
    const root = document.documentElement
    root.setAttribute('data-wallpaper', pref)
    root.classList.toggle('has-wallpaper-image', !!image)
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
  applyLocaleFromProfile(payload.locale)
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
  applyGlassFromProfile(payload)
  applyHomepageWidgetDebugFromProfile(payload)
  applyHomeLayoutFromProfile(payload)
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

