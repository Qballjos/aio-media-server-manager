import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import { computed, reactive, ref } from 'vue'

function setup(file, exports, apiRequest) {
  const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*\n/gm, '')
  return runInNewContext(`${script}\n;({${exports.join(',')}})`, {
    computed, reactive, ref, apiRequest,
    homeSnapshotCache: { snapshot: null }, partialRetryDelay: () => null,
    readJson: async (response) => response.data,
    defineEmits: () => () => {},
    defineProps: () => ({}),
    useRoute: () => ({ query: {} }),
    appWebUrl: () => 'http://localhost:5055',
    onMounted: () => {},
    onUnmounted: () => {},
    watch: () => {},
    setTimeout: () => { throw new Error('Must not wait for configuration to enqueue the next app') },
  })
}

test('wizard shows configuration and real progress without blocking the next package', async () => {
  const row = {
    name: 'seerr', installed: true, install_job: 'configuring',
    install_message: 'Waiting for Jellyfin', install_updated_at: 123,
  }
  const panel = setup('WizardPanel.vue', ['installProgress', 'refreshInstallProgress', 'waitForAppInstall', 'installPercent'],
    async () => ({ ok: true, data: { applications: [row] } }))
  panel.installProgress.value = [{ name: 'seerr', status: 'installing' }, { name: 'sonarr', status: 'queued' }]
  await panel.waitForAppInstall('seerr')
  assert.equal(panel.installProgress.value[0].status, 'configuring')
  assert.equal(panel.installProgress.value[0].message, 'Waiting for Jellyfin')
  assert.equal(panel.installProgress.value[0].updatedAt, 123)
  assert.equal(panel.installPercent.value, 0)

  row.install_job = 'failed'
  row.install_error = 'Connection failed'
  await panel.refreshInstallProgress()
  assert.equal(panel.installProgress.value[0].status, 'failed')
  assert.equal(panel.installProgress.value[0].detail, 'Connection failed')
  assert.equal(panel.installPercent.value, 50)
})

test('failed live job immediately disables a cached running Home tile', () => {
  const panel = setup('HomepagePanel.vue', ['snapshot', 'installJobs', 'launcherGroups', 'launcherOpen'], async () => {})
  panel.snapshot.value.apps = [{ name: 'seerr', state: 'running', category: 'requests' }]
  panel.installJobs.value = { seerr: { status: 'failed', message: 'Build failed', updated_at: 123 } }
  const app = panel.launcherGroups.value[0].apps[0]
  assert.equal(app.state_label, 'Setup failed')
  assert.equal(app.sick, true)
  assert.equal(app.progress_message, 'Build failed')
  assert.equal(panel.launcherOpen(app), false)
})

test('home uses real timestamps, preserves stale progress, and refreshes once on completion', async () => {
  let job = { name: 'seerr', status: 'configuring', message: 'Waiting for Jellyfin', updated_at: 123 }
  let offline = false
  const calls = []
  const panel = setup('HomepagePanel.vue', ['snapshot', 'installJobs', 'loadInstallJobs'], async (path) => {
    calls.push(path)
    if (offline) throw new Error('Network unavailable')
    const data = path === '/api/catalog/install-jobs'
      ? { jobs: [{ ...job }] }
      : { apps: [{ name: 'seerr', state: 'running' }] }
    return { ok: true, data }
  })
  panel.snapshot.value.apps = [{ name: 'seerr', state: 'configuring' }]
  await panel.loadInstallJobs()
  await panel.loadInstallJobs()
  assert.equal(panel.installJobs.value.seerr.updated_at, 123)
  assert.deepEqual(calls, ['/api/catalog/install-jobs', '/api/catalog/install-jobs'])

  offline = true
  await panel.loadInstallJobs()
  assert.equal(panel.installJobs.value.seerr.message, 'Waiting for Jellyfin')
  assert.equal(panel.installJobs.value.seerr.updated_at, 123)

  offline = false
  job = { ...job, status: 'started', message: 'Ready', updated_at: 456 }
  await panel.loadInstallJobs()
  await setImmediate()
  await panel.loadInstallJobs()
  assert.equal(calls.filter((path) => path === '/api/homepage?refresh=1').length, 1)
  assert.equal(panel.snapshot.value.apps[0].state, 'running')
})
