<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiError, apiJson } from '../api.js'

const { t } = useI18n()
const endpoint = '/api/settings/media-users'
const provider = ref('')
const users = ref([])
const selected = ref([])
const busy = ref(false)
const error = ref('')
const notice = ref('')
const loaded = ref(false)
const providerName = computed(() => provider.value === 'plex' ? 'Plex' : 'Jellyfin')
const orderedUsers = computed(() => [...users.value].sort((first, second) => first.name.localeCompare(second.name)))

async function run(action) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
  } catch (err) {
    error.value = t(err.message)
  } finally {
    busy.value = false
  }
}

function refresh() {
  return run(async () => {
    const { res, data } = await apiJson(endpoint)
    if (!res.ok) throw new Error(apiError(data, t('Could not load media accounts.')))
    provider.value = data.provider
    users.value = data.users
    selected.value = []
    loaded.value = true
  })
}

function grantSelected() {
  return run(async () => {
    const { res, data } = await apiJson(endpoint, {
      method: 'POST',
      body: JSON.stringify({ account_ids: selected.value }),
    })
    if (!res.ok) throw new Error(apiError(data, t('Could not grant access.')))
    const enabled = new Set(data.enabled)
    users.value = users.value.map(user => enabled.has(user.id) ? { ...user, imported: true, enabled: true } : user)
    selected.value = []
    notice.value = t('Access granted to {count} account(s).', { count: enabled.size })
  })
}

function revoke(user) {
  return run(async () => {
    const { res, data } = await apiJson(`${endpoint}/${encodeURIComponent(user.id)}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(apiError(data, t('Could not revoke access.')))
    user.enabled = false
    notice.value = t('Access revoked for {name}.', { name: user.name })
  })
}

onMounted(refresh)
</script>

<template>
  <section class="glass-card media-users-card" :aria-busy="busy">
    <header class="media-users-header">
      <h3>{{ loaded ? $t('{provider} accounts', { provider: providerName }) : $t('Media accounts') }}</h3>
      <button type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="refresh">{{ $t('Refresh') }}</button>
    </header>
    <p v-if="busy && !loaded" role="status">{{ $t('Loading media accounts…') }}</p>
    <p v-if="error" class="ui-alert ui-alert-error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loaded && !users.length">{{ $t('No media accounts found.') }}</p>

    <form v-if="users.length" @submit.prevent="grantSelected">
      <ul class="media-users-list">
        <li v-for="user in orderedUsers" :key="user.id">
          <div class="media-user-label">
            <label v-if="!user.enabled">
              <input v-model="selected" type="checkbox" :value="user.id"
                     :disabled="busy || (selected.length >= 100 && !selected.includes(user.id))" />
              <span>{{ user.name }}</span>
            </label>
            <strong v-else>{{ user.name }}</strong>
            <small>{{ user.enabled ? $t('AIO access enabled') : user.imported ? $t('Imported in Seerr') : $t('Ready to import') }}</small>
          </div>
          <button v-if="user.enabled" type="button" class="ui-btn ui-btn-ghost"
                  :aria-label="$t('Revoke access for {name}', { name: user.name })" :disabled="busy" @click="revoke(user)">
            {{ $t('Revoke access') }}
          </button>
        </li>
      </ul>
      <button v-if="users.some(user => !user.enabled)" type="submit" class="ui-btn ui-btn-primary"
              :disabled="busy || !selected.length">{{ $t('Grant access') }}</button>
      <p v-if="selected.length === 100" role="status">{{ $t('Select up to 100 accounts at a time.') }}</p>
    </form>
  </section>
</template>

<style scoped>
.media-users-card { padding: 1rem; min-inline-size: 0; }
.media-users-header, .media-users-list li { display: flex; align-items: center; justify-content: space-between; gap: .75rem; flex-wrap: wrap; }
.media-users-header h3 { margin: 0; }
.media-users-list { margin: .75rem 0; padding: 0; list-style: none; }
.media-users-list li { padding-block: .625rem; border-block-start: 1px solid var(--border-subtle); }
.media-user-label { min-inline-size: 0; overflow-wrap: anywhere; }
.media-user-label label { display: flex; align-items: center; gap: .5rem; min-block-size: 2.75rem; }
.media-user-label small { display: block; color: var(--text-muted); }
</style>
