/** Build Open UI URLs for catalog apps (LAN port vs Cloudflare subdomains). */

function isLanHostname(host) {
  const h = String(host || '').toLowerCase()
  if (!h || h === 'localhost' || h.endsWith('.local') || h.endsWith('.lan')) return true
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(h)) return true
  if (h.includes(':')) return true
  return false
}

const MULTI_PART_SUFFIXES = new Set([
  'co.uk',
  'org.uk',
  'me.uk',
  'ac.uk',
  'gov.uk',
  'com.au',
  'net.au',
  'org.au',
  'co.nz',
  'org.nz',
  'co.jp',
  'or.jp',
  'ne.jp',
  'com.br',
  'com.mx',
  'co.za',
  'org.za',
  'com.cn',
  'com.hk',
  'com.sg',
  'co.in',
  'com.tw',
  'com.tr',
  'co.kr',
  'com.ar',
  'com.pl',
])

function publicSuffixLabels(parts) {
  if (parts.length >= 2) {
    const two = parts.slice(-2).join('.')
    if (MULTI_PART_SUFFIXES.has(two)) return parts.slice(-2)
  }
  if (parts.length >= 3) {
    const three = parts.slice(-3).join('.')
    if (MULTI_PART_SUFFIXES.has(three)) return parts.slice(-3)
  }
  return parts.length ? [parts[parts.length - 1]] : []
}

/** media.example.com → example.com ; media.example.co.uk → example.co.uk */
export function derivePublicAppBaseDomain(hostname) {
  const parts = String(hostname || '')
    .toLowerCase()
    .split('.')
    .filter(Boolean)
  if (parts.length < 2) return ''
  const suffix = publicSuffixLabels(parts)
  const need = suffix.length + 1
  if (parts.length < need) return parts.join('.')
  return parts.slice(-need).join('.')
}

/**
 * @param {object} opts
 * @param {string} opts.appName catalog name (sonarr, jellyfin, …)
 * @param {number|string} opts.port
 * @param {string} [opts.hostname] defaults to window.location.hostname
 * @param {string} [opts.protocol] defaults to window.location.protocol
 * @param {string} [opts.baseDomain] Settings override (e.g. example.com)
 * @param {string} [opts.subdomain] custom subdomain from Settings
 */
export function appWebUrl({ appName, port, hostname, protocol, baseDomain, subdomain } = {}) {
  const host =
    hostname ||
    (typeof window !== 'undefined' ? window.location.hostname : '') ||
    'localhost'
  const proto =
    protocol ||
    (typeof window !== 'undefined' ? window.location.protocol : 'http:') ||
    'http:'
  const portNum = Number(port) || 0
  const configured = String(baseDomain || '')
    .trim()
    .replace(/^\.+|\.+$/g, '')
    .toLowerCase()

  // LAN http://ip access keeps :port links even when Public app domain is set.
  const onLan = proto !== 'https:' && isLanHostname(host)
  if (onLan) {
    return `http://${host}:${portNum || 80}`
  }

  const base = configured || derivePublicAppBaseDomain(host)
  const custom = String(subdomain || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '')
  const name =
    custom ||
    String(appName || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, '')
  if (base && name) {
    return `https://${name}.${base}`
  }
  // Last resort: same host, wrong for Cloudflare but better than nothing.
  return `${proto}//${host}${portNum ? `:${portNum}` : ''}`
}
