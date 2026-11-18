<script setup>
import { onMounted, ref } from 'vue'
import { apiJson } from './api.js'

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
  loadQuota()
  loadReports()
})
</script>

<template>
  <div class="member-utility-widgets">
    <section class="glass-card member-utility" :aria-label="$t('Request limits')">
      <h2>{{ $t('Request limits') }}</h2>
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
    <section class="glass-card member-utility" :aria-label="$t('Support')">
      <h2>{{ $t('Support') }}</h2>
      <p v-if="openReports !== null">{{ $t('Open reports: {count}', { count: openReports }) }}</p>
      <RouterLink class="ui-btn ui-btn-ghost" :to="{ name: 'settings', params: { section: 'support' } }">
        {{ $t('Open support') }}
      </RouterLink>
    </section>
  </div>
</template>

<style scoped>
.member-utility-widgets { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr)); gap: 1rem; }
.member-utility { min-inline-size: 0; padding: 1.25rem; }
.member-utility h2 { margin-block-start: 0; }
.member-utility dl { display: grid; gap: .5rem; margin: 0; }
.member-utility dl div { display: flex; justify-content: space-between; flex-wrap: wrap; gap: .25rem .75rem; }
.member-utility dd { margin: 0; color: var(--text-muted); }
</style>
