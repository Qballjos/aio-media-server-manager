import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, nextTick, ref } from 'vue'
import { useHomeCalendar } from '../src/composables/useHomeCalendar.js'

function calendar(items = [], wide = false) {
  const scope = effectScope(), snapshot = ref({ calendar: items }), calendarWide = ref(wide)
  const state = scope.run(() => useHomeCalendar({ snapshot, calendarWide }))
  return { ...state, snapshot, calendarWide, dispose: () => scope.stop() }
}

test('responsive default changes until the user explicitly selects a view', async () => {
  const state = calendar([], true)
  try {
    assert.equal(state.calView.value, 'week')
    state.calendarWide.value = false
    await nextTick()
    assert.equal(state.calView.value, 'list')
    state.setCalView('month')
    state.calendarWide.value = true
    await nextTick()
    assert.equal(state.calView.value, 'month')
  } finally { state.dispose() }
})

test('a group of episodes only links to the library when every episode is available', () => {
  const state = calendar()
  try {
    const rows = [1, 2].map((episode) => ({ dt: new Date(2026, 10, 2, 12 + episode), item: {
      title: 'Test series', detail: `S01E0${episode}`, has_file: episode === 1,
      play_url: 'episode', series_play_url: 'series',
    } }))
    let grouped = state.groupSameDay(rows)
    assert.equal(grouped.length, 1)
    assert.equal(grouped[0].item.has_file, false)
    rows[1].item.has_file = true
    grouped = state.groupSameDay(rows)
    assert.equal(grouped[0].item.has_file, true)
    assert.equal(grouped[0].item.play_url, 'series')
    assert.match(grouped[0].item.detail, /2 episodes/)
  } finally { state.dispose() }
})

test('month navigation crosses the year boundary and invalid dates are ignored', () => {
  const state = calendar([{ title: 'Invalid', when: 'invalid' }])
  try {
    state.setCalView('month')
    state.calCursor.value = new Date(2026, 11, 1)
    state.shiftCalendar(1)
    assert.equal(state.calCursor.value.getFullYear(), 2027)
    assert.equal(state.calCursor.value.getMonth(), 0)
    assert.equal(state.calendarDays.value.flatMap(day => day.events).length, 0)
    assert.equal(state.parseWhen('invalid'), null)
    assert.equal(state.parseWhen('1793620800').getTime(), 1793620800000)
  } finally { state.dispose() }
})

test('downloaded calendar items prefer the media server and missing items use the automation app', () => {
  const state = calendar()
  try {
    assert.deepEqual(state.calendarTarget({ has_file: true, play_app: 'jellyfin', play_url: 'watch', source: 'sonarr', url: 'manage' }), { app: 'jellyfin', url: 'watch' })
    assert.deepEqual(state.calendarTarget({ has_file: false, source: 'sonarr', url: 'manage' }), { app: 'sonarr', url: 'manage' })
    assert.equal(state.calendarTarget({}), null)
  } finally { state.dispose() }
})
