<script setup>
import { onMounted, ref } from 'vue'
import { apiJson } from './api.js'
import MemberPosterRail from './MemberPosterRail.vue'
import MemberPosterTile from './MemberPosterTile.vue'

const items = ref([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { res, data } = await apiJson('/api/media-discovery/resume')
    if (!res.ok) {
      error.value = res.status === 409
        ? 'Sign in again to access your media library.'
        : 'Could not load Continue watching.'
      return
    }
    items.value = data.items
  } catch (_) {
    error.value = 'Could not load Continue watching.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <MemberPosterRail :title="$t('Continue watching')" :has-items="!!items.length">
    <MemberPosterTile v-for="item in items" :key="item.id" :title="item.title"
                      :poster="`/api/media-discovery/recent/art/${encodeURIComponent(item.posterId)}`"
                      :media-type="item.mediaType" :meta="item.detail" :href="item.playUrl"
                      :action-label="$t('Open {title} to continue watching', { title: item.title })" />
    <template #status>
      <p v-if="loading" class="home-muted" role="status">{{ $t('Loading…') }}</p>
      <template v-else-if="error">
        <p class="home-muted" role="alert">{{ $t(error) }}</p>
        <button type="button" class="ui-btn ui-btn-ghost" @click="load">{{ $t('Retry') }}</button>
      </template>
      <p v-else-if="!items.length" class="home-muted">{{ $t('Nothing to continue watching.') }}</p>
    </template>
  </MemberPosterRail>
</template>
