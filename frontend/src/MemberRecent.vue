<script setup>
import { onMounted, ref } from 'vue'
import MemberPosterRail from './MemberPosterRail.vue'
import MemberPosterTile from './MemberPosterTile.vue'
import MemberMediaDetails from './MemberMediaDetails.vue'
import { apiJson } from './api.js'

const emit = defineEmits(['report-sent'])
const details = ref(null)
const items = ref([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(false)
let page = 0
const posterUrl = item => `/api/media-discovery/recent/art/${encodeURIComponent(item.id)}`

async function load() {
  if (loading.value) return
  const nextPage = page + 1
  loading.value = true
  error.value = ''
  try {
    const { res, data } = await apiJson(`/api/media-discovery/recent?page=${nextPage}`)
    if (!res.ok) {
      error.value = res.status === 409
        ? 'Sign in again to access your media library.'
        : 'Recently added media is temporarily unavailable.'
      return
    }
    const seen = new Set(items.value.map(item => item.id))
    items.value = [...items.value, ...data.items.filter(item => !seen.has(item.id))]
    page = nextPage
    hasMore.value = data.has_more === true
  } catch (_) {
    error.value = 'Recently added media is temporarily unavailable.'
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
</script>

<template>
  <MemberPosterRail :title="$t('Newly available')" :has-items="!!items.length"
                    :auto-load="hasMore && !loading && !error" @load-more="load()">
    <MemberPosterTile v-for="item in items" :key="item.id"
                      :title="item.title" :poster="posterUrl(item)" :media-type="item.mediaType" :action-label="item.title"
                      @open="details.open({ ...item, poster: posterUrl(item) }, 'Available')" />
    <template #status>
      <p v-if="loading" class="home-muted" role="status">{{ $t('Loading recent titles…') }}</p>
      <template v-else-if="error">
        <p class="home-muted" role="alert">{{ $t(error) }}</p>
        <button type="button" class="ui-btn ui-btn-ghost" @click="load()">{{ $t('Retry') }}</button>
      </template>
      <p v-else-if="!items.length && !hasMore" class="home-muted">{{ $t('No recently added titles in your libraries.') }}</p>
    </template>
  </MemberPosterRail>
  <MemberMediaDetails ref="details" library-title @report-sent="emit('report-sent')" />
</template>
