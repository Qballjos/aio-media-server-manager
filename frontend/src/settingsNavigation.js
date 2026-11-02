/** Settings pages and search terms shared by the router and sidebar. */
export const SETTINGS_GROUPS = [
  { label: 'Personal', items: [
    { id: 'account', label: 'Profile', icon: 'user', description: 'Your details, profile image and password.', keywords: 'account username email avatar password wachtwoord naam' },
    { id: 'visuals', label: 'Language and appearance', icon: 'palette', description: 'Make the manager feel like home.', keywords: 'theme language wallpaper branding glass transparency taal thema achtergrond kleur' },
  ] },
  { label: 'Dashboard', items: [
    { id: 'homepage', label: 'Start page', icon: 'grid', description: 'Personalize your home and sign-in screen.', keywords: 'home dock login welcome startpagina aanmelden welkomsttekst' },
  ] },
  { label: 'Connections', items: [
    { id: 'vpn', label: 'VPN', icon: 'shield', description: 'Manage the secure connection for your apps.', keywords: 'wireguard openvpn provider tunnel privadovpn' },
    { id: 'remote', label: 'External access', icon: 'globe', description: 'Reach your apps securely outside your home.', keywords: 'cloudflare tunnel domain subdomain dns proxy access externe toegang domein' },
    { id: 'integrations', label: 'App connections', icon: 'link', description: 'Connect media services and pair your TV or Homey.', keywords: 'jellyfin seerr api key token tv homey pairing koppelingen sleutel' },
    { id: 'usenet', label: 'Usenet', icon: 'download', description: 'Configure your Usenet provider and download clients.', keywords: 'nzb sabnzbd nzbget server provider download' },
  ] },
  { label: 'Maintenance', items: [
    { id: 'updates', label: 'Updates', icon: 'refresh', description: 'Keep your apps and manager up to date.', keywords: 'github token schedule update planning bijwerken' },
    { id: 'backups', label: 'Backups', icon: 'database', description: 'Protect your settings and restore a backup.', keywords: 'backup restore retention schedule herstellen bewaren' },
    { id: 'notifications', label: 'Notifications', icon: 'bell', description: 'Choose how and when you receive notifications.', keywords: 'discord email smtp events meldingen berichten' },
  ] },
  { label: 'System', items: [
    { id: 'system', label: 'Server and storage', icon: 'server', description: 'Manage your server, file permissions and storage.', keywords: 'puid pgid timezone logs permissions storage tijdzone rechten opslag' },
    { id: 'diagnostics', label: 'Help and diagnostics', icon: 'help', description: 'Find problems and share diagnostics with support.', keywords: 'debug errors support widgets help fouten diagnose' },
    { id: 'about', label: 'About this app', icon: 'info', description: 'Install the manager on your device and support the project.', keywords: 'pwa install donate paypal ko-fi installeren doneren' },
  ] },
]
export const SETTINGS_PAGES = SETTINGS_GROUPS.flatMap(group => group.items)
export const SETTINGS_SECTIONS = SETTINGS_PAGES.map(item => item.id)
export const SETTINGS_NAV = SETTINGS_PAGES.map(item => [item.id, item.label])
export const SETTINGS_ALIASES = {
  general: 'system', storage: 'system', permissions: 'system', github: 'updates',
  network: 'vpn', debug: 'diagnostics', theming: 'visuals', appearance: 'visuals', branding: 'visuals',
}
export function resolveSettingsSection(section) {
  const value = String(section || '')
  if (SETTINGS_SECTIONS.includes(value)) return value
  return Object.hasOwn(SETTINGS_ALIASES, value) ? SETTINGS_ALIASES[value] : 'account'
}
export function filterSettingsGroups(query, translate = value => value) {
  const terms = String(query || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return SETTINGS_GROUPS.map(group => ({
    ...group,
    items: group.items.filter(item => {
      const text = [translate(group.label), translate(item.label), translate(item.description), item.keywords].join(' ').toLocaleLowerCase()
      return terms.every(term => text.includes(term))
    }),
  })).filter(group => group.items.length)
}
