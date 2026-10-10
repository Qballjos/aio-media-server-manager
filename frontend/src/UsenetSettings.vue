<script setup>
import { onMounted, ref } from 'vue'
import { apiError, apiJson } from './api.js'

const CLIENT_NAMES = { sabnzbd: 'SABnzbd', nzbget: 'NZBGet' }

const overview = ref({ server: null, clients: [], prowlarr: false, indexers: [] })
const loaded = ref(false)
const server = ref({ host: '', port: 563, ssl: true, username: '', password: '', connections: 8 })
const serverState = ref({ saving: false, message: '', error: false })
const indexer = ref({ name: '', url: '', api_key: '' })
const indexerState = ref({ saving: false, message: '', error: false })

async function load() {
  try {
    const { res, data } = await apiJson('/api/usenet')
    if (!res.ok) return
    overview.value = { ...overview.value, ...data }
    // Do not overwrite what someone already started typing.
    if (data.server && !server.value.host) server.value = { ...server.value, ...data.server, password: '' }
  } catch (_) {
    /* the forms still work without the overview */
  } finally {
    loaded.value = true
  }
}

function appliedMessage(applied) {
  const names = Object.keys(applied || {})
  if (!names.length) return 'Saved. SABnzbd or NZBGet gets it once installed.'
  const sent = names.filter((name) => applied[name]).map((name) => CLIENT_NAMES[name] || name)
  const later = names.filter((name) => !applied[name]).map((name) => CLIENT_NAMES[name] || name)
  if (!later.length) return `Saved and sent to ${sent.join(' and ')}.`
  return `Saved. ${later.join(' and ')} could not be reached and gets it on its next start.`
}

async function saveServer() {
  serverState.value = { saving: true, message: '', error: false }
  const body = {
    ...server.value,
    port: Number(server.value.port) || 563,
    connections: Number(server.value.connections) || 8,
  }
  delete body.has_password
  if (!body.password) delete body.password
  try {
    const { res, data } = await apiJson('/api/usenet/server', { method: 'PUT', body: JSON.stringify(body) })
    if (!res.ok) {
      serverState.value = { saving: false, message: apiError(data, 'Could not save the Usenet server.'), error: true }
      return
    }
    overview.value.server = data.server
    server.value.password = ''
    serverState.value = { saving: false, message: appliedMessage(data.applied), error: false }
  } catch (err) {
    serverState.value = { saving: false, message: err.message || 'Could not save the Usenet server.', error: true }
  }
}

async function addIndexer() {
  indexerState.value = { saving: true, message: 'Prowlarr is checking the API key…', error: false }
  try {
    const { res, data } = await apiJson('/api/usenet/indexers', { method: 'POST', body: JSON.stringify(indexer.value) })
    if (!res.ok) {
      indexerState.value = { saving: false, message: apiError(data, 'Could not add the indexer.'), error: true }
      return
    }
    overview.value.indexers = data.indexers || overview.value.indexers
    indexer.value = { name: '', url: '', api_key: '' }
    indexerState.value = { saving: false, message: data.detail, error: false }
  } catch (err) {
    indexerState.value = { saving: false, message: err.message || 'Could not add the indexer.', error: true }
  }
}

onMounted(load)
</script>

<template>
  <!-- Enter must not submit the surrounding port/autostart form. -->
  <section class="usenet-settings" @keydown.enter.prevent>
    <h4>Usenet provider</h4>
    <p class="settings-hint">
      The news server from your Usenet provider. AIO sends it to SABnzbd and NZBGet.
    </p>
    <div class="usenet-grid">
      <label class="ui-field usenet-wide">
        Server
        <input v-model.trim="server.host" class="ui-input font-mono" placeholder="news.example.com" autocomplete="off" />
      </label>
      <label class="ui-field">
        Port
        <input v-model.number="server.port" class="ui-input font-mono" type="number" min="1" max="65535" />
      </label>
      <label class="ui-field">
        Connections
        <input v-model.number="server.connections" class="ui-input font-mono" type="number" min="1" max="100" />
      </label>
      <label class="ui-field">
        Username
        <input v-model.trim="server.username" class="ui-input font-mono" autocomplete="off" />
      </label>
      <label class="ui-field">
        Password
        <input
          v-model="server.password"
          class="ui-input"
          type="password"
          autocomplete="new-password"
          :placeholder="overview.server?.has_password ? 'Saved, blank keeps it' : ''"
        />
      </label>
    </div>
    <label class="usenet-check">
      <input v-model="server.ssl" type="checkbox" />
      SSL / TLS
    </label>
    <div class="usenet-actions">
      <button type="button" class="ui-btn ui-btn-primary" :disabled="serverState.saving || !server.host" @click="saveServer">
        {{ serverState.saving ? 'Saving…' : 'Save server' }}
      </button>
      <span v-if="serverState.message" class="settings-hint" :class="{ 'usenet-error': serverState.error }" role="status">
        {{ serverState.message }}
      </span>
    </div>

    <h4>Usenet indexers</h4>
    <p class="settings-hint">
      NZB sites such as NZBgeek or Usenet Crawler. Paste the site's address and the API key from your profile there.
      Prowlarr checks the key and shares the indexer with Sonarr and Radarr.
    </p>
    <ul v-if="overview.indexers.length" class="usenet-indexers">
      <li v-for="row in overview.indexers" :key="row.name">
        <strong>{{ row.name }}</strong>
        <span class="font-mono text-dim">{{ row.url }}</span>
      </li>
    </ul>
    <template v-if="overview.prowlarr">
      <div class="usenet-grid">
        <label class="ui-field usenet-wide">
          Address
          <input v-model.trim="indexer.url" class="ui-input font-mono" placeholder="https://www.usenet-crawler.com" autocomplete="off" />
        </label>
        <label class="ui-field">
          API key
          <input v-model.trim="indexer.api_key" class="ui-input font-mono" type="password" autocomplete="off" />
        </label>
        <label class="ui-field">
          Name
          <input v-model.trim="indexer.name" class="ui-input" placeholder="Optional, from the address" autocomplete="off" />
        </label>
      </div>
      <div class="usenet-actions">
        <button
          type="button"
          class="ui-btn ui-btn-primary"
          :disabled="indexerState.saving || !indexer.url || !indexer.api_key"
          @click="addIndexer"
        >
          {{ indexerState.saving ? 'Adding…' : 'Add to Prowlarr' }}
        </button>
        <span v-if="indexerState.message" class="settings-hint" :class="{ 'usenet-error': indexerState.error }" role="status">
          {{ indexerState.message }}
        </span>
      </div>
    </template>
    <p v-else-if="loaded" class="settings-hint">Install Prowlarr to add Usenet indexers.</p>
    <p v-else class="settings-hint" role="status">Loading indexers…</p>
  </section>
</template>

<style scoped>
.usenet-settings {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--border-subtle);
}
.usenet-settings h4 {
  margin: 0.4rem 0 0;
  font-size: 0.95rem;
}
.usenet-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem 0.75rem;
}
.usenet-wide {
  grid-column: 1 / -1;
}
.usenet-check {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}
.usenet-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.usenet-actions .settings-hint {
  margin: 0;
}
.usenet-error {
  color: var(--color-danger-fg);
}
.usenet-indexers {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.35rem;
}
.usenet-indexers li {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: baseline;
  font-size: 0.9rem;
}
@media (max-width: 520px) {
  .usenet-grid {
    grid-template-columns: 1fr;
  }
}
</style>
