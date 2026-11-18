<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiJson } from './api.js'
import { useHomeCalendar } from './composables/useHomeCalendar.js'

const { locale } = useI18n()
const snapshot = ref({ calendar: [] })
const { calCursor, groupSameDay, parseWhen, dayKey, shiftCalendar, goToday } = useHomeCalendar({
  snapshot, calendarWide: ref(false),
})
const loading = ref(false)
const error = ref(false)
const week = computed(() => {
  const end = new Date(calCursor.value)
  end.setDate(end.getDate() + 6)
  return new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'short' }).formatRange(calCursor.value, end)
})
const calendarList = computed(() => groupSameDay(snapshot.value.calendar
  .map(item => ({ item, dt: parseWhen(item.when) }))
  .filter(row => row.dt)
  .sort((first, second) => first.dt - second.dt)))
let revision = 0

async function load(start) {
  const current = ++revision
  loading.value = true
  error.value = false
  snapshot.value = { calendar: [] }
  try {
    const { res, data } = await apiJson(`/api/media-discovery/calendar?start=${start}`)
    if (!res.ok) throw new Error()
    if (current === revision) {
      snapshot.value = { calendar: data.items.map(item => ({ ...item, has_file: item.available })) }
    }
  } catch (_) {
    if (current === revision) error.value = true
  } finally {
    if (current === revision) loading.value = false
  }
}

watch(() => dayKey(calCursor.value), load, { immediate: true })
</script>

<template>
  <section class="glass-card home-card home-card-calendar" :aria-label="$t('Calendar')">
    <header class="cal-head">
      <div>
        <h3>{{ $t('Calendar') }}</h3>
        <span class="home-muted">{{ week }}</span>
      </div>
      <div class="home-rail-tools">
        <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Previous')" @click="shiftCalendar(-1)">‹</button>
        <button type="button" class="ui-btn ui-btn-ghost" @click="goToday">{{ $t('Today') }}</button>
        <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Next')" @click="shiftCalendar(1)">›</button>
      </div>
    </header>
    <div class="home-card-body cal-list">
      <p v-if="loading" class="home-muted" role="status">{{ $t('Loading calendar…') }}</p>
      <p v-else-if="error" class="home-muted" role="alert">{{ $t('Could not load your calendar.') }}</p>
      <p v-else-if="!calendarList.length" class="home-muted">{{ $t('No releases in your calendar this week.') }}</p>
      <ul v-else>
        <li v-for="({ item, dt }, index) in calendarList" :key="`${item.when}:${item.title}:${index}`"
            class="cal-row" :data-source="item.kind === 'movie' ? 'radarr' : 'sonarr'"
            :class="{ 'is-have': item.has_file, 'is-today': dayKey(dt) === dayKey(new Date()) }">
          <div class="cal-row-link">
            <time class="cal-chip" :datetime="dayKey(dt)">
              <span>{{ dt.toLocaleDateString(locale, { weekday: 'short' }) }}</span>
              <strong>{{ dt.getDate() }}</strong>
            </time>
            <span class="cal-row-body">
              <strong>{{ item.title }}</strong>
              <span class="cal-row-meta">{{ [item.detail, $t(item.has_file ? 'Available' : 'Upcoming')].filter(Boolean).join(' · ') }}</span>
            </span>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>
