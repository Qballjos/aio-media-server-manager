<script setup>
import { onMounted, ref } from 'vue'
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
  <section class="glass-card member-requests" :aria-label="$t('My requests')">
    <header>
      <h2>{{ $t('My requests') }}</h2>
      <button type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="load({ refresh: true })">{{ $t('Refresh') }}</button>
    </header>
    <p v-if="busy" role="status">{{ $t('Loading requests…') }}</p>
    <p v-else-if="error" role="alert">{{ $t('Could not load your requests.') }}</p>
    <p v-else-if="!items.length && !hasMore">{{ $t('You have no requests yet.') }}</p>
    <ul v-if="items.length">
      <li v-for="item in items" :key="item.id">
        <button type="button" class="request-poster"
                :aria-label="$t('Open request details for {title}', { title: item.title || $t('Request #{id}', { id: item.id }) })"
                @click="details.open(item, statusLabel(item))">
          <img v-if="item.poster" :src="item.poster" alt="" loading="lazy" referrerpolicy="no-referrer" />
          <span v-else aria-hidden="true">{{ item.title?.charAt(0) || '#' }}</span>
        </button>
        <div class="request-summary">
          <strong>{{ item.title || $t('Request #{id}', { id: item.id }) }}</strong>
          <span>{{ $t(statusLabel(item)) }}</span>
        </div>
      </li>
    </ul>
    <button v-if="hasMore" type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="load()">{{ $t('Load more') }}</button>
    <MemberMediaDetails ref="details" @report-sent="emit('report-sent')" />
  </section>
</template>

<style scoped>
.member-requests { min-inline-size: 0; padding: 1.25rem; }
.member-requests header, .member-requests li { display: flex; align-items: center; justify-content: space-between; gap: .5rem .75rem; flex-wrap: wrap; }
.member-requests h2 { margin: 0; }
.member-requests ul { padding: 0; list-style: none; }
.member-requests li { padding-block: .625rem; border-block-start: 1px solid var(--border-subtle); overflow-wrap: anywhere; }
.member-requests li { justify-content: start; flex-wrap: nowrap; }
.request-poster { display: grid; place-items: center; flex: 0 0 auto; inline-size: 3rem; aspect-ratio: 2 / 3; background: var(--bg-base); border: 1px solid var(--border-subtle); border-radius: .5rem; padding: 0; color: var(--text-main); overflow: hidden; cursor: pointer; }
.request-poster img { inline-size: 100%; block-size: 100%; object-fit: cover; }
.request-poster:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.request-summary { display: grid; gap: .25rem; min-inline-size: 0; }
.member-requests li span { color: var(--text-muted); }
</style>
