<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiJson } from '../api.js'

defineProps({ administrator: Boolean })

const { t, locale } = useI18n()
const reports = ref([])
const newCount = ref(0)
const current = ref(null)
const subject = ref('')
const message = ref('')
const reply = ref('')
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const statuses = { new: 'New', in_progress: 'In progress', resolved: 'Resolved' }

function date(value) {
  const timestamp = new Date(value.replace(' ', 'T') + 'Z')
  return timestamp.toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' })
}

async function request(path = '', method = 'GET', body) {
  const { res, data } = await apiJson(`/api/support${path}`, {
    method,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(t('Support request failed. Try again.'))
  return data
}

async function run(action) {
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (_) {
    error.value = t('Support request failed. Try again.')
  } finally {
    busy.value = false
  }
}

async function refresh() {
  const data = await request()
  reports.value = data.reports
  newCount.value = data.new_count
  loaded.value = true
}

function openReport(report) {
  return run(async () => {
    current.value = await request(`/${report.id}`)
    reply.value = ''
  })
}

function submitReport() {
  return run(async () => {
    current.value = await request('', 'POST', { subject: subject.value.trim(), message: message.value.trim() })
    subject.value = ''
    message.value = ''
    await refresh()
  })
}

function submitReply() {
  return run(async () => {
    current.value = await request(`/${current.value.id}/replies`, 'POST', { message: reply.value.trim() })
    reply.value = ''
  })
}

function setStatus(status) {
  return run(async () => {
    current.value = await request(`/${current.value.id}`, 'PATCH', { status })
    await refresh()
  })
}

onMounted(() => run(refresh))
</script>

<template>
  <section class="support-settings" :class="{ 'glass-card': administrator }" :aria-busy="busy">
    <header class="support-actions">
      <h3>{{ administrator ? $t('Support inbox') : $t('My reports') }}</h3>
      <span v-if="administrator && loaded">{{ $t('New reports: {count}', { count: newCount }) }}</span>
      <button type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="run(refresh)">{{ $t('Refresh') }}</button>
    </header>
    <p v-if="!loaded && busy" role="status">{{ $t('Loading support reports…') }}</p>
    <p v-if="error" class="ui-alert ui-alert-error" role="alert">{{ error }}</p>
    <p v-if="loaded && !reports.length">{{ $t('No support reports yet.') }}</p>
    <ul v-if="reports.length" class="support-list">
      <li v-for="report in reports" :key="report.id">
        <button type="button" class="ui-btn ui-btn-ghost" :disabled="busy"
                :aria-pressed="current?.id === report.id" @click="openReport(report)">{{ report.subject }}</button>
        <span>{{ $t(statuses[report.status]) }} · {{ date(report.created_at) }}</span>
        <span v-if="administrator">{{ report.provider === 'plex' ? 'Plex' : 'Jellyfin' }} · {{ report.account_id }}</span>
      </li>
    </ul>

    <article v-if="current" class="support-thread">
      <h4>{{ current.subject }}</h4>
      <p class="support-message">{{ current.message }}</p>
      <p>{{ $t(statuses[current.status]) }}</p>
      <div v-if="administrator" class="support-actions" :aria-label="$t('Report status')" role="group">
        <button v-for="(label, status) in statuses" :key="status" type="button" class="ui-btn ui-btn-ghost"
                :disabled="busy || current.status === status" @click="setStatus(status)">{{ $t(label) }}</button>
      </div>
      <ol v-if="current.replies.length" class="support-list">
        <li v-for="entry in current.replies" :key="entry.id">
          <strong>{{ entry.author === 'admin' ? $t('Administrator') : $t('Media account') }}</strong>
          <time>{{ date(entry.created_at) }}</time>
          <p class="support-message">{{ entry.message }}</p>
        </li>
      </ol>
      <form class="support-form" @submit.prevent="submitReply">
        <label class="ui-field">{{ $t('Reply') }}
          <textarea v-model="reply" class="ui-input" rows="3" maxlength="4000" required />
        </label>
        <button type="submit" class="ui-btn ui-btn-primary" :disabled="busy || !reply.trim()">{{ $t('Send reply') }}</button>
      </form>
    </article>

    <form v-if="!administrator" class="support-form support-thread" @submit.prevent="submitReport">
      <h4>{{ $t('Report a problem') }}</h4>
      <label class="ui-field">{{ $t('Subject') }}
        <input v-model="subject" class="ui-input" maxlength="160" required />
      </label>
      <label class="ui-field">{{ $t('Description') }}
        <textarea v-model="message" class="ui-input" rows="4" maxlength="4000" required />
      </label>
      <button type="submit" class="ui-btn ui-btn-primary"
              :disabled="busy || !subject.trim() || !message.trim()">{{ $t('Send report') }}</button>
    </form>
  </section>
</template>

<style scoped>
.support-settings { min-inline-size: 0; overflow-wrap: anywhere; }
.support-settings.glass-card { padding: 1rem; }
.support-actions { display: flex; align-items: center; flex-wrap: wrap; gap: .5rem .75rem; }
.support-actions h3 { flex: 1; margin: 0; }
.support-list { list-style: none; padding: 0; }
.support-list li { display: flex; align-items: baseline; flex-wrap: wrap; gap: .375rem .75rem; padding-block: .5rem; border-block-start: 1px solid var(--border-subtle); }
.support-list button { max-inline-size: 100%; white-space: normal; }
.support-thread { margin-block-start: 1rem; padding-block-start: 1rem; border-block-start: 1px solid var(--border-subtle); }
.support-message { white-space: pre-wrap; flex-basis: 100%; }
.support-form { display: grid; justify-items: start; gap: .75rem; }
.support-form label { width: 100%; }
.support-form textarea { resize: vertical; }
.support-form h4 { margin: 0; }
</style>
