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
const posterUrl = item => `/api/media-discovery/recent/art/${encodeURIComponent(item.id)}`

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { res, data } = await apiJson('/api/media-discovery/recent')
    if (!res.ok) {
      error.value = res.status === 409
        ? 'Sign in again to access your media library.'
        : 'Recently added media is temporarily unavailable.'
      return
    }
    items.value = data.items
  } catch (_) {
    error.value = 'Recently added media is temporarily unavailable.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <MemberPosterRail :title="$t('Newly available')" :has-items="!loading && !error && !!items.length">
    <template #tools>
      <button type="button" class="ui-btn ui-btn-ghost" :disabled="loading" @click="load">{{ $t('Refresh') }}</button>
    </template>
    <MemberPosterTile v-for="item in items" :key="item.id"
                      :title="item.title" :poster="posterUrl(item)" :media-type="item.mediaType" :action-label="item.title"
                      @open="details.open({ ...item, poster: posterUrl(item) }, 'Available')" />
    <template #status>
      <p v-if="loading" class="home-muted" role="status">{{ $t('Loading recent titles…') }}</p>
      <p v-else-if="error" class="home-muted" role="alert">{{ $t(error) }}</p>
      <p v-else-if="!items.length" class="home-muted">{{ $t('No recently added titles in your libraries.') }}</p>
    </template>
  </MemberPosterRail>
  <MemberMediaDetails ref="details" library-title @report-sent="emit('report-sent')" />
</template>
