/** Bundled dashboard icons served from /app-icons (public/). */
const ICON_FILES = {
  flaresolverr: 'flaresolverr.png',
  grimmory: 'grimmory.svg',
  shelfmark: 'shelfmark.png',
  autobrr: 'autobrr.svg',
  bazarr: 'bazarr.svg',
  cleanuparr: 'cleanuparr.png',
  jellyfin: 'jellyfin.svg',
  kometa: 'kometa.svg',
  lidarr: 'lidarr.svg',
  maintainerr: 'maintainerr.svg',
  mylar3: 'mylar.png',
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
  tautulli: 'tautulli.svg',
  unpackerr: 'unpackerr.png',
}

export function appIconSrc(name) {
  const file = ICON_FILES[name]
  return file ? `/app-icons/${file}` : ''
}
