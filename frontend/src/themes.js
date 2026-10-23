/** Themes: a wallpaper, day or night, an accent and the glass tuning — chosen together in Settings → Visuals. */

export const THEMES = [
  ['aurora', 'Aurora', 'aurora', 'light', '#0a6cff', { alpha: 0.5, blur: 28, depth: 1 }],
  ['midnight', 'Midnight Glass', 'city', 'dark', '#5aa2ff', { alpha: 0.5, blur: 28, depth: 1 }],
  ['forest', 'Forest Zen', 'forest', 'light', '#16a34a', { alpha: 0.55, blur: 30, depth: 1 }],
  ['ocean', 'Ocean', 'ocean', 'light', '#0a6cff', { alpha: 0.55, blur: 30, depth: 1 }],
  ['alpine', 'Alpine', 'alpine', 'light', '#0ea5e9', { alpha: 0.55, blur: 30, depth: 1 }],
  ['dunes', 'Dunes', 'dunes', 'light', '#f97316', { alpha: 0.55, blur: 30, depth: 1 }],
  ['lavender', 'Lavender Dreams', 'lavender', 'light', '#8b5cf6', { alpha: 0.6, blur: 32, depth: 1 }],
  ['sunset', 'Sunset Beach', 'sunset', 'light', '#f43f5e', { alpha: 0.55, blur: 30, depth: 1 }],
  ['northern', 'Northern Lights', 'northern', 'dark', '#22d3ee', { alpha: 0.5, blur: 28, depth: 1 }],
  ['starry', 'Starry Night', 'starry', 'dark', '#a78bfa', { alpha: 0.5, blur: 28, depth: 1 }],
  ['nebula', 'Nebula', 'nebula', 'dark', '#f472b6', { alpha: 0.55, blur: 30, depth: 1 }],
  ['tide', 'Tide', 'tide', 'light', '#1e5aa8', { alpha: 0.45, blur: 22, depth: 1 }],
  ['retrowave', 'Retrowave', 'retrowave', 'dark', '#ff4fa3', { alpha: 0.42, blur: 22, depth: 1.2 }],
  ['candy', 'Candy', 'candy', 'light', '#ec4899', { alpha: 0.5, blur: 28, depth: 1 }],
  ['mono', 'Monochrome', 'mono', 'dark', '#64748b', { alpha: 0.5, blur: 28, depth: 0.6 }],
  ['jellyfin', 'Jellyfin', 'jellyfin', 'dark', '#a855f7', { alpha: 0.5, blur: 28, depth: 1 }],
  ['plex', 'Plex', 'plex', 'dark', '#e5a00d', { alpha: 0.5, blur: 28, depth: 1 }],
].map(([id, name, wallpaper, mode, accent, glass]) => ({ id, name, wallpaper, mode, accent, glass }))
