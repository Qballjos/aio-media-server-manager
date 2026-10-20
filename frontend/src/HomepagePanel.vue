<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { appIconSrc } from './appIcons.js'
import { apiError, apiRequest, readJson } from './api.js'
import { appWebUrl } from './appWebUrl.js'
import { homeSnapshotCache, partialRetryDelay } from './homeSnapshotCache.js'
import { BP_ORDER, BREAKPOINTS, GRID_IDS, WIDGETS, collapseEmptyRows, dockHidden, firstFree, fitItem, homeEditing, homeGrid, homeGridSaves, layoutFor, resolve, restoreGrid, saveGridLayout, viewportBp } from './homeLayout.js'
import HomeEditBar from './HomeEditBar.vue'
import HomeGrid from './HomeGrid.vue'
import HomeGridSheet from './HomeGridSheet.vue'
import { openApp } from './appOpen.js'
import { startGuardedInterval } from './pageVisible.js'
import { formatBytes, formatUptime } from './format.js'
import { addNetSample } from './netRates.js'
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
  if (!at) return 'Paused until you resume'
  return `Paused · resumes ${new Date(at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
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
    search: true,
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
  showToast(`${WIDGETS[id].label} removed from ${BREAKPOINTS[activeBp.value].label}`, () => restoreGrid(before))
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

const todayLabel = computed(() => new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' }))
const greeting = computed(() => {
  const hour = new Date().getHours()
  const part = hour < 6 ? 'Good night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const name = props.username ? `, ${props.username}` : ''
  return `${part}${name}.`
})
/** One line under the greeting: what is moving and what needs a look. */
const heroSummary = computed(() => {
  const parts = []
  const n = movingDownloads.value.length
  if (downloadPause.value.paused) parts.push(pausedLabel.value)
  else if (n) parts.push(`${n} download${n === 1 ? '' : 's'} on the way`)
  const sick = (snapshot.value.apps || []).filter((app) => app.sick).map((app) => app.display_name)
  if (sick.length) parts.push(`${sick.join(', ')} need${sick.length === 1 ? 's' : ''} a look`)
  if (!parts.length) parts.push(snapshot.value.apps?.length ? 'Everything is running.' : 'Nothing running yet.')
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
  const x = (point) => ((point.at - first) / span) * 100
  const y = (value) => 40 - (value / top) * 38
  const line = (key) => points.map((point, i) => `${i ? 'L' : 'M'}${x(point).toFixed(2)} ${y(point[key]).toFixed(2)}`).join(' ')
  const peak = (key) => formatSpeed(Math.max(...points.map((point) => point[key]))) || '0 B/s'
  return {
    down: line('rxRate'),
    up: line('txRate'),
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

function onNetHover(event) {
  const box = event.currentTarget.getBoundingClientRect()
  const points = netPoints.value
  if (points.length < 2 || !box.width) return
  const first = points[0].at
  const at = first + ((event.clientX - box.left) / box.width) * (points.at(-1).at - first)
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

function usageClass(percent) {
  return percent >= 90 ? 'is-full' : percent >= 80 ? 'is-high' : ''
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
    const busy = !app.sick && job && ['queued', 'installing', 'configuring'].includes(job.status)
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
    .filter((app) => app.sick || ['queued', 'installing', 'configuring'].includes(app.state))
    .map((app) => [`${app.display_name}: ${app.state_label || app.state}`, app.progress_message].filter(Boolean).join(' — ')),
)

const recentItems = computed(() =>
  (snapshot.value.recent || []).map((item) => withPublicUrls(item, item.source)),
)
const requestItems = computed(() =>
  (snapshot.value.requests || [])
    .filter((item) => mediaTypeMatches(item, requestsFilter.value))
    .map((item) => withPublicUrls(item, 'seerr')),
)
const trendingItems = computed(() =>
  (snapshot.value.trending || [])
    .filter((item) => mediaTypeMatches(item, trendingFilter.value))
    .map((item) => withPublicUrls(item, 'seerr')),
)
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
      !['queued', 'installing', 'configuring'].includes(job.status)
      && installJobs.value[job.name]?.status !== job.status
      && (
        ['queued', 'installing', 'configuring'].includes(installJobs.value[job.name]?.status)
        || snapshot.value.apps.some((app) => app.name === job.name && ['queued', 'installing', 'configuring'].includes(app.state))
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

async function runSearch() {
  const q = query.value.trim()
  if (q.length < 2) {
    results.value = []
    searchSeerr.value = false
    searchError.value = ''
    searchedFor.value = ''
    return
  }
  searching.value = true
  try {
    const res = await apiRequest(`/api/homepage/search?q=${encodeURIComponent(q)}`)
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
    results.value = []
    searchError.value = err?.message || 'Search failed'
  } finally {
    searchedFor.value = q
    searching.value = false
  }
}

/** Search results open over the widgets below the greeting instead of making it taller. */
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
  searchTimer = setTimeout(runSearch, 280)
}

async function requestTitle(item) {
  if (!item?.can_request) return
  const key = `${item.mediaType}-${item.mediaId}`
  requestBusy.value = key
  notice.value = ''
  try {
    const res = await apiRequest('/api/homepage/request', {
      method: 'POST',
      body: JSON.stringify({
        mediaType: item.mediaType,
        mediaId: item.mediaId,
        seasons: item.mediaType === 'tv' ? 'all' : undefined,
      }),
    })
    const data = await readJson(res)
    if (res.ok && data.ok !== false) {
      notice.value = data.detail || 'Request submitted.'
      item.status = 'requested'
      item.can_request = false
      loadSnapshot(true)
    } else {
      notice.value = apiError(data, 'Request failed.')
    }
  } catch (err) {
    notice.value = err.message || 'Request failed.'
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

function addDays(value, amount) {
  const dt = new Date(value)
  dt.setDate(dt.getDate() + amount)
  return dt
}

function eventKind(item) {
  return item?.kind || item?.source || ''
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
    byDay[key].sort((a, b) => (parseWhen(a.when)?.getTime() || 0) - (parseWhen(b.when)?.getTime() || 0))
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
      continue
    }
    out.push({ ...row, count: 1, last: row })
  }
  return out.map((row) => {
    if (row.count === 1) return row
    const code = (r) => String(r.item.detail || '').split(' ')[0]
    const span = code(row) && code(row.last) ? `${code(row)} – ${code(row.last)} · ` : ''
    return { ...row, item: { ...row.item, detail: `${span}${row.count} episodes` } }
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
    <div v-if="loading" class="home-skeleton" role="status" aria-label="Loading Home">
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
      <a href="#/settings/network" class="home-notice-link">Open Settings → Network</a>
    </p>

    <div v-if="!loading && !snapshot.apps.length" class="home-empty glass-card">
      <h3>Nothing to launch yet</h3>
      <p>Finish setup or install apps from Catalog. This page only lists installed applications with a WebUI.</p>
      <button type="button" class="ui-btn ui-btn-primary" @click="emit('manage')">Go to Catalog</button>
    </div>

    <template v-else-if="!loading">
      <Teleport to=".app-container" defer>
      <nav v-if="!dockHidden" ref="dockElement" class="home-dock is-floating glass-pill" aria-label="Apps">
        <div class="home-dock-row">
          <component
            :is="launcherOpen(app) ? 'a' : 'span'"
            v-for="app in dockApps"
            :key="app.name"
            class="home-app"
            :class="{ 'is-down': app.state !== 'running' && !app.sick, 'is-sick': app.sick, 'is-busy': ['queued', 'installing', 'configuring'].includes(app.state) }"
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
        :raise="searchOpen && !editing ? 'search' : ''"
        :bottom-inset="(dockHidden ? 0 : dockHeight) + (editing ? 96 : 24)"
        @change="onGridChange"
        @remove="removeWidget"
        @open="openWidget"
      >
      <template #search>
      <section class="home-hero">
        <span class="home-hero-date">{{ todayLabel }}</span>
        <h2 class="home-hero-title">{{ greeting }}</h2>
        <p class="home-hero-sub">{{ heroSummary }}</p>
        <form class="home-search-pill glass-pill" role="search" @submit.prevent="runSearch">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
          <label class="home-sr" for="home-search">Search</label>
          <input
            id="home-search"
            v-model="query"
            class="home-search-input"
            type="search"
            autocomplete="off"
            :placeholder="snapshot.seerr.available ? 'Search movies and TV to request' : 'Search Sonarr and Radarr'"
            @input="onQueryInput"
            @keydown.esc="closeSearch"
          />
          <button type="submit" class="ui-btn ui-btn-primary home-search-btn" :disabled="searching">Search</button>
        </form>
        <div v-if="searchOpen" class="home-hero-results glass-card">
        <button type="button" class="ui-btn ui-btn-ghost ui-btn-icon home-results-close" aria-label="Close search results" title="Close" @click="closeSearch">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <p v-if="notice" class="home-notice">{{ notice }}</p>
        <p v-if="searchError" class="home-notice home-notice-error">{{ searchError }}</p>
        <p v-else-if="!snapshot.seerr.available && !notice" class="home-muted">
          Install and start Seerr to request titles from this page.
        </p>
        <p v-if="searching" class="home-muted">Searching…</p>
        <p v-else-if="searchedFor && !results.length && !searchError" class="home-muted">
          No results for “{{ searchedFor }}”.
        </p>
        <ul v-if="results.length" class="home-results">
          <li v-for="item in results" :key="`${item.source}-${item.mediaType}-${item.mediaId}`" class="home-result">
            <img v-if="item.poster" :src="item.poster" alt="" class="home-poster" />
            <div class="home-result-body">
              <strong>{{ item.title }}</strong>
              <span>{{ item.mediaType === 'tv' ? 'TV' : 'Movie' }} {{ String(item.year || '').slice(0, 4) }}</span>
              <span v-if="statusLabel(item)" class="home-status" :class="`is-${item.status}`">{{ statusLabel(item) }}</span>
            </div>
            <button
              v-if="item.can_request && searchSeerr"
              type="button"
              class="ui-btn ui-btn-primary"
              :disabled="requestBusy === `${item.mediaType}-${item.mediaId}`"
              @click="requestTitle(item)"
            >
              {{ requestBusy === `${item.mediaType}-${item.mediaId}` ? 'Requesting…' : 'Get it now' }}
            </button>
          </li>
        </ul>
        </div>
      </section>
      </template>

      <template #recent>
        <article class="home-card glass-card">
          <div class="home-rail-head">
            <h3>Recently added</h3>
            <div class="home-rail-tools">
              <div v-if="snapshot.recent.length" class="home-rail-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Previous recently added" @click="scrollRail('recent', -1)">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Next recently added" @click="scrollRail('recent', 1)">›</button>
              </div>
            </div>
          </div>
          <div v-if="snapshot.recent.length" ref="recentRail" class="home-rail">
            <a
              v-for="(item, idx) in recentItems"
              :key="idx"
              class="home-tile"
              :href="item.url || undefined"
              :target="item.url ? '_blank' : undefined"
              rel="noopener noreferrer"
              @click="item.url && openApp($event, item.source || 'jellyfin', item.url)"
            >
              <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
              <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
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
          <p v-else class="home-muted">Nothing recently added.</p>
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
            <h3>Requests</h3>
            <div class="home-rail-tools">
              <div v-if="snapshot.requests.length" class="home-type-filter" role="group" aria-label="Filter requests">
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': requestsFilter === 'all' }" @click="requestsFilter = 'all'">All</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': requestsFilter === 'movie' }" @click="requestsFilter = 'movie'">Movies</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': requestsFilter === 'tv' }" @click="requestsFilter = 'tv'">Series</button>
              </div>
              <div v-if="requestItems.length" class="home-rail-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Previous requests" @click="scrollRail('requests', -1)">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Next requests" @click="scrollRail('requests', 1)">›</button>
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
            No {{ requestsFilter === 'movie' ? 'movie' : requestsFilter === 'tv' ? 'series' : '' }} requests in this filter.
          </p>
          <p v-else class="home-muted">No Seerr requests yet. Search above to request a title.</p>
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
            <h3>Trending</h3>
            <div class="home-rail-tools">
              <div v-if="snapshot.trending.length" class="home-type-filter" role="group" aria-label="Filter trending">
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': trendingFilter === 'all' }" @click="trendingFilter = 'all'">All</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': trendingFilter === 'movie' }" @click="trendingFilter = 'movie'">Movies</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': trendingFilter === 'tv' }" @click="trendingFilter = 'tv'">Series</button>
              </div>
              <div v-if="trendingItems.length" class="home-rail-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Previous trending" @click="scrollRail('trending', -1)">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Next trending" @click="scrollRail('trending', 1)">›</button>
              </div>
            </div>
          </div>
          <div v-if="trendingItems.length" ref="trendingRail" class="home-rail">
            <div v-for="(item, idx) in trendingItems" :key="idx" class="home-tile home-tile-trending">
              <a
                class="home-tile-link"
                :href="item.url || seerrHomeUrl || undefined"
                :target="item.url || seerrHomeUrl ? '_blank' : undefined"
                rel="noopener noreferrer"
                @click="(item.url || seerrHomeUrl) && openApp($event, 'seerr', item.url || seerrHomeUrl)"
              >
                <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
                <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
                <span class="home-tile-title">{{ item.title }}</span>
                <span v-if="item.detail" class="home-tile-meta">{{ item.detail }}</span>
                <span v-if="statusLabel(item)" class="home-tile-meta">{{ statusLabel(item) }}</span>
              </a>
              <button
                v-if="item.can_request"
                type="button"
                class="ui-btn ui-btn-ghost home-tile-request"
                :disabled="requestBusy === `${item.mediaType}-${item.mediaId}`"
                @click="requestTitle(item)"
              >
                {{ requestBusy === `${item.mediaType}-${item.mediaId}` ? 'Requesting…' : 'Request' }}
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
            No {{ trendingFilter === 'movie' ? 'movies' : trendingFilter === 'tv' ? 'series' : 'titles' }} in this filter.
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
              <button v-if="!calOnToday" type="button" class="ui-btn ui-btn-ghost" @click="goToday">Today</button>
              <select v-model="calFilter" class="ui-input cal-select" aria-label="Filter calendar">
                <option value="all">All</option>
                <option value="tv">TV</option>
                <option value="movies">Movies</option>
                <option value="missing">Not downloaded</option>
              </select>
              <select :value="calView" class="ui-input cal-select" aria-label="Calendar view" @change="setCalView($event.target.value)">
                <option value="list">List</option>
                <option value="day">Day</option>
                <option value="week">Week</option>
                <option value="month">Month</option>
              </select>
              <div class="cal-nav">
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" @click="shiftCalendar(-1)" aria-label="Previous">‹</button>
                <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" @click="shiftCalendar(1)" aria-label="Next">›</button>
              </div>
            </div>
          </div>
          <div class="home-card-body">
          <div v-if="calView === 'list'" class="cal-list">
            <div v-if="!calendarList.length && isPending('calendar')" aria-hidden="true">
              <span v-for="n in 4" :key="n" class="home-skel home-skel-line"></span>
            </div>
            <p v-else-if="!calendarList.length" class="home-muted">Nothing in this range.</p>
            <ul v-else>
              <li v-for="(row, idx) in calendarList" :key="idx" class="cal-row" :data-kind="eventKind(row.item)" :class="{ 'is-have': row.item.has_file, 'is-today': isToday(row.dt) }">
                <span class="cal-chip" aria-hidden="true"><span>{{ chipDay(row.dt) }}</span><strong>{{ row.dt.getDate() }}</strong></span>
                <span class="cal-row-body">
                  <strong>{{ row.item.title }}</strong>
                  <span class="cal-row-meta">{{ [row.item.detail, formatEventTime(row.item.when)].filter(Boolean).join(' · ') }}</span>
                </span>
              </li>
            </ul>
          </div>
          <div v-else class="cal" :class="'cal-mode-' + calView" role="grid" aria-label="Upcoming releases calendar">
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
                      <span class="cal-event-time">{{ formatEventTime(item.when) }}</span>
                      <strong>{{ item.title }}</strong>
                      <span v-if="item.detail" class="cal-event-detail">{{ item.detail }}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
          <p v-if="!snapshot.calendar.length && widgetDebug" class="home-muted">Nothing on the calendar.</p>
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
            <h3>Downloading</h3>
            <span v-if="movingDownloads.length && !downloadPause.paused" class="home-card-stat">{{ movingDownloads.length }}<template v-if="totalSpeed"> · {{ totalSpeed }}</template></span>
            <select v-if="movingDownloads.length > 1" v-model="downloadSort" class="ui-input home-sort" aria-label="Sort downloads">
              <option value="queue">Queue order</option>
              <option value="desc">Most done first</option>
              <option value="asc">Least done first</option>
            </select>
            <div v-if="downloadPause.paused" class="home-pause is-paused">
              <span class="home-muted">{{ pausedLabel }}</span>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="pauseBusy" @click="setDownloadsPaused(false)">Resume all</button>
            </div>
            <div v-else-if="snapshot.downloads.length" class="home-pause">
              <select v-model="pauseFor" class="ui-input" aria-label="Pause for">
                <option value="30">30 min</option>
                <option value="60">1 hour</option>
                <option value="180">3 hours</option>
                <option value="until">Until I resume</option>
              </select>
              <button type="button" class="ui-btn ui-btn-ghost ui-btn-icon" :disabled="pauseBusy" title="Pause all downloads" aria-label="Pause all downloads" @click="setDownloadsPaused(true)">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
              </button>
            </div>
          </div>
          <div v-if="movingDownloads.length && !downloadPause.paused" class="home-dl-compact">
            <span class="home-dl-count">{{ movingDownloads.length }}<small>active</small></span>
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
          <p v-else class="home-muted">No active downloads.</p>
          <details v-if="stuckItems.length" class="home-stuck">
            <summary class="home-muted">Not moving: {{ stuckSummary }}</summary>
            <div class="home-stuck-head">
              <span class="home-muted">Removing blocklists the release; Sonarr and Radarr search for another.</span>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="removeBusy.size > 0" @click="removeDownloads(stuckItems, true)">Remove all</button>
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
                  :aria-label="`Remove ${item.title}`"
                  :title="`Remove ${item.title}`"
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
        <article class="home-card glass-card home-card-playing">
          <div class="home-widget-head">
            <h3>Now playing</h3>
            <span v-if="homeStatus.playing.length" class="home-card-stat">{{ homeStatus.playing.length }} watching</span>
          </div>
          <div class="home-card-body">
            <ul v-if="homeStatus.playing.length" class="np-list">
              <li v-for="(item, idx) in homeStatus.playing" :key="idx">
                <component
                  :is="item.url ? 'a' : 'span'"
                  class="np-row"
                  v-bind="item.url ? { href: item.url, target: '_blank', rel: 'noopener noreferrer' } : {}"
                  @click="item.url && openApp($event, item.source, item.url)"
                >
                  <img v-if="item.poster" :src="item.poster" alt="" class="np-poster" />
                  <span class="np-body">
                    <strong>{{ item.title }}</strong>
                    <span v-if="item.detail" class="np-detail">{{ item.detail }}</span>
                    <span class="np-meta">
                      <span>{{ [item.user, item.device].filter(Boolean).join(' · ') }}</span>
                      <span v-if="item.paused" class="np-chip">Paused</span>
                      <span v-if="item.transcoding" class="np-chip is-transcode">Transcoding</span>
                      <span v-else class="np-chip">Direct play</span>
                    </span>
                    <span class="home-bar"><span :style="{ width: `${item.progress}%` }" /></span>
                    <span v-if="item.minutes_left != null" class="home-muted np-left">{{ item.minutes_left }} min left</span>
                  </span>
                </component>
              </li>
            </ul>
            <p v-else-if="!statusLoaded" class="home-muted">Checking who is watching…</p>
            <p v-else-if="hasMediaServer" class="home-muted">Nobody is watching right now.</p>
            <p v-else class="home-muted">Install Jellyfin or Plex to see who is watching.</p>
          </div>
        </article>
      </template>
      <template #storage>
        <article class="home-card glass-card home-card-storage">
          <div class="home-widget-head">
            <h3>Storage</h3>
          </div>
          <div v-if="fullestVolume" class="st-compact">
            <span class="home-dl-count">{{ Math.round(fullestVolume.percent) }}<small>% used</small></span>
            <span class="home-muted home-dl-meta">{{ fullestVolume.labels.join(' · ') }} · {{ formatBytes(fullestVolume.free) }} free</span>
            <span class="home-bar" :class="usageClass(fullestVolume.percent)"><span :style="{ width: `${fullestVolume.percent}%` }" /></span>
          </div>
          <div class="home-card-body">
            <ul v-if="homeStatus.storage.length">
              <li v-for="volume in homeStatus.storage" :key="volume.labels.join()">
                <span class="home-dl-row">
                  <strong>{{ volume.labels.join(' · ') }}</strong>
                  <span class="home-dl-pct font-mono">{{ formatBytes(volume.free) }} free</span>
                </span>
                <span class="home-bar" :class="usageClass(volume.percent)"><span :style="{ width: `${volume.percent}%` }" /></span>
                <span class="home-muted home-dl-meta">{{ formatBytes(volume.used) }} of {{ formatBytes(volume.total) }} · {{ Math.round(volume.percent) }}% used</span>
              </li>
            </ul>
            <p v-else class="home-muted">{{ statusLoaded ? 'No data folders found.' : 'Checking disks…' }}</p>
          </div>
        </article>
      </template>
      <template #server>
        <article class="home-card glass-card home-card-server">
          <div class="home-widget-head">
            <h3>Server</h3>
            <span v-if="homeStatus.server" class="home-muted sv-up">Up {{ upFor(homeStatus.server.uptime_seconds) }}</span>
          </div>
          <div v-if="homeStatus.server" class="sv-meters">
            <div class="sv-meter">
              <span class="sv-label">CPU</span>
              <span class="sv-value">{{ Math.round(homeStatus.server.cpu_percent) }}<small>%</small></span>
              <span class="home-bar" :class="usageClass(homeStatus.server.cpu_percent)"><span :style="{ width: `${homeStatus.server.cpu_percent}%` }" /></span>
              <span class="home-muted sv-note">{{ homeStatus.server.cpu_count }} cores<template v-if="homeStatus.server.temperature != null"> · {{ Math.round(homeStatus.server.temperature) }} °C</template></span>
            </div>
            <div class="sv-meter">
              <span class="sv-label">Memory</span>
              <span class="sv-value">{{ Math.round(homeStatus.server.memory_percent) }}<small>%</small></span>
              <span class="home-bar" :class="usageClass(homeStatus.server.memory_percent)"><span :style="{ width: `${homeStatus.server.memory_percent}%` }" /></span>
              <span class="home-muted sv-note">{{ formatBytes(homeStatus.server.memory_used) }} of {{ formatBytes(homeStatus.server.memory_total) }}</span>
            </div>
          </div>
          <div v-if="homeStatus.server" class="sv-net">
            <div class="sv-net-head">
              <span class="sv-label">Network</span>
              <span class="sv-net-rates">
                <span><i class="sv-key is-down" aria-hidden="true"></i>↓ {{ netRate(netShown?.rxRate) }}</span>
                <span><i class="sv-key is-up" aria-hidden="true"></i>↑ {{ netRate(netShown?.txRate) }}</span>
                <span v-if="netAgo" class="home-muted">{{ netAgo }}</span>
              </span>
            </div>
            <svg v-if="netChart" class="sv-spark" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" :aria-label="netChart.label" @pointermove="onNetHover" @pointerleave="netHoverIdx = -1">
              <line class="sv-base" x1="0" y1="40" x2="100" y2="40" />
              <path class="sv-line is-down" :d="netChart.down" />
              <path class="sv-line is-up" :d="netChart.up" />
              <line v-if="netChart.hoverX != null" class="sv-cross" :x1="netChart.hoverX" y1="0" :x2="netChart.hoverX" y2="40" />
            </svg>
            <p v-else class="home-muted sv-net-wait">Measuring network use…</p>
          </div>
          <p v-else class="home-muted">Reading the server…</p>
        </article>
      </template>
      <template #attention>
        <article class="home-card glass-card home-card-attention">
          <div class="home-widget-head">
            <h3>Needs attention</h3>
            <span v-if="homeStatus.attention.length" class="at-count" :class="{ 'is-problem': homeStatus.attention.some((item) => item.level === 'problem') }">{{ homeStatus.attention.length }}</span>
          </div>
          <div class="home-card-body">
            <ul v-if="homeStatus.attention.length" class="at-list">
              <li v-for="(item, idx) in homeStatus.attention" :key="idx">
                <a :href="item.href" class="at-row" :class="`is-${item.level}`">
                  <span class="at-dot" aria-hidden="true"></span>
                  <span class="at-body">
                    <strong>{{ item.title }}</strong>
                    <span class="home-muted">{{ item.detail }}</span>
                  </span>
                  <svg class="at-go" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
                </a>
              </li>
            </ul>
            <div v-else-if="statusLoaded" class="at-ok">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
              <strong>Everything is running</strong>
              <span class="home-muted">Apps, VPN, tunnel, updates and disks look fine.</span>
            </div>
            <p v-else class="home-muted">Checking…</p>
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
        Calendar, downloads, recently added, trending, and requests appear after Sonarr, Radarr, download clients, Jellyfin, Plex, or Seerr are running.
        Turn on Widget debug in Settings → Diagnostics to see why a source is skipped or failing.
      </p>
    </template>
    <article v-if="!loading && widgetDebug" class="home-widget glass-card home-debug-panel">
      <h3>Widget debug</h3>
      <p class="home-muted">
        Per-source status for Home. API keys are never shown. Toggle this under
        Settings → Diagnostics, or add <code>?debug=1</code> to the URL.
      </p>
      <ul v-if="widgetNotes.length" class="home-debug">
        <li v-for="(note, idx) in widgetNotes" :key="idx">
          <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
          <span>{{ note.widget }} / {{ note.source }} — {{ note.detail }}</span>
        </li>
      </ul>
      <p v-else class="home-muted">No widget sources reported yet. Reload Home.</p>
    </article>
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
  font-size: 0.92rem;
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
  font-size: 0.75rem;
  color: var(--text-muted);
  text-align: center;
}
.home-notice-link {
  margin-left: 0.35rem;
  text-decoration: underline;
}
/* Hero: date, greeting and the search pill, centred like the mockup. */
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
  font-size: 0.8rem;
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
  font-size: 1rem;
  color: var(--text-main);
  text-shadow: var(--wallpaper-text-shadow);
}
.home-search-pill {
  background: var(--control-bg);
  width: 100%;
  max-width: 620px;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  height: 3.5rem;
  margin-top: 0.4rem;
  padding: 0 0.5rem 0 1.25rem;
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
}
.home-search-pill svg {
  flex: 0 0 auto;
  color: var(--text-muted);
}
.home-search-input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 1rem;
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
  top: calc(100% + 0.5rem);
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  width: min(720px, 100%);
  max-height: min(60vh, 34rem);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 1rem 1.1rem;
  text-align: left;
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
@container (max-height: 172px) {
  .home-hero-sub {
    display: none;
  }
}
/* One row high: the greeting sits beside the search pill. */
@container (max-height: 130px) {
  .home-hero {
    flex-direction: row;
    justify-content: flex-start;
    gap: 1rem;
    text-align: left;
  }
  .home-hero-date {
    display: none;
  }
  .home-hero-title {
    flex: 0 1 auto;
    min-width: 0;
    font-size: 1.5rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .home-search-pill {
    flex: 1 1 auto;
    margin-top: 0;
    height: 3rem;
  }
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
  font-size: 0.9rem;
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
  font-size: 0.82rem;
}
.home-result-body .home-status {
  justify-self: start;
  margin-top: 0.2rem;
  padding: 0.05rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
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
.hg.is-editing .home-hero {
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
  font-size: 1.05rem;
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
  font-size: 1.15rem;
}
.home-rail {
  flex: 1 1 auto;
  min-height: 0;
  align-items: flex-start;
  display: flex;
  gap: 0.85rem;
  overflow-x: auto;
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
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text-muted);
}
.home-tile-title {
  font-size: 0.82rem;
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
  font-size: 0.74rem;
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
  font-size: 1rem;
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
  font-size: 0.72rem;
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
  font-size: 0.78rem;
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
  font-size: 0.68rem;
  font-family: var(--font-mono);
  color: var(--color-warning, #f59e0b);
}
.cal-event.is-have .cal-event-time {
  color: var(--color-success, #10b981);
}
.cal-event strong {
  font-size: 0.78rem;
  line-height: 1.2;
}
.cal-event-detail {
  font-size: 0.7rem;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
.cal-event[data-kind='movie'] {
  background: color-mix(in srgb, var(--color-primary) 16%, var(--bg-input));
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
  font-size: 0.64rem;
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: 0.04em;
}
.cal-chip strong {
  font-size: 0.9rem;
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
  font-size: 0.85rem;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cal-row-meta {
  font-size: 0.74rem;
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
  overscroll-behavior: contain;
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
  font-size: 1.05rem;
}
.home-card .ui-input {
  width: auto;
}
.home-card .cal-select {
  min-width: 0;
  padding-left: 0.9rem;
}
.home-card-stat {
  font-size: 0.78rem;
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
  font-size: 0.85rem;
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
  font-size: 0.85rem;
  font-weight: 700;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.home-dl-pct {
  flex: 0 0 auto;
  font-size: 0.76rem;
  color: var(--text-muted);
}
.home-dl-meta {
  font-size: 0.74rem;
}
.home-when {
  font-size: 0.75rem;
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
  font-size: 0.8rem;
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
  font-size: 0.8rem;
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
  font-size: 0.85rem;
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
  font-size: 0.82rem;
  color: var(--text-muted);
}
.home-debug-state {
  flex: 0 0 auto;
  font-family: var(--font-mono);
  font-size: 0.7rem;
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
/* Status widgets: bars turn amber from 80% and red from 90%, like the disk warning in Needs attention. */
.home-bar.is-high span {
  background: var(--color-warning);
}
.home-bar.is-full span {
  background: var(--color-danger);
}
/* Now playing: poster, title, who and where, and how far along. */
.home-card .np-list {
  gap: 0.9rem;
}
.np-row {
  display: flex;
  align-items: flex-start;
  gap: 0.8rem;
  min-width: 0;
  color: inherit;
  text-decoration: none;
}
.np-poster {
  flex: 0 0 auto;
  width: 3.4rem;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}
.np-body {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 0.25rem;
}
.np-body strong,
.np-detail {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.np-body strong {
  font-size: 0.9rem;
  font-weight: 700;
}
.np-detail {
  font-size: 0.8rem;
  color: var(--text-muted);
}
.np-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.74rem;
  color: var(--text-muted);
}
.np-chip {
  padding: 0.05rem 0.45rem;
  border: 1px solid var(--border-strong);
  border-radius: 999px;
  font-weight: 600;
}
.np-chip.is-transcode {
  color: var(--color-warning-fg);
  border-color: color-mix(in srgb, var(--color-warning) 50%, transparent);
}
.np-left {
  font-size: 0.72rem;
}
@container (max-width: 300px) or (max-height: 220px) {
  .np-poster,
  .np-meta,
  .np-left {
    display: none;
  }
}
/* Storage: one row per disk; a small card shows only the fullest one. */
.st-compact {
  display: none;
  flex: 1 1 auto;
  flex-direction: column;
  justify-content: flex-end;
  gap: 0.4rem;
  min-height: 0;
}
@container (max-width: 260px) or (max-height: 140px) {
  .home-card-storage .st-compact {
    display: flex;
  }
  .home-card-storage .st-compact + .home-card-body {
    display: none;
  }
}
/* Server: CPU and memory side by side, stacked in a narrow card; network use below when there is room.
   Series colours: categorical slots 1 and 2 of the reference palette, validated on both card surfaces. */
.home-card-server {
  --series-down: #3987e5;
  --series-up: #d95926;
}
:global([data-theme='light'] .home-card-server) {
  --series-down: #2a78d6;
  --series-up: #eb6834;
}
.sv-up {
  font-size: 0.8rem;
}
.sv-meters {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: end;
  gap: 0.6rem 1.2rem;
}
.sv-meter {
  display: grid;
  gap: 0.25rem;
  min-width: 0;
}
.sv-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.sv-value {
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.sv-value small {
  margin-left: 0.1rem;
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--text-muted);
}
.sv-note {
  font-size: 0.74rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sv-net {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.sv-net-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.2rem 0.75rem;
}
.sv-net-rates {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem 0.75rem;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
}
.sv-key {
  display: inline-block;
  width: 0.55rem;
  height: 0.55rem;
  margin-right: 0.3rem;
  border-radius: 2px;
}
.sv-key.is-down {
  background: var(--series-down);
}
.sv-key.is-up {
  background: var(--series-up);
}
.sv-spark {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  overflow: visible;
  cursor: crosshair;
}
.sv-line {
  fill: none;
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
}
.sv-line.is-down {
  stroke: var(--series-down);
}
.sv-line.is-up {
  stroke: var(--series-up);
}
.sv-base,
.sv-cross {
  stroke: var(--border-strong);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.sv-net-wait {
  margin: 0;
  font-size: 0.78rem;
}
/* Two rows high: the rates stay, the graph goes. */
@container (max-height: 200px) {
  .sv-spark,
  .sv-net-wait {
    display: none;
  }
}
@container (max-height: 150px) {
  .sv-net {
    display: none;
  }
}
@container (max-width: 300px) {
  .sv-net {
    display: none;
  }
  .sv-meters {
    grid-template-columns: minmax(0, 1fr);
  }
  .sv-value {
    font-size: 1.45rem;
  }
  .sv-note {
    display: none;
  }
}
/* Needs attention: a coloured dot per row, each row opens where to fix it; empty means all is well. */
.at-count {
  min-width: 1.5rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  text-align: center;
  font-size: 0.78rem;
  font-weight: 800;
  background: var(--color-warning-bg);
  color: var(--color-warning-fg);
}
.at-count.is-problem {
  background: var(--color-danger-bg);
  color: var(--color-danger-fg);
}
.home-card .at-list {
  gap: 0.4rem;
}
.at-row {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  min-width: 0;
  padding: 0.55rem 0.6rem;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: var(--bg-surface);
  color: inherit;
  text-decoration: none;
}
.at-row:hover {
  border-color: var(--border-hover);
}
.at-dot {
  flex: 0 0 auto;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  background: var(--color-primary);
}
.at-row.is-problem .at-dot {
  background: var(--color-danger);
}
.at-row.is-warning .at-dot {
  background: var(--color-warning);
}
.at-body {
  flex: 1;
  min-width: 0;
  display: grid;
}
.at-body strong,
.at-body .home-muted {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.at-body strong {
  font-size: 0.86rem;
}
.at-body .home-muted {
  font-size: 0.76rem;
}
.at-go {
  flex: 0 0 auto;
  width: 1rem;
  height: 1rem;
  color: var(--text-dim);
}
.at-ok {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  text-align: center;
}
.at-ok svg {
  width: 2rem;
  height: 2rem;
  padding: 0.4rem;
  border-radius: 50%;
  color: var(--color-success-fg);
  background: var(--color-success-bg);
}
@container (max-height: 160px) {
  .at-ok .home-muted {
    display: none;
  }
}
</style>
