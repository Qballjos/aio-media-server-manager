import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { computed, ref, nextTick } from 'vue'

function panel(file, exports, apiRequest) {
  const source = readFileSync(new URL(`../src/${file}.vue`, import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*\n/gm, '')
  return runInNewContext(`${script}\n;({${exports.join(',')}})`, {
    computed, ref, nextTick, apiRequest, readJson: async response => response.data,
    apiError: data => data.detail || 'Request failed',
    defineExpose: () => {}, onMounted: () => {}, onUnmounted: () => {},
    setInterval: () => 1, clearInterval: () => {},
  })
}

test('preflight displays blocking conditions and cancellation does not start installation', async () => {
  const calls = []
  const view = panel('PreflightReview', ['review', 'finish', 'report', 'open'], async path => {
    calls.push(path)
    return { ok: true, data: { ok: false, checks: [{ name: 'storage', status: 'blocked', detail: 'Not enough space' }] } }
  })
  const result = view.review('sonarr')
  await setImmediate()
  assert.equal(view.report.value.ok, false)
  assert.equal(view.report.value.checks[0].detail, 'Not enough space')
  view.finish(false)
  assert.equal(await result, false)
  assert.equal(view.open.value, false)
  assert.equal(calls.length, 1)
})

test('installation activity can be dismissed and reopened with current stages', async () => {
  let status = 'installing'
  const view = panel('InstallationActivity', ['show', 'refresh', 'open', 'jobs'], async () => ({ ok: true, data: { jobs: [{ name: 'sonarr', status, history: [{ message: 'Download finished' }] }] } }))
  view.show(); await setImmediate()
  assert.equal(view.jobs.value[0].status, 'installing')
  view.open.value = false
  status = 'started'
  view.show(); await setImmediate()
  assert.equal(view.open.value, true)
  assert.equal(view.jobs.value[0].status, 'started')
  assert.equal(view.jobs.value[0].history[0].message, 'Download finished')
})

test('public indexer opt-in is explicit and does not start wiring by itself', async () => {
  const calls = []
  const view = panel('IntegrationCheck', ['choice', 'saveChoice'], async (path, options) => { calls.push([path, options]); return { ok: true, data: { enabled: true, indexers: [] } } })
  assert.equal(view.choice.value.enabled, false)
  view.choice.value.enabled = true
  await view.saveChoice()
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], '/api/integrations/public-indexers')
  assert.equal(JSON.parse(calls[0][1].body).enabled, true)
})

test('external settings preserve blank secrets and clear entered passwords after saving', async () => {
  const calls = []
  const view = panel('ExternalBackupSettings', ['form', 'save', 'error'], async (path, options) => {
    calls.push([path, options])
    return { ok: true, data: { enabled: true, url: 'https://dav.example/backups', username: 'user', password_saved: true, encryption_password_saved: true } }
  })
  view.form.value.url = 'https://dav.example/backups'
  view.form.value.enabled = true
  view.form.value.encryption_password = 'offline-recovery-password'
  await view.save()
  const body = JSON.parse(calls[0][1].body)
  assert.equal(body.password, null)
  assert.equal(body.encryption_password, 'offline-recovery-password')
  assert.equal(view.form.value.encryption_password, '')
  assert.equal(view.error.value, '')
})

test('external transfer failure is visible and releases busy controls', async () => {
  const view = panel('ExternalBackupSettings', ['run', 'name', 'error', 'busy'], async () => ({ ok: false, data: { detail: 'Backup is already running' } }))
  view.name.value = 'amm-test.tar.gz'
  await view.run('export')
  assert.equal(view.error.value, 'Backup is already running')
  assert.equal(view.busy.value, false)
})
