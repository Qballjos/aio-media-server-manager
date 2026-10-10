import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { homeSnapshotCache, partialRetryDelay } from '../src/homeSnapshotCache.js'

function panel(apiRequest, timers) {
  const source = readFileSync(new URL('../src/HomepagePanel.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*\n/gm, '')
  return runInNewContext(`${script}\n;({snapshot, loading, widgetsPending, loadSnapshot})`, {
    computed, reactive, ref, apiRequest, homeSnapshotCache, partialRetryDelay,
    readJson: async (response) => response.data,
    defineEmits: () => () => {},
    defineProps: () => ({}),
    useRoute: () => ({ query: {} }),
    appWebUrl: () => 'http://localhost:5055',
    onMounted: () => {},
    onUnmounted: () => {},
    watch: () => {},
    setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length },
    clearTimeout: () => {},
  })
}

test('partial snapshots are re-fetched quickly with a short, bounded back-off', () => {
  const delays = [0, 1, 2, 3, 4, 5].map(partialRetryDelay)
  assert.deepEqual(delays.slice(0, 5), [800, 1600, 3200, 5000, 5000])
  assert.equal(partialRetryDelay(8), null)
})

test('home shows the cached snapshot at once and refetches a partial one without waiting for the poll', async () => {
  homeSnapshotCache.snapshot = null
  const timers = []
  let partial = true
  const first = panel(async () => ({ ok: true, data: { apps: [{ name: 'seerr', state: 'running' }], partial } }), timers)
  assert.equal(first.loading.value, true)
  await first.loadSnapshot()
  assert.equal(first.loading.value, false)
  assert.equal(first.widgetsPending.value, true)
  assert.equal(timers.length, 1)
  assert.equal(timers[0].delay, 800)

  partial = false
  await timers[0].fn()
  assert.equal(first.widgetsPending.value, false)
  assert.equal(timers.length, 1)

  // Coming back to Home later: the last snapshot renders immediately.
  const again = panel(async () => ({ ok: true, data: { apps: [] } }), [])
  assert.equal(again.loading.value, false)
  assert.equal(again.snapshot.value.apps[0].name, 'seerr')
})
