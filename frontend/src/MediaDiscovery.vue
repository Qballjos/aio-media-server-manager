<script setup>
import { onMounted, ref } from 'vue'
import MemberUtilityWidgets from './MemberUtilityWidgets.vue'
import MemberRequestDialog from './MemberRequestDialog.vue'
import MemberRecent from './MemberRecent.vue'
import MemberRequests from './MemberRequests.vue'
import { t } from './i18n/index.js'
import { apiJson } from './api.js'

const query = ref('')
const requestDialog = ref(null)
const requestRevision = ref(0)
const reportRevision = ref(0)
const results = ref([])
const trending = ref([])
const searched = ref(false)
const searchBusy = ref(false)
const trendingBusy = ref(false)
const searchError = ref(false)
const trendingError = ref(false)
const hasMore = ref(false)
let page = 0

function seasonLabel(numbers) {
  return numbers.map(number => number === 0 ? t('Specials') : t('Season {number}', { number })).join(', ')
}

async function search() {
  const term = query.value.trim()
  if (searchBusy.value || term.length < 2) return
  searchBusy.value = true
  searchError.value = false
  searched.value = false
  results.value = []
  try {
    const { res, data } = await apiJson(`/api/media-discovery/search?q=${encodeURIComponent(term)}`)
    if (!res.ok) throw new Error()
    results.value = data.items
    searched.value = true
  } catch (_) {
    searchError.value = true
  } finally {
    searchBusy.value = false
  }
}

async function loadTrending() {
  if (trendingBusy.value) return
  trendingBusy.value = true
  trendingError.value = false
  try {
    const { res, data } = await apiJson(`/api/media-discovery/trending?page=${page + 1}`)
    if (!res.ok) throw new Error()
    const seen = new Set(trending.value.map(item => `${item.mediaType}:${item.mediaId}`))
    trending.value.push(...data.items.filter(item => !seen.has(`${item.mediaType}:${item.mediaId}`)))
    page += 1
    hasMore.value = data.has_more
  } catch (_) {
    trendingError.value = true
  } finally {
    trendingBusy.value = false
  }
}

onMounted(loadTrending)
</script>

<template>
  <div class="member-discovery">
    <section class="glass-card discovery-panel" :aria-label="$t('Search')">
      <h2>{{ $t('Search') }}</h2>
      <form class="discovery-search" role="search" @submit.prevent="search">
        <input v-model="query" class="ui-input" type="search" maxlength="160"
               :aria-label="$t('Search films and series')" :placeholder="$t('Search films and series')" />
        <button class="ui-btn ui-btn-primary" type="submit"
                :disabled="searchBusy || query.trim().length < 2">{{ $t('Search') }}</button>
      </form>
      <p v-if="searchBusy" role="status">{{ $t('Searching…') }}</p>
      <p v-else-if="searchError" role="alert">{{ $t('Media search is temporarily unavailable.') }}</p>
      <p v-else-if="searched && !results.length" role="status">{{ $t('No matching titles.') }}</p>
      <ul v-if="results.length" class="discovery-grid">
        <li v-for="item in results" :key="`${item.mediaType}:${item.mediaId}`">
          <img v-if="item.poster" :src="item.poster" alt="" loading="lazy" referrerpolicy="no-referrer" />
          <strong>{{ item.title }}</strong>
          <span>{{ item.year ? item.year.slice(0, 4) + ' · ' : '' }}{{ $t(item.mediaType === 'tv' ? 'Series' : 'Movie') }}</span>
          <span v-if="item.availableSeasons?.length" class="discovery-available">
            {{ $t('Available seasons: {seasons}', { seasons: seasonLabel(item.availableSeasons) }) }}
          </span>
          <span v-if="item.available" class="discovery-available">{{ $t('Available') }}</span>
          <button v-else type="button" class="ui-btn ui-btn-ghost"
                  :aria-label="$t('Request {title}', { title: item.title })"
                  @click="requestDialog.open(item)">{{ $t('Request') }}</button>
        </li>
      </ul>
    </section>

    <p v-if="requestRevision" role="status">{{ $t('Request sent.') }}</p>
    <MemberRequests :key="requestRevision" @report-sent="reportRevision += 1" />
    <MemberUtilityWidgets :key="`${requestRevision}:${reportRevision}`" />

    <MemberRecent @report-sent="reportRevision += 1" />

    <section class="glass-card discovery-panel" :aria-label="$t('Trending')">
      <h2>{{ $t('Trending') }}</h2>
      <ul v-if="trending.length" class="discovery-grid">
        <li v-for="item in trending" :key="`${item.mediaType}:${item.mediaId}`">
          <img v-if="item.poster" :src="item.poster" alt="" loading="lazy" referrerpolicy="no-referrer" />
          <strong>{{ item.title }}</strong>
          <span>{{ $t(item.mediaType === 'tv' ? 'Series' : 'Movie') }}</span>
          <span v-if="item.availableSeasons?.length" class="discovery-available">
            {{ $t('Available seasons: {seasons}', { seasons: seasonLabel(item.availableSeasons) }) }}
          </span>
          <span v-if="item.available" class="discovery-available">{{ $t('Available') }}</span>
          <button v-else type="button" class="ui-btn ui-btn-ghost"
                  :aria-label="$t('Request {title}', { title: item.title })"
                  @click="requestDialog.open(item)">{{ $t('Request') }}</button>
        </li>
      </ul>
      <p v-if="trendingBusy" role="status">{{ $t('Loading Trending…') }}</p>
      <p v-else-if="trendingError" role="alert">{{ $t('Trending is temporarily unavailable.') }}</p>
      <p v-else-if="!trending.length && !hasMore">{{ $t('No trending titles.') }}</p>
      <button v-if="hasMore || trendingError" type="button" class="ui-btn ui-btn-ghost"
              :disabled="trendingBusy" @click="loadTrending">{{ trendingError ? $t('Retry') : $t('Load more') }}</button>
    </section>
    <MemberRequestDialog ref="requestDialog" @submitted="requestRevision += 1" />
  </div>
</template>

<style scoped>
.member-discovery { display: grid; gap: 1rem; max-inline-size: 72rem; margin-inline: auto; }
.discovery-panel { min-inline-size: 0; padding: 1.25rem; }
.discovery-panel h2 { margin-block-start: 0; }
.discovery-search { display: flex; flex-wrap: wrap; gap: .625rem; }
.discovery-search input { flex: 1 1 14rem; min-inline-size: 0; }
.discovery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(8rem, 100%), 1fr)); gap: .875rem; list-style: none; padding: 0; }
.discovery-grid li { display: grid; align-content: start; gap: .3rem; min-inline-size: 0; overflow-wrap: anywhere; }
.discovery-grid img { inline-size: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: var(--radius-tile); }
.discovery-grid span { color: var(--text-muted); }
.discovery-grid .discovery-available { color: var(--color-success); }
</style>
