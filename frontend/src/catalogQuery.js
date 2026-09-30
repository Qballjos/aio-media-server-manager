/** Catalog filters stored in the hash query (`#/catalog?q=&status=&cat=&sort=`). */

export const STATUS_KEYS = ['active', 'installed', 'available']

export function parseList(value) {
  const raw = Array.isArray(value) ? value.join(',') : String(value || '')
  return raw
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function catalogStateFromQuery(query) {
  const source = query || {}
  return {
    q: String(source.q || ''),
    sort: source.sort === 'az' ? 'az' : 'popularity',
    status: parseList(source.status).filter((key) => STATUS_KEYS.includes(key)),
    cat: parseList(source.cat),
  }
}

export function catalogQueryFromState(state) {
  const query = {}
  const q = String(state.q || '').trim()
  if (q) query.q = q
  if (state.sort === 'az') query.sort = 'az'
  if (state.status?.length) query.status = state.status.join(',')
  if (state.cat?.length) query.cat = state.cat.join(',')
  return query
}

export function sameCatalogQuery(a, b) {
  return JSON.stringify(catalogQueryFromState(a)) === JSON.stringify(catalogQueryFromState(b))
}
