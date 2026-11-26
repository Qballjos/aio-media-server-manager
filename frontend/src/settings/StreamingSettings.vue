<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { apiJson } from '../api.js'
import UiSelect from '../UiSelect.vue'
import { streamingCountryForTimeZone } from './streamingCountry.js'

const props = defineProps({ scope: { type: String, required: true } })
const { locale, t } = useI18n()
const route = useRoute()
const heading = ref(null)
const country = ref('')
const regions = ref([])
const providers = ref([])
const selected = ref([])
const providerNames = new Map()
const search = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
let retry = load

const regionOptions = computed(() => {
  const names = new Intl.DisplayNames([locale.value], { type: 'region' })
  return [
    { value: '', label: t('Choose a country'), disabled: true },
    ...regions.value.map(value => ({ value, label: names.of(value) }))
      .sort((a, b) => a.label.localeCompare(b.label, locale.value)),
  ]
})
const visibleProviders = computed(() => providers.value.filter(provider =>
  provider.name.toLocaleLowerCase(locale.value).includes(search.value.trim().toLocaleLowerCase(locale.value)),
))

const availableIds = computed(() => new Set(providers.value.map(provider => provider.id)))
const removed = computed(() => selected.value.filter(id => !availableIds.value.has(id))
  .map(id => providerNames.get(id) || String(id)))

async function fetchData(path, options) {
  const { res, data } = await apiJson(`/api/streaming/${props.scope}/${path}`, options)
  if (!res.ok) throw new Error('Streaming request failed')
  return data
}

async function load() {
  loading.value = true
  error.value = ''
  retry = load
  try {
    const [preference, catalog] = await Promise.all([fetchData('preferences'), fetchData('catalog')])
    regions.value = catalog.regions
    selected.value = preference.provider_ids
    const initialCountry = preference.country || streamingCountryForTimeZone(
      Intl.DateTimeFormat().resolvedOptions().timeZone,
    )
    if (regions.value.includes(initialCountry)) {
      await loadCountry(initialCountry)
    }
  } catch (_) {
    error.value = 'Could not load streaming subscriptions.'
  } finally {
    loading.value = false
  }
}

async function loadCountry(value) {
  if (!value) return
  country.value = value
  search.value = ''
  saved.value = false
  loading.value = true
  error.value = ''
  retry = () => loadCountry(value)
  try {
    const data = await fetchData(`catalog?country=${value}`)
    for (const provider of data.providers) providerNames.set(provider.id, provider.name)
    providers.value = data.providers.sort((a, b) => a.name.localeCompare(b.name, locale.value))
  } catch (_) {
    error.value = 'Could not load streaming subscriptions.'
  } finally {
    loading.value = false
  }
}

async function save() {
  if (loading.value || saving.value || !country.value) return
  saving.value = true
  saved.value = false
  error.value = ''
  retry = save
  try {
    const providerIds = selected.value.filter(id => availableIds.value.has(id))
    await fetchData('preferences', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ country: country.value, provider_ids: providerIds }),
    })
    selected.value = providerIds
    saved.value = true
  } catch (_) {
    error.value = 'Could not save streaming subscriptions.'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (route.query.streaming === '1') heading.value?.focus()
  load()
})
</script>

<template>
  <section class="glass-card settings-card streaming-settings" aria-labelledby="streaming-settings-heading">
    <div class="settings-card-head">
      <h3 id="streaming-settings-heading" ref="heading" tabindex="-1">{{ $t('Streaming subscriptions') }}</h3>
      <p>{{ $t('Choose your services to see where Trending titles are streaming.') }}</p>
    </div>
    <form class="form-stack streaming-form" @submit.prevent="save">
      <label v-if="regions.length" class="ui-field">
        {{ $t('Streaming country') }}
        <UiSelect :model-value="country" :options="regionOptions" searchable
                  :search-placeholder="$t('Search')"
                  :empty-label="$t('No matches')" :aria-label="$t('Streaming country')"
                  :disabled="loading || saving" @update:model-value="loadCountry" />
      </label>
      <p v-if="loading" role="status">{{ $t('Loading streaming services…') }}</p>
      <div v-if="error" class="streaming-feedback">
        <p role="alert">{{ $t(error) }}</p>
        <button type="button" class="ui-btn ui-btn-ghost" @click="retry">{{ $t('Retry') }}</button>
      </div>
      <p v-if="!loading && !error && !regions.length">{{ $t('No streaming countries available.') }}</p>
      <template v-if="country && !loading && (!error || retry === save)">
        <label v-if="providers.length" class="ui-field">
          {{ $t('Find a service') }}
          <input v-model="search" type="search" class="ui-input" :placeholder="$t('Search streaming services')">
        </label>
        <fieldset v-if="visibleProviders.length" class="streaming-services" :aria-label="$t('Streaming subscriptions')" :disabled="saving">
          <legend>{{ $t('Subscription services ({count})', { count: providers.length }) }}</legend>
          <label v-for="provider in visibleProviders" :key="provider.id" class="streaming-service">
            <input v-model="selected" type="checkbox" :value="provider.id" @change="saved = false">
            <img v-if="provider.logo_url" :src="provider.logo_url" alt="" width="32" height="32"
                 loading="lazy" referrerpolicy="no-referrer" @error="$event.target.hidden = true">
            <span>{{ provider.name }}</span>
          </label>
        </fieldset>
        <p v-else>{{ $t(providers.length ? 'No matches' : 'No streaming services available.') }}</p>
        <p v-if="removed.length" role="status">{{ $t('Removed when you save: {services}', { services: removed.join(', ') }) }}</p>
        <div class="streaming-feedback">
          <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">
            {{ $t(saving ? 'Saving…' : 'Save subscriptions') }}
          </button>
          <p v-if="saved" role="status">{{ $t('Subscriptions saved.') }}</p>
        </div>
      </template>
    </form>
  </section>
</template>

<style scoped src="./settingsForms.css"></style>

<style scoped>
.streaming-settings { container-type: inline-size; }
.streaming-form { max-inline-size: none; }
.streaming-services {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: .35rem .75rem;
  min-inline-size: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.streaming-services legend { padding: 0; margin-block-end: .45rem; font-weight: 600; }
.streaming-service {
  display: grid;
  grid-template-columns: 1.1rem 2rem minmax(0, 1fr);
  gap: .5rem;
  align-items: center;
  min-block-size: max(44px, 2.75rem);
  padding: .25rem;
  border-radius: var(--radius-inset);
  cursor: pointer;
}
.streaming-service:hover, .streaming-service:has(input:checked) { background: var(--bg-surface); }
.streaming-service input { margin: 0; inline-size: 1.1rem; block-size: 1.1rem; accent-color: var(--color-primary); }
.streaming-service img { inline-size: 2rem; block-size: 2rem; border-radius: var(--radius-inset); }
.streaming-service span { grid-column: 3; overflow-wrap: anywhere; }
.streaming-service:not(:has(img:not([hidden]))) span { grid-column: 2 / -1; }
@container (min-width: 18rem) {
  .streaming-services { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@container (min-width: 41rem) {
  .streaming-services { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .streaming-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem 1rem; }
  .streaming-form > :not(label) { grid-column: 1 / -1; }
}
.streaming-settings .settings-card-head { margin-block-end: 1rem; }
.streaming-settings .settings-card-head p { color: var(--text-muted); }
.streaming-settings p { margin: 0; }
.streaming-feedback { display: flex; flex-wrap: wrap; align-items: center; gap: .65rem; }
</style>
