<script setup>
import { ref } from 'vue'
import HomeCalendarWidget from './HomeCalendarWidget.vue'
import { apiJson } from './api.js'

defineProps({ wide: Boolean, phone: Boolean })
const snapshot = ref({ calendar: [] })
const loading = ref(true)
const error = ref(false)
let revision = 0

async function load(start, days) {
  const current = ++revision
  loading.value = true
  error.value = false
  snapshot.value = { calendar: [] }
  try {
    const { res, data } = await apiJson(`/api/media-discovery/calendar?start=${start}&days=${days}`)
    if (!res.ok) throw new Error()
    if (current === revision) {
      snapshot.value = { calendar: data.items.map(item => ({ ...item, has_file: item.available, source: item.kind === 'movie' ? 'radarr' : 'sonarr' })) }
    }
  } catch (_) {
    if (current === revision) error.value = true
  } finally {
    if (current === revision) loading.value = false
  }
}
</script>

<template>
  <HomeCalendarWidget member :wide="wide" :phone="phone" :snapshot="snapshot" :pending="loading" :error="error" @range="load" />
</template>
