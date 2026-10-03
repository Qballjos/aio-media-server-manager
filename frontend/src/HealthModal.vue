<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { apiRequest, readJson } from './api.js'
import { formatBytes, formatCpu, formatMemShare } from './format.js'
import { startGuardedInterval } from './pageVisible.js'

const props = defineProps({
  systemInfo: { type: Object, default: null },
  catalogApps: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'system-info'])

const healthHistory = ref([])
const HEALTH_MAX_SAMPLES = 60
let stopHealthPoll = null
const localInfo = ref(null)

const info = computed(() => localInfo.value || props.systemInfo)
const cpuPercent = computed(() => info.value?.metrics?.cpu_percent)
const memPercent = computed(() => info.value?.metrics?.memory?.percent)
const diskPercent = computed(() => info.value?.metrics?.disk?.percent)
const diskFree = computed(() => {
  const disk = info.value?.metrics?.disk || {}
  if (disk.free != null) return Number(disk.free) || 0
  return Math.max(0, (Number(disk.total) || 0) - (Number(disk.used) || 0))
})

function recordHealthSample(payload) {
  const metrics = payload?.metrics
  if (!metrics) return
  healthHistory.value = [
    ...healthHistory.value,
    {
      t: Date.now(),
      cpu: Number(metrics.cpu_percent) || 0,
      mem: Number(metrics.memory?.percent) || 0,
      disk: Number(metrics.disk?.percent) || 0,
    },
  ].slice(-HEALTH_MAX_SAMPLES)
}

function chartPath(values) {
  const w = 320
  const h = 88
  const pad = 6
  const series = values.length ? values : [0]
  const pts = series.length === 1 ? [series[0], series[0]] : series
  const n = Math.max(pts.length - 1, 1)
  const coords = pts.map((v, i) => {
    const x = pad + (i / n) * (w - pad * 2)
    const y = pad + (1 - Math.min(100, Math.max(0, Number(v) || 0)) / 100) * (h - pad * 2)
    return [x, y]
  })
  const line = coords.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const last = coords[coords.length - 1]
  const first = coords[0]
  const fill = `${line} L${last[0].toFixed(1)} ${(h - pad).toFixed(1)} L${first[0].toFixed(1)} ${(h - pad).toFixed(1)} Z`
  return { line, fill, w, h }
}

const cpuChart = computed(() => chartPath(healthHistory.value.map((s) => s.cpu)))
const memChart = computed(() => chartPath(healthHistory.value.map((s) => s.mem)))
const diskChart = computed(() => chartPath(healthHistory.value.map((s) => s.disk)))

const healthProcesses = computed(() => {
  const rows = info.value?.metrics?.processes
  if (!Array.isArray(rows)) return []
  const labels = new Map(props.catalogApps.map((s) => [s.name, s.display_name || s.displayName || s.name]))
  return rows.map((row) => ({
    ...row,
    displayName: labels.get(row.name) || row.name,
  }))
})

const healthTone = computed(() => {
  const cpu = Number(cpuPercent.value) || 0
  const mem = Number(memPercent.value) || 0
  const disk = Number(diskPercent.value) || 0
  if (cpu >= 90 || mem >= 90 || disk >= 90) return 'warn'
  return 'ok'
})

async function fetchSystemInfo() {
  try {
    const res = await apiRequest('/api/system/info')
    if (res.ok) {
      const data = await readJson(res)
      localInfo.value = data
      recordHealthSample(data)
      emit('system-info', data)
    }
  } catch (err) {
    console.error('System info fetch error:', err)
  }
}

function closeHealthModal() {
  emit('close')
}

onMounted(() => {
  localInfo.value = props.systemInfo
  recordHealthSample(props.systemInfo)
  fetchSystemInfo()
  stopHealthPoll = startGuardedInterval(fetchSystemInfo, 5000)
})

onUnmounted(() => {
  if (stopHealthPoll) stopHealthPoll()
})
</script>

<template>
    <div class="modal-backdrop" @click.self="closeHealthModal">
      <div class="health-modal glass-card animate-scale" @click.stop>
        <div class="modal-header">
          <div class="modal-title-group">
            <h3>Host health</h3>
            <span class="font-mono" :class="healthTone === 'ok' ? 'text-emerald' : 'text-warn'">
              {{ healthTone === 'ok' ? 'OK' : 'HIGH LOAD' }}
            </span>
          </div>
          <button type="button" class="btn-icon" title="Close" @click="closeHealthModal">×</button>
        </div>
        <div class="health-body">
          <p v-if="info && info.debug === false" class="health-chart-meta">
            Storage paths and full debug dumps stay off until Diagnostics → Support share is on (or you open the UI on localhost).
          </p>
          <article class="health-chart-card">
            <div class="health-chart-head">
              <span>CPU</span>
              <strong class="font-mono">{{ cpuPercent != null ? Math.round(cpuPercent) + '%' : '—' }}</strong>
            </div>
            <p class="health-chart-meta">{{ info?.metrics?.cpu_count || '—' }} cores</p>
            <svg class="health-svg" :viewBox="`0 0 ${cpuChart.w} ${cpuChart.h}`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="cpuChart.fill" class="health-fill cpu"></path>
              <path :d="cpuChart.line" class="health-line cpu"></path>
            </svg>
          </article>
          <article class="health-chart-card">
            <div class="health-chart-head">
              <span>RAM</span>
              <strong class="font-mono">{{ memPercent != null ? Math.round(memPercent) + '%' : '—' }}</strong>
            </div>
            <p class="health-chart-meta">
              {{ formatBytes((info?.metrics?.memory?.total || 0) - (info?.metrics?.memory?.available || 0)) }}
              used of {{ formatBytes(info?.metrics?.memory?.total) }}
            </p>
            <svg class="health-svg" :viewBox="`0 0 ${memChart.w} ${memChart.h}`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="memChart.fill" class="health-fill mem"></path>
              <path :d="memChart.line" class="health-line mem"></path>
            </svg>
          </article>
          <article class="health-chart-card">
            <div class="health-chart-head">
              <span>Disk</span>
              <strong class="font-mono">{{ diskPercent != null ? Math.round(diskPercent) + '%' : '—' }}</strong>
            </div>
            <p class="health-chart-meta">
              {{ formatBytes(info?.metrics?.disk?.used) }}
              used · {{ formatBytes(diskFree) }} free
              of {{ formatBytes(info?.metrics?.disk?.total) }}
            </p>
            <svg class="health-svg" :viewBox="`0 0 ${diskChart.w} ${diskChart.h}`" preserveAspectRatio="none" aria-hidden="true">
              <path :d="diskChart.fill" class="health-fill disk"></path>
              <path :d="diskChart.line" class="health-line disk"></path>
            </svg>
          </article>
          <article class="health-apps-card">
            <div class="health-chart-head">
              <span>Applications</span>
              <strong class="font-mono">{{ healthProcesses.length }}</strong>
            </div>
            <p class="health-chart-meta">CPU and RAM include all processes for each app.</p>
            <p v-if="!healthProcesses.length" class="health-chart-meta">No running apps yet. Start them from Catalog.</p>
            <div v-else class="health-apps-table-wrap">
              <table class="health-apps-table">
                <thead>
                  <tr>
                    <th>App</th>
                    <th>CPU</th>
                    <th>RAM</th>
                    <th class="hide-narrow">Share</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in healthProcesses" :key="row.name">
                    <td>
                      <span class="health-app-name">{{ row.displayName }}</span>
                      <span class="health-app-state">{{ row.state || 'stopped' }}</span>
                    </td>
                    <td class="font-mono">{{ formatCpu(row.cpu_percent) }}</td>
                    <td class="font-mono">{{ row.memory_rss != null ? formatBytes(row.memory_rss) : '—' }}</td>
                    <td class="font-mono hide-narrow">{{ formatMemShare(row.memory_percent) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </div>
    </div>
</template>
