/** Bundled dashboard icons served from /app-icons (public/). */
const ICON_FILES = {
  flaresolverr: 'flaresolverr.png',
  grimmory: 'grimmory.svg',
  shelfmark: 'shelfmark.png',
  bazarr: 'bazarr.svg',
  jellyfin: 'jellyfin.svg',
  lidarr: 'lidarr.svg',
  neutarr: 'neutarr.svg',
  nzbget: 'nzbget.svg',
  plex: 'plex.svg',
  profilarr: 'profilarr.svg',
  prowlarr: 'prowlarr.svg',
  qbittorrent: 'qbittorrent.svg',
  radarr: 'radarr.svg',
  recyclarr: 'recyclarr.svg',
  sabnzbd: 'sabnzbd.svg',
  seerr: 'seerr.svg',
  sonarr: 'sonarr.svg',
}

export function appIconSrc(name) {
  const file = ICON_FILES[name]
  return file ? `/app-icons/${file}` : ''
}
