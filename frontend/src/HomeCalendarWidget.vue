<script setup>
import { computed, nextTick, onBeforeUnmount, ref, toRef, watch } from 'vue'
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
const emit = defineEmits(['range', 'retry'])
const { locale } = useI18n()
const {
  dayKey, calendarRange, nextCalendarRange, formatEventTime, weekdayLabels, calView, calFilter,
  selectedDayKey, setCalView, selectCalDay, eventKind, calendarTarget, calendarLinkTitle,
  openCalendarItem, calendarRangeLabel, calendarDays, calendarWeeks, calendarList,
  calOnToday, shiftCalendar, goToday,
} = useHomeCalendar({ snapshot: toRef(props, 'snapshot'), calendarWide: toRef(props, 'wide'), calendarPhone: toRef(props, 'phone') })

const requestFilter = ref('all')
const surface = ref(null)
const track = ref(null)
const page = ref(null)
const range = computed(() => calendarRange())
let pageMotion = null
let leaving = null
let scrollFrame = null
let queuedDirection = 0
let dragOffset = 0

function stopMotion() {
  pageMotion?.cancel()
  pageMotion = null
  if (scrollFrame !== null) cancelAnimationFrame(scrollFrame)
  scrollFrame = null
  queuedDirection = 0
  dragOffset = 0
  leaving?.remove()
  leaving = null
  if (track.value) track.value.style.width = ''
  if (page.value) {
    page.value.style.transform = ''
    page.value.style.width = ''
    page.value.style.marginLeft = ''
  }
  if (surface.value) surface.value.scrollLeft = 0
}

function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

async function turnCalendar(direction) {
  if (!nextCalendarRange(direction)) return
  if (leaving) {
    queuedDirection = direction
    return
  }
  const offset = dragOffset
  stopMotion()
  if (reducedMotion() || !page.value) {
    shiftCalendar(direction)
    if (surface.value) surface.value.scrollTop = 0
    return
  }

  const viewport = surface.value
  const width = track.value.clientWidth
  const origin = direction > 0 ? 0 : width
  const destination = width - origin
  const outgoing = page.value.cloneNode(true)
  leaving = outgoing
  outgoing.inert = true
  outgoing.setAttribute('aria-hidden', 'true')
  outgoing.style.cssText = `position:absolute;top:${-viewport.scrollTop}px;left:${origin}px;width:${width}px`
  track.value.append(outgoing)

  track.value.style.width = `${width * 2}px`
  page.value.style.width = `${width}px`
  page.value.style.marginLeft = `${destination}px`
  viewport.scrollTop = 0
  const start = Math.max(0, Math.min(width, origin - offset))
  viewport.scrollLeft = start
  shiftCalendar(direction)
  await nextTick()
  if (leaving !== outgoing) return

  const started = performance.now()
  function scroll(now) {
    const progress = Math.min(1, Math.max(0, (now - started) / 300))
    const eased = 1 - (1 - progress) ** 3
    viewport.scrollLeft = start + (destination - start) * eased
    if (progress < 1) {
      scrollFrame = requestAnimationFrame(scroll)
      return
    }
    const nextDirection = queuedDirection
    stopMotion()
    if (nextDirection) turnCalendar(nextDirection)
  }
  scrollFrame = requestAnimationFrame(scroll)
}

watch([() => range.value.start, () => range.value.days, calView, requestFilter], () => {
  emit('range', range.value, nextCalendarRange(), requestFilter.value === 'own', nextCalendarRange(-1))
}, { immediate: true })
watch([calView, requestFilter], stopMotion)
onBeforeUnmount(stopMotion)

let wheelTime = -Infinity
let wheelDistance = 0
let wheelTurned = false
function scrollCalendar(event) {
  if (event.ctrlKey || event.metaKey) return
  const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY)
  if (!horizontal && !event.shiftKey) return
  const distance = (horizontal ? event.deltaX : event.deltaY) * (event.deltaMode ? 24 : 1)
  if (!distance) return
  event.preventDefault()
  const reversed = Math.abs(distance) >= 24 && Math.sign(distance) !== Math.sign(wheelDistance)
  if (event.timeStamp - wheelTime > 90 || reversed) {
    wheelDistance = 0
    wheelTurned = false
  }
  wheelTime = event.timeStamp
  if (wheelTurned) return
  wheelDistance += distance
  if (Math.abs(wheelDistance) < 40) return
  wheelTurned = true
  turnCalendar(Math.sign(wheelDistance))
}

let touchStart = null
let touchOrigin = 0
let suppressClickUntil = 0
function startSwipe(event) {
  if (event.touches.length !== 1) {
    cancelSwipe()
    return
  }
  touchStart = leaving ? null : event.touches[0]
}

function moveSwipe(event) {
  if (!touchStart || event.touches.length !== 1 || leaving || reducedMotion()) return
  const touch = event.touches[0]
  const x = touch.clientX - touchStart.clientX
  const y = touch.clientY - touchStart.clientY
  if (!dragOffset) {
    if (Math.abs(x) < 8 || Math.abs(x) < Math.abs(y) * 1.5) return
    touchOrigin = dragOffset
    stopMotion()
  }
  const limit = page.value.clientWidth * 0.26
  dragOffset = Math.max(-limit, Math.min(limit, touchOrigin + x))
  page.value.style.transform = `translateX(${dragOffset}px)`
}

function returnToToday() {
  stopMotion()
  goToday()
}

function cancelSwipe() {
  touchStart = null
  if (!dragOffset) return
  const offset = dragOffset
  stopMotion()
  const returning = page.value.animate(
    [{ transform: `translateX(${offset}px)` }, { transform: 'translateX(0)' }],
    { duration: 140, easing: 'ease-out' },
  )
  pageMotion = returning
  returning.finished.then(() => {
    if (pageMotion === returning) stopMotion()
  }).catch(() => {})
}

function finishSwipe(event) {
  if (!touchStart || event.touches.length) return
  const end = event.changedTouches[0]
  const x = touchStart.clientX - end.clientX
  const y = touchStart.clientY - end.clientY
  touchStart = null
  if (Math.abs(x) < 45 || Math.abs(x) < Math.abs(y) * 1.5 || !nextCalendarRange(Math.sign(x))) {
    cancelSwipe()
    return
  }
  suppressClickUntil = event.timeStamp + 350
  turnCalendar(Math.sign(x))
}
function suppressSwipeClick(event) {
  if (event.detail && event.timeStamp < suppressClickUntil) {
    event.preventDefault()
    event.stopPropagation()
  }
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
        <button v-if="!calOnToday" type="button" class="ui-btn ui-btn-ghost" @click="returnToToday">{{ $t('Today') }}</button>
        <UiSelect
          v-if="member"
          v-model="requestFilter"
          class="cal-select"
          variant="inline"
          :aria-label="$t('Calendar releases')"
          :options="[
            { value: 'all', label: $t('All releases') },
            { value: 'own', label: $t('My requests') },
          ]"
        />
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
      </div>
    </div>
    <div ref="surface" class="home-card-body cal-surface" role="group" tabindex="0" :aria-label="$t('Swipe or use arrow keys to change dates')"
         @wheel="scrollCalendar" @touchstart.passive="startSwipe" @touchmove.passive="moveSwipe" @touchend.passive="finishSwipe"
         @touchcancel="cancelSwipe" @click.capture="suppressSwipeClick"
         @keydown.left.self.prevent="turnCalendar(-1)" @keydown.right.self.prevent="turnCalendar(1)">
      <div ref="track" class="cal-track">
        <div ref="page" class="cal-page">
          <div v-if="error">
            <p class="home-muted" role="alert">{{ $t('Could not load your calendar.') }}</p>
            <button type="button" class="ui-btn ui-btn-ghost" @click="emit('retry')">{{ $t('Retry') }}</button>
          </div>
          <p v-else-if="pending" class="home-muted" role="status">{{ $t('Loading calendar…') }}</p>
          <div v-else-if="calView === 'list'" class="cal-list">
            <p v-if="!calendarList.length" class="home-muted">{{ $t('Nothing in this range.') }}</p>
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
                      <span v-if="mediaLabel(row.item)" class="cal-media-type">{{ $t(mediaLabel(row.item)) }}</span>
                      <CalendarMilestones :milestones="row.item.milestones" />
                    </span>
                    <span class="cal-row-meta">{{ [row.item.detail, member ? $t(row.item.has_file ? 'Available' : 'Upcoming') : formatEventTime(row.item.when)].filter(Boolean).join(' · ') }}</span>
                  </span>
                </component>
              </li>
            </ul>
          </div>
          <div v-else class="cal"
               :class="'cal-mode-' + calView"
               role="grid" :aria-label="$t('Upcoming releases calendar')">
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
                          <span v-if="mediaLabel(item)" class="cal-media-type">{{ $t(mediaLabel(item)) }}</span>
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
        </div>
      </div>
      <slot />
    </div>
  </article>
</template>

<style scoped src="./homeCalendarWidget.css"></style>
