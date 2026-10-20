import assert from 'node:assert/strict'
import test from 'node:test'
import * as home from '../src/homeLayout.js'

test('an old Home keeps its order, hidden cards and hidden dock until someone arranges the grid', async () => {
  home.homeGrid.value = {}
  home.homeLayout.value = ['downloads', 'apps', 'search', 'calendar', 'recent', 'requests', 'trending']
  home.homeSizes.value = { calendar: 12 }
  home.homeHidden.value = ['trending', 'apps']

  const desktop = home.layoutFor('desktop')
  assert.deepEqual(desktop.map((item) => item.id), ['downloads', 'search', 'calendar', 'recent', 'requests'])
  assert.equal(home.dockHidden.value, true)
  assert.ok(home.layoutFor('phone').every((item) => item.w === 4))

  // Showing the dock again leaves the hidden card hidden.
  await home.setDockHidden(false)
  assert.deepEqual(home.homeHidden.value, ['trending'])
  assert.equal(home.layoutFor('desktop').some((item) => item.id === 'trending'), false)
})

test('arranging one screen size keeps desktop and leaves the others derived', () => {
  home.homeGrid.value = {}
  home.homeLayout.value = []
  home.homeSizes.value = {}
  home.homeHidden.value = []
  const before = home.layoutFor('desktop')

  home.saveGridLayout('phone', [{ id: 'downloads', x: 0, y: 0, w: 2, h: 2 }])
  assert.deepEqual(home.homeGrid.value.desktop, before)
  assert.deepEqual(home.layoutFor('phone'), [{ id: 'downloads', x: 0, y: 0, w: 2, h: 2 }])
  assert.equal(home.homeGrid.value.tablet, undefined)

  home.restoreGrid({})
  assert.deepEqual(home.homeGrid.value, {})
})

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

test('grid saves reach the server one at a time and in order', async () => {
  await wait(400) // let earlier tests' saves go out first
  const realFetch = globalThis.fetch
  const sent = []
  const answers = []
  globalThis.fetch = (url, options) => {
    sent.push(JSON.parse(options.body).homepage_grid.phone[0].x)
    return new Promise((resolve) => answers.push(() => resolve({ ok: true, status: 200 })))
  }
  try {
    home.saveGridLayout('phone', [{ id: 'downloads', x: 0, y: 0, w: 2, h: 2 }])
    await wait(350)
    assert.deepEqual(sent, [0])
    home.saveGridLayout('phone', [{ id: 'downloads', x: 2, y: 0, w: 2, h: 2 }])
    await wait(350)
    assert.deepEqual(sent, [0], 'the second save waits until the first one is answered')
    answers.shift()()
    await wait(20)
    assert.deepEqual(sent, [0, 2])
    answers.shift()()
    await wait(20)
  } finally {
    globalThis.fetch = realFetch
  }
})

test('a grid save the server never got is not overwritten by an older copy from the profile', async () => {
  await wait(50)
  const realFetch = globalThis.fetch
  globalThis.fetch = async () => {
    throw new Error('offline')
  }
  try {
    home.saveGridLayout('phone', [{ id: 'downloads', x: 1, y: 0, w: 2, h: 2 }])
    await wait(350)
    home.applyHomeLayoutFromProfile({ homepage_grid: {} })
    assert.deepEqual(home.layoutFor('phone'), [{ id: 'downloads', x: 1, y: 0, w: 2, h: 2 }])
  } finally {
    globalThis.fetch = realFetch
  }
})
