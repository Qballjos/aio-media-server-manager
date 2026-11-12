import { useI18n } from 'vue-i18n'
import { ref, computed, onUnmounted } from 'vue'
import { apiRequest, readJson, apiError } from '../api.js'
import { startGuardedInterval } from '../pageVisible.js'

export function useBackups({ snapshot, error, notice, reload }) {
  const { t } = useI18n()
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
    if (job.status === 'error') return t('{kind} failed: {error}', { kind: t(job.kind), error: job.error })
    if (job.kind === 'backup') {
      const warn = (result.warnings || []).length
      return warn ? t('Created {name} with {count} warning(s).', { name: result.name, count: warn }) : t('Created {name}.', { name: result.name })
    }
    if (job.kind === 'verify') {
      return result.ok
        ? t('{name} is intact ({count} files checked).', { name: result.name, count: result.checked })
        : t('{name} failed verification: {error}', { name: result.name, error: result.error })
    }
    if (job.kind === 'restore') {
      const parts = [t('Restored {count} files ({sections}).', { count: result.files, sections: (result.sections || []).map(section => t(section)).join(', ') })]
      if (result.safety_backup) parts.push(t('Previous state saved as {name}.', { name: result.safety_backup }))
      if ((result.restarted || []).length) parts.push(t('Restarted {apps}.', { apps: result.restarted.join(', ') }))
      if ((result.restart_failed || []).length) parts.push(t('Could not restart {apps}.', { apps: result.restart_failed.join(', ') }))
      return parts.join(' ')
    }
    return t('Done.')
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
        error.value = apiError(data, t('Backup action failed.'))
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
      error.value = apiError(data, t('Could not read backup.'))
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
    const scope = target.selected.includes('all') ? t('everything') : target.selected.map(section => t(section)).join(', ')
    if (!window.confirm(t('Restore {scope} from {name}? Affected apps are stopped, the current state is saved first, then apps restart.', { scope, name: target.name }))) return
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
        error.value = apiError(data, t('Download failed (HTTP {status}).', { status: res.status }))
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
        error.value = apiError(data, t('Upload failed.'))
        return
      }
      notice.value = t('Uploaded {name}. Verify it, then restore when ready.', { name: data.backup?.name || file.name })
      await loadAll()
    } catch (err) {
      error.value = err.message
    } finally {
      uploading.value = false
    }
  }

  async function deleteBackup(name) {
    if (!window.confirm(t('Delete {name}?', { name }))) return
    const res = await apiRequest(`/api/backups/${encodeURIComponent(name)}`, { method: 'DELETE' })
    if (res.ok) await loadAll()
  }

  function backupKindLabel(item) {
    return {
      manual: t('Manual'),
      scheduled: t('Scheduled'),
      'pre-restore': t('Before restore'),
      uploaded: t('Uploaded'),
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
