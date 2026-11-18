<script setup>
import { onMounted, ref } from 'vue'
import MemberMediaDetails from './MemberMediaDetails.vue'
import { apiJson } from './api.js'

const emit = defineEmits(['report-sent'])
const details = ref(null)
const items = ref([])
const loading = ref(false)
const error = ref('')
const missingPosters = ref(new Set())
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
    missingPosters.value = new Set()
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
  <section class="glass-card member-recent" :aria-label="$t('Newly available')">
    <header>
      <h2>{{ $t('Newly available') }}</h2>
      <button type="button" class="ui-btn ui-btn-ghost" :disabled="loading" @click="load">{{ $t('Refresh') }}</button>
    </header>
    <p v-if="loading" role="status">{{ $t('Loading recent titles…') }}</p>
    <p v-else-if="error" role="alert">{{ $t(error) }}</p>
    <p v-else-if="!items.length">{{ $t('No recently added titles in your libraries.') }}</p>
    <ul v-else>
      <li v-for="item in items" :key="item.id">
        <button type="button" class="recent-tile"
                @click="details.open({ ...item, poster: missingPosters.has(item.id) ? '' : posterUrl(item) }, 'Available')">
          <span class="recent-art" aria-hidden="true">
            <img v-if="!missingPosters.has(item.id)" :src="posterUrl(item)" alt="" loading="lazy"
                 @error="missingPosters.add(item.id)" />
            <span v-else>{{ item.title.charAt(0) }}</span>
          </span>
          <strong>{{ item.title }}</strong>
          <span class="recent-kind">{{ $t(item.mediaType === 'tv' ? 'Series' : 'Movie') }}</span>
        </button>
      </li>
    </ul>
    <MemberMediaDetails ref="details" library-title @report-sent="emit('report-sent')" />
  </section>
</template>

<style scoped>
.member-recent { min-inline-size: 0; padding: 1.25rem; }
.member-recent header { display: flex; align-items: center; justify-content: space-between; gap: .5rem .75rem; flex-wrap: wrap; }
.member-recent h2 { margin: 0; }
.member-recent ul { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(7rem, 100%), 1fr)); gap: .875rem; padding: 0; list-style: none; }
.recent-tile { display: grid; gap: .25rem; inline-size: 100%; color: inherit; background: none; border: 0; padding: 0; font: inherit; text-align: start; cursor: pointer; overflow-wrap: anywhere; }
.recent-tile:hover strong { text-decoration: underline; }
.recent-art { display: grid; place-items: center; aspect-ratio: 2 / 3; border-radius: var(--radius-tile); overflow: hidden; background: var(--bg-base); }
.recent-art img { inline-size: 100%; block-size: 100%; object-fit: cover; }
.recent-kind { color: var(--text-muted); }
</style>
