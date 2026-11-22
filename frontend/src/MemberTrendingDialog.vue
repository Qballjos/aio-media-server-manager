<script setup>
import StreamingAvailability from './StreamingAvailability.vue'
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiJson } from './api.js'
import { youtubeIdFromUrl } from './trailer.js'

const emit = defineEmits(['request'])
const { t } = useI18n()
const dialog = ref(null)
const item = ref(null)
const detail = ref(null)
const pending = ref(false)
const failed = ref(false)
const playing = ref(false)
let version = 0

const title = computed(() => detail.value?.title || item.value?.title)
const trailerId = computed(() => youtubeIdFromUrl(detail.value?.trailer))
const ratings = computed(() => [
  [detail.value?.voteAverage, 'TMDB', false], [detail.value?.imdb, 'IMDb', false],
  [detail.value?.rtCritics, t('Critics'), true], [detail.value?.rtAudience, t('Audience'), true],
].filter(([score]) => score != null).map(([score, label, percent]) => ({
  label, value: percent ? `${score}%` : Number(score).toFixed(1),
})))

async function open(media) {
  const current = ++version
  item.value = media
  detail.value = null
  pending.value = true
  failed.value = false
  playing.value = false
  await nextTick()
  dialog.value.showModal()
  try {
    const { res, data } = await apiJson(`/api/media-discovery/titles/${media.mediaType}/${media.mediaId}`)
    if (!res.ok) throw new Error()
    if (current === version) detail.value = data
  } catch (_) {
    if (current === version) failed.value = true
  } finally {
    if (current === version) pending.value = false
  }
}

function close() {
  version += 1
  playing.value = false
  item.value = null
}

function request() {
  if (!item.value || item.value.available) return
  const selected = item.value
  dialog.value.close()
  emit('request', selected)
}

defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" class="glass-popover home-title-dialog member-trending-dialog"
          :aria-label="$t('Title details')" @close="close">
    <template v-if="item">
      <div class="home-title-head">
        <h3>{{ title }}</h3>
        <button type="button" class="ui-btn ui-btn-ghost" @click="dialog.close()">{{ $t('Close') }}</button>
      </div>
      <div class="home-title-body">
        <img v-if="detail?.poster || item.poster" :src="detail?.poster || item.poster" alt="" class="home-title-poster" referrerpolicy="no-referrer" />
        <span v-else class="home-tile-fallback" aria-hidden="true">{{ title?.charAt(0) }}</span>
        <div>
          <p class="home-title-meta">
            <span class="media-badge">{{ $t(item.mediaType === 'tv' ? 'Series' : 'Movie') }}</span>
            <span>{{ detail?.year || item.detail }}</span>
            <span v-if="item.available">{{ $t('Available') }}</span>
            <span v-else-if="item.partiallyAvailable || item.availableSeasons?.length">{{ $t('Partially available') }}</span>
          </p>
          <p v-if="detail?.overview || item.overview" class="home-title-overview">{{ detail?.overview || item.overview }}</p>
          <p v-else-if="pending" class="home-muted" role="status">{{ $t('Loading title…') }}</p>
          <p v-else-if="failed" class="home-muted" role="alert">{{ $t('Could not load this title from Seerr.') }}</p>
          <p v-else class="home-title-overview home-muted">{{ $t('No overview from Seerr.') }}</p>
          <ul v-if="ratings.length" class="home-title-ratings" :aria-label="$t('Ratings')">
            <li v-for="row in ratings" :key="row.label"><span>{{ row.label }}</span> {{ row.value }}</li>
          </ul>
          <p v-else-if="!pending && !failed" class="home-muted">{{ $t('Seerr did not include ratings.') }}</p>
        </div>
      </div>
      <StreamingAvailability :streaming="detail?.streaming" :series="item.mediaType === 'tv'" @setup="dialog.close()" />
      <div v-if="playing && trailerId" class="home-trailer-frame">
        <iframe :src="`https://www.youtube-nocookie.com/embed/${trailerId}?autoplay=1&rel=0`"
                :title="`${$t('Trailer')} · ${title}`" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen />
      </div>
      <div class="home-request-actions">
        <button v-if="trailerId" type="button" class="ui-btn ui-btn-primary" :aria-pressed="playing"
                @click="playing = !playing">{{ $t('Trailer') }}</button>
        <button v-if="!item.available" type="button" class="ui-btn" @click="request">{{ $t(item.requestableSeasons?.length ? 'Request remaining seasons' : item.mediaType === 'tv' ? 'Request seasons' : 'Request') }}</button>
      </div>
    </template>
  </dialog>
</template>

<style scoped>
.member-trending-dialog { width: min(40rem, calc(100vw - 1.5rem)); max-height: calc(100dvh - 2rem); color: var(--text-main); }
.member-trending-dialog[open] { display: grid; }
.member-trending-dialog::backdrop { background: rgb(0 0 0 / 55%); }
</style>
