<script setup>
import { computed, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import CalendarMilestones from './CalendarMilestones.vue'
import UiSelect from './UiSelect.vue'
import { useHomeCalendar } from './composables/useHomeCalendar.js'

const props = defineProps({
  snapshot: { type: Object, required: true },
  wide: Boolean,
  phone: Boolean,
  pending: Boolean,
  error: Boolean,
  member: Boolean,
})
const emit = defineEmits(['range'])
const { locale } = useI18n()
const {
  dayKey, startOfWeek, calCursor, formatEventTime, weekdayLabels, calView, calFilter,
  selectedDayKey, setCalView, selectCalDay, eventKind, calendarTarget, calendarLinkTitle,
  openCalendarItem, calendarRangeLabel, calendarDays, calendarWeeks, calendarList,
  calOnToday, shiftCalendar, goToday,
} = useHomeCalendar({ snapshot: toRef(props, 'snapshot'), calendarWide: toRef(props, 'wide'), calendarPhone: toRef(props, 'phone') })

const range = computed(() => ({
  start: calView.value === 'list' ? dayKey(startOfWeek(calCursor.value)) : calendarDays.value[0].key,
  days: calView.value === 'list' ? 7 : calendarDays.value.length,
}))
if (props.member) {
  watch([() => range.value.start, () => range.value.days], ([start, days]) => emit('range', start, days), { immediate: true })
}

function chipDay(dt) {
  return dt.toLocaleDateString(locale.value, { weekday: 'short' }).replace('.', '').toUpperCase()
}

function isToday(dt) {
  return dayKey(dt) === dayKey(new Date())
}

function mediaLabel(item) {
  const kind = String(item.mediaType || item.kind || item.source || '').toLowerCase()
  if (['tv', 'series', 'episode', 'season', 'sonarr'].includes(kind)) return 'Series'
  if (['movie', 'radarr'].includes(kind)) return 'Movie'
  return ''
}
</script>

<template>
  <article class="home-card glass-card home-card-calendar" role="region" :aria-label="$t('Calendar')">
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
            { value: 'missing', label: $t(member ? 'Upcoming' : 'Not downloaded') },
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
      <p v-if="error" class="home-muted" role="alert">{{ $t('Could not load your calendar.') }}</p>
      <p v-else-if="member && pending" class="home-muted" role="status">{{ $t('Loading calendar…') }}</p>
      <div v-else-if="calView === 'list'" class="cal-list">
        <div v-if="!calendarList.length && pending" aria-hidden="true">
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
                  <span v-if="mediaLabel(row.item)" class="media-badge">{{ $t(mediaLabel(row.item)) }}</span>
                  <CalendarMilestones :milestones="row.item.milestones" />
                </span>
                <span class="cal-row-meta">{{ [row.item.detail, member ? $t(row.item.has_file ? 'Available' : 'Upcoming') : formatEventTime(row.item.when)].filter(Boolean).join(' · ') }}</span>
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
                      <span class="cal-event-time">{{ member ? $t(item.has_file ? 'Available' : 'Upcoming') : formatEventTime(item.when) }}</span>
                      <span v-if="mediaLabel(item)" class="media-badge">{{ $t(mediaLabel(item)) }}</span>
                    </span>
                    <span v-if="item.milestones?.length" class="cal-event-title">
                      <strong>{{ item.title }}</strong>
                      <CalendarMilestones :milestones="item.milestones" />
                    </span>
                    <strong v-else>{{ item.title }}</strong>
                    <span v-if="item.detail" class="cal-event-detail">{{ item.detail }}</span>
                  </component>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
      <slot />
    </div>
  </article>
</template>

<style scoped src="./homeCalendarWidget.css"></style>
