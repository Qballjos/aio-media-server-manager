<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { apiError, apiRequest, getAuthToken, readJson } from './api.js'
import { startGuardedInterval } from './pageVisible.js'
import { useToasts } from './useToasts.js'

const props = defineProps({
  app: { type: Object, default: null },
})
const emit = defineEmits(['close'])
const { showToast } = useToasts()

const iconFailed = ref({})
const logLines = ref([])
const logLoading = ref(false)
const autoScrollLogs = ref(true)
const logFilter = ref('')
const logOnlyErrors = ref(false)
const logContainerRef = ref(null)
let logWs = null
let stopLogPoll = null

const filteredLogLines = computed(() => {
  let lines = logLines.value
  if (logOnlyErrors.value) {
    lines = lines.filter((l) => /error|fatal|fail|exception/i.test(l))
  }
  if (logFilter.value) {
    const q = logFilter.value.toLowerCase()
    lines = lines.filter((l) => l.toLowerCase().includes(q))
  }
  return lines
})

function closeLogs() {
  if (logWs) {
    logWs.close()
    logWs = null
  }
  if (stopLogPoll) {
    stopLogPoll()
    stopLogPoll = null
  }
  emit('close')
}

function startLiveWebSocket(name) {
  if (logWs) {
    logWs.close()
    logWs = null
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = getAuthToken()
  const qs = token ? `?token=${encodeURIComponent(token)}` : ''
  const wsUrl = `${protocol}//${window.location.host}/api/logs/ws/${encodeURIComponent(name)}${qs}`
  try {
    logWs = new WebSocket(wsUrl)
    logWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data && data.line) {
          logLines.value.push(data.line)
          if (autoScrollLogs.value) {
            nextTick(() => {
              if (logContainerRef.value) {
                logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
              }
            })
          }
        }
      } catch (e) {}
    }
    logWs.onerror = () => {
      startLogPolling(name)
    }
  } catch (e) {
    startLogPolling(name)
  }
}

async function fetchLogs(name) {
  if (!name) return
  logLoading.value = true
  try {
    const res = await apiRequest(`/api/applications/${name}/logs`)
    if (res.ok) {
      const data = await readJson(res)
      logLines.value = data.lines || []
      if (autoScrollLogs.value) {
        await nextTick()
        if (logContainerRef.value) {
          logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
        }
      }
    }
  } catch (err) {
    console.error('Failed to fetch logs:', err)
  } finally {
    logLoading.value = false
  }
}

function startLogPolling(name) {
  if (stopLogPoll) stopLogPoll()
  stopLogPoll = startGuardedInterval(() => {
    fetchLogs(name)
  }, 2500)
}

async function downloadLogs(name) {
  if (!name) return
  try {
    const res = await apiRequest(`/api/logs/download?app=${encodeURIComponent(name)}`)
    if (!res.ok) {
      const data = await readJson(res)
      showToast(apiError(data, 'Could not download logs.'), 'error')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename="([^"]+)"/)
    link.download = match?.[1] || `${name}-logs.txt`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    showToast(err.message || 'Could not download logs.', 'error')
  }
}

watch(
  () => props.app,
  async (app) => {
    if (!app) return
    logLines.value = []
    logFilter.value = ''
    logOnlyErrors.value = false
    await fetchLogs(app.name)
    startLiveWebSocket(app.name)
  },
  { immediate: true }
)

onUnmounted(() => {
  if (logWs) {
    logWs.close()
    logWs = null
  }
  if (stopLogPoll) stopLogPoll()
})
</script>

<template>
        <div v-if="app" class="modal-backdrop" @click.self="closeLogs">
      <div class="log-modal glass-card animate-scale">
        <div class="modal-header">
          <div class="modal-title-group">
            <span class="modal-dot"></span>
            <img
              v-if="app?.iconSrc && !iconFailed[app.name]"
              :src="app.iconSrc"
              :alt="app.displayName"
              class="app-icon app-icon-sm"
            />
            <h3>{{ app?.displayName }} logs</h3>
            <span class="font-mono text-dim">({{ app?.name }})</span>
          </div>

          <div class="modal-controls">
            <input
              type="text"
              v-model="logFilter"
              placeholder="Search logs…"
              class="ui-input font-mono log-search"
            />
            <label class="toggle-control font-mono">
              <input type="checkbox" v-model="logOnlyErrors" />
              <span>Errors only</span>
            </label>
            <label class="toggle-control font-mono">
              <input type="checkbox" v-model="autoScrollLogs" />
              <span>Auto-scroll</span>
            </label>
            <button @click="downloadLogs(app?.name)" class="btn-icon" title="Download logs">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </button>
            <button @click="fetchLogs(app?.name)" class="btn-icon" title="Refresh">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': logLoading }">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
            </button>
            <button @click="closeLogs" class="btn-icon btn-close" title="Close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>

        <div class="log-console font-mono" ref="logContainerRef">
          <div v-if="filteredLogLines.length === 0" class="log-empty">
            <span v-if="logLoading">Loading logs…</span>
            <span v-else-if="logLines.length > 0">No logs match this filter.</span>
            <span v-else>No logs yet for this app.</span>
          </div>
          <div
            v-for="(line, idx) in filteredLogLines"
            :key="idx"
            class="log-line"
            :style="/error|fatal|fail|exception/i.test(line) ? 'color: #f87171;' : ''"
          >
            <span class="line-num">{{ idx + 1 }}</span>
            <span class="line-content">{{ line }}</span>
          </div>
        </div>
      </div>
    </div>
</template>
