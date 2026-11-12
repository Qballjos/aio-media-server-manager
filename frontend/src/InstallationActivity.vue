<script setup>
import { computed, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { trapDialogTab } from './dialogFocus.js'
import { apiRequest, readJson, apiError } from './api.js'
const open = ref(false)
const jobs = ref([])
const error = ref('')
const active = computed(() => jobs.value.some(job => ['queued', 'installing', 'configuring', 'updating'].includes(job.status)))
const needsAttention = computed(() => active.value || jobs.value.some(job => ['failed', 'rolled_back', 'rollback_failed', 'restart_required'].includes(job.status)))
const dialog = ref(null)
let timer
async function refresh() {
  try {
    const response = await apiRequest('/api/catalog/install-jobs')
    const data = await readJson(response)
    if (!response.ok) throw new Error(apiError(data))
    jobs.value = data.jobs || []
    error.value = ''
  } catch (err) { error.value = err.message }
}
function show() { open.value = true; refresh(); nextTick(() => dialog.value?.querySelector('button')?.focus()) }
defineExpose({ show, refresh })
onMounted(() => { refresh(); timer = setInterval(() => { if (open.value || active.value) refresh() }, 2000) })
onUnmounted(() => clearInterval(timer))
</script>
<template>
  <button v-if="needsAttention || error" type="button" class="ui-btn ui-btn-ghost" @click="show">{{ $t('Installation activity') }}</button>
  <Teleport to="body">
    <div v-if="open" class="activity-backdrop" @click.self="open = false" @keydown.esc="open = false">
      <section role="dialog" aria-modal="true" aria-labelledby="activity-title" ref="dialog" @keydown.tab="trapDialogTab($event, dialog)" class="glass-card activity-dialog" tabindex="-1">
        <div class="share-row"><h2 id="activity-title">{{ $t('Installation activity') }}</h2><button autofocus class="ui-btn ui-btn-ghost" @click="open = false">{{ $t('Close') }}</button></div>
        <p>{{ $t('You can close this window and reopen it while installation continues. History is kept until the manager restarts.') }}</p>
        <p v-if="error" role="alert">{{ error }}</p>
        <p v-if="!jobs.length">{{ $t('No installation activity yet.') }}</p>
        <article v-for="job in jobs" :key="job.name">
          <h3>{{ job.name }} — {{ job.status }}</h3><p aria-live="polite">{{ job.message }}</p>
          <button class="ui-btn ui-btn-ghost" @click="open = false; $emit('logs', job)">{{ $t('View logs') }}</button>
          <ol><li v-for="(event, index) in job.history || []" :key="index">{{ new Date(event.at * 1000).toLocaleTimeString() }} — {{ event.message || event.status }}</li></ol>
          <button v-if="['failed', 'rollback_failed'].includes(job.status)" class="ui-btn ui-btn-ghost" @click="$emit('retry', job)">{{ $t('Try again') }}</button>
        </article>
      </section>
    </div>
  </Teleport>
</template>
<style scoped>
.activity-backdrop { position: fixed; inset: 0; z-index: 1000; background: #0008; display: grid; place-items: center; padding: 1rem; }
.activity-dialog { width: min(48rem, 100%); max-height: 85dvh; overflow: auto; padding: 1.5rem; }
.activity-dialog article { padding-block: 1rem; border-top: 1px solid var(--border-color, #8884); }
.activity-dialog li { overflow-wrap: anywhere; }
</style>
