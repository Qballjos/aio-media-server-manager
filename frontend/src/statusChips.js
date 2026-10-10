/** Header chips for the VPN and the Cloudflare Tunnel, shown only when switched on. */

export function vpnChip(vpn) {
  if (!vpn?.enabled) return null
  if (vpn.tunnel_up && vpn.handshake_ok !== false) {
    const provider = vpn.provider ? ` (${vpn.provider})` : ''
    return { label: 'VPN', tone: 'ok', title: `VPN connected${provider}` }
  }
  const reason = vpn.last_error ? `: ${vpn.last_error}` : ''
  return {
    label: 'VPN down',
    tone: 'bad',
    title: `VPN is on but not connected; qBittorrent, Prowlarr and FlareSolverr wait for it${reason}`,
  }
}

export function tunnelChip(tunnel) {
  if (!tunnel?.enabled) return null
  if (tunnel.running && tunnel.connected) {
    return { label: 'Tunnel', tone: 'ok', title: 'Cloudflare Tunnel connected' }
  }
  if (tunnel.running) {
    return { label: 'Tunnel connecting', tone: 'warn', title: 'Cloudflare Tunnel is starting or reconnecting' }
  }
  const reason = tunnel.summary ? `: ${tunnel.summary}` : ''
  return { label: 'Tunnel down', tone: 'bad', title: `Cloudflare Tunnel is not running${reason}` }
}

export function versionLabel(health) {
  if (!health?.version) return ''
  const sha = String(health.git_sha || '').slice(0, 7)
  return sha ? `v${health.version} (${sha})` : `v${health.version}`
}
