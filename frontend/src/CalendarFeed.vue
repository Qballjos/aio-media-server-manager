<script setup>
import { ref } from 'vue'
import HomeCalendarWidget from './HomeCalendarWidget.vue'
import { apiJson } from './api.js'

const props = defineProps({ wide: Boolean, phone: Boolean, member: Boolean })
const snapshot = ref({ calendar: [] })
const loading = ref(true)
const error = ref(false)
const cache = new Map()
let revision = 0

function fetchRange({ start, days }, own) {
  const key = `${start}:${days}:${own}`
  const now = Date.now()
  const cached = cache.get(key)
  if (cached && now < cached.expires) return cached.promise
  const endpoint = props.member ? '/api/media-discovery/calendar' : '/api/homepage/calendar'
  const promise = apiJson(`${endpoint}?start=${start}&days=${days}${own ? '&own_requests=true' : ''}`).then(({ res, data }) => {
    if (!res.ok || !Array.isArray(data.items)) throw new Error()
    if (!data.items.length && data.widgets?.some(note => note.state === 'error')) throw new Error()
    return {
      calendar: props.member ? data.items.map(item => ({
        ...item, has_file: item.available, source: item.kind === 'movie' ? 'radarr' : 'sonarr',
      })) : data.items,
      widgets: data.widgets || [],
    }
  }).catch(err => {
    if (cache.get(key)?.promise === promise) cache.delete(key)
    throw err
  })
  cache.delete(key)
  cache.set(key, { promise, expires: now + 60000 })
  if (cache.size > 12) cache.delete(cache.keys().next().value)
  return promise
}

let visibleRange
let nextRange
let previousRange
let ownRequests = false
async function load(range = visibleRange, next = nextRange, own = ownRequests, previous = previousRange) {
  visibleRange = range
  nextRange = next
  previousRange = previous
  ownRequests = own
  const current = ++revision
  loading.value = true
  error.value = false
  snapshot.value = { calendar: [] }
  try {
    const data = await fetchRange(range, own)
    if (current !== revision) return
    snapshot.value = data
    if (next) fetchRange(next, own).catch(() => {})
    if (previous) fetchRange(previous, own).catch(() => {})
  } catch (_) {
    if (current === revision) error.value = true
  } finally {
    if (current === revision) loading.value = false
  }
}
</script>

<template>
  <HomeCalendarWidget :member="member" :wide="wide" :phone="phone" :snapshot="snapshot" :pending="loading"
                      :error="error" @range="load" @retry="load()">
    <slot :notes="snapshot.widgets || []" />
  </HomeCalendarWidget>
</template>
