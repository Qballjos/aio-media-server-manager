<script setup>
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiJson } from './api.js'

const props = defineProps({ libraryTitle: Boolean })
const emit = defineEmits(['report-sent'])
const { t, locale } = useI18n()
const dialog = ref(null)
const request = ref(null)
const status = ref('')
const description = ref('')
const busy = ref(false)
const error = ref(false)
const sent = ref(false)
const reference = computed(() => request.value && !props.libraryTitle ? t('Request #{id}', { id: request.value.id }) : '')
const title = computed(() => request.value?.title || reference.value)
const createdAt = computed(() => {
  if (!request.value?.createdAt) return ''
  const date = new Date(request.value.createdAt)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(locale.value, {
    dateStyle: 'medium', timeStyle: 'short',
  })
})
function formatSeasons(numbers) {
  return (numbers || []).map(number => number === 0 ? t('Specials') : t('Season {number}', { number })).join(', ')
}

const seasons = computed(() => formatSeasons(request.value?.seasons))
const availableSeasons = computed(() => formatSeasons(request.value?.availableSeasons))

async function open(item, statusLabel) {
  request.value = item
  status.value = statusLabel
  description.value = ''
  error.value = false
  sent.value = false
  await nextTick()
  dialog.value.showModal()
}

async function sendReport() {
  if (busy.value || sent.value || !description.value.trim()) return
  busy.value = true
  error.value = false
  try {
    const { res } = await apiJson('/api/support', {
      method: 'POST',
      body: JSON.stringify({
        subject: title.value.slice(0, 160),
        message: [reference.value, description.value.trim()].filter(Boolean).join('\n\n'),
      }),
    })
    if (!res.ok) throw new Error()
    sent.value = true
    emit('report-sent')
  } catch (_) {
    error.value = true
  } finally {
    busy.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" class="glass-dialog request-details" :aria-label="$t(libraryTitle ? 'Title details' : 'Request details')"
          @close="request = null" @cancel="busy && $event.preventDefault()">
    <template v-if="request">
      <header>
        <img v-if="request.poster" :src="request.poster" alt="" referrerpolicy="no-referrer" @error="request.poster = ''" />
        <div>
          <h2>{{ title }}</h2>
          <p>{{ reference ? reference + ' · ' : '' }}{{ $t(request.mediaType === 'tv' ? 'Series' : 'Movie') }}</p>
          <dl v-if="status || createdAt || seasons">
            <template v-if="status"><dt>{{ $t('Status') }}</dt><dd>{{ $t(status) }}</dd></template>
            <template v-if="createdAt">
              <dt>{{ $t('Requested on') }}</dt><dd>{{ createdAt }}</dd>
            </template>
            <template v-if="seasons">
              <dt>{{ $t('Seasons') }}</dt><dd>{{ seasons }}</dd>
            </template>
            <template v-if="availableSeasons">
              <dt>{{ $t('Available seasons') }}</dt><dd>{{ availableSeasons }}</dd>
            </template>
          </dl>
        </div>
      </header>
      <p v-if="request.overview">{{ request.overview }}</p>
      <a v-if="libraryTitle && request.playUrl" class="ui-btn ui-btn-primary member-play"
         :href="request.playUrl" target="_blank" rel="noopener noreferrer">
        {{ $t(request.playProvider === 'plex' ? 'Open in Plex' : 'Open in Jellyfin') }}
      </a>
      <form @submit.prevent="sendReport">
        <h3>{{ $t('Report a problem') }}</h3>
        <p v-if="sent" role="status">{{ $t('Report sent to the administrator.') }}</p>
        <label v-else class="ui-field">{{ $t('Description') }}
          <textarea v-model="description" class="ui-input" rows="3" :maxlength="reference ? 3998 - reference.length : 4000"
                    :disabled="busy" required />
        </label>
        <p v-if="error" role="alert" class="ui-alert ui-alert-error">{{ $t('Support request failed. Try again.') }}</p>
        <footer>
          <button v-if="!sent" type="submit" class="ui-btn ui-btn-primary"
                  :disabled="busy || !description.trim()">{{ $t('Send report') }}</button>
          <button type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="dialog.close()">{{ $t('Close') }}</button>
        </footer>
      </form>
    </template>
  </dialog>
</template>

<style scoped>
.request-details { inline-size: min(34rem, calc(100% - 2rem)); max-block-size: calc(100dvh - 2rem); padding: 1.25rem; color: var(--text-main); overflow-wrap: anywhere; }
.request-details header { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: .875rem; }
.request-details header > div:only-child { grid-column: 1 / -1; }
.request-details img { width: clamp(3.5rem, 18vw, 6rem); aspect-ratio: 2 / 3; object-fit: cover; border-radius: var(--radius-tile); }
.request-details h2 { margin-block-start: 0; }
.request-details dl { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .25rem .75rem; }
.request-details dd { margin: 0; }
.member-play { display: inline-flex; margin-block-start: .75rem; }
.request-details form { border-block-start: 1px solid var(--border-subtle); margin-block-start: 1rem; }
.request-details textarea { resize: vertical; }
.request-details footer { display: flex; flex-wrap: wrap; gap: .5rem; margin-block-start: .75rem; }
</style>
