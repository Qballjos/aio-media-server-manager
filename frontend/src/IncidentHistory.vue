<script setup>
import { ref, onMounted } from 'vue'
import { apiRequest, readJson, apiError } from './api.js'
const rows = ref([]), error = ref('')
async function load() {
  try { const response = await apiRequest('/api/notifications/history'); const data = await readJson(response); if (!response.ok) throw new Error(apiError(data)); rows.value = (data.incidents || []).slice().reverse(); error.value = '' }
  catch (err) { error.value = err.message }
}
onMounted(load)
</script>
<template><section class="glass-card settings-card"><h3>{{ $t('Recent incidents') }}</h3><button class="ui-btn ui-btn-ghost" @click="load">{{ $t('Refresh') }}</button><p v-if="error" role="alert">{{ error }}</p><p v-if="!rows.length">{{ $t('No incidents recorded yet.') }}</p><article v-for="(row, index) in rows" :key="index"><strong>{{ row.subject }}</strong><p>{{ new Date(row.at * 1000).toLocaleString() }} — {{ row.body }}</p></article></section></template>
