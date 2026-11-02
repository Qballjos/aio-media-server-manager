<script setup>
import { ref, nextTick, onUnmounted } from 'vue'
import { trapDialogTab } from './dialogFocus.js'
import { apiRequest, readJson, apiError } from './api.js'
const open = ref(false), loading = ref(false), report = ref(null), error = ref(''), app = ref('')
let resolve
let sequence = 0
let previousFocus
const dialog = ref(null)
async function review(name, operation = 'install') {
  if (resolve) resolve(false)
  const current = ++sequence
  previousFocus = globalThis.document?.activeElement
  app.value = name; open.value = true; loading.value = true; report.value = null; error.value = ''
  const result = new Promise(done => { resolve = done })
  nextTick(() => dialog.value?.querySelector('button')?.focus())
  try {
    const response = await apiRequest(`/api/catalog/${encodeURIComponent(name)}/preflight?operation=${operation}`)
    const data = await readJson(response)
    if (!response.ok) throw new Error(apiError(data))
    if (current === sequence) report.value = data
  } catch (err) { if (current === sequence) error.value = err.message }
  finally { if (current === sequence) loading.value = false }
  return result
}
function finish(value) { if (value && !report.value?.ok) return; ++sequence; open.value = false; resolve?.(value); resolve = null; previousFocus?.focus() }
onUnmounted(() => finish(false))
defineExpose({ review })
</script>
<template>
  <Teleport to="body"><div v-if="open" class="preflight-overlay" @click.self="finish(false)" @keydown.esc="finish(false)">
    <section role="dialog" aria-modal="true" aria-labelledby="preflight-title" ref="dialog" tabindex="-1" @keydown.tab="trapDialogTab($event, dialog)" class="glass-card preflight-card">
      <h2 id="preflight-title">{{ $t('Ready to proceed?') }} — {{ app }}</h2>
      <p v-if="loading" aria-live="polite">{{ $t('Checking storage, maintenance and download access…') }}</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <ul><li v-for="check in report?.checks || []" :key="check.name"><strong>{{ check.status }}</strong> — {{ check.detail }}</li></ul>
      <div class="share-row"><button autofocus class="ui-btn ui-btn-ghost" @click="finish(false)">{{ $t('Cancel') }}</button><button class="ui-btn ui-btn-primary" :disabled="loading || !report?.ok" @click="finish(true)">{{ $t('Continue') }}</button></div>
    </section>
  </div></Teleport>
</template>
<style scoped>
.preflight-overlay { position: fixed; inset: 0; z-index: 1100; display: grid; place-items: center; background: #0008; padding: 1rem; }
.preflight-card { width: min(42rem, 100%); padding: 1.5rem; max-height: 85dvh; overflow: auto; }
li { margin-block: .75rem; overflow-wrap: anywhere; }
</style>
