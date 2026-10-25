<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { appIconSrc } from './appIcons.js'
import { apiError, apiRequest, readJson } from './api.js'
import { appWebUrl } from './appWebUrl.js'
import { homeSnapshotCache, partialRetryDelay } from './homeSnapshotCache.js'
import { BP_ORDER, BREAKPOINTS, GRID_IDS, WIDGETS, collapseEmptyRows, dockHidden, firstFree, fitItem, homeEditing, homeGrid, homeGridSaves, layoutFor, resolve, restoreGrid, saveGridLayout, viewportBp } from './homeLayout.js'
import UiSelect from './UiSelect.vue'
import HomeEditBar from './HomeEditBar.vue'
import HomeGrid from './HomeGrid.vue'
import HomeGridSheet from './HomeGridSheet.vue'
import { openApp } from './appOpen.js'
import { startGuardedInterval } from './pageVisible.js'
import { formatBytes, formatUptime } from './format.js'
import { i18n, t } from './i18n/index.js'

function i18nLocale() {
  return i18n.global.locale.value
}
import { addNetSample } from './netRates.js'
import { MOOD_COLORS, attentionMood, serverMood, storageMood } from './statusMood.js'
import { readHomepageWidgetDebug, HOMEPAGE_WIDGET_DEBUG_EVENT } from './homepageDebug.js'

const props = defineProps({
  systemInfo: { type: Object, default: null },
  username: { type: String, default: '' },
})
const emit = defineEmits(['manage'])
const route = useRoute()

function subdomainFor(appName) {
  const row = (props.systemInfo?.public_app_hostnames || {})[appName]
  return row && row.enabled ? row.subdomain : ''
}

/** Keep path/hash from the API link; swap host for LAN vs Cloudflare subdomains. */
function publicAppUrl(appName, port, currentUrl = '') {
  const base = appWebUrl({
    appName,
    port,
    baseDomain: props.systemInfo?.public_app_base_domain || '',
    subdomain: subdomainFor(appName),
  })
  if (!currentUrl) return base
  try {
    const old = new URL(currentUrl, window.location.origin)
    const next = new URL(base)
    return `${next.origin}${old.pathname}${old.search}${old.hash}`
  } catch {
    return base
  }
}

function withPublicUrls(item, appName) {
  if (!item || typeof item !== 'object') return item
  const port = Number(
    (snapshot.value.apps || []).find((app) => app.name === appName)?.port || 0,
  )
  if (!port && !item.url) return item
  return {
    ...item,
    url: publicAppUrl(appName, port || item.port || 0, item.url || ''),
  }
}
const emptySnapshot = () => ({
  apps: [],
  calendar: [],
  downloads: [],
  recent: [],
  requests: [],
  trending: [],
  seerr: { available: false, url: null },
  vpn: null,
  widgets: [],
  waiting: [],
})

const snapshot = ref(homeSnapshotCache.snapshot || emptySnapshot())
const installJobs = ref({})
/** Job states during which an app is being installed, set up or updated. */
const BUSY_JOBS = ['queued', 'installing', 'configuring', 'updating']
const progressNow = ref(Date.now() / 1000)
const loading = ref(!homeSnapshotCache.snapshot)
// Widgets still on their way: the first response only carries the launcher.
const widgetsPending = computed(() => loading.value || !!snapshot.value.partial)
let partialAttempts = 0
let partialTimer = null
const snapshotError = ref('')
const widgetDebug = ref(false)
const query = ref('')
const results = ref([])
const searching = ref(false)
const searchSeerr = ref(false)
const searchError = ref('')
const searchedFor = ref('')
const notice = ref('')
const requestBusy = ref('')
const requestChoice = ref(null)
const SEARCH_PROVIDER_KEY = 'amm-home-search-provider'
const searchProvider = ref((() => {
  try {
    return localStorage.getItem(SEARCH_PROVIDER_KEY) === 'prowlarr' ? 'prowlarr' : 'seerr'
  } catch (_) {
    return 'seerr'
  }
})())
const searchPlaceholder = computed(() => {
  if (searchProvider.value === 'prowlarr') return t('Search Prowlarr indexers')
  return snapshot.value.seerr?.available ? t('Search movies and TV to request') : t('Search Sonarr and Radarr')
})
const downloadsFresh = ref(false)
const downloadPause = ref({ paused: false, resume_at: null })
const pauseFor = ref('60')
const pauseBusy = ref(false)
const SORT_KEY = 'amm-downloads-sort'
const downloadSort = ref((() => {
  try {
    return localStorage.getItem(SORT_KEY) || 'queue'
  } catch (_) {
    return 'queue'
  }
})())
// Stable sort, so equal percentages keep their queue order.
const sortedDownloads = computed(() => {
  const list = [...snapshot.value.downloads]
  if (downloadSort.value === 'queue') return list
  const dir = downloadSort.value === 'asc' ? 1 : -1
  return list.sort((a, b) => dir * ((a.progress || 0) - (b.progress || 0)))
})
// Stuck items (no peers, files gone, paused) never move; list what is moving and count the rest.
// Paused by Pause all is different: then the list shows everything.
const STUCK_STATUSES = { Stalled: 'stalled', 'Missing files': 'missing files', Paused: 'paused', Error: 'error' }
const movingDownloads = computed(() =>
  downloadPause.value.paused ? sortedDownloads.value : sortedDownloads.value.filter((item) => !(item.status in STUCK_STATUSES)),
)
const stuckSummary = computed(() => {
  if (downloadPause.value.paused) return ''
  const counts = {}
  for (const item of snapshot.value.downloads) {
    const label = STUCK_STATUSES[item.status]
    if (label) counts[label] = (counts[label] || 0) + 1
  }
  return Object.entries(counts).map(([label, n]) => `${n} ${label}`).join(' · ')
})
const stuckItems = computed(() =>
  downloadPause.value.paused ? [] : snapshot.value.downloads.filter((item) => item.status in STUCK_STATUSES),
)
const removeBusy = ref(new Set())

/** Sonarr/Radarr blocklist a removed download and search for another release; the rest leave the client. */
async function removeDownloads(items, confirmFirst = false) {
  const list = items.filter((item) => item.download_id)
  if (!list.length) return
  const what = `${list.length} stuck download${list.length === 1 ? '' : 's'}`
  if (confirmFirst && !window.confirm(`Remove ${what}? Sonarr and Radarr search for another release.`)) return
  removeBusy.value = new Set([...removeBusy.value, ...list.map((item) => item.download_id)])
  try {
    await apiRequest('/api/downloads/remove', {
      method: 'POST',
      body: JSON.stringify({ items: list.map((item) => ({ source: item.source, download_id: item.download_id })) }),
    })
  } catch (_) {
    /* the next poll shows what is left */
  } finally {
    const next = new Set(removeBusy.value)
    for (const item of list) next.delete(item.download_id)
    removeBusy.value = next
    loadDownloads()
  }
}
watch(downloadSort, (value) => {
  try {
    localStorage.setItem(SORT_KEY, value)
  } catch (_) {
    /* only this session remembers it */
  }
})
const pausedLabel = computed(() => {
  const at = downloadPause.value.resume_at
  if (!at) return t('Paused until you resume')
  const time = new Date(at * 1000).toLocaleTimeString(i18nLocale(), { hour: '2-digit', minute: '2-digit' })
  return t('Paused · resumes {time}', { time })
})
const requestsFilter = ref('all')
const trendingFilter = ref('all')
let poll = null
let downloadsPoll = null
let statusPoll = null
let installPoll = null
let searchTimer = null

const hasMediaServer = computed(() =>
  (snapshot.value.apps || []).some((app) => app.name === 'jellyfin' || app.name === 'plex'),
)
const hasCalendarSource = computed(() =>
  (snapshot.value.apps || []).some((app) => app.name === 'sonarr' || app.name === 'radarr'),
)
const hasWidgets = computed(
  () =>
    snapshot.value.calendar.length ||
    snapshot.value.downloads.length ||
    snapshot.value.recent.length ||
    snapshot.value.requests.length ||
    snapshot.value.trending.length ||
    hasMediaServer.value ||
    hasCalendarSource.value ||
    snapshot.value.seerr.available,
)
const editing = homeEditing
const dockElement = ref(null)
const dockHeight = ref(72)
let dockObserver = null
// Reserve the real dock height, including any installation or health notices.
watch(dockElement, (element) => {
  dockObserver?.disconnect()
  if (!element) return
  dockObserver = new ResizeObserver(() => {
    dockHeight.value = element.getBoundingClientRect().height
  })
  dockObserver.observe(element)
})
const showWidgets = computed(() => hasWidgets.value || widgetDebug.value || editing.value)

/** Edit mode can show a smaller screen's layout on this one; outside it Home follows the window. */
const previewBp = ref('')
const activeBp = computed(() => (editing.value && previewBp.value) || viewportBp.value)
const previewOptions = computed(() => BP_ORDER.slice(0, BP_ORDER.indexOf(viewportBp.value) + 1))
const previewing = computed(() => activeBp.value !== viewportBp.value)
/** A widget just added lights up for a moment. */
const highlight = ref('')
const gridLayout = computed(() => layoutFor(activeBp.value))

/** Outside edit mode a widget shows when there is something in it, or it is still loading. */
const widgetHasContent = computed(() => {
  const s = snapshot.value
  return {
    greeting: true,
    searchbar: true,
    recent: !!(s.recent.length || (hasMediaServer.value && isPending('recent'))),
    requests: !!(s.requests.length || (s.seerr.available && isPending('requests'))),
    trending: !!(s.trending.length || (s.seerr.available && isPending('trending'))),
    calendar: !!(s.calendar.length || (hasCalendarSource.value && isPending('calendar'))),
    downloads: !!(s.downloads.length || downloadPause.value.paused),
    playing: hasMediaServer.value,
    storage: true,
    server: true,
    attention: true,
  }
})
// Empty widgets leave Home outside edit mode, and the rows they had to themselves close up.
const shownLayout = computed(() => {
  if (editing.value) return gridLayout.value
  return collapseEmptyRows(gridLayout.value.filter((item) => widgetDebug.value || widgetHasContent.value[item.id]))
})

function onGridChange(layout) {
  saveGridLayout(activeBp.value, layout)
}

/** While arranging: the Add widget or widget sheet, and the note after a removal. */
const sheet = ref(null)
const sheetItem = computed(() => (sheet.value?.mode === 'widget' ? gridLayout.value.find((item) => item.id === sheet.value.id) || null : null))
const missingIds = computed(() => GRID_IDS.filter((id) => !gridLayout.value.some((item) => item.id === id)))
const elsewhere = computed(() => {
  const out = {}
  for (const id of missingIds.value) {
    out[id] = BP_ORDER.filter((bp) => bp !== activeBp.value && layoutFor(bp).some((item) => item.id === id)).map((bp) => BREAKPOINTS[bp].label)
  }
  return out
})
const notOn = computed(() => missingIds.value.filter((id) => elsewhere.value[id].length).length)
const toast = ref(null)
let toastTimer = null

function showToast(text, undo) {
  clearTimeout(toastTimer)
  toast.value = { text, undo }
  toastTimer = setTimeout(() => {
    toast.value = null
  }, 5000)
}

function undoToast() {
  const undo = toast.value?.undo
  clearTimeout(toastTimer)
  toast.value = null
  undo?.()
}

function removeWidget(id) {
  const before = JSON.parse(JSON.stringify(homeGrid.value))
  saveGridLayout(activeBp.value, gridLayout.value.filter((item) => item.id !== id))
  if (sheet.value?.id === id) sheet.value = null
  showToast(t('{name} removed from {size}', { name: t(WIDGETS[id].label), size: t(BREAKPOINTS[activeBp.value].label) }), () => restoreGrid(before))
}

function openWidget(id) {
  sheet.value = { mode: 'widget', id }
}

/** A widget lands in the first free spot of each chosen screen size, lights up and scrolls into view. */
function addWidget(id, everySize) {
  for (const bp of everySize ? BP_ORDER : [activeBp.value]) {
    const layout = layoutFor(bp)
    if (layout.some((item) => item.id === id)) continue
    const cols = BREAKPOINTS[bp].cols
    const [w, h] = WIDGETS[id].size[bp]
    const fitted = fitItem({ id, x: 0, y: 0, w, h }, cols)
    saveGridLayout(bp, [...layout, { ...fitted, ...firstFree(layout, fitted.w, fitted.h, cols) }])
  }
  sheet.value = null
  highlight.value = id
  setTimeout(() => {
    if (highlight.value === id) highlight.value = ''
  }, 1800)
  nextTick(() => document.querySelector(`[data-widget="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}

function resizeWidget(w, h) {
  const item = sheetItem.value
  if (!item) return
  const cols = BREAKPOINTS[activeBp.value].cols
  const width = Math.min(w, cols)
  saveGridLayout(activeBp.value, resolve(gridLayout.value, item.id, { ...item, w: width, h, x: Math.min(item.x, cols - width) }, cols, null))
}

function onArrangeKey(event) {
  if (event.key === 'Escape' && editing.value && !sheet.value && !event.defaultPrevented) editing.value = false
}

const todayLabel = computed(() => new Date().toLocaleDateString(i18nLocale(), { weekday: 'long', day: 'numeric', month: 'long' }))
const greeting = computed(() => {
  const hour = new Date().getHours()
  const part = t(hour < 6 ? 'Good night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening')
  return props.username ? `${part}, ${props.username}.` : `${part}.`
})
/** One line under the greeting: what is moving and what needs a look. */
const heroSummary = computed(() => {
  const parts = []
  const n = movingDownloads.value.length
  if (downloadPause.value.paused) parts.push(pausedLabel.value)
  else if (n === 1) parts.push(t('{n} download on the way', { n }))
  else if (n) parts.push(t('{n} downloads on the way', { n }))
  const sick = (snapshot.value.apps || []).filter((app) => app.sick).map((app) => app.display_name)
  if (sick.length === 1) parts.push(t('{names} needs a look', { names: sick[0] }))
  else if (sick.length) parts.push(t('{names} need a look', { names: sick.join(', ') }))
  if (!parts.length) parts.push(snapshot.value.apps?.length ? t('Everything is running.') : t('Nothing running yet.'))
  return parts.join('. ').replace(/\.?$/, '.')
})
const totalSpeed = computed(() => {
  // SABnzbd repeats the queue speed on every slot, torrent clients report per torrent: max per Usenet source, sum for the rest.
  const bySource = {}
  for (const item of movingDownloads.value) {
    const bps = Number(item.speed_bps) || 0
    const key = String(item.source || '')
    bySource[key] = key === 'sabnzbd' || key === 'nzbget' ? Math.max(bySource[key] || 0, bps) : (bySource[key] || 0) + bps
  }
  return formatSpeed(Object.values(bySource).reduce((sum, bps) => sum + bps, 0))
})
/** Now playing, Storage, Server and Needs attention share one status call, made only while one of them is on Home. */
const STATUS_IDS = ['playing', 'storage', 'server', 'attention']
const homeStatus = ref({ playing: [], server: null, storage: [], attention: [] })
const statusLoaded = ref(false)
const statusWanted = computed(() => gridLayout.value.some((item) => STATUS_IDS.includes(item.id)))
const fullestVolume = computed(() => homeStatus.value.storage[0] || null)
const fullestFree = computed(() => (fullestVolume.value ? formatBytes(fullestVolume.value.free).split(' ') : ['', '']))
const serverStatus = computed(() => (homeStatus.value.server ? serverMood(homeStatus.value.server) : null))
const storageStatus = computed(() => (fullestVolume.value ? storageMood(fullestVolume.value.percent) : null))
const attentionStatus = computed(() => attentionMood(homeStatus.value.attention))
const nowItem = computed(() => homeStatus.value.playing[0] || null)
// The last 30 polls (5 minutes) of network use, drawn in the Server widget; kept for the tab, like the snapshot.
const netHistory = ref(homeSnapshotCache.netHistory || [])
const netHoverIdx = ref(-1)
const netPoints = computed(() => netHistory.value.filter((point) => point.rxRate != null))
const netShown = computed(() => netPoints.value[netHoverIdx.value] || netPoints.value.at(-1) || null)
const netChart = computed(() => {
  const points = netPoints.value
  if (points.length < 2) return null
  const first = points[0].at
  const span = points.at(-1).at - first || 1
  const top = Math.max(1, ...points.map((point) => Math.max(point.rxRate, point.txRate))) * 1.15
  // ponytail: the line stops 4% short of the right edge so the marker on the latest point is not clipped.
  const x = (point) => ((point.at - first) / span) * 96
  const y = (value) => 40 - (value / top) * 38
  const line = (key) => points.map((point, i) => `${i ? 'L' : 'M'}${x(point).toFixed(2)} ${y(point[key]).toFixed(2)}`).join(' ')
  const peak = (key) => formatSpeed(Math.max(...points.map((point) => point[key]))) || '0 B/s'
  const last = points.at(-1)
  return {
    down: line('rxRate'),
    up: line('txRate'),
    downArea: `${line('rxRate')} L ${x(last).toFixed(2)} 40 L 0 40 Z`,
    upArea: `${line('txRate')} L ${x(last).toFixed(2)} 40 L 0 40 Z`,
    end: { x: x(last), down: (y(last.rxRate) / 40) * 100, up: (y(last.txRate) / 40) * 100 },
    minutes: Math.max(1, Math.round(span / 60)),
    hoverX: netHoverIdx.value >= 0 && points[netHoverIdx.value] ? x(points[netHoverIdx.value]) : null,
    label: `Network over the last ${Math.round(span / 60) || 1} min: download peak ${peak('rxRate')}, upload peak ${peak('txRate')}`,
  }
})
const netAgo = computed(() => {
  const point = netPoints.value[netHoverIdx.value]
  return point ? `${Math.round(netPoints.value.at(-1).at - point.at)} s ago` : ''
})

function netRate(value) {
  return value == null ? '—' : formatSpeed(value) || '0 B/s'
}

/** "12 MB/s" as figure and unit, for the big download number. */
function netParts(value) {
  return value == null ? ['—', ''] : netRate(value).split(' ')
}

function onNetHover(event) {
  const box = event.currentTarget.getBoundingClientRect()
  const points = netPoints.value
  if (points.length < 2 || !box.width) return
  const first = points[0].at
  const at = first + ((event.clientX - box.left) / (box.width * 0.96)) * (points.at(-1).at - first)
  let best = 0
  points.forEach((point, i) => {
    if (Math.abs(point.at - at) < Math.abs(points[best].at - at)) best = i
  })
  netHoverIdx.value = best
}

async function loadStatus() {
  if (!statusWanted.value) return
  try {
    const res = await apiRequest('/api/homepage/status')
    if (!res.ok) return
    const data = await readJson(res)
    homeStatus.value = { playing: data.playing || [], server: data.server || null, storage: data.storage || [], attention: data.attention || [] }
    const net = data.server?.network
    if (net && data.server.sampled_at) {
      netHistory.value = addNetSample(netHistory.value, { at: data.server.sampled_at, rx: net.rx_bytes, tx: net.tx_bytes })
      homeSnapshotCache.netHistory = netHistory.value
    }
    statusLoaded.value = true
  } catch (_) {
    /* keep the last status */
  }
}

function upFor(seconds) {
  const days = Math.floor(seconds / 86400)
  if (days) return `${days} day${days === 1 ? '' : 's'}`
  const hours = Math.floor(seconds / 3600)
  return hours ? `${hours} h` : `${Math.max(1, Math.floor(seconds / 60))} min`
}

/** How far the moving downloads are together, for the small Downloading card. */
const downloadsProgress = computed(() => {
  const list = movingDownloads.value
  if (!list.length) return 0
  return Math.round(list.reduce((sum, item) => sum + (Number(item.progress) || 0), 0) / list.length)
})
function chipDay(dt) {
  return dt.toLocaleDateString(undefined, { weekday: 'short' }).replace('.', '').toUpperCase()
}
function isToday(dt) {
  return dayKey(dt) === dayKey(new Date())
}
const widgetNotes = computed(() => snapshot.value.widgets || [])
const CATEGORY_LABELS = {
  media: 'Media',
  requests: 'Requests',
  automation: 'Automation',
  indexers: 'Indexers',
  downloading: 'Downloading',
  subtitles: 'Subtitles',
  optimization: 'Optimization',
  maintenance: 'Maintenance',
}
const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS)

const launcherGroups = computed(() => {
  const groups = new Map()
  for (const app of snapshot.value.apps || []) {
    const job = installJobs.value[app.name]
    const busy = !app.sick && job && BUSY_JOBS.includes(job.status)
    const id = app.category || 'other'
    if (!groups.has(id)) {
      groups.set(id, {
        id,
        label: CATEGORY_LABELS[id] || id,
        apps: [],
      })
    }
    groups.get(id).apps.push({
      ...app,
      ...(job?.status === 'failed' ? { state: 'unhealthy', state_label: 'Setup failed', sick: true } : {}),
      ...(busy ? { state: job.status, state_label: `${job.status[0].toUpperCase()}${job.status.slice(1)}…` } : {}),
      progress_message: job && !busy && job.status !== 'failed' ? '' : job?.message ?? app.progress_message,
      progress_updated_at: job?.updated_at ?? app.progress_updated_at,
      url: publicAppUrl(app.name, app.port, app.url || ''),
    })
  }
  return [...groups.values()].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a.id)
    const bi = CATEGORY_ORDER.indexOf(b.id)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
})
// The dock shows every app in group order; anything busy or unhealthy gets a line under it.
const dockApps = computed(() => launcherGroups.value.flatMap((group) => group.apps))
const dockNotes = computed(() =>
  dockApps.value
    .filter((app) => app.sick || BUSY_JOBS.includes(app.state))
    .map((app) => [`${app.display_name}: ${app.state_label || app.state}`, app.progress_message].filter(Boolean).join(' — ')),
)

// Every Jellyfin show and movie, newest first, appended as the rail scrolls; the snapshot keeps the latest activity fresh.
const recentMore = ref([])
const recentItems = computed(() => {
  const seen = new Set()
  return [...(snapshot.value.recent || []), ...recentMore.value]
    .filter((item) => {
      const key = `${item.source}-${item.id || item.title}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .map((item) => withPublicUrls(item, item.source))
})
const requestItems = computed(() =>
  (snapshot.value.requests || [])
    .filter((item) => mediaTypeMatches(item, requestsFilter.value))
    .map((item) => withPublicUrls(item, 'seerr')),
)
// Pages 2+ of Seerr's trending list, appended as the rail scrolls; the snapshot keeps page 1 fresh.
const trendingMore = ref([])
const trendingItems = computed(() => {
  const seen = new Set()
  return [...(snapshot.value.trending || []), ...trendingMore.value]
    .filter((item) => {
      const key = `${item.mediaType}-${item.mediaId}`
      if (seen.has(key)) return false
      seen.add(key)
      return mediaTypeMatches(item, trendingFilter.value)
    })
    .map((item) => withPublicUrls(item, 'seerr'))
})
const seerrHomeUrl = computed(() => {
  const seerr = snapshot.value.seerr || {}
  const port = Number((snapshot.value.apps || []).find((app) => app.name === 'seerr')?.port || 5055)
  return publicAppUrl('seerr', port, seerr.url || '')
})

function mediaTypeMatches(item, filter) {
  if (!filter || filter === 'all') return true
  const kind = String(item?.mediaType || '').toLowerCase()
  if (filter === 'movie') return kind === 'movie'
  if (filter === 'tv') return kind === 'tv' || kind === 'series'
  return true
}

function requestStatusDot(item) {
  const status = String(item?.status || 'missing')
  if (status === 'available') return { cls: 'is-available', label: 'Available' }
  if (status === 'partial') return { cls: 'is-partial', label: 'Partially available' }
  if (status === 'requested' || status === 'monitored') return { cls: 'is-requested', label: 'Requested' }
  return { cls: 'is-missing', label: 'Not available' }
}

function notesFor(widget) {
  return widgetNotes.value.filter((item) => item.widget === widget)
}

const SOURCE_NAMES = { jellyfin: 'Jellyfin', plex: 'Plex', seerr: 'Seerr', sonarr: 'Sonarr', radarr: 'Radarr' }

/** Still loading: first load, a cold server cache, or a source that has not answered yet. */
function isPending(widget) {
  return widgetsPending.value || (snapshot.value.waiting || []).includes(widget)
}

function waitingLabel(widget) {
  if (!(snapshot.value.waiting || []).includes(widget)) return ''
  const names = [...new Set(notesFor(widget).filter((note) => note.state === 'error').map((note) => SOURCE_NAMES[note.source] || note.source))]
  return names.length ? `Waiting for ${names.join(' and ')}…` : ''
}

function debugFlagFromRoute() {
  const raw = route.query.debug
  return raw === '1' || raw === 'true'
}

async function loadSnapshot(force = false) {
  try {
    const res = await apiRequest(force ? '/api/homepage?refresh=1' : '/api/homepage')
    if (res.ok) {
      const data = await readJson(res)
      snapshot.value = {
        ...emptySnapshot(),
        ...data,
        calendar: data.calendar || [],
        downloads: downloadsFresh.value ? snapshot.value.downloads : data.downloads || [],
        recent: data.recent || [],
        requests: data.requests || [],
        trending: data.trending || [],
        widgets: mergeWidgetNotes(data.widgets || []),
        seerr: data.seerr || { available: false, url: null },
        waiting: data.waiting || [],
      }
      homeSnapshotCache.snapshot = snapshot.value
      if (data.partial || (data.waiting || []).length) {
        // Ask again soon instead of waiting for the 20-second poll.
        const delay = partialRetryDelay(partialAttempts++)
        if (delay !== null && !partialTimer) {
          partialTimer = setTimeout(() => {
            partialTimer = null
            return loadSnapshot()
          }, delay)
        }
      } else {
        partialAttempts = 0
      }
      snapshotError.value = ''
    } else {
      snapshotError.value = `Home API HTTP ${res.status}`
    }
  } catch (err) {
    snapshotError.value = err?.message || 'Home snapshot failed'
  } finally {
    loading.value = false
  }
  if (force) loadDownloads()
}

async function loadInstallJobs() {
  progressNow.value = Date.now() / 1000
  try {
    const res = await apiRequest('/api/catalog/install-jobs')
    if (!res.ok) return
    const data = await readJson(res)
    const jobs = data.jobs || []
    const finished = jobs.some((job) =>
      !BUSY_JOBS.includes(job.status)
      && installJobs.value[job.name]?.status !== job.status
      && (
        BUSY_JOBS.includes(installJobs.value[job.name]?.status)
        || snapshot.value.apps.some((app) => app.name === job.name && BUSY_JOBS.includes(app.state))
      ),
    )
    installJobs.value = Object.fromEntries(jobs.map((job) => [job.name, job]))
    if (finished) loadSnapshot(true)
  } catch (_) {
    /* keep last progress and let its age show that it is stale */
  }
}

function mergeWidgetNotes(incoming) {
  if (!downloadsFresh.value) return incoming
  return [
    ...incoming.filter((note) => note.widget !== 'downloads'),
    ...(snapshot.value.widgets || []).filter((note) => note.widget === 'downloads'),
  ]
}

async function setDownloadsPaused(pause) {
  pauseBusy.value = true
  try {
    const body = pause ? { minutes: pauseFor.value === 'until' ? null : Number(pauseFor.value) } : {}
    const res = await apiRequest(`/api/downloads/${pause ? 'pause' : 'resume'}`, { method: 'POST', body: JSON.stringify(body) })
    if (res.ok) downloadPause.value = await readJson(res)
  } catch (_) {
    /* the next poll shows the real state */
  } finally {
    pauseBusy.value = false
    loadDownloads()
  }
}

async function loadDownloads() {
  try {
    const res = await apiRequest('/api/homepage/downloads')
    if (!res.ok) return
    const data = await readJson(res)
    snapshot.value.downloads = data.downloads || []
    if (data.pause) downloadPause.value = data.pause
    downloadsFresh.value = true
    if (Array.isArray(data.widgets) && data.widgets.length) {
      snapshot.value.widgets = [
        ...(snapshot.value.widgets || []).filter((note) => note.widget !== 'downloads'),
        ...data.widgets,
      ]
    }
  } catch (_) {
    /* keep last queue */
  }
}

function formatSpeed(bps) {
  const n = Number(bps)
  if (!Number.isFinite(n) || n <= 0) return ''
  if (n >= 1000000) return `${(n / 1000000).toFixed(n >= 10000000 ? 0 : 1)} MB/s`
  if (n >= 1000) return `${Math.round(n / 1000)} KB/s`
  return `${Math.round(n)} B/s`
}

let searchGen = 0

async function runSearch() {
  const q = query.value.trim()
  const gen = ++searchGen
  if (q.length < 2) {
    results.value = []
    searchSeerr.value = false
    searchError.value = ''
    searchedFor.value = ''
    return
  }
  searching.value = true
  const provider = searchProvider.value === 'prowlarr' ? 'prowlarr' : 'seerr'
  try {
    const res = await apiRequest(`/api/homepage/search?q=${encodeURIComponent(q)}&provider=${provider}`)
    if (gen !== searchGen) return
    if (res.ok) {
      const data = await readJson(res)
      results.value = data.results || []
      searchSeerr.value = !!data.seerr
      searchError.value = data.error || ''
    } else {
      results.value = []
      searchError.value = `Search failed (HTTP ${res.status})`
    }
  } catch (err) {
    if (gen !== searchGen) return
    results.value = []
    searchError.value = err?.message || 'Search failed'
  } finally {
    if (gen === searchGen) {
      searchedFor.value = q
      searching.value = false
    }
  }
}

function onProviderChange() {
  try {
    localStorage.setItem(SEARCH_PROVIDER_KEY, searchProvider.value)
  } catch (_) {
    /* the choice still applies for this visit */
  }
  results.value = []
  searchedFor.value = ''
  searchError.value = ''
  notice.value = ''
  if (query.value.trim().length >= 2) runSearch()
}

function resultKey(item) {
  if (item?.source === 'prowlarr') return item.token
  return `${item?.mediaType}-${item?.mediaId}`
}

/** Search results open over the widgets below the greeting instead of making it taller. */
/** A narrow search bar opens its results toward the middle of the screen, so they stay on it. */
const searchAnchor = computed(() => {
  const item = shownLayout.value.find((one) => one.id === 'searchbar')
  const cols = BREAKPOINTS[activeBp.value].cols
  if (!item || item.w > cols / 2) return ''
  return item.x + item.w / 2 > cols / 2 ? 'is-right' : 'is-left'
})
const searchOpen = computed(() => !!(notice.value || searchError.value || searching.value || searchedFor.value))

function closeSearch() {
  clearTimeout(searchTimer)
  results.value = []
  searchedFor.value = ''
  searchError.value = ''
  notice.value = ''
}

const STATUS_LABELS = {
  available: 'Available',
  partial: 'Partly available',
  requested: 'Requested',
  monitored: 'In library, not downloaded yet',
  missing: 'Not in library',
}

function statusLabel(item) {
  return STATUS_LABELS[item?.status] || ''
}

function onQueryInput() {
  notice.value = ''
  clearTimeout(searchTimer)
  const wait = searchProvider.value === 'prowlarr' ? 700 : 280
  searchTimer = setTimeout(runSearch, wait)
}

function preferredId(options, current) {
  const ids = (options || []).map((option) => option.id)
  if (ids.includes(current)) return current
  return ids[0] ?? null
}

function preferredPath(folders, current) {
  const paths = (folders || []).map((folder) => folder.path)
  if (paths.includes(current)) return current
  return paths[0] || ''
}

function choiceFromServers(item, servers) {
  const server = servers.find((one) => one.isDefault) || servers[0]
  return {
    item,
    servers,
    serverId: server.id,
    profileId: preferredId(server.profiles, server.profileId),
    rootFolder: preferredPath(server.folders, server.rootFolder),
    languageProfileId: preferredId(server.languages, server.languageProfileId),
  }
}

function onRequestServer(serverId) {
  const choice = requestChoice.value
  if (!choice) return
  const server = choice.servers.find((one) => one.id === serverId)
  if (!server) return
  requestChoice.value = {
    ...choice,
    serverId: server.id,
    profileId: preferredId(server.profiles, server.profileId),
    rootFolder: preferredPath(server.folders, server.rootFolder),
    languageProfileId: preferredId(server.languages, server.languageProfileId),
  }
}

const choiceServer = computed(() => {
  const choice = requestChoice.value
  if (!choice) return null
  return choice.servers.find((one) => one.id === choice.serverId) || choice.servers[0] || null
})

async function requestTitle(item) {
  if (!item?.can_request) return
  if (item.source === 'prowlarr') {
    await downloadRelease(item)
    return
  }
  const key = resultKey(item)
  requestBusy.value = key
  notice.value = ''
  try {
    const opt = await apiRequest(`/api/homepage/request-options?mediaType=${encodeURIComponent(item.mediaType)}`)
    if (opt.ok) {
      const options = await readJson(opt)
      if (options.needsChoice && options.servers?.length) {
        requestChoice.value = choiceFromServers(item, options.servers)
        requestBusy.value = ''
        return
      }
    }
    await submitRequest(item)
  } catch (err) {
    notice.value = err.message || 'Request failed.'
  } finally {
    if (!requestChoice.value) requestBusy.value = ''
  }
}

async function confirmRequest() {
  const choice = requestChoice.value
  const server = choiceServer.value
  if (!choice || !server) return
  const extra = { serverId: choice.serverId }
  if (choice.profileId != null && server.profiles?.length) extra.profileId = choice.profileId
  if (choice.rootFolder && server.folders?.length) extra.rootFolder = choice.rootFolder
  if (choice.languageProfileId != null && (server.languages?.length || 0) > 1) {
    extra.languageProfileId = choice.languageProfileId
  }
  const ok = await submitRequest(choice.item, extra)
  if (ok) requestChoice.value = null
}

async function submitRequest(item, extra = {}) {
  const key = resultKey(item)
  requestBusy.value = key
  notice.value = ''
  try {
    const res = await apiRequest('/api/homepage/request', {
      method: 'POST',
      body: JSON.stringify({
        mediaType: item.mediaType,
        mediaId: item.mediaId,
        seasons: item.mediaType === 'tv' ? 'all' : undefined,
        ...extra,
      }),
    })
    const data = await readJson(res)
    if (res.ok && data.ok !== false) {
      notice.value = data.detail || 'Request submitted.'
      item.status = 'requested'
      item.can_request = false
      trendingMore.value = trendingMore.value.map((t) =>
        resultKey(t) === key ? { ...t, status: 'requested', can_request: false } : t,
      )
      loadSnapshot(true)
      return true
    }
    notice.value = apiError(data, 'Request failed.')
    return false
  } catch (err) {
    notice.value = err.message || 'Request failed.'
    return false
  } finally {
    requestBusy.value = ''
  }
}

async function downloadRelease(item) {
  const key = resultKey(item)
  requestBusy.value = key
  notice.value = ''
  try {
    const res = await apiRequest('/api/homepage/grab', {
      method: 'POST',
      body: JSON.stringify({ token: item.token }),
    })
    const data = await readJson(res)
    if (res.ok && data.ok !== false) {
      notice.value = data.detail || 'Sent to the download client.'
      item.status = 'requested'
      item.can_request = false
      return
    }
    notice.value = apiError(data, 'Download failed.')
  } catch (err) {
    notice.value = err.message || 'Download failed.'
  } finally {
    requestBusy.value = ''
  }
}

function parseWhen(value) {
  if (!value) return null
  const text = String(value)
  if (/^\d+$/.test(text) && text.length >= 9) {
    const dt = new Date(Number(text) * 1000)
    return Number.isNaN(dt.getTime()) ? null : dt
  }
  const dt = new Date(text)
  return Number.isNaN(dt.getTime()) ? null : dt
}

function formatEventTime(value) {
  const dt = parseWhen(value)
  if (!dt) return ''
  return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function dayKey(dt) {
  const y = dt.getFullYear()
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const d = String(dt.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const calViewPicked = ref(false)
const calView = ref(defaultCalView())
const calFilter = ref('all')
const selectedDayKey = ref(dayKey(new Date()))
const recentRail = ref(null)
const requestsRail = ref(null)
const trendingRail = ref(null)

function defaultCalView() {
  return 'list'
}

// A calendar spanning more than half the grid shows the week; a narrower one (or any on a phone) the list.
const calendarWide = computed(() => {
  const item = gridLayout.value.find((entry) => entry.id === 'calendar')
  return !!item && activeBp.value !== 'phone' && item.w * 12 >= 7 * BREAKPOINTS[activeBp.value].cols
})
watch(
  calendarWide,
  (wide) => {
    if (!calViewPicked.value) calView.value = wide ? 'week' : 'list'
  },
  { immediate: true },
)
watch(statusWanted, (wanted) => {
  if (wanted) loadStatus()
})
// A smaller screen's preview that no longer fits the window gives way to the window's own layout.
watch(viewportBp, () => {
  if (previewBp.value && !previewOptions.value.includes(previewBp.value)) previewBp.value = ''
})
watch(editing, (on) => {
  if (on) return
  previewBp.value = ''
  sheet.value = null
  toast.value = null
})

function setCalView(view) {
  calViewPicked.value = true
  calView.value = view
  if ((view === 'week' || view === 'day' || view === 'list') && !selectedDayKey.value) {
    selectedDayKey.value = dayKey(new Date())
  }
}

function selectCalDay(day) {
  if (!day?.key) return
  selectedDayKey.value = day.key
  if (calView.value === 'month' || calView.value === 'week') {
    const parts = day.key.split('-').map(Number)
    if (parts.length === 3 && parts.every((n) => Number.isFinite(n))) {
      calCursor.value = new Date(parts[0], parts[1] - 1, parts[2])
    }
  }
}

function syncCalViewToViewport() {
  if (calViewPicked.value) return
  const next = calendarWide.value ? 'week' : defaultCalView()
  if (calView.value !== next) calView.value = next
}

function launcherTitle(app) {
  if (app.state_label) return `${app.display_name}: ${app.state_label}`
  return app.display_name
}

function launcherOpen(app) {
  return app.state === 'running'
}

const vpnNotice = computed(() => {
  const vpn = snapshot.value.vpn
  if (!vpn?.enabled || vpn.tunnel_up || !vpn.waiting?.length) return ''
  const names = vpn.waiting.map(
    (name) => (snapshot.value.apps || []).find((app) => app.name === name)?.display_name || name,
  )
  const verb = names.length === 1 ? 'stays' : 'stay'
  const error = vpn.last_error ? ` Last VPN error: ${vpn.last_error}` : ''
  return `VPN is on but not connected yet, so ${names.join(', ')} ${verb} stopped until it is.${error}`
})

function startOfWeek(value) {
  const dt = new Date(value)
  dt.setHours(0, 0, 0, 0)
  dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
  return dt
}

const calCursor = ref(startOfWeek(new Date()))

function scrollRail(which, direction) {
  const node =
    which === 'requests' ? requestsRail.value : which === 'trending' ? trendingRail.value : recentRail.value
  if (!node) return
  const step = Math.max(node.clientWidth * 0.72, 232)
  node.scrollBy({ left: direction * step, behavior: 'smooth' })
}

// Seerr's trending and Jellyfin's titles come up to 500 pages at a time; fetch the next once the rail
// is within a screen of its end. `shown` is the page the snapshot already covers.
function railPager(railRef, more, path, shown) {
  let page = shown
  let done = false
  let loading = false
  async function load() {
    const rail = railRef.value
    if (!rail || loading || done) return
    if (rail.scrollWidth - rail.scrollLeft - rail.clientWidth > rail.clientWidth) return
    loading = true
    let loaded = false
    try {
      const res = await apiRequest(`${path}?page=${page + 1}`)
      const data = res.ok ? await readJson(res) : null
      if (data && !data.error) {
        page += 1
        more.value = [...more.value, ...(data.items || [])]
        done = !(data.items || []).length || page >= 500
        loaded = true
      }
    } catch {
      // A failed page is tried again on the next scroll.
    } finally {
      loading = false
    }
    // A filtered rail, or a page of titles the rail already shows, can still end inside the screen; keep going.
    if (loaded) nextTick(load)
  }
  return load
}
const loadMoreTrending = railPager(trendingRail, trendingMore, '/api/homepage/trending', 1)
// Jellyfin's title pages start over from the newest, so the snapshot's tiles come again and are skipped.
const loadMoreRecent = railPager(recentRail, recentMore, '/api/homepage/recent', 0)
// A rail wide enough to show every tile never scrolls, so also check when it appears or the filter changes.
watch([trendingRail, trendingFilter], () => nextTick(loadMoreTrending))
watch(recentRail, () => nextTick(loadMoreRecent))

function addDays(value, amount) {
  const dt = new Date(value)
  dt.setDate(dt.getDate() + amount)
  return dt
}

function eventKind(item) {
  return item?.kind || item?.source || ''
}

const MEDIA_LABELS = { tv: 'Series', movie: 'Movie' }

// Requests, trending and recent carry mediaType; calendar entries only kind and source.
function mediaKind(item) {
  const kind = String(item?.mediaType || item?.kind || item?.source || '').toLowerCase()
  if (['tv', 'series', 'episode', 'season', 'sonarr'].includes(kind)) return 'tv'
  if (['movie', 'radarr'].includes(kind)) return 'movie'
  return ''
}

function matchesCalFilter(item) {
  if (calFilter.value === 'tv') return eventKind(item) === 'episode' || item?.source === 'sonarr'
  if (calFilter.value === 'movies') return eventKind(item) === 'movie' || item?.source === 'radarr'
  if (calFilter.value === 'missing') return !item?.has_file
  return true
}

const filteredCalendar = computed(() =>
  (snapshot.value.calendar || []).filter(matchesCalFilter),
)

const calendarRangeLabel = computed(() => {
  if (calView.value === 'month') {
    return calCursor.value.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  }
  if (calView.value === 'day') {
    return calCursor.value.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })
  }
  if (calView.value === 'list' && calendarListInfo.value.label) return calendarListInfo.value.label
  const start = startOfWeek(calCursor.value)
  const end = addDays(start, 6)
  const opts = { day: 'numeric', month: 'short' }
  return `${start.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(undefined, { ...opts, year: 'numeric' })}`
})

const calendarDays = computed(() => {
  const byDay = {}
  for (const item of filteredCalendar.value) {
    const dt = parseWhen(item.when)
    if (!dt) continue
    const key = dayKey(dt)
    if (!byDay[key]) byDay[key] = []
    byDay[key].push(item)
  }
  for (const key of Object.keys(byDay)) {
    const rows = byDay[key].map((item) => ({ item, dt: parseWhen(item.when) })).sort((a, b) => a.dt - b.dt)
    byDay[key] = groupSameDay(rows).map((row) => row.item)
  }
  const todayKey = dayKey(new Date())
  if (calView.value === 'day' || calView.value === 'list') {
    const key = dayKey(calCursor.value)
    return [
      {
        key,
        date: calCursor.value.getDate(),
        month: calCursor.value.getMonth() + 1,
        weekday: weekdayLabels[(calCursor.value.getDay() + 6) % 7],
        inMonth: true,
        isToday: key === todayKey,
        events: byDay[key] || [],
      },
    ]
  }
  if (calView.value === 'week') {
    const start = startOfWeek(calCursor.value)
    const days = []
    for (let i = 0; i < 7; i += 1) {
      const cursor = addDays(start, i)
      const key = dayKey(cursor)
      days.push({
        key,
        date: cursor.getDate(),
        month: cursor.getMonth() + 1,
        weekday: weekdayLabels[i],
        inMonth: true,
        isToday: key === todayKey,
        events: byDay[key] || [],
      })
    }
    return days
  }
  const year = calCursor.value.getFullYear()
  const month = calCursor.value.getMonth()
  const first = new Date(year, month, 1)
  const start = startOfWeek(first)
  const last = new Date(year, month + 1, 0)
  const end = addDays(startOfWeek(last), 6)
  const days = []
  const cursor = new Date(start)
  while (cursor <= end) {
    const key = dayKey(cursor)
    days.push({
      key,
      date: cursor.getDate(),
      month: cursor.getMonth() + 1,
      weekday: weekdayLabels[(cursor.getDay() + 6) % 7],
      inMonth: cursor.getMonth() === month,
      isToday: key === todayKey,
      events: byDay[key] || [],
    })
    cursor.setDate(cursor.getDate() + 1)
  }
  return days
})

const calendarWeeks = computed(() => {
  const days = calendarDays.value
  if (calView.value !== 'month') return [{ key: days[0]?.key || 'week', isCurrent: true, days }]
  const weeks = []
  for (let i = 0; i < days.length; i += 7) {
    const slice = days.slice(i, i + 7)
    weeks.push({
      key: slice[0]?.key || String(i),
      isCurrent: slice.some((day) => day.isToday),
      days: slice,
    })
  }
  return weeks
})

const calendarListInfo = computed(() => {
  const rows = filteredCalendar.value
    .map((item) => ({ item, dt: parseWhen(item.when) }))
    .filter((row) => row.dt)
    .sort((a, b) => a.dt - b.dt)
  if (calView.value !== 'list') {
    const end = addDays(calCursor.value, 1)
    return { rows: rows.filter((row) => row.dt >= calCursor.value && row.dt < end), label: '' }
  }
  const weekStart = startOfWeek(calCursor.value)
  const thisWeek = dayKey(weekStart) === dayKey(startOfWeek(new Date()))
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const start = thisWeek ? today : weekStart
  const end = addDays(weekStart, 7)
  const inWeek = groupSameDay(rows.filter((row) => row.dt >= start && row.dt < end))
  if (inWeek.length || !thisWeek) return { rows: inWeek, label: thisWeek ? 'This week' : '' }
  // ponytail: nothing left this week → the next few releases instead of an empty card
  return { rows: groupSameDay(rows.filter((row) => row.dt >= start)).slice(0, 8), label: 'Coming up' }
})

/** Episodes of one series on one day collapse into a single row ("S03E01 – S03E05 · 5 episodes"). */
function groupSameDay(rows) {
  const out = []
  for (const row of rows) {
    const prev = out[out.length - 1]
    if (prev && prev.item.title === row.item.title && dayKey(prev.dt) === dayKey(row.dt)) {
      prev.count += 1
      prev.last = row
      prev.have = prev.have && row.item.has_file
      continue
    }
    out.push({ ...row, count: 1, last: row, have: row.item.has_file })
  }
  return out.map((row) => {
    if (row.count === 1) return row
    const code = (r) => String(r.item.detail || '').split(' ')[0]
    const span = code(row) && code(row.last) ? `${code(row)} – ${code(row.last)} · ` : ''
    // Downloaded only when every episode in the group is.
    return { ...row, item: { ...row.item, detail: `${span}${row.count} episodes`, has_file: row.have } }
  })
}
const calendarList = computed(() => calendarListInfo.value.rows)
const calOnToday = computed(() => {
  const now = new Date()
  if (calView.value === 'month') return calCursor.value.getMonth() === now.getMonth() && calCursor.value.getFullYear() === now.getFullYear()
  if (calView.value === 'day') return dayKey(calCursor.value) === dayKey(now)
  return dayKey(startOfWeek(calCursor.value)) === dayKey(startOfWeek(now))
})

function shiftCalendar(direction) {
  if (calView.value === 'month') {
    calCursor.value = new Date(calCursor.value.getFullYear(), calCursor.value.getMonth() + direction, 1)
    return
  }
  const step = calView.value === 'day' ? 1 : 7
  calCursor.value = addDays(calView.value === 'week' ? startOfWeek(calCursor.value) : calCursor.value, direction * step)
}

function goToday() {
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  selectedDayKey.value = dayKey(now)
  if (calView.value === 'month') {
    calCursor.value = new Date(now.getFullYear(), now.getMonth(), 1)
    return
  }
  if (calView.value === 'week' || calView.value === 'list') {
    calCursor.value = startOfWeek(now)
    return
  }
  calCursor.value = now
}

function onWidgetDebugEvent(event) {
  if (debugFlagFromRoute()) {
    widgetDebug.value = true
    return
  }
  if (event?.detail && typeof event.detail.enabled === 'boolean') {
    widgetDebug.value = event.detail.enabled
    return
  }
  widgetDebug.value = readHomepageWidgetDebug()
}

onMounted(() => {
  try {
    const params = new URLSearchParams(window.location.search)
    widgetDebug.value =
      debugFlagFromRoute() || params.get('debug') === '1' || readHomepageWidgetDebug()
  } catch (_) {
    widgetDebug.value = debugFlagFromRoute() || readHomepageWidgetDebug()
  }
  syncCalViewToViewport()
  window.addEventListener('resize', syncCalViewToViewport)
  window.addEventListener(HOMEPAGE_WIDGET_DEBUG_EVENT, onWidgetDebugEvent)
  window.addEventListener('keydown', onArrangeKey)
  loadSnapshot()
  // Defer live queues so first paint is the launcher snapshot.
  setTimeout(() => loadDownloads(), 750)
  poll = startGuardedInterval(loadSnapshot, 20000)
  downloadsPoll = startGuardedInterval(loadDownloads, 8000)
  installPoll = startGuardedInterval(loadInstallJobs, 3000, { immediate: true })
  statusPoll = startGuardedInterval(loadStatus, 10000, { immediate: true })
})
watch(
  () => route.query.debug,
  (value) => {
    if (value === '1' || value === 'true') widgetDebug.value = true
    if (value === undefined && route.name === 'home') {
      widgetDebug.value = readHomepageWidgetDebug()
    }
  }
)
watch(calView, (view) => {
  if (view === 'day') {
    goToday()
    return
  }
  if (view === 'week' || view === 'list') {
    calCursor.value = startOfWeek(calCursor.value)
  }
})
onUnmounted(() => {
  homeEditing.value = false
  dockObserver?.disconnect()
  window.removeEventListener('resize', syncCalViewToViewport)
  window.removeEventListener(HOMEPAGE_WIDGET_DEBUG_EVENT, onWidgetDebugEvent)
  window.removeEventListener('keydown', onArrangeKey)
  clearTimeout(toastTimer)
  if (poll) poll()
  if (downloadsPoll) downloadsPoll()
  if (installPoll) installPoll()
  if (statusPoll) statusPoll()
  if (partialTimer) clearTimeout(partialTimer)
  clearTimeout(searchTimer)
})
</script>

<template>
  <section class="home-shell" :class="{ 'has-floating-dock': !loading && snapshot.apps.length && !dockHidden, 'is-arranging': editing }" :style="{ '--home-dock-height': `${dockHeight}px` }">
    <div v-if="loading" class="home-skeleton" role="status" :aria-label="$t('Loading Home')">
      <div class="home-dock glass-pill" aria-hidden="true">
        <div class="home-dock-row">
          <span v-for="n in 8" :key="n" class="home-skel home-skel-icon"></span>
        </div>
      </div>
      <article class="home-widget glass-card" aria-hidden="true">
        <span class="home-skel home-skel-label"></span>
        <div class="home-rail">
          <span v-for="n in 6" :key="n" class="home-skel home-skel-poster"></span>
        </div>
      </article>
    </div>
    <p v-if="snapshotError" class="home-notice">{{ snapshotError }}</p>
    <p v-if="vpnNotice" class="home-notice">
      {{ vpnNotice }}
      <a href="#/settings/network" class="home-notice-link">{{ $t('Open Settings → Network') }}</a>
    </p>

    <div v-if="!loading && !snapshot.apps.length" class="home-empty glass-card">
      <h3>{{ $t('Nothing to launch yet') }}</h3>
      <p>{{ $t('Finish setup or install apps from Catalog. This page only lists installed applications with a WebUI.') }}</p>
      <button type="button" class="ui-btn ui-btn-primary" @click="emit('manage')">{{ $t('Go to Catalog') }}</button>
    </div>

    <template v-else-if="!loading">
      <Teleport to=".app-container" defer>
      <nav v-if="!dockHidden" ref="dockElement" class="home-dock is-floating glass-pill" :aria-label="$t('Apps')">
        <div class="home-dock-row">
          <component
            :is="launcherOpen(app) ? 'a' : 'span'"
            v-for="app in dockApps"
            :key="app.name"
            class="home-app"
            :class="{ 'is-down': app.state !== 'running' && !app.sick, 'is-sick': app.sick, 'is-busy': BUSY_JOBS.includes(app.state) }"
            v-bind="launcherOpen(app) ? { href: app.url, target: '_blank', rel: 'noopener noreferrer' } : {}"
            :title="launcherTitle(app)"
            :aria-label="launcherTitle(app)"
            @click="launcherOpen(app) && openApp($event, app.name, app.url)"
          >
            <img v-if="appIconSrc(app.name)" :src="appIconSrc(app.name)" alt="" class="home-app-icon" />
            <span v-else class="home-app-fallback">{{ app.display_name.slice(0, 1) }}</span>
          </component>
        </div>
        <p v-if="dockNotes.length" class="home-dock-notes" aria-live="polite">{{ dockNotes.join(' · ') }}</p>
      </nav>
      </Teleport>

      <div class="home-grid-wrap" :class="{ 'is-preview': previewing }" :style="previewing ? { maxWidth: `${BREAKPOINTS[activeBp].preview}px` } : null">
      <HomeGrid
        :layout="shownLayout"
        :bp="activeBp"
        :editing="editing"
        :highlight="highlight"
        :raise="searchOpen && !editing ? 'searchbar' : ''"
        :bottom-inset="(dockHidden ? 0 : dockHeight) + (editing ? 96 : 24)"
        @change="onGridChange"
        @remove="removeWidget"
        @open="openWidget"
      >
      <template #greeting>
      <section class="home-hero">
        <span class="home-hero-date">{{ todayLabel }}</span>
        <h2 class="home-hero-title">{{ greeting }}</h2>
        <p class="home-hero-sub">{{ heroSummary }}</p>
      </section>
      </template>

      <template #searchbar>
      <section class="home-search">
        <form class="home-search-pill glass-pill" role="search" @submit.prevent="runSearch">
          <label class="home-sr" for="home-search-provider">{{ $t('Search in') }}</label>
          <UiSelect
            id="home-search-provider"
            v-model="searchProvider"
            class="home-search-provider"
            variant="search"
            :aria-label="$t('Search in')"
            :options="[
              { value: 'seerr', label: $t('Movies & Series') },
              { value: 'prowlarr', label: $t('Other') },
            ]"
            @change="onProviderChange"
          />
          <svg class="home-search-mark" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
          <label class="home-sr" for="home-search">{{ $t('Search') }}</label>
          <input
            id="home-search"
            v-model="query"
            class="home-search-input"
            type="search"
            enterkeyhint="search"
            autocomplete="off"
            :placeholder="searchPlaceholder"
            @input="onQueryInput"
            @keydown.esc="closeSearch"
          />
          <button type="submit" class="ui-btn ui-btn-primary home-search-btn" :aria-label="$t('Search')" :disabled="searching">
            <svg class="home-search-go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
            <span>{{ $t('Search') }}</span>
          </button>
        </form>
        <div v-if="searchOpen" class="home-hero-results glass-card" :class="searchAnchor">
          <div class="home-results-scroll">
            <button type="button" class="ui-btn ui-btn-ghost ui-btn-icon home-results-close" :aria-label="$t('Close search results')" :title="$t('Close')" @click="closeSearch">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
            <p v-if="notice" class="home-notice">{{ notice }}</p>
            <p v-if="searchError" class="home-notice home-notice-error">{{ searchError }}</p>
            <p v-else-if="searchProvider === 'seerr' && !snapshot.seerr.available && !notice" class="home-muted">
              {{ $t('Install and start Seerr to request titles from this page.') }}
            </p>
            <p v-if="searching" class="home-muted">{{ $t('Searching…') }}</p>
            <p v-else-if="searchedFor && !results.length && !searchError" class="home-muted">
              {{ $t('No results for “{query}”.', { query: searchedFor }) }}
            </p>
            <ul v-if="results.length" class="home-results">
              <li v-for="item in results" :key="resultKey(item)" class="home-result">
                <img v-if="item.poster" :src="item.poster" alt="" class="home-poster" />
                <div class="home-result-body">
                  <strong>{{ item.title }}</strong>
                  <span v-if="item.source === 'prowlarr'">{{ item.detail }}</span>
                  <span v-else>{{ item.mediaType === 'tv' ? $t('TV') : 'Movie' }} {{ String(item.year || '').slice(0, 4) }}</span>
                  <span v-if="statusLabel(item)" class="home-status" :class="`is-${item.status}`">{{ statusLabel(item) }}</span>
                </div>
                <button
                  v-if="item.can_request && (searchSeerr || item.source === 'prowlarr')"
                  type="button"
                  class="ui-btn ui-btn-primary"
                  :disabled="requestBusy === resultKey(item)"
                  @click="requestTitle(item)"
                >
                  {{ requestBusy === resultKey(item) ? (item.source === 'prowlarr' ? $t('Sending…') : $t('Requesting…')) : (item.source === 'prowlarr' ? $t('Download') : $t('Get it now')) }}
                </button>
              </li>
            </ul>
          </div>
        </div>
      </section>
      </template>

      <template #recent>
        <article class="home-card glass-card">
          <div class="home-rail-head">
            <h3>{{ $t('Recently added') }}</h3>
            <div class="home-rail-tools">
              <div v-if="snapshot.recent.length" class="home-rail-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Previous recently added')" @click="scrollRail('recent', -1)">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Next recently added')" @click="scrollRail('recent', 1)">›</button>
              </div>
            </div>
          </div>
          <div v-if="snapshot.recent.length" ref="recentRail" class="home-rail" @scroll.passive="loadMoreRecent">
            <a
              v-for="(item, idx) in recentItems"
              :key="idx"
              class="home-tile"
              :href="item.url || undefined"
              :target="item.url ? '_blank' : undefined"
              rel="noopener noreferrer"
              @click="item.url && openApp($event, item.source || 'jellyfin', item.url)"
            >
              <span class="home-tile-art">
                <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
                <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                <span v-if="mediaKind(item)" class="media-badge">{{ MEDIA_LABELS[mediaKind(item)] }}</span>
              </span>
              <span class="home-tile-title">{{ item.title }}</span>
              <span v-if="item.detail" class="home-tile-meta">{{ item.detail }}</span>
            </a>
          </div>
          <template v-else-if="isPending('recent')">
            <div class="home-rail" aria-hidden="true">
              <span v-for="n in 6" :key="n" class="home-skel home-skel-poster"></span>
            </div>
            <p v-if="waitingLabel('recent')" class="home-muted">{{ waitingLabel('recent') }}</p>
          </template>
          <p v-else class="home-muted">{{ $t('Nothing recently added.') }}</p>
          <ul v-if="widgetDebug && notesFor('recent').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('recent')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
      </template>
      <template #requests>
        <article class="home-card glass-card">
          <div class="home-rail-head">
            <h3>{{ $t('Requests') }}</h3>
            <div class="home-rail-tools">
              <div v-if="snapshot.requests.length" class="home-type-filter" role="group" :aria-label="$t('Filter requests')">
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': requestsFilter === 'all' }" @click="requestsFilter = 'all'">{{ $t('All') }}</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': requestsFilter === 'movie' }" @click="requestsFilter = 'movie'">{{ $t('Movies') }}</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': requestsFilter === 'tv' }" @click="requestsFilter = 'tv'">{{ $t('Series') }}</button>
              </div>
              <div v-if="requestItems.length" class="home-rail-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Previous requests')" @click="scrollRail('requests', -1)">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Next requests')" @click="scrollRail('requests', 1)">›</button>
              </div>
            </div>
          </div>
          <div v-if="requestItems.length" ref="requestsRail" class="home-rail">
            <a
              v-for="(item, idx) in requestItems"
              :key="idx"
              class="home-tile"
              :href="item.url || seerrHomeUrl || undefined"
              :target="item.url || seerrHomeUrl ? '_blank' : undefined"
              rel="noopener noreferrer"
              @click="(item.url || seerrHomeUrl) && openApp($event, 'seerr', item.url || seerrHomeUrl)"
            >
              <span class="home-tile-art">
                <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
                <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                <span class="home-status-dot" :class="requestStatusDot(item).cls" :title="requestStatusDot(item).label" role="img" :aria-label="requestStatusDot(item).label"></span>
                <span v-if="mediaKind(item)" class="media-badge">{{ MEDIA_LABELS[mediaKind(item)] }}</span>
              </span>
              <span class="home-tile-title">{{ item.title }}</span>
              <span class="home-tile-meta home-req-status" :class="requestStatusDot(item).cls">{{ requestStatusDot(item).label }}</span>
            </a>
          </div>
          <template v-else-if="isPending('requests')">
            <div class="home-rail" aria-hidden="true">
              <span v-for="n in 6" :key="n" class="home-skel home-skel-poster"></span>
            </div>
            <p v-if="waitingLabel('requests')" class="home-muted">{{ waitingLabel('requests') }}</p>
          </template>
          <p v-else-if="snapshot.requests.length" class="home-muted">
            {{ requestsFilter === 'movie' ? $t('No movie requests in this filter.') : requestsFilter === 'tv' ? $t('No series requests in this filter.') : $t('No requests in this filter.') }}
          </p>
          <p v-else class="home-muted">{{ $t('No Seerr requests yet. Search above to request a title.') }}</p>
          <ul v-if="widgetDebug && notesFor('requests').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('requests')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
      </template>
      <template #trending>
        <article class="home-card glass-card home-card-trending">
          <div class="home-rail-head">
            <h3>{{ $t('Trending') }}</h3>
            <div class="home-rail-tools">
              <div v-if="snapshot.trending.length" class="home-type-filter" role="group" :aria-label="$t('Filter trending')">
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': trendingFilter === 'all' }" @click="trendingFilter = 'all'">{{ $t('All') }}</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': trendingFilter === 'movie' }" @click="trendingFilter = 'movie'">{{ $t('Movies') }}</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': trendingFilter === 'tv' }" @click="trendingFilter = 'tv'">{{ $t('Series') }}</button>
              </div>
              <div v-if="trendingItems.length" class="home-rail-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Previous trending')" @click="scrollRail('trending', -1)">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Next trending')" @click="scrollRail('trending', 1)">›</button>
              </div>
            </div>
          </div>
          <div v-if="trendingItems.length" ref="trendingRail" class="home-rail" @scroll.passive="loadMoreTrending">
            <div v-for="(item, idx) in trendingItems" :key="idx" class="home-tile home-tile-trending">
              <a
                class="home-tile-link"
                :href="item.url || seerrHomeUrl || undefined"
                :target="item.url || seerrHomeUrl ? '_blank' : undefined"
                rel="noopener noreferrer"
                @click="(item.url || seerrHomeUrl) && openApp($event, 'seerr', item.url || seerrHomeUrl)"
              >
                <span class="home-tile-art">
                  <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
                  <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                  <span v-if="mediaKind(item)" class="media-badge">{{ MEDIA_LABELS[mediaKind(item)] }}</span>
                </span>
                <span class="home-tile-title">{{ item.title }}</span>
                <span v-if="item.detail" class="home-tile-meta">{{ item.detail }}</span>
                <span v-if="statusLabel(item)" class="home-tile-meta">{{ statusLabel(item) }}</span>
              </a>
              <button
                v-if="item.can_request"
                type="button"
                class="ui-btn ui-btn-ghost home-tile-request"
                :disabled="requestBusy === resultKey(item)"
                @click="requestTitle(item)"
              >
                {{ requestBusy === resultKey(item) ? $t('Requesting…') : $t('Request') }}
              </button>
            </div>
          </div>
          <template v-else-if="isPending('trending')">
            <div class="home-rail" aria-hidden="true">
              <span v-for="n in 6" :key="n" class="home-skel home-skel-poster"></span>
            </div>
            <p v-if="waitingLabel('trending')" class="home-muted">{{ waitingLabel('trending') }}</p>
          </template>
          <p v-else-if="snapshot.trending.length" class="home-muted">
            {{ trendingFilter === 'movie' ? $t('No movies in this filter.') : trendingFilter === 'tv' ? $t('No series in this filter.') : $t('No titles in this filter.') }}
          </p>
          <p v-else class="home-muted">{{ snapshot.seerr?.available ? 'No trending titles right now.' : 'Trending titles appear when Seerr is running.' }}</p>
          <ul v-if="widgetDebug && notesFor('trending').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('trending')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
      </template>
      <template #calendar>
        <article class="home-card glass-card home-card-calendar">
          <div class="cal-head">
            <h3>{{ calendarRangeLabel }}</h3>
            <div class="cal-tools">
              <button v-if="!calOnToday" type="button" class="ui-btn ui-btn-ghost" @click="goToday">{{ $t('Today') }}</button>
              <UiSelect
                v-model="calFilter"
                class="cal-select"
                variant="inline"
                :aria-label="$t('Filter calendar')"
                :options="[
                  { value: 'all', label: $t('All') },
                  { value: 'tv', label: $t('TV') },
                  { value: 'movies', label: $t('Movies') },
                  { value: 'missing', label: $t('Not downloaded') },
                ]"
              />
              <UiSelect
                :model-value="calView"
                class="cal-select"
                variant="inline"
                :aria-label="$t('Calendar view')"
                :options="[
                  { value: 'list', label: $t('List') },
                  { value: 'day', label: $t('Day') },
                  { value: 'week', label: $t('Week') },
                  { value: 'month', label: $t('Month') },
                ]"
                @update:model-value="setCalView"
              />
              <div class="cal-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" @click="shiftCalendar(-1)" :aria-label="$t('Previous')">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" @click="shiftCalendar(1)" :aria-label="$t('Next')">›</button>
              </div>
            </div>
          </div>
          <div class="home-card-body">
          <div v-if="calView === 'list'" class="cal-list">
            <div v-if="!calendarList.length && isPending('calendar')" aria-hidden="true">
              <span v-for="n in 4" :key="n" class="home-skel home-skel-line"></span>
            </div>
            <p v-else-if="!calendarList.length" class="home-muted">{{ $t('Nothing in this range.') }}</p>
            <ul v-else>
              <li v-for="(row, idx) in calendarList" :key="idx" class="cal-row" :data-kind="eventKind(row.item)" :class="{ 'is-have': row.item.has_file, 'is-today': isToday(row.dt) }">
                <span class="cal-chip" aria-hidden="true"><span>{{ chipDay(row.dt) }}</span><strong>{{ row.dt.getDate() }}</strong></span>
                <span class="cal-row-body">
                  <span class="cal-row-title">
                    <strong>{{ row.item.title }}</strong>
                    <span v-if="mediaKind(row.item)" class="media-badge">{{ MEDIA_LABELS[mediaKind(row.item)] }}</span>
                  </span>
                  <span class="cal-row-meta">{{ [row.item.detail, formatEventTime(row.item.when)].filter(Boolean).join(' · ') }}</span>
                </span>
              </li>
            </ul>
          </div>
          <div v-else class="cal" :class="'cal-mode-' + calView" role="grid" :aria-label="$t('Upcoming releases calendar')">
            <div v-if="calView === 'week'" class="cal-weekdays">
              <span v-for="day in calendarDays" :key="day.key">{{ day.weekday }} {{ day.date }}-{{ day.month }}</span>
            </div>
            <div v-else-if="calView === 'month'" class="cal-weekdays">
              <span v-for="label in weekdayLabels" :key="label">{{ label }}</span>
            </div>
            <div class="cal-weeks" :class="{ 'is-week': calView === 'week', 'is-day': calView === 'day' }">
              <div
                v-for="week in calendarWeeks"
                :key="week.key"
                class="cal-week"
                :class="{ 'is-current': week.isCurrent, 'is-single': calView !== 'month' }"
              >
                <div
                  v-for="day in week.days"
                  :key="day.key"
                  class="cal-day"
                  :class="{
                    'is-today': day.isToday,
                    'is-selected': day.key === selectedDayKey,
                    'is-outside': !day.inMonth,
                  }"
                  role="button"
                  tabindex="0"
                  :aria-pressed="day.key === selectedDayKey"
                  @click="selectCalDay(day)"
                  @keydown.enter.prevent="selectCalDay(day)"
                  @keydown.space.prevent="selectCalDay(day)"
                >
                  <span class="cal-num">{{ calView === 'week' ? day.weekday + ' ' + day.date : day.date }}</span>
                  <ul v-if="day.events.length" class="cal-events">
                    <li
                      v-for="(item, idx) in day.events"
                      :key="idx"
                      class="cal-event"
                      :data-kind="eventKind(item)"
                      :class="{ 'is-have': item.has_file }"
                    >
                      <span class="cal-event-top">
                        <span class="cal-event-time">{{ formatEventTime(item.when) }}</span>
                        <span v-if="mediaKind(item)" class="media-badge">{{ MEDIA_LABELS[mediaKind(item)] }}</span>
                      </span>
                      <strong>{{ item.title }}</strong>
                      <span v-if="item.detail" class="cal-event-detail">{{ item.detail }}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
          <p v-if="!snapshot.calendar.length && widgetDebug" class="home-muted">{{ $t('Nothing on the calendar.') }}</p>
          <ul v-if="widgetDebug && notesFor('calendar').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('calendar')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
          </div>
        </article>
      </template>
      <template #downloads>
        <article class="home-card glass-card home-card-downloads">
          <div class="home-widget-head">
            <h3>{{ $t('Downloading') }}</h3>
            <span v-if="movingDownloads.length && !downloadPause.paused" class="home-card-stat">{{ movingDownloads.length }}<template v-if="totalSpeed"> · {{ totalSpeed }}</template></span>
            <UiSelect
              v-if="movingDownloads.length > 1"
              v-model="downloadSort"
              class="home-sort"
              variant="inline"
              :aria-label="$t('Sort downloads')"
              :options="[
                { value: 'queue', label: $t('Queue order') },
                { value: 'desc', label: $t('Most done first') },
                { value: 'asc', label: $t('Least done first') },
              ]"
            />
            <div v-if="downloadPause.paused" class="home-pause is-paused">
              <span class="home-muted">{{ pausedLabel }}</span>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="pauseBusy" @click="setDownloadsPaused(false)">{{ $t('Resume all') }}</button>
            </div>
            <div v-else-if="snapshot.downloads.length" class="home-pause">
              <UiSelect
                v-model="pauseFor"
                variant="inline"
                :aria-label="$t('Pause for')"
                :options="[
                  { value: '30', label: $t('30 min') },
                  { value: '60', label: $t('1 hour') },
                  { value: '180', label: $t('3 hours') },
                  { value: 'until', label: $t('Until I resume') },
                ]"
              />
              <button type="button" class="ui-btn ui-btn-ghost ui-btn-icon" :disabled="pauseBusy" :title="$t('Pause all downloads')" :aria-label="$t('Pause all downloads')" @click="setDownloadsPaused(true)">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
              </button>
            </div>
          </div>
          <div v-if="movingDownloads.length && !downloadPause.paused" class="home-dl-compact">
            <span class="home-dl-count">{{ movingDownloads.length }}<small>{{ $t('active') }}</small></span>
            <span class="home-muted home-dl-meta">{{ totalSpeed || 'Waiting for speed' }}</span>
            <span class="home-bar"><span :style="{ width: `${downloadsProgress}%` }" /></span>
          </div>
          <div class="home-card-body">
          <ul v-if="movingDownloads.length">
            <li v-for="(item, idx) in movingDownloads" :key="idx">
              <span class="home-dl-row">
                <strong>{{ item.title }}</strong>
                <span class="home-dl-pct font-mono">{{ item.progress }}%</span>
              </span>
              <span class="home-bar"><span :style="{ width: `${item.progress}%` }" /></span>
              <span class="home-muted home-dl-meta">
                {{ item.source }} · {{ item.status }}
                <span v-if="formatSpeed(item.speed_bps)" class="home-speed"> · {{ formatSpeed(item.speed_bps) }}</span>
                <span v-if="item.eta"> · {{ item.eta }}</span>
              </span>
            </li>
          </ul>
          <p v-else class="home-muted">{{ $t('No active downloads.') }}</p>
          <details v-if="stuckItems.length" class="home-stuck">
            <summary class="home-muted">{{ $t('Not moving:') }} {{ stuckSummary }}</summary>
            <div class="home-stuck-head">
              <span class="home-muted">{{ $t('Removing blocklists the release; Sonarr and Radarr search for another.') }}</span>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="removeBusy.size > 0" @click="removeDownloads(stuckItems, true)">{{ $t('Remove all') }}</button>
            </div>
            <ul>
              <li v-for="item in stuckItems" :key="item.download_id || item.title" class="home-stuck-item">
                <span class="home-stuck-title">
                  {{ item.title }}
                  <small class="home-muted">{{ item.source }} · {{ item.status }} · {{ item.progress }}%</small>
                </span>
                <button
                  type="button"
                  class="home-stuck-remove"
                  :aria-label="$t('Remove {name}', { name: item.title })"
                  :title="$t('Remove {name}', { name: item.title })"
                  :disabled="!item.download_id || removeBusy.has(item.download_id)"
                  @click="removeDownloads([item])"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6" />
                  </svg>
                </button>
              </li>
            </ul>
          </details>
          <ul v-if="widgetDebug && notesFor('downloads').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('downloads')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
          </div>
        </article>
      </template>
      <template #playing>
        <article class="home-card glass-card home-card-playing" :class="{ 'has-art': nowItem?.poster }">
          <template v-if="nowItem">
            <img v-if="nowItem.poster" class="np-art" :src="nowItem.poster" alt="" aria-hidden="true" />
            <span v-if="nowItem.poster" class="np-shade" aria-hidden="true"></span>
            <div class="np-top">
              <span class="gh-pill">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z" /></svg>
                {{ nowItem.device || (nowItem.source === 'plex' ? 'Plex' : 'Jellyfin') }}
              </span>
              <span v-if="homeStatus.playing.length > 1" class="gh-pill">+{{ homeStatus.playing.length - 1 }} {{ $t('watching') }}</span>
            </div>
            <component
              :is="nowItem.url ? 'a' : 'div'"
              class="np-bottom"
              v-bind="nowItem.url ? { href: nowItem.url, target: '_blank', rel: 'noopener noreferrer' } : {}"
              @click="nowItem.url && openApp($event, nowItem.source, nowItem.url)"
            >
              <strong class="np-title">{{ nowItem.title }}</strong>
              <span v-if="nowItem.detail" class="np-sub">{{ nowItem.detail }}</span>
              <span class="np-progress"><span :style="{ width: `${nowItem.progress}%` }" /></span>
              <span class="np-foot">
                <span>{{ nowItem.user }}<template v-if="nowItem.paused"> {{ $t('· Paused') }}</template></span>
                <span>{{ nowItem.transcoding ? $t('Transcoding') : $t('Direct play') }}<template v-if="nowItem.minutes_left != null"> · {{ nowItem.minutes_left }} {{ $t('min left') }}</template></span>
              </span>
            </component>
          </template>
          <template v-else>
            <div class="gh-head">
              <h3>{{ $t('Now playing') }}</h3>
              <span class="gh-status is-idle">{{ !statusLoaded ? $t('Checking who is watching…') : hasMediaServer ? $t('Nobody is watching') : $t('Install Jellyfin or Plex') }}</span>
            </div>
            <div v-if="statusLoaded && hasMediaServer" class="gh-empty">
              <span class="gh-big">{{ $t('Nothing on') }}</span>
              <span class="gh-label">{{ $t('What plays on Jellyfin or Plex shows up here.') }}</span>
            </div>
          </template>
        </article>
      </template>
      <template #storage>
        <article class="home-card glass-card home-card-storage">
          <div class="gh-head">
            <h3>{{ $t('Storage') }}</h3>
            <span v-if="storageStatus" class="gh-status" :style="{ '--dot': MOOD_COLORS[storageStatus.level] }">{{ storageStatus.text }}</span>
            <span v-else class="gh-status is-idle">{{ statusLoaded ? 'No data folders found' : 'Checking disks…' }}</span>
          </div>
          <template v-if="fullestVolume">
            <div class="gh-figure">
              <span class="gh-big">{{ fullestFree[0] }}<small>{{ fullestFree[1] }} {{ $t('free') }}</small></span>
              <span class="gh-label">{{ $t('of') }} {{ formatBytes(fullestVolume.total) }} · {{ Math.round(fullestVolume.percent) }}{{ $t('% used') }}</span>
            </div>
            <span class="gh-meter" :class="`is-${storageStatus.level}`"><span :style="{ width: `${fullestVolume.percent}%` }" /></span>
            <div class="gh-pills">
              <span v-for="volume in homeStatus.storage" :key="volume.labels.join()" class="gh-pill">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2.5" /><path d="M7 14h.01M11 14h6" /></svg>
                {{ volume.labels.join(' · ') }}<template v-if="homeStatus.storage.length > 1"> · {{ Math.round(volume.percent) }}%</template>
              </span>
            </div>
          </template>
        </article>
      </template>
      <template #server>
        <article class="home-card glass-card home-card-server">
          <div v-if="homeStatus.server && netChart" class="sv-chart">
            <svg class="sv-spark" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" :aria-label="netChart.label" @pointermove="onNetHover" @pointerleave="netHoverIdx = -1">
              <defs>
                <linearGradient id="sv-down-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" style="stop-color: var(--series-down); stop-opacity: 0.35" />
                  <stop offset="100%" style="stop-color: var(--series-down); stop-opacity: 0" />
                </linearGradient>
                <linearGradient id="sv-up-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" style="stop-color: var(--series-up); stop-opacity: 0.3" />
                  <stop offset="100%" style="stop-color: var(--series-up); stop-opacity: 0" />
                </linearGradient>
              </defs>
              <path :d="netChart.downArea" fill="url(#sv-down-fill)" />
              <path :d="netChart.upArea" fill="url(#sv-up-fill)" />
              <path class="sv-line is-down" :d="netChart.down" />
              <path class="sv-line is-up" :d="netChart.up" />
              <line v-if="netChart.hoverX != null" class="sv-cross" :x1="netChart.hoverX" y1="0" :x2="netChart.hoverX" y2="40" />
            </svg>
            <span class="sv-end is-down" :style="{ left: `${netChart.end.x}%`, top: `${netChart.end.down}%` }" aria-hidden="true"></span>
            <span class="sv-end is-up" :style="{ left: `${netChart.end.x}%`, top: `${netChart.end.up}%` }" aria-hidden="true"></span>
          </div>
          <div class="gh-head">
            <h3>{{ $t('Server') }}</h3>
            <span v-if="serverStatus" class="gh-status" :style="{ '--dot': MOOD_COLORS[serverStatus.level] }">{{ serverStatus.text }}</span>
            <span v-else class="gh-status is-idle">{{ $t('Reading the server…') }}</span>
          </div>
          <template v-if="homeStatus.server">
            <div class="sv-figures">
              <div class="gh-figure">
                <span class="gh-big">{{ Math.round(homeStatus.server.cpu_percent) }}<small>%</small></span>
                <span class="gh-label">{{ $t('CPU') }}</span>
              </div>
              <div class="gh-figure">
                <span class="gh-big">{{ Math.round(homeStatus.server.memory_percent) }}<small>%</small></span>
                <span class="gh-label">{{ $t('Memory') }}<span class="sv-mem-bytes"> · {{ formatBytes(homeStatus.server.memory_used) }} {{ $t('of') }} {{ formatBytes(homeStatus.server.memory_total) }}</span></span>
              </div>
              <div class="gh-figure sv-net-figure">
                <span class="gh-big">{{ netParts(netShown?.rxRate)[0] }}<small>{{ netParts(netShown?.rxRate)[1] }} <b class="sv-key">↓</b></small></span>
                <span class="gh-label">{{ netAgo || $t('Network') }}<template v-if="netShown"> · <b class="sv-key is-up">↑</b> {{ netRate(netShown.txRate) }}</template></span>
              </div>
            </div>
            <div class="gh-pills sv-pills">
              <span class="gh-pill">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></svg>
                {{ homeStatus.server.cpu_count }} {{ $t('cores') }}
              </span>
              <span v-if="homeStatus.server.temperature != null" class="gh-pill">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M14 14.76V4a2 2 0 0 0-4 0v10.76a4 4 0 1 0 4 0z" /></svg>
                {{ Math.round(homeStatus.server.temperature) }} °C
              </span>
              <span class="gh-pill">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
                Up {{ upFor(homeStatus.server.uptime_seconds) }}
              </span>
            </div>
          </template>
        </article>
      </template>
      <template #attention>
        <article class="home-card glass-card home-card-attention">
          <div class="gh-head">
            <h3>{{ $t('Needs attention') }}</h3>
            <span v-if="statusLoaded" class="gh-status" :style="{ '--dot': MOOD_COLORS[attentionStatus.level] }">{{ attentionStatus.text }}</span>
            <span v-else class="gh-status is-idle">{{ $t('Checking…') }}</span>
          </div>
          <div class="home-card-body">
            <ol v-if="homeStatus.attention.length" class="at-timeline">
              <li v-for="(item, idx) in homeStatus.attention" :key="idx">
                <a :href="item.href" class="at-item" :class="`is-${item.level}`">
                  <span class="at-dot" aria-hidden="true"></span>
                  <span class="at-text">
                    <strong>{{ item.title }}</strong>
                    <span class="gh-label">{{ item.detail }}</span>
                  </span>
                  <span class="at-kind">{{ item.level === 'problem' ? 'Problem' : item.level === 'warning' ? 'Warning' : 'Update' }}</span>
                </a>
              </li>
            </ol>
            <div v-else-if="statusLoaded" class="gh-empty">
              <span class="gh-big">{{ $t('All clear') }}</span>
              <span class="gh-label">{{ $t('Apps, VPN, tunnel, updates and disks look fine.') }}</span>
            </div>
          </div>
        </article>
      </template>
      </HomeGrid>
      </div>
      <HomeEditBar
        v-if="editing"
        :bp="activeBp"
        :preview-options="previewOptions"
        :not-on="notOn"
        :toast="toast"
        :dock-offset="dockHidden ? 0 : dockHeight"
        :saves="homeGridSaves"
        @preview="previewBp = $event === viewportBp ? '' : $event"
        @add="sheet = { mode: 'add' }"
        @done="editing = false"
        @undo="undoToast"
      />
      <HomeGridSheet
        v-if="editing && sheet && (sheet.mode === 'add' || sheetItem)"
        :key="sheet.mode + (sheet.id || '')"
        :mode="sheet.mode"
        :bp="activeBp"
        :item="sheetItem"
        :missing="missingIds"
        :elsewhere="elsewhere"
        @add="addWidget"
        @resize="resizeWidget"
        @remove="removeWidget(sheet.id)"
        @close="sheet = null"
      />
      <p v-if="!showWidgets" class="home-muted">
        {{ $t('Calendar, downloads, recently added, trending, and requests appear after Sonarr, Radarr, download clients, Jellyfin, Plex, or Seerr are running.') }}
        {{ $t('Turn on Widget debug in Settings → Diagnostics to see why a source is skipped or failing.') }}
      </p>
    </template>
    <article v-if="!loading && widgetDebug" class="home-widget glass-card home-debug-panel">
      <h3>{{ $t('Widget debug') }}</h3>
      <p class="home-muted">
        {{ $t('Per-source status for Home. API keys are never shown. Toggle this under Settings → Diagnostics, or add') }} <code>?debug=1</code> {{ $t('to the URL.') }}
      </p>
      <ul v-if="widgetNotes.length" class="home-debug">
        <li v-for="(note, idx) in widgetNotes" :key="idx">
          <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
          <span>{{ note.widget }} / {{ note.source }} — {{ note.detail }}</span>
        </li>
      </ul>
      <p v-else class="home-muted">{{ $t('No widget sources reported yet. Reload Home.') }}</p>
    </article>
    <Teleport to="body">
      <div v-if="requestChoice && choiceServer" class="modal-backdrop" @click.self="requestChoice = null">
        <form class="modal-content home-request-dialog" role="dialog" aria-modal="true" aria-labelledby="home-request-title" @submit.prevent="confirmRequest">
          <h3 id="home-request-title">{{ $t('Request') }} {{ requestChoice.item.title }}</h3>
          <p class="home-muted">{{ $t('Choose where Seerr should add it.') }}</p>
          <label v-if="requestChoice.servers.length > 1" class="home-request-field">
            {{ $t('Server') }}
            <UiSelect
              :model-value="requestChoice.serverId"
              :options="requestChoice.servers.map((server) => ({ value: server.id, label: server.name + (server.is4k ? ' (4K)' : '') }))"
              @update:model-value="onRequestServer"
            />
          </label>
          <label v-if="choiceServer.profiles.length > 1" class="home-request-field">
            {{ $t('Quality profile') }}
            <UiSelect
              v-model="requestChoice.profileId"
              :options="choiceServer.profiles.map((profile) => ({ value: profile.id, label: profile.name }))"
            />
          </label>
          <label v-if="choiceServer.folders.length > 1" class="home-request-field">
            {{ $t('Folder') }}
            <UiSelect
              v-model="requestChoice.rootFolder"
              :options="choiceServer.folders.map((folder) => ({ value: folder.path, label: folder.path }))"
            />
          </label>
          <label v-if="choiceServer.languages.length > 1" class="home-request-field">
            {{ $t('Language profile') }}
            <UiSelect
              v-model="requestChoice.languageProfileId"
              :options="choiceServer.languages.map((language) => ({ value: language.id, label: language.name }))"
            />
          </label>
          <div class="home-request-actions">
            <button type="button" class="ui-btn" @click="requestChoice = null">{{ $t('Cancel') }}</button>
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="requestBusy === resultKey(requestChoice.item)">
              {{ requestBusy === resultKey(requestChoice.item) ? $t('Requesting…') : $t('Request') }}
            </button>
          </div>
        </form>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.home-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
  min-width: 0;
}
.home-shell.has-floating-dock {
  padding-bottom: calc(var(--home-dock-height) + 2rem + env(safe-area-inset-bottom, 0px));
}
/* Placeholders in the shape of what loads into them. */
.home-skeleton {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.home-skel {
  display: block;
  background: var(--pill-bg);
  border-radius: var(--radius-md);
  animation: home-skel-pulse 1.4s ease-in-out infinite;
}
.home-skel-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 15px;
  flex: 0 0 auto;
}
.home-skel-poster {
  flex: 0 0 7.25rem;
  width: 7.25rem;
  height: 10.6rem;
}
.home-skel-line {
  height: 0.9rem;
  margin: 0.6rem 0;
}
.home-skel-line:nth-child(2n) {
  width: 65%;
}
@keyframes home-skel-pulse {
  50% {
    opacity: 0.45;
  }
}
@media (prefers-reduced-motion: reduce) {
  .home-skel {
    animation: none;
  }
}
.home-muted {
  color: var(--text-muted);
  font-size: var(--text-body);
}
.home-empty {
  padding: 1.5rem;
  display: grid;
  gap: 0.75rem;
  justify-items: start;
}
/* The dock: one glass pill of app tiles that stays at the bottom of the window while you scroll. */
.home-dock {
  position: relative;
  z-index: 5;
  justify-self: center;
  margin-top: 1rem;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  padding: 0.5rem 0.65rem;
  border-radius: 2rem;
  background: var(--control-bg);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
}
.home-dock.is-floating {
  position: fixed;
  bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
  width: max-content;
  max-width: calc(100% - 2rem);
  margin: 0;
}
.home-dock-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  max-width: 100%;
  overflow-x: auto;
  padding: 0.15rem;
  scrollbar-width: none;
}
.home-dock-row::-webkit-scrollbar {
  display: none;
}
.home-app {
  position: relative;
  flex: 0 0 auto;
  width: 3rem;
  height: 3rem;
  border-radius: 15px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  box-shadow: inset 0 1px 0 var(--glass-highlight);
  color: inherit;
  text-decoration: none;
  transition: transform 0.2s, background 0.2s;
}
.home-app:hover {
  transform: translateY(-3px) scale(1.06);
  background: var(--bg-surface-elevated);
}
/* Status dot on the tile's corner: green running, grey stopped, amber busy, red unhealthy. */
.home-app::after {
  content: '';
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 0 2px rgb(255 255 255 / 0.8);
}
.home-app.is-down {
  opacity: 0.55;
  cursor: default;
}
.home-app.is-down:hover {
  transform: none;
}
.home-app.is-down::after {
  background: var(--text-dim);
}
.home-app.is-busy::after {
  background: var(--color-warning);
  animation: home-skel-pulse 1.4s ease-in-out infinite;
}
.home-app.is-sick {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
}
.home-app.is-sick::after {
  background: var(--color-danger);
}
.home-app-icon,
.home-app-fallback {
  width: 1.9rem;
  height: 1.9rem;
  border-radius: 0.5rem;
  object-fit: contain;
}
.home-app-fallback {
  display: grid;
  place-items: center;
  font-weight: 700;
  background: var(--bg-surface-elevated);
}
.home-dock-notes {
  margin: 0;
  padding: 0 0.6rem 0.2rem;
  font-size: var(--text-kicker);
  color: var(--text-muted);
  text-align: center;
}
.home-notice-link {
  margin-left: 0.35rem;
  text-decoration: underline;
}
/* Greeting: date, greeting and a line about today, centred like the mockup. */
.home-hero {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0.55rem;
  padding: 0.5rem;
  container-type: size;
}
.home-hero-date {
  font-size: var(--text-body);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-main);
  text-shadow: var(--wallpaper-text-shadow);
}
.home-hero-title {
  margin: 0;
  font-size: clamp(1.6rem, 5.5cqw, 3rem);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.02;
  color: var(--text-heading);
  text-shadow: var(--wallpaper-text-shadow);
}
.home-hero-sub {
  margin: 0;
  font-size: var(--text-ui);
  color: var(--text-main);
  text-shadow: var(--wallpaper-text-shadow);
}
/* Search: the pill, centred in a wide card and filling a small one. */
.home-search {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 0;
  padding: 0;
  container-type: inline-size;
}
.home-search-pill {
  background: var(--control-bg);
  width: 100%;
  max-width: 720px;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  height: min(3.5rem, 100%);
  padding: 0 0.5rem 0 0;
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
  overflow: hidden;
}
.home-search-provider {
  align-self: stretch;
  flex: 0 1 12.4rem;
  width: 12.4rem;
  max-width: 12.4rem;
  min-width: 0;
  border-right: 1px solid var(--border-subtle);
}
.home-search-mark {
  flex: 0 0 auto;
  color: var(--text-muted);
}
.home-search-go {
  display: none;
}
.home-search-input {
  flex: 1 1 0;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  /* 16px keeps iOS from zooming the page when the field is focused. */
  font-size: var(--text-ui);
  -webkit-appearance: none;
  appearance: none;
  border-radius: 0;
}
.home-search-input::-webkit-search-decoration,
.home-search-input::-webkit-search-cancel-button {
  -webkit-appearance: none;
  appearance: none;
  display: none;
}
.home-search-input::placeholder {
  color: var(--text-dim);
}
.home-search-btn {
  min-height: 2.6rem;
  padding: 0 1.1rem;
}
.home-hero-results {
  position: absolute;
  top: calc(50% + min(1.75rem, 50%) - 1px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  width: min(720px, max(100%, min(28rem, calc(100vw - 2rem))));
  max-width: calc(100vw - 1.5rem);
  padding: 0;
  text-align: left;
}
.home-results-scroll {
  max-height: min(60vh, 34rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 1rem 1.1rem;
  display: grid;
  gap: 0.5rem;
}
.home-results-close {
  justify-self: end;
  margin: -0.4rem -0.5rem -0.6rem 0;
}
.home-results-close svg {
  width: 16px;
  height: 16px;
}
.home-hero-results.is-left {
  left: 0;
  transform: none;
}
.home-hero-results.is-right {
  left: auto;
  right: 0;
  transform: none;
}
@container (max-height: 172px) {
  .home-hero-sub {
    display: none;
  }
}
/* A phone-width bar keeps the field typeable. The worded button becomes an icon; Enter still submits. */
@container (max-width: 560px) {
  .home-search-pill {
    gap: 0.4rem;
    padding-right: 0.3rem;
  }
  .home-search-provider {
    flex: 0 1 10.4rem;
    width: auto;
    max-width: min(10.4rem, 46%);
    --ui-select-font: 0.92rem;
    --ui-select-pad: 0.7rem;
  }
  .home-search-mark {
    display: none;
  }
  .home-search-go {
    display: block;
    flex: 0 0 auto;
  }
  .home-search-btn {
    flex: 0 0 auto;
    width: min(2.55rem, calc(100% - 0.35rem));
    min-width: 0;
    height: min(2.55rem, calc(100% - 0.35rem));
    min-height: 0;
    aspect-ratio: 1;
    padding: 0;
  }
  .home-search-btn span {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  .home-hero-results,
  .home-hero-results.is-left,
  .home-hero-results.is-right {
    left: 0;
    right: 0;
    width: 100%;
    max-width: 100%;
    transform: none;
  }
}
@container (max-width: 280px) {
  .home-search-provider {
    max-width: min(6.4rem, 46%);
    --ui-select-pad: 0.55rem;
  }
}
.home-request-dialog {
  max-width: 28rem;
  padding: 1.15rem 1.25rem 1.2rem;
  gap: 0.75rem;
}
.home-request-dialog h3 {
  margin: 0;
}
.home-request-field {
  display: grid;
  gap: 0.3rem;
  font-size: var(--text-body);
}
.home-request-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.home-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.home-notice {
  color: var(--color-info);
  font-size: var(--text-body);
}
.home-notice-error {
  color: var(--color-danger, #f87171);
}
.home-results {
  list-style: none;
  display: grid;
  gap: 0.5rem;
}
.home-result {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}
.home-poster {
  width: 2.5rem;
  height: 3.6rem;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}
.home-result-body {
  flex: 1 1 auto;
  min-width: 0;
  display: grid;
}
.home-result-body span {
  color: var(--text-muted);
  font-size: var(--text-body);
}
.home-result-body .home-status {
  justify-self: start;
  margin-top: 0.2rem;
  padding: 0.05rem 0.5rem;
  border-radius: 999px;
  font-size: var(--text-kicker);
  font-weight: 600;
  border: 1px solid currentColor;
}
.home-status.is-available {
  color: var(--color-success-fg);
}
.home-status.is-partial,
.home-status.is-requested,
.home-status.is-monitored {
  color: var(--color-warning-fg);
}
.home-status.is-missing {
  color: var(--color-danger-fg);
}
/* The grid itself lives in HomeGrid; a smaller screen previewed in edit mode sits centred in a dashed frame. */
.home-grid-wrap {
  width: 100%;
  min-width: 0;
}
.home-grid-wrap.is-preview {
  margin-inline: auto;
  padding: 1rem;
  border: 1px dashed var(--border-strong);
  border-radius: calc(var(--radius-glass) + 1rem);
}
.home-shell.is-arranging {
  padding-bottom: calc(var(--home-dock-height) + 8rem + env(safe-area-inset-bottom, 0px));
}
/* While arranging, a card's own buttons step aside so the grip and corner are what you see. */
.hg.is-editing :is(.home-rail-tools, .home-rail-nav, .cal-nav, .cal-tools, .home-widget-head > :not(h3)) {
  visibility: hidden;
}
.hg.is-editing :is(.home-hero, .home-search) {
  border-radius: var(--radius-glass);
  outline: 1px dashed var(--border-strong);
  outline-offset: -1px;
}
/* Section heads: a bold title left, links and round buttons right. */
.home-rail-head,
.home-widget-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
  flex-wrap: wrap;
}
.home-card h3 {
  margin: 0;
  font-size: var(--text-strong);
  font-weight: 800;
  letter-spacing: -0.01em;
}
.home-rail-tools {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.home-type-filter {
  display: inline-flex;
  gap: 0.1rem;
  padding: 0.2rem;
  border-radius: 999px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
}
.home-type-filter .ui-btn {
  min-height: calc(var(--btn-h) - 0.5rem);
  padding: 0 0.8rem;
  border: none;
  background: transparent;
  box-shadow: none;
  color: var(--text-muted);
}
.home-type-filter .ui-btn.is-active {
  background: var(--pill-active);
  color: var(--text-heading);
  box-shadow: inset 0 1px 0 var(--glass-highlight);
}
.home-rail-nav {
  display: flex;
  gap: 0.35rem;
}
/* In a narrow card you swipe the rail, so the arrows go and the filter keeps the head on one line. */
@container (max-width: 400px) {
  .home-rail-nav {
    display: none;
  }
}
.cal-nav-btn {
  width: var(--btn-h);
  min-width: var(--btn-h);
  padding: 0;
  border-radius: 50%;
  font-size: var(--text-strong);
}
.home-rail {
  flex: 1 1 auto;
  min-height: 0;
  align-items: flex-start;
  display: flex;
  gap: 0.85rem;
  overflow-x: auto;
  /* Tiles round up a pixel taller than the rail; a vertically scrollable rail keeps the wheel from the page. */
  overflow-y: hidden;
  padding: 0.25rem 0.25rem 0.5rem;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.home-rail::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
.home-tile {
  --tile-w: clamp(4rem, calc((100cqh - var(--rail-chrome)) * 2 / 3), 9.5rem);
  flex: 0 0 var(--tile-w);
  width: var(--tile-w);
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  color: inherit;
  text-decoration: none;
  min-width: 0;
  scroll-snap-align: start;
}
.home-tile-trending {
  min-height: 0;
}
.home-tile-link {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  color: inherit;
  text-decoration: none;
  min-width: 0;
  flex: 1 1 auto;
}
.home-tile-request {
  width: 100%;
  margin-top: 0.4rem;
  padding-inline: 0.5rem;
  color: var(--color-primary-text);
}
.home-tile-art {
  position: relative;
  display: block;
  width: 100%;
}
.home-status-dot {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.85);
  pointer-events: none;
}
.home-status-dot.is-requested {
  background: var(--color-primary);
}
.home-status-dot.is-available {
  background: var(--color-success);
}
.home-status-dot.is-partial {
  background: var(--color-warning);
}
.home-status-dot.is-missing {
  background: var(--color-danger);
}
/* Posters: 2:3 glass tiles that lift a little on hover. */
.home-tile-poster,
.home-tile-fallback {
  width: 100%;
  aspect-ratio: 2 / 3;
  border-radius: 18px;
  object-fit: cover;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
  transition: transform 0.2s;
}
.home-tile:hover .home-tile-poster,
.home-tile:hover .home-tile-fallback {
  transform: translateY(-3px);
}
.home-tile-fallback {
  display: grid;
  place-items: center;
  font-size: var(--text-title);
  font-weight: 700;
  color: var(--text-muted);
}
.home-tile-title {
  font-size: var(--text-body);
  font-weight: 700;
  line-height: 1.2;
  height: calc(1.2em * 2);
  padding-left: 0.25rem;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}
.home-tile-meta {
  font-size: var(--text-kicker);
  line-height: 1.25;
  height: 1.25em;
  color: var(--text-muted);
  padding-left: 0.25rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* Request status under a poster. */
.home-req-status.is-requested {
  color: var(--color-primary-text);
}
.home-req-status.is-available {
  color: var(--color-success-fg);
}
.home-req-status.is-partial {
  color: var(--color-warning-fg);
}
.cal-nav {
  gap: 0.3rem;
}
.cal-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem 1rem;
  margin-bottom: 0.75rem;
}
.cal-head h3 {
  margin: 0;
  font-size: var(--text-ui);
}
.cal-nav,
.cal-tools,
.cal-views {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}
.cal-nav-btn {
  min-width: 2.1rem;
  padding-inline: 0.45rem;
}
.cal-select {
  width: auto;
  min-width: 9rem;
}
.cal-views .ui-btn.is-active {
  border-color: rgba(var(--color-primary-rgb), 0.45);
  background: rgba(var(--color-primary-rgb), 0.14);
  color: var(--color-primary-text);
}
.cal {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
}
.cal-weekdays,
.cal-week {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0.28rem;
}
.cal-mode-week {
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.cal-mode-week::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
.cal-mode-week .cal-weekdays,
.cal-mode-week .cal-week {
  min-width: min(56rem, 100%);
}
.cal-weeks.is-week .cal-week,
.cal-weeks.is-day .cal-week {
  overflow-x: visible;
}
.cal-weeks.is-week .cal-week {
  min-width: min(56rem, 100%);
}
@media (min-width: 1280px) {
  .cal-mode-week .cal-weekdays,
  .cal-mode-week .cal-week,
  .cal-weeks.is-week .cal-week {
    min-width: 0;
  }
}
.cal-weeks.is-day .cal-week {
  grid-template-columns: 1fr;
  min-width: 0;
}
.cal-weekdays span {
  font-size: var(--text-kicker);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-dim);
  text-align: center;
}
.cal-weeks {
  display: grid;
  gap: 0.28rem;
}
.cal-day {
  min-width: 0;
  min-height: 7.25rem;
  padding: 0.4rem 0.4rem 0.5rem;
  border: 1px solid var(--border-subtle);
  border-radius: 0.55rem;
  background: color-mix(in srgb, var(--bg-surface-elevated, var(--bg-card)) 82%, transparent);
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
}
.cal-day:hover {
  border-color: var(--border-hover);
}
.cal-day::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
.cal-weeks.is-week .cal-day {
  min-height: clamp(6rem, calc(100cqh - 6.5rem), 22rem);
}
.cal-weeks.is-week .cal-num {
  display: none;
}
.cal-day.is-outside {
  opacity: 0.45;
}
.cal-day.is-today {
  border-color: color-mix(in srgb, var(--color-info) 70%, var(--border-subtle));
}
.cal-day.is-selected {
  border-color: var(--color-primary);
  box-shadow: inset 0 0 0 1px rgba(var(--color-primary-rgb), 0.55), 0 0 0 1px rgba(var(--color-primary-rgb), 0.2);
  background: color-mix(in srgb, rgba(var(--color-primary-rgb), 0.16) 55%, var(--bg-surface-elevated, var(--bg-card)));
}
.cal-num {
  font-size: var(--text-kicker);
  font-weight: 600;
  color: var(--text-muted);
}
.cal-day.is-today .cal-num {
  color: var(--color-info);
}
.cal-day.is-selected .cal-num {
  color: var(--color-primary-text);
}
.cal-events,
.cal-list ul {
  list-style: none;
  display: grid;
  gap: 0.28rem;
  margin: 0;
  padding: 0;
}
.cal-event {
  display: grid;
  gap: 0.05rem;
  padding: 0.28rem 0.35rem;
  border-radius: 0.35rem;
  background: color-mix(in srgb, var(--bg-input) 78%, transparent);
  min-width: 0;
  border-left: 3px solid var(--color-warning, #f59e0b);
}
.cal-event.is-have {
  border-left-color: var(--color-success, #10b981);
}
.cal-event-time {
  font-size: var(--text-kicker);
  font-family: var(--font-mono);
  color: var(--color-warning, #f59e0b);
}
.cal-event.is-have .cal-event-time {
  color: var(--color-success, #10b981);
}
.cal-event strong {
  font-size: var(--text-kicker);
  line-height: 1.2;
}
.cal-event-detail {
  font-size: var(--text-kicker);
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
.cal-event[data-kind='movie'] {
  background: color-mix(in srgb, var(--color-primary) 16%, var(--bg-input));
}
.cal-event-top,
.cal-row-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  min-width: 0;
}
.cal-event-top {
  flex-wrap: wrap;
  justify-content: space-between;
}
.cal-row-title strong {
  min-width: 0;
}
/* Series or movie: a small pill on calendar entries and, overlaid, on posters. */
.media-badge {
  flex: none;
  padding: 0 0.4rem;
  border-radius: 999px;
  font-size: 0.58rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  line-height: 1.6;
  text-transform: uppercase;
  color: var(--text-muted);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
}
.home-tile-art .media-badge {
  position: absolute;
  top: 0.45rem;
  right: 0.45rem;
  color: #fff;
  background: rgba(10, 12, 20, 0.62);
  border-color: rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(6px);
  pointer-events: none;
}
/* Calendar list rows: a day chip (accent for today), the title and its detail. */
.cal-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.6rem;
}
.home-card li.cal-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}
.cal-chip {
  flex: 0 0 2.75rem;
  display: grid;
  text-align: center;
  padding: 0.3rem 0;
  border-radius: 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  font-size: var(--text-kicker);
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: 0.04em;
}
.cal-chip strong {
  font-size: var(--text-body);
}
.cal-row.is-today .cal-chip {
  background: var(--color-primary-button);
  border-color: transparent;
  color: var(--color-primary-contrast);
}
.cal-row-body {
  display: grid;
  min-width: 0;
}
.cal-row-body strong {
  font-size: var(--text-body);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cal-row-meta {
  font-size: var(--text-kicker);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cal-row.is-have .cal-row-meta {
  color: var(--color-success-fg);
}
/* Cards: glass panels with a bold head, compact controls and lists with progress bars. */
.home-card {
  --rail-chrome: 7.9rem;
  height: 100%;
  overflow: hidden;
  container-type: size;
  padding: 1.35rem 1.35rem 1.3rem;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}
.home-card > :is(.home-rail-head, .home-widget-head, .cal-head) {
  flex: 0 0 auto;
}
.home-card-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  overflow-y: auto;
  padding-right: 0.35rem;
  scrollbar-width: thin;
}
.home-card-trending {
  --rail-chrome: 12.4rem;
}
.home-card .cal-head {
  margin: 0;
  gap: 0.4rem 0.6rem;
}
.home-card .cal-head h3 {
  font-size: var(--text-strong);
}
.home-card .ui-input {
  width: auto;
}
.home-card .cal-select {
  min-width: 0;
}
.home-card-stat {
  font-size: var(--text-kicker);
  font-weight: 700;
  color: var(--color-success-fg);
}
.home-widget-head .home-sort {
  margin-left: auto;
}
.home-widget-head .home-sort + .home-pause {
  margin-left: 0;
}
.home-pause {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: auto;
}
.home-card ul {
  list-style: none;
  display: grid;
  gap: 0.7rem;
  margin: 0;
  padding: 0;
}
.home-card li {
  display: grid;
  gap: 0.3rem;
  min-width: 0;
}
@container (min-width: 760px) {
  .home-card-downloads .home-card-body > ul {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 1.5rem;
  }
}
/* A small Downloading card shows how many are moving, how fast, and how far along together. */
.home-dl-compact {
  display: none;
  flex: 1 1 auto;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.4rem;
  min-height: 0;
}
.home-dl-count {
  font-size: 2.6rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
}
.home-dl-count small {
  margin-left: 0.4rem;
  font-size: var(--text-body);
  font-weight: 600;
  letter-spacing: 0;
  color: var(--text-muted);
}
@container (max-width: 260px) or (max-height: 220px) {
  .home-card-downloads .home-dl-compact {
    display: flex;
  }
  .home-card-downloads .home-dl-compact + .home-card-body,
  .home-card-downloads :is(.home-sort, .home-pause:not(.is-paused), .home-card-stat) {
    display: none;
  }
}
.home-dl-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
}
.home-dl-row strong {
  font-size: var(--text-body);
  font-weight: 700;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.home-dl-pct {
  flex: 0 0 auto;
  font-size: var(--text-kicker);
  color: var(--text-muted);
}
.home-dl-meta {
  font-size: var(--text-kicker);
}
.home-when {
  font-size: var(--text-kicker);
  color: var(--color-info);
  font-family: var(--font-mono);
}
.home-bar {
  display: block;
  height: 6px;
  border-radius: 999px;
  background: var(--switch-track);
  overflow: hidden;
}
.home-bar span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--color-primary);
}
.home-speed {
  color: var(--color-info);
  font-variant-numeric: tabular-nums;
}
.home-stuck {
  margin-top: 0;
}
.home-stuck summary {
  cursor: pointer;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-muted);
}
.home-stuck-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
  margin: 0.6rem 0;
  font-size: var(--text-body);
}
.home-card .home-stuck-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}
.home-stuck-title {
  display: grid;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: var(--text-body);
}
.home-stuck-remove {
  flex: 0 0 auto;
  display: inline-flex;
  padding: 0.4rem;
  border: 1px solid var(--border-subtle);
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.home-stuck-remove:hover:not(:disabled) {
  color: var(--color-danger-fg);
  border-color: var(--color-danger);
}
.home-stuck-remove:disabled {
  opacity: 0.5;
  cursor: default;
}
.home-stuck-remove svg {
  width: 16px;
  height: 16px;
}
.home-debug-panel {
  padding: 1rem 1.15rem;
}
.home-debug {
  list-style: none;
  display: grid;
  gap: 0.4rem;
  margin-top: 0.65rem;
}
.home-debug li {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  font-size: var(--text-body);
  color: var(--text-muted);
}
.home-debug-state {
  flex: 0 0 auto;
  font-family: var(--font-mono);
  font-size: var(--text-kicker);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--bg-input);
}
.home-debug-state[data-state='ok'] {
  color: var(--color-success, #3dd68c);
}
.home-debug-state[data-state='error'] {
  color: var(--color-danger, #ff6b6b);
}
.home-debug-state[data-state='empty'] {
  color: var(--color-warning, #e6b84d);
}
/* Status widgets, after GlassHome: a title with a one-line status, big light figures, quiet pills and charts. */
.gh-head {
  flex: 0 0 auto;
  display: grid;
  gap: 0.15rem;
}
.gh-status {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: var(--text-body);
  color: var(--text-muted);
}
.gh-status::before {
  content: '';
  flex: 0 0 auto;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--dot, var(--text-dim));
}
.gh-status.is-idle::before {
  display: none;
}
.gh-figure {
  display: grid;
  gap: 0.2rem;
  min-width: 0;
}
.gh-big {
  font-size: clamp(2.2rem, 12cqw, 3.6rem);
  font-weight: 300;
  letter-spacing: -0.045em;
  line-height: 1;
  color: var(--text-heading);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.gh-big small {
  margin-left: 0.2em;
  font-size: 0.32em;
  font-weight: 500;
  letter-spacing: 0;
  vertical-align: top;
  color: var(--text-muted);
}
.gh-label {
  font-size: var(--text-body);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gh-pills {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  min-width: 0;
}
.gh-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  max-width: 100%;
  padding: 0.38rem 0.75rem;
  border-radius: 999px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  font-size: var(--text-body);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gh-pill svg {
  flex: 0 0 auto;
  width: 0.95rem;
  height: 0.95rem;
  opacity: 0.75;
}
.gh-meter {
  display: block;
  height: 6px;
  border-radius: 999px;
  background: var(--switch-track);
  overflow: hidden;
}
.gh-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--text-main);
  opacity: 0.85;
}
.gh-meter.is-warn span {
  background: var(--color-warning);
  opacity: 1;
}
.gh-meter.is-crit span {
  background: var(--color-danger);
  opacity: 1;
}
/* Now playing: the poster fills the card, the title sits on it. */
.home-card-playing.has-art {
  color: #fff;
}
.home-card-playing > .np-art,
.home-card-playing > .np-shade {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.home-card-playing > .np-art {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 22%;
}
.home-card-playing > .np-shade {
  background: linear-gradient(180deg, rgb(0 0 0 / 0.35) 0%, rgb(0 0 0 / 0) 30%, rgb(0 0 0 / 0.25) 50%, rgb(0 0 0 / 0.8) 100%);
}
.np-top {
  flex: 0 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.has-art .gh-pill {
  color: #fff;
  background: rgb(0 0 0 / 0.35);
  border-color: rgb(255 255 255 / 0.18);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.np-bottom {
  margin-top: auto;
  display: grid;
  gap: 0.35rem;
  min-width: 0;
  color: inherit;
  text-decoration: none;
}
.np-title {
  font-size: clamp(1.25rem, 7cqw, 2rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.np-sub {
  font-size: var(--text-kicker);
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  opacity: 0.8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.np-progress {
  display: block;
  height: 4px;
  margin-top: 0.35rem;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.25);
  overflow: hidden;
}
.home-card-playing:not(.has-art) .np-progress {
  background: var(--switch-track);
}
.np-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: currentColor;
}
.np-foot {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: var(--text-kicker);
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}
.np-foot span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@container (max-height: 200px) {
  .np-sub,
  .np-foot span:first-child {
    display: none;
  }
}
/* Storage: free space as the big figure, a meter, and a pill per disk. */
.home-card-storage .gh-meter {
  margin-top: auto;
}
@container (max-height: 200px) {
  .home-card-storage .gh-pills {
    display: none;
  }
}
@container (max-width: 260px) {
  .home-card-storage .gh-pills,
  .home-card-storage .gh-figure .gh-label {
    display: none;
  }
}
/* Server: CPU and memory as figures, the last few minutes of network use as an area chart, details as pills. */
.sv-figures {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}
/* Three figures side by side leave no room for the memory in bytes until the card is wide. */
@container (max-width: 560px) {
  .sv-mem-bytes {
    display: none;
  }
}
/* Network use is drawn behind the card along its bottom edge, so even a two-row card shows it.
   Download blue, upload pink: categorical slots of the reference palette, validated on both card surfaces. */
.home-card-server {
  --series-down: #3987e5;
  --series-up: #d55181;
}
:global([data-theme='light'] .home-card-server) {
  --series-down: #2a78d6;
  --series-up: #e87ba4;
}
.sv-key {
  color: var(--series-down);
  font-weight: 700;
}
.sv-key.is-up {
  color: var(--series-up);
}
.home-card-server > .sv-chart {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 0;
  height: 46%;
  color: var(--text-main);
}
/* The figures and pills sit on the chart; let the pointer through to it for the crosshair. */
.home-card-server > :not(.sv-chart) {
  pointer-events: none;
}
.sv-pills {
  margin-top: auto;
}
.sv-spark {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
  cursor: crosshair;
}
.sv-line {
  fill: none;
  stroke: var(--series-down);
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
  opacity: 0.85;
}
.sv-line.is-up {
  stroke: var(--series-up);
}
.sv-cross {
  stroke: var(--border-strong);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.sv-end {
  position: absolute;
  width: 0.7rem;
  height: 0.7rem;
  margin: -0.35rem 0 0 -0.35rem;
  border-radius: 50%;
  border: 2px solid var(--series-down);
  background: var(--bg-card);
  pointer-events: none;
}
.sv-end.is-up {
  border-color: var(--series-up);
}
@container (max-width: 300px) {
  .sv-pills,
  .sv-net-figure,
  .home-card-server > .sv-chart {
    display: none;
  }
  .sv-figures {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }
}
/* Needs attention: a timeline; each row opens where to fix it. */
.at-timeline {
  position: relative;
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.15rem;
}
.at-timeline::before {
  content: '';
  position: absolute;
  left: 0.3rem;
  top: 0.9rem;
  bottom: 0.9rem;
  width: 1px;
  background: var(--border-strong);
}
.home-card .at-timeline li {
  display: block;
}
.at-item {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  padding: 0.45rem 0;
  color: inherit;
  text-decoration: none;
}
.at-item:hover strong {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.at-dot {
  position: relative;
  flex: 0 0 auto;
  width: 0.62rem;
  height: 0.62rem;
  margin-top: 0.3rem;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 0 3px var(--bg-card);
}
.at-item.is-problem .at-dot {
  background: var(--color-danger);
}
.at-item.is-warning .at-dot {
  background: var(--color-warning);
}
.at-text {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 0.1rem;
}
.at-text strong {
  font-size: var(--text-body);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.at-kind {
  flex: 0 0 auto;
  font-size: var(--text-body);
  color: var(--text-muted);
}
.gh-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.35rem;
}
.gh-empty .gh-big {
  font-size: clamp(1.8rem, 10cqw, 2.8rem);
}
@container (max-width: 300px) {
  .at-kind {
    display: none;
  }
}
</style>
