<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { appIconSrc } from './appIcons.js'
import { apiError, apiRequest, readJson } from './api.js'
import { appWebUrl } from './appWebUrl.js'
import { homeSnapshotCache, partialRetryDelay } from './homeSnapshotCache.js'
import { BP_ORDER, BREAKPOINTS, GRID_IDS, WIDGETS, collapseEmptyRows, dockHidden, firstFree, fitItem, homeEditing, homeGrid, homeGridSaves, layoutFor, resolve, restoreGrid, saveGridLayout, viewportBp } from './homeLayout.js'
import UiSelect from './UiSelect.vue'
import { useHomeCalendar } from './composables/useHomeCalendar.js'
import HomeEditBar from './HomeEditBar.vue'
import HomeGrid from './HomeGrid.vue'
import HomePoster from './HomePoster.vue'
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
  firstName: { type: String, default: '' },
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
  return Object.entries(counts).map(([label, n]) => `${n} ${t(label)}`).join(' · ')
})
const stuckItems = computed(() =>
  downloadPause.value.paused ? [] : snapshot.value.downloads.filter((item) => item.status in STUCK_STATUSES),
)
const removeBusy = ref(new Set())

/** Sonarr/Radarr blocklist a removed download and search for another release; the rest leave the client. */
async function removeDownloads(items, confirmFirst = false) {
  const list = items.filter((item) => item.download_id)
  if (!list.length) return
  if (confirmFirst && !window.confirm(t('Remove {count} stuck downloads? Sonarr and Radarr search for another release.', { count: list.length }))) return
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
const requestsWindowStart = ref(0)
const REQUESTS_WINDOW_SIZE = 20
const trendingFilter = ref('all')
let poll = null
let downloadsPoll = null
let statusPoll = null
let otherPoll = null
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
    other: true,
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
  if (event.key !== 'Escape' || event.defaultPrevented) return
  if (requestChoice.value) {
    requestChoice.value = null
    return
  }
  if (trailerPlayer.value) {
    closeTrailer()
    return
  }
  if (trendingDetail.value) {
    trendingDetail.value = null
    return
  }
  if (searchOpen.value) {
    closeSearch()
    return
  }
  if (editing.value && !sheet.value) editing.value = false
}

const todayLabel = computed(() => new Date().toLocaleDateString(i18nLocale(), { weekday: 'long', day: 'numeric', month: 'long' }))
const greeting = computed(() => {
  const hour = new Date().getHours()
  const part = t(hour < 6 ? 'Good night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening')
  const who = props.firstName.trim() || props.username
  return who ? `${part}, ${who}.` : `${part}.`
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
    label: t('Network over the last {minutes} min: download peak {download}, upload peak {upload}', { minutes: Math.round(span / 60) || 1, download: peak('rxRate'), upload: peak('txRate') }),
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

/** Other downloads: what the download clients got besides films and series, asked for only while the widget is on Home. */
const otherDownloads = ref([])
const otherLoaded = ref(false)
const otherWanted = computed(() => gridLayout.value.some((item) => item.id === 'other'))
/** Per kind of download: its name and the outline icon it gets (24 × 24, stroked). */
const OTHER_KINDS = {
  music: ['Music', 'M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0a3 3 0 0 1 6 0M21 16a3 3 0 1 1-6 0a3 3 0 0 1 6 0'],
  book: ['Book', 'M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2zM22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z'],
  game: ['Game', 'M6 11h4M8 9v4M15 12h.01M18 10h.01M17.32 5H6.68a4 4 0 0 0-3.98 3.59l-.7 6.98A3 3 0 0 0 5 19c1 0 1.6-.5 2.1-1.1L8.5 16h7l1.4 1.9c.5.6 1.1 1.1 2.1 1.1a3 3 0 0 0 3-3.43l-.7-6.98A4 4 0 0 0 17.32 5z'],
  disc: ['Disc image', 'M22 12a10 10 0 1 1-20 0a10 10 0 0 1 20 0M14 12a2 2 0 1 1-4 0a2 2 0 0 1 4 0'],
  app: ['Software', 'M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8'],
  archive: ['Archive', 'M3 4h18v4H3zM5 8v12h14V8M10 12h4'],
  video: ['Video', 'M3 5h18v14H3zM7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4'],
  file: ['File', 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6'],
}

function otherKind(item) {
  return OTHER_KINDS[item.kind] || OTHER_KINDS.file
}

function otherMeta(item) {
  const when = item.done && item.when ? new Date(item.when * 1000).toLocaleDateString(i18nLocale(), { day: 'numeric', month: 'short' }) : ''
  return [item.size ? formatBytes(item.size) : '', item.source, item.done ? when : item.status].filter(Boolean).join(' · ')
}

async function loadOther() {
  if (!otherWanted.value) return
  try {
    const res = await apiRequest('/api/homepage/other-downloads')
    if (!res.ok) return
    otherDownloads.value = (await readJson(res)).items || []
    otherLoaded.value = true
  } catch (_) {
    /* keep the last list */
  }
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
  if (days) return t(days === 1 ? '{count} day' : '{count} days', { count: days })
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
  return dt.toLocaleDateString(i18nLocale(), { weekday: 'short' }).replace('.', '').toUpperCase()
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
        label: t(CATEGORY_LABELS[id] || id),
        apps: [],
      })
    }
    groups.get(id).apps.push({
      ...app,
      ...(['failed', 'rollback_failed'].includes(job?.status) ? { state: 'unhealthy', state_label: t(job.status === 'rollback_failed' ? 'Recovery incomplete' : 'Setup failed'), sick: true } : {}),
      ...(busy ? { state: job.status, state_label: t({ queued: 'Queued', installing: 'Installing', configuring: 'Configuring', updating: 'Updating' }[job.status]) } : {}),
      progress_message: job && !busy && !['failed', 'rollback_failed'].includes(job.status) ? '' : job?.message ?? app.progress_message,
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
const requestsWindowItems = computed(() => requestItems.value.slice(
  requestsWindowStart.value, requestsWindowStart.value + REQUESTS_WINDOW_SIZE,
))
let shiftingRequests = false
async function scrollRequests() {
  const rail = requestsRail.value
  if (!rail || shiftingRequests || rail.children.length < 2) return
  const pitch = rail.children[1].offsetLeft - rail.children[0].offsetLeft
  if (pitch <= 0) return
  const start = requestsWindowStart.value
  let shift = 0
  if (rail.scrollLeft <= 1 && start > 0) {
    shift = -Math.min(10, start)
  } else if (rail.scrollWidth - rail.scrollLeft - rail.clientWidth <= pitch) {
    shift = Math.min(10, Math.floor(rail.scrollLeft / pitch),
      Math.max(0, requestItems.value.length - REQUESTS_WINDOW_SIZE - start))
  }
  if (!shift) return
  shiftingRequests = true
  const left = rail.scrollLeft
  requestsWindowStart.value += shift
  await nextTick()
  // Keep the same titles under the user's finger while recycling offscreen tiles.
  rail.scrollLeft = left - shift * pitch
  shiftingRequests = false
}
watch(requestsFilter, async () => {
  requestsWindowStart.value = 0
  await nextTick()
  if (requestsRail.value) requestsRail.value.scrollLeft = 0
})
watch(() => requestItems.value.length, count => {
  requestsWindowStart.value = Math.min(requestsWindowStart.value, Math.max(0, count - REQUESTS_WINDOW_SIZE))
})
// Pages 2+ of Seerr's trending list, appended as the rail scrolls; the snapshot keeps page 1 fresh.
const trendingMore = ref([])
const trendingDetail = ref(null)
const trailerPlayer = ref(null)
const trendingItems = computed(() => {
  const seen = new Set()
  return [...(snapshot.value.trending || []), ...trendingMore.value]
    .filter((item) => {
      const key = `${item.mediaType}-${item.mediaId}`
      if (seen.has(key)) return false
      seen.add(key)
      return mediaTypeMatches(item, trendingFilter.value) &&
        !isHiddenTrendingStatus(item)
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
  if (status === 'available') return { cls: 'is-available', label: t('Available') }
  if (status === 'partial') return { cls: 'is-partial', label: t('Partially available') }
  if (status === 'requested' || status === 'monitored') return { cls: 'is-requested', label: t('Requested') }
  return { cls: 'is-missing', label: t('Not available') }
}

function isHiddenTrendingStatus(item) {
  return ['available', 'partial', 'requested', 'monitored', 'deleted'].includes(String(item?.status || ''))
}

function trendingStatusDot(item) {
  const status = String(item?.status || '')
  if (status === 'deleted') return { cls: 'is-deleted', label: t('Deleted') }
  if (!['available', 'requested', 'monitored'].includes(status)) return null
  return requestStatusDot(item)
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
  return names.length ? t('Waiting for {names}…', { names: names.join(t(' and ')) }) : ''
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
      snapshotError.value = t('Home API HTTP {status}', { status: res.status })
    }
  } catch (err) {
    snapshotError.value = err?.message || t('Home snapshot failed')
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
    searchError.value = err?.message || t('Search failed')
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
const searchRoot = ref(null)

function closeSearch() {
  clearTimeout(searchTimer)
  searchGen += 1
  searching.value = false
  results.value = []
  searchedFor.value = ''
  searchError.value = ''
  notice.value = ''
}

function clearSearchQuery() {
  query.value = ''
  closeSearch()
}

/** Results float over Home; a click outside the bar (and its provider menu) dismisses them. */
function onSearchPointerDown(event) {
  if (!searchOpen.value) return
  const target = event.target
  if (!(target instanceof Element)) return
  if (searchRoot.value?.contains(target)) return
  if (target.closest('.ui-select-menu, .modal-backdrop, .modal-content')) return
  closeSearch()
}

const STATUS_LABELS = {
  available: 'Available',
  partial: 'Partly available',
  requested: 'Requested',
  monitored: 'In library, not downloaded yet',
  missing: 'Not in library',
}

function statusLabel(item) {
  const label = STATUS_LABELS[item?.status]
  return label ? t(label) : ''
}

function closeTrending() {
  closeTrailer()
  trendingDetail.value = null
}

function closeTrailer() {
  trailerPlayer.value = null
}

/** Pull a YouTube id from a watch/share/embed URL so the Trailer button can open an in-app player. */
function youtubeIdFromUrl(url) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    const host = parsed.hostname.replace(/^www\./, '').toLowerCase()
    let ident = ''
    if (host === 'youtu.be') {
      ident = parsed.pathname.replace(/^\/+/, '').split('/')[0] || ''
    } else if (host === 'youtube.com' || host === 'm.youtube.com' || host === 'youtube-nocookie.com') {
      ident = parsed.searchParams.get('v') || ''
      if (!ident && parsed.pathname.startsWith('/embed/')) {
        ident = parsed.pathname.split('/').filter(Boolean)[1] || ''
      }
    }
    return /^[A-Za-z0-9_-]{6,32}$/.test(ident) ? ident : ''
  } catch {
    return ''
  }
}

function openTrailer(item) {
  const ident = youtubeIdFromUrl(item?.trailer || trendingDetail.value?.data?.trailer)
  if (!ident) return
  trailerPlayer.value = {
    title: item?.title || trendingDetail.value?.data?.title || trendingDetail.value?.item?.title || t('Trailer'),
    embedUrl: `https://www.youtube-nocookie.com/embed/${ident}?autoplay=1&rel=0`,
  }
}

function trendingSeed(item) {
  return {
    title: item.title,
    overview: item.overview || '',
    year: item.detail || '',
    poster: item.poster || '',
    voteAverage: item.voteAverage ?? null,
    imdb: null,
    rtCritics: null,
    rtAudience: null,
    trailer: '',
    url: item.url || '',
    status: item.status,
    can_request: item.can_request,
  }
}

async function openTrending(item) {
  if (!item?.mediaId) return
  const key = `${item.mediaType}:${item.mediaId}`
  trendingDetail.value = { key, item, loading: !item.overview, pending: true, error: '', data: trendingSeed(item) }
  try {
    const res = await apiRequest(
      `/api/homepage/title?mediaType=${encodeURIComponent(item.mediaType || '')}&mediaId=${encodeURIComponent(item.mediaId)}`,
      { signal: AbortSignal.timeout(12000) },
    )
    const data = await readJson(res)
    if (trendingDetail.value?.key !== key) return
    if (!res.ok) {
      trendingDetail.value = {
        ...trendingDetail.value,
        loading: false,
        pending: false,
        error: trendingDetail.value.data?.overview ? '' : apiError(data, t('Could not load this title from Seerr.')),
      }
      return
    }
    const next = { ...trendingDetail.value.data }
    for (const [field, value] of Object.entries(data || {})) {
      if (value == null || value === '') continue
      next[field] = value
    }
    trendingDetail.value = { ...trendingDetail.value, loading: false, pending: false, error: '', data: next }
  } catch (err) {
    if (trendingDetail.value?.key !== key) return
    trendingDetail.value = {
      ...trendingDetail.value,
      loading: false,
      pending: false,
      error: trendingDetail.value.data?.overview ? '' : (err.message || t('Could not load this title from Seerr.')),
    }
  }
}

const trendingRatings = computed(() => {
  const data = trendingDetail.value?.data
  if (!data) return []
  const rows = []
  if (data.voteAverage != null) rows.push({ label: 'TMDB', value: Number(data.voteAverage).toFixed(1) })
  if (data.imdb != null) rows.push({ label: 'IMDb', value: Number(data.imdb).toFixed(1) })
  if (data.rtCritics != null) rows.push({ label: t('Critics'), value: `${data.rtCritics}%` })
  if (data.rtAudience != null) rows.push({ label: t('Audience'), value: `${data.rtAudience}%` })
  return rows
})

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
    notice.value = err.message || t('Request failed.')
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
      notice.value = data.detail || t('Request submitted.')
      item.status = 'requested'
      item.can_request = false
      trendingMore.value = trendingMore.value.map((t) =>
        resultKey(t) === key ? { ...t, status: 'requested', can_request: false } : t,
      )
      loadSnapshot(true)
      return true
    }
    notice.value = apiError(data, t('Request failed.'))
    return false
  } catch (err) {
    notice.value = err.message || t('Request failed.')
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
      notice.value = data.detail || t('Sent to the download client.')
      item.status = 'requested'
      item.can_request = false
      return
    }
    notice.value = apiError(data, t('Download failed.'))
  } catch (err) {
    notice.value = err.message || t('Download failed.')
  } finally {
    requestBusy.value = ''
  }
}

const recentRail = ref(null)
const requestsRail = ref(null)
const trendingRail = ref(null)


// Phones start on today; larger screens choose week or list from the card width.
const calendarPhone = computed(() => activeBp.value === 'phone')
const calendarWide = computed(() => {
  const item = gridLayout.value.find((entry) => entry.id === 'calendar')
  return !!item && activeBp.value !== 'phone' && item.w * 12 >= 7 * BREAKPOINTS[activeBp.value].cols
})
const {
  dayKey,
  formatEventTime,
  weekdayLabels,
  calView,
  calFilter,
  selectedDayKey,
  setCalView,
  selectCalDay,
  syncCalViewToViewport,
  eventKind,
  calendarTarget,
  calendarLinkTitle,
  openCalendarItem,
  calendarRangeLabel,
  calendarDays,
  calendarWeeks,
  calendarList,
  calOnToday,
  shiftCalendar,
  goToday
} = useHomeCalendar({ snapshot, calendarWide, calendarPhone })

watch(statusWanted, (wanted) => {
  if (wanted) loadStatus()
})
watch(otherWanted, (wanted) => {
  if (wanted) loadOther()
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
    const error = vpn.last_error ? ` ${t('Last VPN error: {message}', { message: vpn.last_error })}` : ''
  return t('VPN is on but not connected yet. {names} will remain stopped until it connects.', { names: names.join(', ') }) + error
})

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

const MEDIA_LABELS = { tv: 'Series', movie: 'Movie' }

// Requests, trending and recent carry mediaType; calendar entries only kind and source.
function mediaKind(item) {
  const kind = String(item?.mediaType || item?.kind || item?.source || '').toLowerCase()
  if (['tv', 'series', 'episode', 'season', 'sonarr'].includes(kind)) return 'tv'
  if (['movie', 'radarr'].includes(kind)) return 'movie'
  return ''
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
  document.addEventListener('pointerdown', onSearchPointerDown)
  loadSnapshot()
  // Defer live queues so first paint is the launcher snapshot.
  setTimeout(() => loadDownloads(), 750)
  poll = startGuardedInterval(loadSnapshot, 20000)
  downloadsPoll = startGuardedInterval(loadDownloads, 8000)
  installPoll = startGuardedInterval(loadInstallJobs, 3000, { immediate: true })
  statusPoll = startGuardedInterval(loadStatus, 10000, { immediate: true })
  // History changes slowly, and NZBGet sends all of it.
  otherPoll = startGuardedInterval(loadOther, 60000, { immediate: true })
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
onUnmounted(() => {
  homeEditing.value = false
  dockObserver?.disconnect()
  window.removeEventListener('resize', syncCalViewToViewport)
  window.removeEventListener(HOMEPAGE_WIDGET_DEBUG_EVENT, onWidgetDebugEvent)
  window.removeEventListener('keydown', onArrangeKey)
  document.removeEventListener('pointerdown', onSearchPointerDown)
  clearTimeout(toastTimer)
  if (poll) poll()
  if (downloadsPoll) downloadsPoll()
  if (installPoll) installPoll()
  if (statusPoll) statusPoll()
  if (otherPoll) otherPoll()
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
      <a href="#/settings/vpn" class="home-notice-link">{{ $t('Open Settings → VPN') }}</a>
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
      <section class="home-hero glass-card">
        <span class="home-hero-date">{{ todayLabel }}</span>
        <h2 class="home-hero-title">{{ greeting }}</h2>
        <p class="home-hero-sub">{{ heroSummary }}</p>
      </section>
      </template>

      <template #searchbar>
      <section ref="searchRoot" class="home-search glass-card">
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
          <button
            v-if="query.trim()"
            type="button"
            class="home-search-clear"
            :aria-label="$t('Clear search')"
            :title="$t('Clear search')"
            @click="clearSearchQuery"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
          <button type="submit" class="ui-btn ui-btn-primary home-search-btn" :aria-label="$t('Search')" :disabled="searching">
            <svg class="home-search-go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
            <span>{{ $t('Search') }}</span>
          </button>
        </form>
        <div v-if="searchOpen" class="home-hero-results glass-card" :class="searchAnchor">
          <div class="home-results-scroll">
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
                <img v-if="item.poster" :src="item.poster" loading="lazy" decoding="async" alt="" class="home-poster" />
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
                <HomePoster v-if="item.poster" :src="item.poster" class="home-tile-poster" />
                <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                <span v-if="mediaKind(item)" class="media-badge">{{ $t(MEDIA_LABELS[mediaKind(item)]) }}</span>
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
          <div v-if="requestItems.length" ref="requestsRail" class="home-rail home-requests-rail" @scroll.passive="scrollRequests">
            <a
              v-for="(item, idx) in requestsWindowItems"
              :key="`${requestsWindowStart + idx}-${item.mediaType}-${item.mediaId || item.title}`"
              class="home-tile"
              :href="item.url || seerrHomeUrl || undefined"
              :target="item.url || seerrHomeUrl ? '_blank' : undefined"
              rel="noopener noreferrer"
              @click="(item.url || seerrHomeUrl) && openApp($event, 'seerr', item.url || seerrHomeUrl)"
            >
              <span class="home-tile-art">
                <HomePoster v-if="item.poster" :src="item.poster" class="home-tile-poster" />
                <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                <span class="home-status-dot" :class="requestStatusDot(item).cls" :title="requestStatusDot(item).label" role="img" :aria-label="requestStatusDot(item).label"></span>
                <span v-if="mediaKind(item)" class="media-badge">{{ $t(MEDIA_LABELS[mediaKind(item)]) }}</span>
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
          <div class="home-rail-head home-trending-head">
            <h3>{{ $t('Trending') }}</h3>
            <div class="home-rail-tools home-trending-tools">
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
              <button
                type="button"
                class="home-tile-link"
                :aria-haspopup="item.mediaId ? 'dialog' : undefined"
                @click="openTrending(item)"
              >
                <span class="home-tile-art">
                  <HomePoster v-if="item.poster" :src="item.poster" class="home-tile-poster" />
                  <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                  <span
                    v-if="trendingStatusDot(item)"
                    class="home-status-dot"
                    :class="trendingStatusDot(item).cls"
                    :title="trendingStatusDot(item).label"
                    role="img"
                    :aria-label="trendingStatusDot(item).label"
                  ></span>
                  <span v-if="mediaKind(item)" class="media-badge">{{ $t(MEDIA_LABELS[mediaKind(item)]) }}</span>
                </span>
                <span class="home-tile-title">{{ item.title }}</span>
                <span v-if="item.detail" class="home-tile-meta">{{ item.detail }}</span>
                <span v-if="statusLabel(item)" class="home-tile-meta">{{ statusLabel(item) }}</span>
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
          <p v-else class="home-muted">{{ $t(snapshot.seerr?.available ? 'No trending titles right now.' : 'Trending titles appear when Seerr is running.') }}</p>
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
              <li v-for="(row, idx) in calendarList" :key="idx" class="cal-row" :data-kind="eventKind(row.item)" :data-source="row.item.source" :class="{ 'is-have': row.item.has_file, 'is-today': isToday(row.dt) }">
                <component
                  :is="calendarTarget(row.item) ? 'a' : 'div'"
                  class="cal-row-link"
                  :href="calendarTarget(row.item)?.url"
                  :target="calendarTarget(row.item) ? '_blank' : undefined"
                  rel="noopener noreferrer"
                  :title="calendarLinkTitle(row.item)"
                  @click="openCalendarItem($event, row.item)"
                >
                  <span class="cal-chip" aria-hidden="true"><span>{{ chipDay(row.dt) }}</span><strong>{{ row.dt.getDate() }}</strong></span>
                  <span class="cal-row-body">
                    <span class="cal-row-title">
                      <strong>{{ row.item.title }}</strong>
                      <span v-if="mediaKind(row.item)" class="media-badge">{{ $t(MEDIA_LABELS[mediaKind(row.item)]) }}</span>
                    </span>
                    <span class="cal-row-meta">{{ [row.item.detail, formatEventTime(row.item.when)].filter(Boolean).join(' · ') }}</span>
                  </span>
                </component>
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
                  @click="selectCalDay(day)"
                >
                  <span class="cal-num">{{ calView === 'week' ? day.weekday + ' ' + day.date : day.date }}</span>
                  <ul v-if="day.events.length" class="cal-events">
                    <li v-for="(item, idx) in day.events" :key="idx">
                      <component
                        :is="calendarTarget(item) ? 'a' : 'div'"
                        class="cal-event"
                        :data-kind="eventKind(item)"
                        :data-source="item.source"
                        :class="{ 'is-have': item.has_file }"
                        :href="calendarTarget(item)?.url"
                        :target="calendarTarget(item) ? '_blank' : undefined"
                        rel="noopener noreferrer"
                        :title="calendarLinkTitle(item)"
                        @click="openCalendarItem($event, item)"
                      >
                        <span class="cal-event-top">
                          <span class="cal-event-time">{{ formatEventTime(item.when) }}</span>
                          <span v-if="mediaKind(item)" class="media-badge">{{ $t(MEDIA_LABELS[mediaKind(item)]) }}</span>
                        </span>
                        <strong>{{ item.title }}</strong>
                        <span v-if="item.detail" class="cal-event-detail">{{ item.detail }}</span>
                      </component>
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
            <span class="home-muted home-dl-meta">{{ totalSpeed || $t('Waiting for speed') }}</span>
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
            <img v-if="nowItem.poster" class="np-art" :src="nowItem.poster" loading="lazy" decoding="async" alt="" aria-hidden="true" />
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
            <span v-else class="gh-status is-idle">{{ $t(statusLoaded ? 'No data folders found' : 'Checking disks…') }}</span>
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
                {{ $t('Up') }} {{ upFor(homeStatus.server.uptime_seconds) }}
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
                  <span class="at-kind">{{ $t(item.level === 'problem' ? 'Problem' : item.level === 'warning' ? 'Warning' : 'Update') }}</span>
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
      <template #other>
        <article class="home-card glass-card home-card-other">
          <div class="home-widget-head">
            <h3>{{ $t('Other downloads') }}</h3>
            <span v-if="otherDownloads.length" class="home-card-stat">{{ otherDownloads.length }}</span>
          </div>
          <div class="home-card-body">
            <ul v-if="otherDownloads.length" class="od-list">
              <li v-for="item in otherDownloads" :key="`${item.source}:${item.id}`" class="od-item">
                <span class="od-icon" :title="$t(otherKind(item)[0])">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" role="img" :aria-label="$t(otherKind(item)[0])">
                    <path :d="otherKind(item)[1]" />
                  </svg>
                </span>
                <span class="od-text">
                  <strong :title="item.title">{{ item.title }}</strong>
                  <span class="home-muted home-dl-meta">{{ otherMeta(item) }}</span>
                </span>
                <span v-if="!item.done" class="home-dl-pct font-mono">{{ item.progress }}%</span>
              </li>
            </ul>
            <p v-else-if="otherLoaded" class="home-muted">{{ $t('Nothing besides films and series.') }}</p>
            <p v-else class="home-muted">{{ $t('Checking the download clients…') }}</p>
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
      <div v-if="trendingDetail" class="modal-backdrop" @click.self="closeTrending">
        <div
          class="modal-content glass-popover home-title-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="home-title-heading"
        >
          <div class="home-title-head">
            <h3 id="home-title-heading">{{ trendingDetail.data?.title || trendingDetail.item.title }}</h3>
            <button type="button" class="ui-btn ui-btn-ghost" @click="closeTrending">{{ $t('Close') }}</button>
          </div>
          <p v-if="trendingDetail.error" class="home-notice home-notice-error">{{ trendingDetail.error }}</p>
          <div v-else class="home-title-body">
            <img v-if="trendingDetail.data?.poster || trendingDetail.item.poster" :src="trendingDetail.data?.poster || trendingDetail.item.poster" loading="lazy" decoding="async" alt="" class="home-title-poster" />
            <div>
              <p class="home-title-meta">
                <span v-if="mediaKind(trendingDetail.item)" class="media-badge">{{ $t(MEDIA_LABELS[mediaKind(trendingDetail.item)]) }}</span>
                <span>{{ trendingDetail.data?.year || trendingDetail.item.detail }}</span>
                <span v-if="statusLabel(trendingDetail.data || trendingDetail.item)">{{ statusLabel(trendingDetail.data || trendingDetail.item) }}</span>
              </p>
              <p v-if="trendingDetail.data?.overview" class="home-title-overview">{{ trendingDetail.data.overview }}</p>
              <p v-else-if="trendingDetail.loading" class="home-muted">{{ $t('Loading title…') }}</p>
              <p v-else class="home-title-overview home-muted">{{ $t('No overview from Seerr.') }}</p>
              <ul v-if="trendingRatings.length" class="home-title-ratings" :aria-label="$t('Ratings')">
                <li v-for="row in trendingRatings" :key="row.label"><span>{{ row.label }}</span> {{ row.value }}</li>
              </ul>
              <p v-else-if="!trendingDetail.pending" class="home-muted">{{ $t('Seerr did not include ratings.') }}</p>
            </div>
          </div>
          <div class="home-request-actions">
            <button
              v-if="trendingDetail.data?.trailer && youtubeIdFromUrl(trendingDetail.data.trailer)"
              type="button"
              class="ui-btn ui-btn-primary"
              @click="openTrailer(trendingDetail.data)"
            >{{ $t('Trailer') }}</button>
            <button
              v-if="trendingDetail.item.can_request"
              type="button"
              class="ui-btn"
              :disabled="requestBusy === resultKey(trendingDetail.item)"
              @click="requestTitle(trendingDetail.item)"
            >{{ requestBusy === resultKey(trendingDetail.item) ? $t('Requesting…') : $t('Request') }}</button>
            <button
              v-if="trendingDetail.data?.url"
              type="button"
              class="ui-btn ui-btn-ghost"
              @click="openApp($event, 'seerr', trendingDetail.data.url)"
            >{{ $t('Open in Seerr') }}</button>
          </div>
        </div>
      </div>
      <div v-if="trailerPlayer" class="modal-backdrop home-trailer-backdrop" @click.self="closeTrailer">
        <div
          class="modal-content glass-popover home-trailer-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="home-trailer-heading"
        >
          <div class="home-title-head">
            <h3 id="home-trailer-heading">{{ trailerPlayer.title }}</h3>
            <button type="button" class="ui-btn ui-btn-ghost" @click="closeTrailer">{{ $t('Close') }}</button>
          </div>
          <div class="home-trailer-frame">
            <iframe
              :src="trailerPlayer.embedUrl"
              :title="trailerPlayer.title"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowfullscreen
              referrerpolicy="strict-origin-when-cross-origin"
            ></iframe>
          </div>
        </div>
      </div>
      <div v-if="requestChoice && choiceServer" class="modal-backdrop" @click.self="requestChoice = null">
        <form class="modal-content glass-popover home-request-dialog" role="dialog" aria-modal="true" aria-labelledby="home-request-title" @submit.prevent="confirmRequest">
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

<style scoped src="./homepagePanel.css"></style>
