import { computed, ref, watch } from 'vue'
import { openApp } from '../appOpen.js'
import { i18n, t } from '../i18n/index.js'

/** Calendar state stays with the Home page, including a manually chosen view. */
export function useHomeCalendar({ snapshot, calendarWide, calendarPhone = ref(false) }) {
  function defaultCalView() {
    return calendarPhone.value ? 'day' : calendarWide.value ? 'week' : 'list'
  }

  const SOURCE_NAMES = { jellyfin: 'Jellyfin', plex: 'Plex', sonarr: 'Sonarr', radarr: 'Radarr' }
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
    return dt.toLocaleTimeString(i18n.global.locale.value, { hour: '2-digit', minute: '2-digit' })
  }

  function dayKey(dt) {
    const y = dt.getFullYear()
    const m = String(dt.getMonth() + 1).padStart(2, '0')
    const d = String(dt.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }

  const weekdayLabels = computed(() => Array.from({ length: 7 }, (_, index) =>
    new Date(2024, 0, 1 + index).toLocaleDateString(i18n.global.locale.value, { weekday: 'short' }),
  ))
  const calViewPicked = ref(false)
  const calView = ref(defaultCalView())
  const calFilter = ref('all')
  const selectedDayKey = ref(dayKey(new Date()))

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
    const next = defaultCalView()
    if (calView.value !== next) calView.value = next
  }


  function startOfWeek(value) {
    const dt = new Date(value)
    dt.setHours(0, 0, 0, 0)
    dt.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
    return dt
  }

  const calCursor = ref(startOfWeek(new Date()))


  function addDays(value, amount) {
    const dt = new Date(value)
    dt.setDate(dt.getDate() + amount)
    return dt
  }

  function eventKind(item) {
    return item?.kind || item?.source || ''
  }

  /** Downloaded titles open on Jellyfin or Plex. Everything else opens in Sonarr or Radarr. */
  function calendarTarget(item) {
    if (item?.has_file && item.play_url && item.play_app) {
      return { app: item.play_app, url: item.play_url }
    }
    if (item?.url && item.source) return { app: item.source, url: item.url }
    return null
  }

  function calendarLinkTitle(item) {
    const target = calendarTarget(item)
    if (!target) return undefined
    const app = SOURCE_NAMES[target.app] || target.app
    return t('Open in {app}', { app })
  }

  function openCalendarItem(event, item) {
    const target = calendarTarget(item)
    if (!target) return
    event.stopPropagation()
    openApp(event, target.app, target.url)
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
      return calCursor.value.toLocaleDateString(i18n.global.locale.value, { month: 'long', year: 'numeric' })
    }
    if (calView.value === 'day') {
      return calCursor.value.toLocaleDateString(i18n.global.locale.value, { weekday: 'long', day: 'numeric', month: 'short' })
    }
    if (calView.value === 'list' && calendarListInfo.value.label) return calendarListInfo.value.label
    const start = startOfWeek(calCursor.value)
    const end = addDays(start, 6)
    const opts = { day: 'numeric', month: 'short' }
    return `${start.toLocaleDateString(i18n.global.locale.value, opts)} – ${end.toLocaleDateString(i18n.global.locale.value, { ...opts, year: 'numeric' })}`
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
          weekday: weekdayLabels.value[(calCursor.value.getDay() + 6) % 7],
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
          weekday: weekdayLabels.value[i],
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
        weekday: weekdayLabels.value[(cursor.getDay() + 6) % 7],
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
    if (inWeek.length || !thisWeek) return { rows: inWeek, label: thisWeek ? t('This week') : '' }
    // ponytail: nothing left this week → the next few releases instead of an empty card
    return { rows: groupSameDay(rows.filter((row) => row.dt >= start)).slice(0, 8), label: t('Coming up') }
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
      const item = { ...row.item, detail: `${span}${t('{count} episodes', { count: row.count })}`, has_file: row.have }
      // A run of episodes opens the series, not the first episode.
      if (row.have && item.series_play_url) item.play_url = item.series_play_url
      return { ...row, item }
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


  watch(
    [calendarWide, calendarPhone],
    () => {
      if (!calViewPicked.value) calView.value = defaultCalView()
    },
    { immediate: true },
  )
  watch(calView, (view) => {
    if (view === 'day') {
      goToday()
      return
    }
    if (view === 'week' || view === 'list') {
      calCursor.value = startOfWeek(calCursor.value)
    }
  }, { immediate: true })

  return { parseWhen, dayKey, formatEventTime, weekdayLabels, calViewPicked, calView, calFilter, selectedDayKey, calCursor, setCalView, selectCalDay, syncCalViewToViewport, eventKind, calendarTarget, calendarLinkTitle, openCalendarItem, calendarRangeLabel, calendarDays, calendarWeeks, calendarListInfo, calendarList, calOnToday, shiftCalendar, goToday, groupSameDay, startOfWeek }
}
