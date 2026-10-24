/** Header chips for the VPN and the Cloudflare Tunnel, shown only when switched on. */

import { t } from './i18n/index.js'

export function vpnChip(vpn) {
  if (!vpn?.enabled) return null
  if (vpn.tunnel_up && vpn.handshake_ok !== false) {
    const provider = vpn.provider ? ` (${vpn.provider})` : ''
    return { label: t('VPN'), tone: 'ok', title: t('VPN connected{provider}', { provider }) }
  }
  const reason = vpn.last_error ? `: ${vpn.last_error}` : ''
  return {
    label: t('VPN down'),
    tone: 'bad',
    title: t('VPN is on but not connected; qBittorrent, Prowlarr and FlareSolverr wait for it{reason}', { reason }),
  }
}

export function tunnelChip(tunnel) {
  if (!tunnel?.enabled) return null
  if (tunnel.running && tunnel.connected) {
    return { label: t('Tunnel'), tone: 'ok', title: t('Cloudflare Tunnel connected') }
  }
  if (tunnel.running) {
    return { label: t('Tunnel connecting'), tone: 'warn', title: t('Cloudflare Tunnel is starting or reconnecting') }
  }
  const reason = tunnel.summary ? `: ${tunnel.summary}` : ''
  return { label: t('Tunnel down'), tone: 'bad', title: t('Cloudflare Tunnel is not running{reason}', { reason }) }
}

export function versionLabel(health) {
  if (!health?.version) return ''
  const sha = String(health.git_sha || '').slice(0, 7)
  return sha ? `v${health.version} (${sha})` : `v${health.version}`
}
