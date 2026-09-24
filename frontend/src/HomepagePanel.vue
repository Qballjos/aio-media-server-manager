<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { appIconSrc } from './appIcons.js'

const props = defineProps({
  apiRequest: { type: Function, required: true },
})
const emit = defineEmits(['manage'])

const DEBUG_KEY = 'amm-homepage-widget-debug'
const emptySnapshot = () => ({
  apps: [],
  calendar: [],
  downloads: [],
  recent: [],
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
let poll = null
let searchTimer = null

const hasWidgets = computed(
  () =>
    snapshot.value.calendar.length ||
    snapshot.value.downloads.length ||
    snapshot.value.recent.length,
)
const showWidgets = computed(() => hasWidgets.value || widgetDebug.value)
const widgetNotes = computed(() => snapshot.value.widgets || [])

function notesFor(widget) {
  return widgetNotes.value.filter((item) => item.widget === widget)
}

function toggleWidgetDebug() {
  widgetDebug.value = !widgetDebug.value
  try {
    localStorage.setItem(DEBUG_KEY, widgetDebug.value ? '1' : '0')
  } catch (_) {
    /* ignore */
  }
}

async function loadSnapshot() {
  try {
    const res = await props.apiRequest('/api/homepage')
    if (res.ok) {
      const data = await res.json()
      snapshot.value = {
        ...emptySnapshot(),
        ...data,
        calendar: data.calendar || [],
        downloads: data.downloads || [],
        recent: data.recent || [],
        widgets: data.widgets || [],
        seerr: data.seerr || { available: false, url: null },
      }
      snapshotError.value = ''
    } else {
      snapshotError.value = `Homepage API HTTP ${res.status}`
    }
  } catch (err) {
    snapshotError.value = err?.message || 'Homepage snapshot failed'
  } finally {
    loading.value = false
  }
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
    const res = await props.apiRequest(`/api/homepage/search?q=${encodeURIComponent(q)}`)
    if (res.ok) {
      const data = await res.json()
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
    const res = await props.apiRequest('/api/homepage/request', {
      method: 'POST',
      body: JSON.stringify({
        mediaType: item.mediaType,
        mediaId: item.mediaId,
        seasons: item.mediaType === 'tv' ? 'all' : undefined,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok && data.ok !== false) {
      notice.value = data.detail || 'Request submitted.'
      item.status = 'requested'
      item.can_request = false
    } else {
      notice.value = data.detail || 'Request failed.'
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

const calendarMonthLabel = computed(() =>
  new Date().toLocaleDateString(undefined, { month: 'long', year: 'numeric' }),
)

const calendarWeeks = computed(() => {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth()
  const first = new Date(year, month, 1)
  const start = new Date(first)
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7))
  const last = new Date(year, month + 1, 0)
  const end = new Date(last)
  end.setDate(last.getDate() + ((7 - last.getDay()) % 7))

  const byDay = {}
  for (const item of snapshot.value.calendar || []) {
    const dt = parseWhen(item.when)
    if (!dt) continue
    const key = dayKey(dt)
    if (!byDay[key]) byDay[key] = []
    byDay[key].push(item)
  }

  const todayKey = dayKey(now)
  const weeks = []
  const cursor = new Date(start)
  while (cursor <= end) {
    const days = []
    let isCurrent = false
    for (let i = 0; i < 7; i += 1) {
      const key = dayKey(cursor)
      if (key === todayKey) isCurrent = true
      days.push({
        key,
        date: cursor.getDate(),
        inMonth: cursor.getMonth() === month,
        isToday: key === todayKey,
        events: byDay[key] || [],
      })
      cursor.setDate(cursor.getDate() + 1)
    }
    weeks.push({ key: days[0].key, isCurrent, days })
  }
  return weeks
})

onMounted(() => {
  try {
    const params = new URLSearchParams(window.location.search)
    widgetDebug.value = params.get('debug') === '1' || localStorage.getItem(DEBUG_KEY) === '1'
  } catch (_) {
    widgetDebug.value = false
  }
  loadSnapshot()
  poll = setInterval(loadSnapshot, 15000)
})
onUnmounted(() => {
  if (poll) clearInterval(poll)
  clearTimeout(searchTimer)
})
</script>

<template>
  <section class="home-shell">
    <div class="home-hero glass-card">
      <div>
        <p class="home-kicker">Household</p>
        <h2>Watch and request</h2>
        <p class="home-lead">
          Open installed apps and see what’s airing, downloading, or newly added. Process
          controls stay on Catalog.
        </p>
      </div>
      <div class="home-hero-actions">
        <button
          type="button"
          class="ui-btn ui-btn-ghost"
          :class="{ 'is-on': widgetDebug }"
          @click="toggleWidgetDebug"
        >
          {{ widgetDebug ? 'Hide widget debug' : 'Widget debug' }}
        </button>
        <button type="button" class="ui-btn ui-btn-ghost" @click="emit('manage')">Open Catalog</button>
      </div>
    </div>

    <p v-if="loading" class="home-muted">Loading homepage…</p>
    <p v-if="snapshotError" class="home-notice">{{ snapshotError }}</p>

    <div v-if="!loading && !snapshot.apps.length" class="home-empty glass-card">
      <h3>Nothing to launch yet</h3>
      <p>Finish the wizard or install apps from Catalog. This page only lists installed services.</p>
      <button type="button" class="ui-btn ui-btn-primary" @click="emit('manage')">Go to Catalog</button>
    </div>

    <template v-else-if="!loading">
      <div class="home-launcher">
        <a
          v-for="app in snapshot.apps"
          :key="app.name"
          class="home-app"
          :class="{ 'is-down': !app.running }"
          :href="app.url"
          target="_blank"
          rel="noopener noreferrer"
          :title="app.running ? app.display_name : `${app.display_name} is stopped`"
        >
          <img
            v-if="appIconSrc(app.name)"
            :src="appIconSrc(app.name)"
            :alt="app.display_name"
            class="home-app-icon"
          />
          <span v-else class="home-app-fallback">{{ app.display_name.slice(0, 1) }}</span>
          <span class="home-app-name">{{ app.display_name }}</span>
          <span class="home-app-state">{{ app.running ? 'Open' : 'Stopped' }}</span>
        </a>
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
        <article v-if="snapshot.calendar.length || widgetDebug" class="home-widget glass-card home-widget-calendar">
          <div class="cal-head">
            <h3>Coming up</h3>
            <p class="cal-range cal-range-month">{{ calendarMonthLabel }}</p>
            <p class="cal-range cal-range-week">This week</p>
          </div>
          <div class="cal" role="grid" aria-label="Upcoming releases calendar">
            <div class="cal-weekdays">
              <span v-for="label in weekdayLabels" :key="label">{{ label }}</span>
            </div>
            <div class="cal-weeks">
              <div
                v-for="week in calendarWeeks"
                :key="week.key"
                class="cal-week"
                :class="{ 'is-current': week.isCurrent }"
              >
                <div
                  v-for="day in week.days"
                  :key="day.key"
                  class="cal-day"
                  :class="{ 'is-today': day.isToday, 'is-outside': !day.inMonth }"
                >
                  <span class="cal-num">{{ day.date }}</span>
                  <ul v-if="day.events.length" class="cal-events">
                    <li v-for="(item, idx) in day.events" :key="idx" class="cal-event" :data-kind="item.kind || item.source">
                      <span class="cal-event-time">{{ formatEventTime(item.when) }}</span>
                      <strong>{{ item.title }}</strong>
                      <span v-if="item.detail" class="cal-event-detail">{{ item.detail }}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
          <p v-if="!snapshot.calendar.length" class="home-muted">Nothing on the calendar.</p>
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
              <span class="home-muted">{{ item.source }} · {{ item.status }} · {{ item.progress }}%</span>
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
        <article v-if="snapshot.recent.length || widgetDebug" class="home-widget glass-card">
          <h3>Recently added</h3>
          <ul v-if="snapshot.recent.length">
            <li v-for="(item, idx) in snapshot.recent" :key="idx">
              <strong>{{ item.title }}</strong>
              <span class="home-muted">{{ item.source }} · {{ item.detail }}</span>
            </li>
          </ul>
          <p v-else class="home-muted">Nothing recently added.</p>
          <ul v-if="widgetDebug && notesFor('recent').length" class="home-debug">
            <li v-for="(note, idx) in notesFor('recent')" :key="idx">
              <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
              <span>{{ note.source }} — {{ note.detail }}</span>
            </li>
          </ul>
        </article>
      </div>
      <p v-else class="home-muted">
        Calendar, downloads, and recently added appear after Sonarr, Radarr, download clients, Jellyfin, or Plex are running.
        Turn on Widget debug to see why a source is skipped or failing.
      </p>
    </template>
    <article v-if="!loading && widgetDebug" class="home-widget glass-card home-debug-panel">
      <h3>Widget debug</h3>
      <p class="home-muted">
        Per-source status for this homepage. API keys are never shown. Add
        <code>?debug=1</code> to the URL to keep this on.
      </p>
      <ul v-if="widgetNotes.length" class="home-debug">
        <li v-for="(note, idx) in widgetNotes" :key="idx">
          <span class="home-debug-state" :data-state="note.state">{{ note.state }}</span>
          <span>{{ note.widget }} / {{ note.source }} — {{ note.detail }}</span>
        </li>
      </ul>
      <p v-else class="home-muted">No widget sources reported yet. Reload the homepage.</p>
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
.home-hero {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  padding: 1.25rem 1.4rem;
}
.home-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: flex-end;
}
.home-hero-actions .is-on {
  border-color: var(--color-info);
  color: var(--color-info);
}
.home-kicker {
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--color-info);
  margin-bottom: 0.35rem;
}
.home-hero h2 {
  font-size: 1.45rem;
  margin-bottom: 0.35rem;
}
.home-lead,
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
.home-launcher {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
  gap: 0.75rem;
}
.home-app {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  padding: 0.85rem 0.5rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-card);
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
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1rem;
}
.home-widget-calendar {
  grid-column: 1 / -1;
}
.cal-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.35rem 1rem;
  margin-bottom: 0.75rem;
}
.cal-head h3 {
  margin-bottom: 0;
}
.cal-range {
  margin: 0;
  font-size: 0.88rem;
  color: var(--text-muted);
}
.cal-range-week {
  display: none;
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
.cal-events {
  list-style: none;
  display: grid;
  gap: 0.28rem;
  margin: 0;
  padding: 0;
}
.home-widget-calendar .cal-events {
  gap: 0.28rem;
}
.home-widget-calendar .cal-events li {
  display: grid;
  gap: 0.05rem;
  padding: 0.28rem 0.35rem;
  border-radius: 0.35rem;
  background: var(--bg-input);
  min-width: 0;
}
.cal-event-time {
  font-size: 0.68rem;
  font-family: var(--font-mono);
  color: var(--color-info);
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
@media (max-width: 720px) {
  .home-hero {
    flex-direction: column;
  }
}
@media (max-width: 800px) {
  .cal-range-month {
    display: none;
  }
  .cal-range-week {
    display: block;
  }
  .cal-week:not(.is-current) {
    display: none;
  }
  .cal-week.is-current .cal-day {
    min-height: 9.5rem;
  }
}
</style>
