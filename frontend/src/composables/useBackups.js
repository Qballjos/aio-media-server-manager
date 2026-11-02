import { ref, computed, onUnmounted } from 'vue'
import { apiRequest, readJson, apiError } from '../api.js'
import { startGuardedInterval } from '../pageVisible.js'

export function useBackups({ snapshot, error, notice, reload }) {
  const loadAll = reload
  const backups = ref([])
  const backupInfo = ref({ backup_dir: '', legacy_dir: '', schedule: {} })
  const backupJob = ref(null)
  const restoreTarget = ref(null)
  const uploading = ref(false)
  let stopJobPollFn = null

  const backupJobRunning = computed(() => backupJob.value?.status === 'running')
  const backupOnConfigVolume = computed(() => {
    const dir = backupInfo.value.backup_dir || ''
    const config = snapshot.value.config_dir || ''
    return !!dir && !!config && (dir === config || dir.startsWith(`${config}/`))
  })
  const backupJobPercent = computed(() => {
    const job = backupJob.value
    if (!job || !job.total) return 0
    return Math.min(100, Math.round((job.done / job.total) * 100))
  })

  function stopJobPoll() {
    if (stopJobPollFn) stopJobPollFn()
    stopJobPollFn = null
  }

  function describeJob(job) {
    const result = job.result || {}
    if (job.status === 'error') return `${job.kind} failed: ${job.error}`
    if (job.kind === 'backup') {
      const warn = (result.warnings || []).length
      return `Created ${result.name}${warn ? ` with ${warn} warning(s)` : ''}.`
    }
    if (job.kind === 'verify') {
      return result.ok
        ? `${result.name} is intact (${result.checked} files checked).`
        : `${result.name} failed verification: ${result.error}`
    }
    if (job.kind === 'restore') {
      const parts = [`Restored ${result.files} files (${(result.sections || []).join(', ')}).`]
      if (result.safety_backup) parts.push(`Previous state saved as ${result.safety_backup}.`)
      if ((result.restarted || []).length) parts.push(`Restarted ${result.restarted.join(', ')}.`)
      if ((result.restart_failed || []).length) parts.push(`Could not restart ${result.restart_failed.join(', ')}.`)
      return parts.join(' ')
    }
    return 'Done.'
  }

  function watchJob(job) {
    backupJob.value = job
    stopJobPoll()
    if (!job || job.status !== 'running') return
    stopJobPollFn = startGuardedInterval(async () => {
      try {
        const res = await apiRequest('/api/backups/job')
        if (!res.ok) return
        const data = await readJson(res)
        backupJob.value = data.job
        if (!data.job || data.job.status !== 'running') {
          stopJobPoll()
          if (data.job?.status === 'error' || (data.job?.kind === 'verify' && !data.job?.result?.ok)) {
            error.value = describeJob(data.job)
          } else if (data.job) {
            notice.value = describeJob(data.job)
          }
          await loadAll()
        }
      } catch (_) {
        /* keep polling */
      }
    }, 1000)
  }

  async function startBackupJob(endpoint, body) {
    error.value = ''
    notice.value = ''
    try {
      const res = await apiRequest(endpoint, { method: 'POST', body: JSON.stringify(body || {}) })
      const data = await readJson(res)
      if (!res.ok) {
        error.value = apiError(data, 'Backup action failed.')
        return
      }
      watchJob(data.job)
    } catch (err) {
      error.value = err.message
    }
  }

  function createBackup() {
    return startBackupJob('/api/backups', { label: 'manual' })
  }

  function verifyBackup(name) {
    return startBackupJob(`/api/backups/${encodeURIComponent(name)}/verify`)
  }

  async function openRestore(name) {
    error.value = ''
    const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}`)
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, 'Could not read backup.')
      return
    }
    restoreTarget.value = { name, sections: data.sections || [], selected: ['all'] }
  }

  function toggleRestoreSection(value) {
    const target = restoreTarget.value
    if (!target) return
    if (value === 'all') {
      target.selected = ['all']
      return
    }
    const picked = new Set(target.selected.filter((item) => item !== 'all'))
    if (picked.has(value)) picked.delete(value)
    else picked.add(value)
    target.selected = picked.size ? [...picked] : ['all']
  }

  async function confirmRestore() {
    const target = restoreTarget.value
    if (!target) return
    const scope = target.selected.includes('all') ? 'everything' : target.selected.join(', ')
    if (!window.confirm(`Restore ${scope} from ${target.name}? Affected apps are stopped, the current state is saved first, then apps restart.`)) return
    restoreTarget.value = null
    await startBackupJob(`/api/backups/${encodeURIComponent(target.name)}/restore`, {
      sections: target.selected.includes('all') ? null : target.selected,
    })
  }

  async function downloadBackup(name) {
    error.value = ''
    try {
      const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}/download`)
      if (!res.ok) {
        const data = await readJson(res)
        error.value = apiError(data, `Download failed (HTTP ${res.status}).`)
        return
      }
      const url = URL.createObjectURL(await res.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = name
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) {
      error.value = err.message
    }
  }

  async function uploadBackup(event) {
    const file = event.target?.files?.[0]
    if (event.target) event.target.value = ''
    if (!file) return
    uploading.value = true
    error.value = ''
    notice.value = ''
    try {
      const res = await apiRequest(`/api/backups/upload?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        body: file,
        json: false,
        headers: { 'Content-Type': 'application/octet-stream' },
      })
      const data = await readJson(res)
      if (!res.ok) {
        error.value = apiError(data, 'Upload failed.')
        return
      }
      notice.value = `Uploaded ${data.backup?.name || file.name}. Verify it, then restore when ready.`
      await loadAll()
    } catch (err) {
      error.value = err.message
    } finally {
      uploading.value = false
    }
  }

  async function deleteBackup(name) {
    if (!window.confirm(`Delete ${name}?`)) return
    const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (res.ok) await loadAll()
  }

  function backupKindLabel(item) {
    return {
      manual: 'Manual',
      scheduled: 'Scheduled',
      'pre-restore': 'Before restore',
      uploaded: 'Uploaded',
    }[item.kind] || item.kind
  }


  function applyPayload(bak) {
    backups.value = bak.backups || []
    backupInfo.value = bak
    if (bak.job?.status === 'running' && !stopJobPollFn) watchJob(bak.job)
    else if (!stopJobPollFn) backupJob.value = bak.job
  }
  onUnmounted(stopJobPoll)
  return { backups, backupInfo, backupJob, restoreTarget, uploading, backupJobRunning, backupOnConfigVolume, backupJobPercent, stopJobPoll, watchJob, createBackup, verifyBackup, openRestore, toggleRestoreSection, confirmRestore, downloadBackup, uploadBackup, deleteBackup, backupKindLabel, applyPayload }
}
