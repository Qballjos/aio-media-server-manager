<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { appIconSrc } from './appIcons.js'
import { apiError, apiRequest, readJson } from './api.js'
import { startGuardedInterval } from './pageVisible.js'
import { readHomepageWidgetDebug } from './homepageDebug.js'

const emit = defineEmits(['manage'])
const route = useRoute()
const emptySnapshot = () => ({
  apps: [],
  calendar: [],
  downloads: [],
  recent: [],
  requests: [],
  trending: [],
  seerr: { available: false, url: null },
  widgets: [],
})

const snapshot = ref(emptySnapshot())
const loading = ref(true)
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
let poll = null
let downloadsPoll = null
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
const showWidgets = computed(() => hasWidgets.value || widgetDebug.value)
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
    const id = app.category || 'other'
    if (!groups.has(id)) {
      groups.set(id, {
        id,
        label: CATEGORY_LABELS[id] || id,
        apps: [],
      })
    }
    groups.get(id).apps.push(app)
  }
  return [...groups.values()].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a.id)
    const bi = CATEGORY_ORDER.indexOf(b.id)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
})

function notesFor(widget) {
  return widgetNotes.value.filter((item) => item.widget === widget)
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

function mergeWidgetNotes(incoming) {
  if (!downloadsFresh.value) return incoming
  return [
    ...incoming.filter((note) => note.widget !== 'downloads'),
    ...(snapshot.value.widgets || []).filter((note) => note.widget === 'downloads'),
  ]
}

async function loadDownloads() {
  try {
    const res = await apiRequest('/api/homepage/downloads')
    if (!res.ok) return
    const data = await readJson(res)
    snapshot.value.downloads = data.downloads || []
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
const recentRail = ref(null)
const requestsRail = ref(null)
const trendingRail = ref(null)

function defaultCalView() {
  const width = typeof window === 'undefined' ? 1024 : window.innerWidth
  if (width < 768) return 'list'
  if (width < 1440) return 'week'
  return 'month'
}

function setCalView(view) {
  calViewPicked.value = true
  calView.value = view
}

function syncCalViewToViewport() {
  if (calViewPicked.value) return
  const next = defaultCalView()
  if (calView.value !== next) calView.value = next
}

function launcherTitle(app) {
  if (app.sick) return `${app.display_name} is unhealthy`
  if (!app.running) return `${app.display_name} is stopped`
  return app.display_name
}

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
  if (calView.value === 'day' || calView.value === 'list') {
    return calCursor.value.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })
  }
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

const calendarList = computed(() => {
  const start = calView.value === 'list' ? startOfWeek(calCursor.value) : calCursor.value
  const end = calView.value === 'list' ? addDays(start, 7) : addDays(calCursor.value, 1)
  return filteredCalendar.value
    .map((item) => ({ item, dt: parseWhen(item.when) }))
    .filter((row) => row.dt && row.dt >= start && row.dt < end)
    .sort((a, b) => a.dt - b.dt)
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
  loadSnapshot()
  // Defer live queues so first paint is the launcher snapshot.
  setTimeout(() => loadDownloads(), 750)
  poll = startGuardedInterval(loadSnapshot, 20000)
  downloadsPoll = startGuardedInterval(loadDownloads, 8000)
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
  if (view === 'week' || view === 'list') {
    calCursor.value = startOfWeek(calCursor.value)
  }
})
onUnmounted(() => {
  window.removeEventListener('resize', syncCalViewToViewport)
  if (poll) poll()
  if (downloadsPoll) downloadsPoll()
  clearTimeout(searchTimer)
})
</script>

<template>
  <section class="home-shell">
    <p v-if="loading" class="home-muted">Loading Home…</p>
    <p v-if="snapshotError" class="home-notice">{{ snapshotError }}</p>

    <div v-if="!loading && !snapshot.apps.length" class="home-empty glass-card">
      <h3>Nothing to launch yet</h3>
      <p>Finish setup or install apps from Catalog. This page only lists installed applications with a WebUI.</p>
      <button type="button" class="ui-btn ui-btn-primary" @click="emit('manage')">Go to Catalog</button>
    </div>

    <template v-else-if="!loading">
      <div class="home-launcher-groups">
        <section v-for="group in launcherGroups" :key="group.id" class="home-launcher-group glass-card">
          <h3 class="home-launcher-label">{{ group.label }}</h3>
          <div class="home-launcher">
            <a
              v-for="app in group.apps"
              :key="app.name"
              class="home-app"
              :class="{ 'is-down': !app.running && !app.sick, 'is-sick': app.sick }"
              :href="app.url"
              target="_blank"
              rel="noopener noreferrer"
              :title="launcherTitle(app)"
            >
              <img
                v-if="appIconSrc(app.name)"
                :src="appIconSrc(app.name)"
                :alt="app.display_name"
                class="home-app-icon"
              />
              <span v-else class="home-app-fallback">{{ app.display_name.slice(0, 1) }}</span>
              <span class="home-app-name">{{ app.display_name }}</span>
              <span v-if="app.sick" class="home-app-state">Unhealthy</span>
              <span v-else-if="!app.running" class="home-app-state">Stopped</span>
            </a>
          </div>
        </section>
      </div>

      <form class="home-search glass-card" @submit.prevent="runSearch">
        <label class="home-search-label" for="home-search">Search</label>
        <div class="home-search-row">
          <input
            id="home-search"
            v-model="query"
            class="ui-input"
            type="search"
            autocomplete="off"
            :placeholder="snapshot.seerr.available ? 'Search movies and TV to request' : 'Search Sonarr and Radarr'"
            @input="onQueryInput"
          />
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="searching">Search</button>
        </div>
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
      </form>

      <div v-if="showWidgets" class="home-widgets">
        <article v-if="snapshot.recent.length || hasMediaServer || widgetDebug" class="home-widget glass-card home-widget-rail">
          <div class="home-rail-head">
            <h3>Recently added</h3>
            <div v-if="snapshot.recent.length" class="home-rail-nav">
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Previous recently added" @click="scrollRail('recent', -1)">‹</button>
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Next recently added" @click="scrollRail('recent', 1)">›</button>
            </div>
          </div>
          <div v-if="snapshot.recent.length" ref="recentRail" class="home-rail">
            <a
              v-for="(item, idx) in snapshot.recent"
              :key="idx"
              class="home-tile"
              :href="item.url || undefined"
              :target="item.url ? '_blank' : undefined"
              rel="noopener noreferrer"
            >
              <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
              <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
              <span class="home-tile-title">{{ item.title }}</span>
              <span v-if="item.detail" class="home-tile-meta">{{ item.detail }}</span>
            </a>
          </div>
          <p v-else class="home-muted">Nothing recently added.</p>
          <ul v-if="widgetDebug && notesFor('recent').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('recent')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
        <article v-if="snapshot.requests.length || snapshot.seerr.available || widgetDebug" class="home-widget glass-card home-widget-rail">
          <div class="home-rail-head">
            <h3>Requests</h3>
            <div v-if="snapshot.requests.length" class="home-rail-nav">
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Previous requests" @click="scrollRail('requests', -1)">‹</button>
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Next requests" @click="scrollRail('requests', 1)">›</button>
            </div>
          </div>
          <div v-if="snapshot.requests.length" ref="requestsRail" class="home-rail">
            <a
              v-for="(item, idx) in snapshot.requests"
              :key="idx"
              class="home-tile"
              :href="item.url || snapshot.seerr.url || undefined"
              :target="item.url || snapshot.seerr.url ? '_blank' : undefined"
              rel="noopener noreferrer"
            >
              <img v-if="item.poster" :src="item.poster" alt="" class="home-tile-poster" />
              <span v-else class="home-tile-fallback">{{ item.title.slice(0, 1) }}</span>
              <span class="home-tile-title">{{ item.title }}</span>
              <span v-if="item.detail" class="home-tile-meta">{{ item.detail }}</span>
            </a>
          </div>
          <p v-else class="home-muted">No Seerr requests yet. Search above to request a title.</p>
          <ul v-if="widgetDebug && notesFor('requests').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('requests')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
        <article v-if="snapshot.trending.length || snapshot.seerr.available || widgetDebug" class="home-widget glass-card home-widget-rail">
          <div class="home-rail-head">
            <h3>Trending</h3>
            <div v-if="snapshot.trending.length" class="home-rail-nav">
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Previous trending" @click="scrollRail('trending', -1)">‹</button>
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" aria-label="Next trending" @click="scrollRail('trending', 1)">›</button>
            </div>
          </div>
          <div v-if="snapshot.trending.length" ref="trendingRail" class="home-rail">
            <div v-for="(item, idx) in snapshot.trending" :key="idx" class="home-tile home-tile-trending">
              <a
                class="home-tile-link"
                :href="item.url || snapshot.seerr.url || undefined"
                :target="item.url || snapshot.seerr.url ? '_blank' : undefined"
                rel="noopener noreferrer"
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
                class="ui-btn ui-btn-primary home-tile-request"
                :disabled="requestBusy === `${item.mediaType}-${item.mediaId}`"
                @click="requestTitle(item)"
              >
                {{ requestBusy === `${item.mediaType}-${item.mediaId}` ? 'Requesting…' : 'Request' }}
              </button>
            </div>
          </div>
          <p v-else class="home-muted">Trending titles appear when Seerr is running.</p>
          <ul v-if="widgetDebug && notesFor('trending').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('trending')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
        <article v-if="snapshot.calendar.length || hasCalendarSource || widgetDebug" class="home-widget glass-card home-widget-calendar">
          <div class="cal-head">
            <div class="cal-nav">
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" @click="shiftCalendar(-1)" aria-label="Previous">‹</button>
              <h3>{{ calendarRangeLabel }}</h3>
              <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" @click="shiftCalendar(1)" aria-label="Next">›</button>
              <button type="button" class="ui-btn ui-btn-ghost" @click="goToday">Today</button>
            </div>
            <div class="cal-tools">
              <button type="button" class="ui-btn ui-btn-ghost" @click="loadSnapshot(true)">Refresh</button>
              <select v-model="calFilter" class="ui-input cal-select" aria-label="Filter calendar">
                <option value="all">All</option>
                <option value="tv">TV</option>
                <option value="movies">Movies</option>
                <option value="missing">Not downloaded</option>
              </select>
              <div class="cal-views">
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': calView === 'month' }" @click="setCalView('month')">Month</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': calView === 'week' }" @click="setCalView('week')">Week</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': calView === 'day' }" @click="setCalView('day')">Day</button>
                <button type="button" class="ui-btn ui-btn-ghost" :class="{ 'is-active': calView === 'list' }" @click="setCalView('list')">List</button>
              </div>
            </div>
          </div>
          <div v-if="calView === 'list'" class="cal-list">
            <p v-if="!calendarList.length" class="home-muted">Nothing in this range.</p>
            <ul v-else>
              <li v-for="(row, idx) in calendarList" :key="idx" class="cal-event" :data-kind="eventKind(row.item)" :class="{ 'is-have': row.item.has_file }">
                <span class="cal-event-time">{{ formatEventTime(row.item.when) }}</span>
                <strong>{{ row.item.title }}</strong>
                <span v-if="row.item.detail" class="cal-event-detail">{{ row.item.detail }}</span>
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
                  :class="{ 'is-today': day.isToday, 'is-outside': !day.inMonth }"
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
        </article>
        <article v-if="snapshot.downloads.length || widgetDebug" class="home-widget glass-card">
          <h3>Downloading</h3>
          <ul v-if="snapshot.downloads.length">
            <li v-for="(item, idx) in snapshot.downloads" :key="idx">
              <strong>{{ item.title }}</strong>
              <span class="home-muted">
                {{ item.source }} · {{ item.status }} · {{ item.progress }}%
                <span v-if="formatSpeed(item.speed_bps)" class="home-speed"> · {{ formatSpeed(item.speed_bps) }}</span>
                <span v-if="item.eta"> · {{ item.eta }}</span>
              </span>
              <span class="home-bar"><span :style="{ width: `${item.progress}%` }" /></span>
            </li>
          </ul>
          <p v-else class="home-muted">No active downloads.</p>
          <ul v-if="widgetDebug && notesFor('downloads').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('downloads')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
      </div>
      <p v-else class="home-muted">
        Calendar, downloads, recently added, trending, and requests appear after Sonarr, Radarr, download clients, Jellyfin, Plex, or Seerr are running.
        Turn on Widget debug in Settings → Homepage to see why a source is skipped or failing.
      </p>
    </template>
    <article v-if="!loading && widgetDebug" class="home-widget glass-card home-debug-panel">
      <h3>Widget debug</h3>
      <p class="home-muted">
        Per-source status for Home. API keys are never shown. Toggle this under
        Settings → Homepage, or add <code>?debug=1</code> to the URL.
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
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
  min-width: 0;
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
.home-launcher-groups {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0.75rem;
}
.home-launcher-group.glass-card {
  flex: 0 1 auto;
  width: auto;
  max-width: 100%;
  min-width: 0;
  padding: 0.7rem 0.8rem 0.8rem;
  overflow: visible;
}
.home-launcher-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin: 0 0 0.5rem;
}
.home-launcher {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 0.45rem;
}
.home-app {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  width: 6.35rem;
  flex: 0 0 6.35rem;
  padding: 0.55rem 0.35rem;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.home-app:hover {
  border-color: var(--border-hover);
}
.home-app.is-down {
  opacity: 0.55;
}
.home-app.is-sick,
.home-app.is-sick:hover {
  border-color: rgba(239, 68, 68, 0.85);
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.35);
}
.home-app.is-sick .home-app-state {
  color: #f87171;
}
.home-app-icon,
.home-app-fallback {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.65rem;
  object-fit: contain;
}
.home-app-fallback {
  display: grid;
  place-items: center;
  background: var(--bg-surface-elevated);
  font-weight: 600;
}
.home-app-name {
  font-size: 0.82rem;
  text-align: center;
  line-height: 1.2;
}
.home-app-state {
  font-size: 0.7rem;
  color: var(--text-dim);
}
.home-search {
  padding: 1rem 1.2rem;
  display: grid;
  gap: 0.65rem;
}
.home-search-label {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}
.home-search-row {
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
}
.home-search-row .ui-input {
  flex: 1 1 12rem;
  min-width: 0;
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
  color: #34d399;
}
.home-status.is-partial,
.home-status.is-requested,
.home-status.is-monitored {
  color: #fbbf24;
}
.home-status.is-missing {
  color: var(--text-muted);
}
.home-widgets {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}
.home-widget-rail,
.home-widget-calendar {
  grid-column: 1 / -1;
}
.home-rail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.home-rail-head h3 {
  margin: 0;
}
.home-rail-nav {
  display: flex;
  gap: 0.3rem;
}
.home-rail {
  display: flex;
  gap: 0.75rem;
  overflow-x: auto;
  padding-bottom: 0.35rem;
  scroll-snap-type: x proximity;
}
.home-tile {
  flex: 0 0 7.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  color: inherit;
  text-decoration: none;
  min-width: 0;
  scroll-snap-align: start;
}
.home-tile-trending {
  flex-basis: 7.25rem;
}
.home-tile-link {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  color: inherit;
  text-decoration: none;
  min-width: 0;
}
.home-tile-request {
  font-size: 0.72rem;
  padding: 0.3rem 0.45rem;
}
.home-tile-poster,
.home-tile-fallback {
  width: 7.25rem;
  height: 10.6rem;
  border-radius: 0.45rem;
  object-fit: cover;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
}
.home-tile-fallback {
  display: grid;
  place-items: center;
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-muted);
}
.home-tile-title,
.home-tile-meta {
  font-size: 0.78rem;
  line-height: 1.25;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.home-tile-meta {
  color: var(--text-muted);
  -webkit-line-clamp: 1;
  font-size: 0.72rem;
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
  border-color: var(--color-info);
  color: var(--text-main);
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
}
.cal-mode-week .cal-weekdays,
.cal-mode-week .cal-week {
  min-width: 56rem;
}
.cal-weeks.is-week .cal-week,
.cal-weeks.is-day .cal-week {
  overflow-x: visible;
}
.cal-weeks.is-week .cal-week {
  min-width: 56rem;
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
  background: var(--bg-surface-elevated, var(--bg-card));
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  overflow: auto;
}
.cal-weeks.is-week .cal-day {
  min-height: 18rem;
}
.cal-weeks.is-week .cal-num {
  display: none;
}
.cal-day.is-outside {
  opacity: 0.45;
}
.cal-day.is-today {
  border-color: var(--color-info);
  box-shadow: inset 0 0 0 1px var(--color-info);
}
.cal-num {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-muted);
}
.cal-day.is-today .cal-num {
  color: var(--color-info);
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
  background: var(--bg-input);
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
.home-widget {
  padding: 1rem 1.15rem;
  min-width: 0;
}
.home-widget h3 {
  margin-bottom: 0.75rem;
  font-size: 0.95rem;
}
.home-widget ul {
  list-style: none;
  display: grid;
  gap: 0.7rem;
}
.home-widget-calendar ul {
  gap: 0.28rem;
}
.home-widget li {
  display: grid;
  gap: 0.15rem;
  min-width: 0;
}
.home-widget strong {
  overflow-wrap: anywhere;
}
.home-when {
  font-size: 0.75rem;
  color: var(--color-info);
  font-family: var(--font-mono);
}
.home-bar {
  display: block;
  height: 4px;
  border-radius: 99px;
  background: var(--bg-input);
  overflow: hidden;
}
.home-speed {
  color: var(--color-info);
  font-variant-numeric: tabular-nums;
}
.home-bar span {
  display: block;
  height: 100%;
  background: var(--color-primary);
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
.home-widget-rail h3 {
  margin-bottom: 0;
}
</style>
