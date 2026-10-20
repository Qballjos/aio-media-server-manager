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
