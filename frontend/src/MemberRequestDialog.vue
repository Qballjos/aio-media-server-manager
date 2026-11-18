<script setup>
import { nextTick, ref } from 'vue'
import { apiJson } from './api.js'

const emit = defineEmits(['submitted'])
const dialog = ref(null)
const title = ref(null)
const seasons = ref([])
const selected = ref([])
const loading = ref(false)
const submitting = ref(false)
const error = ref('')

async function open(item) {
  title.value = item
  seasons.value = item.requestableSeasons || []
  selected.value = []
  error.value = ''
  loading.value = item.mediaType === 'tv' && !seasons.value.length
  await nextTick()
  dialog.value.showModal()
  if (!loading.value) return
  try {
    const { res, data } = await apiJson(`/api/media-discovery/tv/${item.mediaId}/seasons`)
    if (!res.ok) throw new Error()
    if (title.value === item) seasons.value = data.seasons
  } catch (_) {
    if (title.value === item) error.value = 'Could not load seasons.'
  } finally {
    if (title.value === item) loading.value = false
  }
}

async function submit() {
  if (submitting.value) return
  submitting.value = true
  error.value = ''
  const { mediaType, mediaId } = title.value
  const payload = { mediaType, mediaId }
  if (mediaType === 'tv') payload.seasons = selected.value
  try {
    const { res } = await apiJson('/api/media-discovery/requests', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error()
    dialog.value.close()
    emit('submitted')
  } catch (_) {
    error.value = 'This title could not be requested.'
  } finally {
    submitting.value = false
  }
}

function close() {
  title.value = null
}

defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" class="glass-card request-dialog" :aria-label="$t('Request media')" @close="close"
          @cancel="submitting && $event.preventDefault()">
    <form v-if="title" @submit.prevent="submit">
      <h2>{{ title.title }}</h2>
      <p v-if="loading" role="status">{{ $t('Loading seasons…') }}</p>
      <fieldset v-else-if="title.mediaType === 'tv' && seasons.length">
        <legend>{{ $t(title.requestableSeasons?.length ? 'Select remaining seasons' : 'Select seasons') }}</legend>
        <label v-for="season in seasons" :key="season">
          <input v-model="selected" type="checkbox" :value="season" :disabled="submitting" />
          {{ season === 0 ? $t('Specials') : $t('Season {number}', { number: season }) }}
        </label>
      </fieldset>
      <p v-else-if="title.mediaType === 'tv' && !error">{{ $t('No seasons found.') }}</p>
      <p v-if="error" role="alert" class="ui-alert ui-alert-error">{{ $t(error) }}</p>
      <footer>
        <button type="submit" class="ui-btn ui-btn-primary"
                :disabled="loading || submitting || (title.mediaType === 'tv' && !selected.length)">
          {{ $t('Send request') }}
        </button>
        <button type="button" class="ui-btn ui-btn-ghost" :disabled="submitting" @click="dialog.close()">{{ $t('Cancel') }}</button>
      </footer>
    </form>
  </dialog>
</template>

<style scoped>
.request-dialog { inline-size: min(28rem, calc(100% - 2rem)); max-block-size: calc(100dvh - 2rem); padding: 1.25rem; color: var(--text-main); }
.request-dialog::backdrop { background: rgb(0 0 0 / 55%); }
.request-dialog h2 { margin-block-start: 0; overflow-wrap: anywhere; }
.request-dialog fieldset { border: 1px solid var(--border-subtle); min-inline-size: 0; }
.request-dialog label { display: flex; align-items: center; gap: .5rem; min-block-size: 2.75rem; }
.request-dialog footer { display: flex; flex-wrap: wrap; gap: .5rem; margin-block-start: 1rem; }
</style>
