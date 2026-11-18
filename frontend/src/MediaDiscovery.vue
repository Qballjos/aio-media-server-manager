<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import HomeGreeting from './HomeGreeting.vue'
import HomeGrid from './HomeGrid.vue'
import MemberPosterRail from './MemberPosterRail.vue'
import MemberPosterTile from './MemberPosterTile.vue'
import { homeEditing, viewportBp } from './homeLayout.js'
import { BREAKPOINTS, collapseEmptyRows, fitItem, resolve } from './homeGrid.js'
import { MEMBER_WIDGETS, addMemberWidget, defaultMemberLayout, memberLayoutFor, readMemberLayouts, saveMemberLayouts } from './memberHomeLayout.js'
import MemberUtilityWidgets from './MemberUtilityWidgets.vue'
import MemberTrendingDialog from './MemberTrendingDialog.vue'
import MemberRequestDialog from './MemberRequestDialog.vue'
import MemberCalendar from './MemberCalendar.vue'
import MemberRecent from './MemberRecent.vue'
import MemberRequests from './MemberRequests.vue'
import { t } from './i18n/index.js'
import { apiJson } from './api.js'

const props = defineProps({ accountId: { type: String, required: true }, displayName: String })
const layouts = ref(readMemberLayouts(props.accountId))
const layout = computed(() => memberLayoutFor(layouts.value, viewportBp.value))
const calendarPhone = computed(() => viewportBp.value === 'phone')
const calendarWide = computed(() => {
  const item = layout.value.find(entry => entry.id === 'calendar')
  return !!item && !calendarPhone.value && item.w * 12 >= 7 * BREAKPOINTS[viewportBp.value].cols
})
const missingWidgets = computed(() => Object.keys(MEMBER_WIDGETS).filter(id => !layout.value.some(item => item.id === id)))
const editingWidget = ref('')
function saveLayout(next) {
  const upgraded = Object.fromEntries(
    Object.keys(BREAKPOINTS).filter(bp => Array.isArray(layouts.value[bp])).map(bp => [bp, memberLayoutFor(layouts.value, bp)]),
  )
  layouts.value = { ...upgraded, greetingAdded: true, [viewportBp.value]: collapseEmptyRows(next) }
  saveMemberLayouts(props.accountId, layouts.value)
}
function removeWidget(id) {
  saveLayout(layout.value.filter(item => item.id !== id))
  editingWidget.value = ''
}
function resizeWidget(w, h) {
  const item = layout.value.find(row => row.id === editingWidget.value)
  if (!item) return
  const cols = BREAKPOINTS[viewportBp.value].cols
  saveLayout(resolve(layout.value, item.id, fitItem({ ...item, w, h }, cols, MEMBER_WIDGETS), cols))
}
onUnmounted(() => { homeEditing.value = false })

const query = ref('')
const searchInput = ref(null)
let searchVersion = 0
const requestDialog = ref(null)
const trendingDialog = ref(null)
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
let trendingVersion = 0

function seasonLabel(numbers) {
  return numbers.map(number => number === 0 ? t('Specials') : t('Season {number}', { number })).join(', ')
}

function clearSearch() {
  searchVersion += 1
  query.value = ''
  searched.value = false
  searchBusy.value = false
  searchError.value = false
  results.value = []
  searchInput.value?.focus()
}

async function search() {
  const term = query.value.trim()
  if (searchBusy.value || term.length < 2) return
  const current = ++searchVersion
  searchBusy.value = true
  searchError.value = false
  searched.value = false
  results.value = []
  try {
    const { res, data } = await apiJson(`/api/media-discovery/search?q=${encodeURIComponent(term)}`)
    if (!res.ok) throw new Error()
    if (current !== searchVersion) return
    results.value = data.items
    searched.value = true
  } catch (_) {
    if (current === searchVersion) searchError.value = true
  } finally {
    if (current === searchVersion) searchBusy.value = false
  }
}

async function loadTrending({ replace = false } = {}) {
  if (trendingBusy.value && !replace) return
  const current = ++trendingVersion
  const nextPage = replace ? 1 : page + 1
  trendingBusy.value = true
  trendingError.value = false
  if (replace) {
    trending.value = []
    page = 0
  }
  try {
    const { res, data } = await apiJson(`/api/media-discovery/trending?page=${nextPage}`)
    if (!res.ok) throw new Error()
    if (current !== trendingVersion) return
    const seen = new Set(trending.value.map(item => `${item.mediaType}:${item.mediaId}`))
    trending.value.push(...data.items.filter(item => !seen.has(`${item.mediaType}:${item.mediaId}`)))
    page = nextPage
    hasMore.value = data.has_more
  } catch (_) {
    if (current === trendingVersion) trendingError.value = true
  } finally {
    if (current === trendingVersion) trendingBusy.value = false
  }
}

function onRequestSubmitted() {
  requestRevision.value += 1
  loadTrending({ replace: true })
}

onMounted(() => loadTrending())
</script>

<template>
  <div class="member-discovery">
    <div v-if="homeEditing" class="glass-card home-card member-edit-controls">
      <div class="home-widget-head">
        <h3>{{ $t('Edit the Home layout') }}</h3>
        <button type="button" class="ui-btn ui-btn-ghost" @click="saveLayout(defaultMemberLayout(viewportBp))">{{ $t('Reset to defaults') }}</button>
      </div>
      <div v-if="missingWidgets.length" class="member-edit-actions">
        <span>{{ $t('Add widget') }}</span>
        <button v-for="id in missingWidgets" :key="id" type="button" class="ui-btn ui-btn-ghost"
                @click="saveLayout(addMemberWidget(layout, id, viewportBp))">{{ $t(MEMBER_WIDGETS[id].label) }}</button>
      </div>
      <div v-if="editingWidget" class="member-edit-actions">
        <strong>{{ $t(MEMBER_WIDGETS[editingWidget].label) }}</strong>
        <button v-for="[w, h, label] in (MEMBER_WIDGETS[editingWidget].presets || [[4, 2, 'Small'], [6, 2, 'Half'], [12, 3, 'Full']])"
                :key="label" type="button" class="ui-btn ui-btn-ghost" @click="resizeWidget(w, h)">{{ $t(label) }}</button>
        <button type="button" class="ui-btn ui-btn-ghost" @click="editingWidget = ''">{{ $t('Close') }}</button>
      </div>
    </div>
    <p v-if="requestRevision" class="home-muted" role="status">{{ $t('Request sent.') }}</p>
    <HomeGrid :layout="layout" :bp="viewportBp" :editing="homeEditing" :widget-specs="MEMBER_WIDGETS"
              :raise="!homeEditing && (searched || searchBusy || searchError) ? 'searchbar' : ''"
              @change="saveLayout" @remove="removeWidget" @open="editingWidget = $event">
      <template #greeting><HomeGreeting :name="displayName" /></template>
      <template #searchbar>
        <section class="home-search member-search" :aria-label="$t('Search')">
          <form class="home-search-pill glass-pill" role="search" @submit.prevent="search">
            <svg class="home-search-mark" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>
            <input ref="searchInput" v-model="query" class="home-search-input" type="search" maxlength="160" enterkeyhint="search"
                   :aria-label="$t('Search films and series')" :placeholder="$t('Search movies and TV to request')" />
            <button v-if="query" type="button" class="home-search-clear" :aria-label="$t('Clear search')" @click="clearSearch">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>
            <button class="ui-btn ui-btn-primary home-search-btn" type="submit" :aria-label="$t('Search')"
                    :disabled="searchBusy || query.trim().length < 2">
              <svg class="home-search-go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>
              <span>{{ $t('Search') }}</span>
            </button>
          </form>
          <div v-if="!homeEditing && (searched || searchBusy || searchError)" class="home-hero-results glass-card">
            <div class="home-results-scroll">
              <div class="home-widget-head">
                <h3>{{ $t('Search') }}</h3>
                <button type="button" class="ui-btn ui-btn-ghost" @click="clearSearch">{{ $t('Close') }}</button>
              </div>
              <p v-if="searchBusy" class="home-muted" role="status">{{ $t('Searching…') }}</p>
              <p v-else-if="searchError" class="home-muted" role="alert">{{ $t('Media search is temporarily unavailable.') }}</p>
              <p v-else-if="!results.length" class="home-muted">{{ $t('No matching titles.') }}</p>
              <ul v-else class="home-results">
                <li v-for="item in results" :key="`${item.mediaType}:${item.mediaId}`" class="home-result">
                  <img v-if="item.poster" :src="item.poster" alt="" loading="lazy" referrerpolicy="no-referrer" class="home-poster" />
                  <div class="home-result-body">
                    <strong>{{ item.title }}</strong>
                    <span>{{ $t(item.mediaType === 'tv' ? 'TV' : 'Movie') }} {{ item.year?.slice(0, 4) }}</span>
                    <span v-if="item.available" class="home-status is-available">{{ $t('Available') }}</span>
                    <span v-else-if="item.availableSeasons?.length" class="home-status is-partial">
                      {{ $t('Available seasons: {seasons}', { seasons: seasonLabel(item.availableSeasons) }) }}
                    </span>
                  </div>
                  <button v-if="!item.available" type="button" class="ui-btn ui-btn-primary" @click="requestDialog.open(item)">
                    {{ $t('Request') }}
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </section>
      </template>
      <template #requests><MemberRequests :key="requestRevision" @report-sent="reportRevision += 1" /></template>
      <template #recent><MemberRecent @report-sent="reportRevision += 1" /></template>
      <template #calendar><MemberCalendar :wide="calendarWide" :phone="calendarPhone" /></template>
      <template #limits><MemberUtilityWidgets :key="requestRevision" widget="limits" /></template>
      <template #support><MemberUtilityWidgets :key="reportRevision" widget="support" /></template>
      <template #trending>
        <MemberPosterRail :title="$t('Trending')" :has-items="!!trending.length"
                          :auto-load="hasMore && !trendingBusy && !trendingError" @load-more="loadTrending()">
          <MemberPosterTile v-for="item in trending" :key="`${item.mediaType}:${item.mediaId}`"
                            :title="item.title" :poster="item.poster" :media-type="item.mediaType"
                            :meta="item.availableSeasons?.length ? $t('Partially available') : item.detail"
                            :tone="item.availableSeasons?.length ? 'is-partial' : ''"
                            :action-label="item.title"
                            @open="trendingDialog.open(item)" />
          <template #status>
            <p v-if="trendingBusy" class="home-muted" role="status">{{ $t('Loading Trending…') }}</p>
            <template v-else-if="trendingError">
              <p class="home-muted" role="alert">{{ $t('Trending is temporarily unavailable.') }}</p>
              <button type="button" class="ui-btn ui-btn-ghost" @click="loadTrending()">{{ $t('Retry') }}</button>
            </template>
            <p v-else-if="!trending.length && !hasMore" class="home-muted">{{ $t('No trending titles.') }}</p>
          </template>
        </MemberPosterRail>
      </template>
    </HomeGrid>
    <MemberTrendingDialog ref="trendingDialog" @request="requestDialog.open($event)" />
    <MemberRequestDialog ref="requestDialog" @submitted="onRequestSubmitted" />
  </div>
</template>

<style scoped>
.member-discovery { display: grid; gap: 1rem; min-width: 0; }
.member-edit-controls { container-type: inline-size; height: auto; }
.member-edit-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
.member-search .home-search-pill { padding-inline-start: 1rem; }
</style>
