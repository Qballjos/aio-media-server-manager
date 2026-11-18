<script setup>
import { onMounted, ref } from 'vue'
import { apiJson } from './api.js'

const props = defineProps({ widget: { type: String, required: true } })
const quota = ref(null)
const quotaError = ref(false)
const openReports = ref(null)
const categories = { movie: 'Movies', tv: 'Series seasons' }

async function loadQuota() {
  quotaError.value = false
  try {
    const { res, data } = await apiJson('/api/media-discovery/quota')
    if (!res.ok) throw new Error()
    quota.value = data
  } catch (_) {
    quotaError.value = true
  }
}

async function loadReports() {
  try {
    const { res, data } = await apiJson('/api/support')
    if (res.ok) openReports.value = data.reports.filter(report => report.status !== 'resolved').length
  } catch (_) {}
}

onMounted(() => {
  if (props.widget === 'limits') loadQuota()
  if (props.widget === 'support') loadReports()
})
</script>

<template>
    <section v-if="widget === 'limits'" class="glass-card home-card member-utility" :aria-label="$t('Request limits')">
      <header class="home-widget-head"><h3>{{ $t('Request limits') }}</h3></header>
      <div v-if="quotaError" role="alert">
        <p>{{ $t('Could not load request limits.') }}</p>
        <button type="button" class="ui-btn ui-btn-ghost" @click="loadQuota">{{ $t('Retry') }}</button>
      </div>
      <p v-else-if="!quota" role="status">{{ $t('Loading request limits…') }}</p>
      <dl v-else>
        <div v-for="(label, kind) in categories" :key="kind">
          <dt>{{ $t(label) }}</dt>
          <dd v-if="quota[kind]">
            {{ quota[kind].days
              ? $t('{remaining} of {limit} remaining per {days} days', quota[kind])
              : $t('{remaining} of {limit} remaining', quota[kind]) }}
          </dd>
          <dd v-else>{{ $t('No limit') }}</dd>
        </div>
      </dl>
    </section>
    <section v-else class="glass-card home-card member-utility" :aria-label="$t('Support')">
      <header class="home-widget-head"><h3>{{ $t('Support') }}</h3></header>
      <p v-if="openReports !== null">{{ $t('Open reports: {count}', { count: openReports }) }}</p>
      <footer class="member-support-actions">
        <RouterLink class="ui-btn ui-btn-ghost" :to="{ name: 'settings', params: { section: 'support' } }">
          {{ $t('Open support') }}
        </RouterLink>
      </footer>
    </section>
</template>

<style scoped>
.member-support-actions { margin-block-start: auto; padding-block-start: .375rem; }
.member-utility p { margin: 0; }
.member-utility dl { display: grid; gap: .5rem; margin: 0; }
.member-utility dl div { display: flex; justify-content: space-between; flex-wrap: wrap; gap: .25rem .75rem; }
.member-utility dd { margin: 0; color: var(--text-muted); }
</style>
