<script setup>
import { onMounted, ref } from 'vue'
import MemberPosterRail from './MemberPosterRail.vue'
import MemberPosterTile from './MemberPosterTile.vue'
import MemberMediaDetails from './MemberMediaDetails.vue'
import { apiJson } from './api.js'

const emit = defineEmits(['report-sent'])
const details = ref(null)
const items = ref([])
const busy = ref(false)
const error = ref(false)
const hasMore = ref(false)
const statusLabels = {
  pending: 'Waiting for approval',
  approved: 'Approved',
  declined: 'Declined',
  unknown: 'Unknown status',
}
function statusLabel(item) {
  if (item.status === 'approved' && item.available) return 'Available'
  return statusLabels[item.status] || statusLabels.unknown
}

let page = 0

async function load({ refresh = false } = {}) {
  if (busy.value) return
  busy.value = true
  error.value = false
  const nextPage = refresh ? 1 : page + 1
  try {
    const { res, data } = await apiJson(`/api/media-discovery/requests?page=${nextPage}`)
    if (!res.ok) throw new Error()
    if (refresh) items.value = []
    const seen = new Set(items.value.map(item => item.id))
    items.value.push(...data.items.filter(item => !seen.has(item.id)))
    page = nextPage
    hasMore.value = data.has_more
  } catch (_) {
    error.value = true
  } finally {
    busy.value = false
  }
}

onMounted(() => load())
</script>

<template>
  <MemberPosterRail :title="$t('My requests')" :has-items="!!items.length">
    <template #tools>
      <button type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="load({ refresh: true })">{{ $t('Refresh') }}</button>
      <button v-if="hasMore" type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="load()">{{ $t('Load more') }}</button>
    </template>
    <MemberPosterTile v-for="item in items" :key="item.id"
                      :title="item.title || $t('Request #{id}', { id: item.id })" :poster="item.poster" :media-type="item.mediaType"
                      :meta="$t(statusLabel(item))" :tone="statusLabel(item) === 'Available' ? 'is-available' : 'is-requested'"
                      :action-label="$t('Open request details for {title}', { title: item.title || $t('Request #{id}', { id: item.id }) })"
                      @open="details.open(item, statusLabel(item))" />
    <template #status>
      <p v-if="busy" class="home-muted" role="status">{{ $t('Loading requests…') }}</p>
      <p v-else-if="error" class="home-muted" role="alert">{{ $t('Could not load your requests.') }}</p>
      <p v-else-if="!items.length && !hasMore" class="home-muted">{{ $t('You have no requests yet.') }}</p>
    </template>
  </MemberPosterRail>
  <MemberMediaDetails ref="details" @report-sent="emit('report-sent')" />
</template>
