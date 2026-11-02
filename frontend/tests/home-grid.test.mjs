import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  BREAKPOINTS,
  GRID_IDS,
  LEGACY_IDS,
  WIDGETS,
  bpForWidth,
  collapseEmptyRows,
  collides,
  deriveLayout,
  firstFree,
  fitItem,
  fromLegacy,
  normalizeLayout,
  resolve,
} from '../src/homeGrid.js'

const byId = (layout) => Object.fromEntries(layout.map((item) => [item.id, item]))
const readingOrder = (layout) => [...layout].sort((a, b) => a.y - b.y || a.x - b.x).map((item) => item.id)

function assertNoOverlap(layout, cols = 12) {
  for (const item of layout) {
    assert.ok(item.x >= 0 && item.y >= 0 && item.x + item.w <= cols, `${item.id} sits inside ${cols} columns`)
  }
  for (let i = 0; i < layout.length; i++) {
    for (let j = i + 1; j < layout.length; j++) {
      assert.ok(!collides(layout[i], layout[j]), `${layout[i].id} and ${layout[j].id} overlap`)
    }
  }
}

test('resolve swaps two equal neighbours', () => {
  const layout = [
    { id: 'search', x: 0, y: 0, w: 6, h: 3 },
    { id: 'recent', x: 6, y: 0, w: 6, h: 3 },
  ]
  const out = byId(resolve(layout, 'recent', { x: 0, y: 0, w: 6, h: 3 }, 12, layout[1]))
  assert.deepEqual([out.recent.x, out.recent.y], [0, 0])
  assert.deepEqual([out.search.x, out.search.y], [6, 0])
})

test('resolve leaves untouched widgets in place', () => {
  const layout = [
    { id: 'search', x: 0, y: 0, w: 6, h: 3 },
    { id: 'recent', x: 6, y: 0, w: 6, h: 3 },
    { id: 'calendar', x: 0, y: 3, w: 12, h: 3 },
  ]
  const out = byId(resolve(layout, 'recent', { x: 0, y: 0, w: 6, h: 3 }, 12, layout[1]))
  assert.deepEqual(out.calendar, { id: 'calendar', x: 0, y: 3, w: 12, h: 3 })
})

test('resolve never overlaps', () => {
  const base = [
    { id: 'search', x: 0, y: 0, w: 12, h: 2 },
    { id: 'recent', x: 0, y: 2, w: 4, h: 3 },
    { id: 'calendar', x: 4, y: 2, w: 4, h: 3 },
    { id: 'downloads', x: 8, y: 2, w: 4, h: 3 },
    { id: 'requests', x: 0, y: 5, w: 6, h: 3 },
    { id: 'trending', x: 6, y: 5, w: 6, h: 3 },
  ]
  for (let x = 0; x <= 8; x++) {
    for (let y = 0; y <= 6; y++) {
      const out = resolve(base, 'recent', { x, y, w: 4, h: 3 }, 12, base[1])
      assert.equal(out.length, base.length)
      assert.deepEqual([byId(out).recent.x, byId(out).recent.y], [x, y])
      assertNoOverlap(out)
    }
  }
})

test('firstFree finds the first hole in reading order', () => {
  const layout = [
    { id: 'search', x: 0, y: 0, w: 4, h: 2 },
    { id: 'recent', x: 8, y: 0, w: 4, h: 2 },
  ]
  assert.deepEqual(firstFree(layout, 4, 2, 12), { x: 4, y: 0 })
  assert.deepEqual(firstFree(layout, 6, 1, 12), { x: 0, y: 2 })
})

test('normalizeLayout sanitises bad data', () => {
  const out = normalizeLayout(
    [
      { id: 'bogus', x: 0, y: 0, w: 2, h: 2 },
      { id: 'search', x: 0, y: 0, w: 12, h: 2 },
      { id: 'search', x: 0, y: 4, w: 4, h: 2 },
      { id: 'recent', x: -2, y: 0, w: 40, h: 0 },
      { id: 'calendar', x: 0, y: 1, w: 6, h: 4 },
      { id: 'downloads', x: '3', y: '2', w: 4, h: 4 },
      { id: 'requests', x: 'left', y: 0, w: 4, h: 3 },
    ],
    'desktop',
  )
  assert.deepEqual(out.map((item) => item.id).sort(), ['calendar', 'downloads', 'greeting', 'recent', 'searchbar'])
  assert.deepEqual(byId(out).greeting, { id: 'greeting', x: 0, y: 0, w: 12, h: 1 })
  assert.ok(byId(out).recent.h >= 3, 'recent keeps its minimum height')
  assertNoOverlap(out)
})

test('fromLegacy keeps order, widths and hidden cards', () => {
  const out = fromLegacy({ order: ['downloads', 'apps', 'search', 'calendar', 'recent'], sizes: { calendar: 12 }, hidden: ['trending', 'apps'] })
  const items = byId(out)
  assert.equal(items.apps, undefined)
  assert.equal(items.trending, undefined)
  assert.equal(items.downloads.y, 0)
  assert.ok(items.greeting.y >= items.downloads.y + items.downloads.h, 'the greeting sits below downloads')
  assert.deepEqual([items.searchbar.x, items.searchbar.y, items.searchbar.w], [0, items.greeting.y + 1, 12])
  assert.equal(items.calendar.w, 12)
  assert.ok(items.requests, 'a card missing from the old order is added')
  assert.deepEqual(readingOrder(out).slice(0, 5), ['downloads', 'greeting', 'searchbar', 'calendar', 'recent'])
  assertNoOverlap(out)
})

test('fromLegacy with empty input gives the default arrangement', () => {
  const out = fromLegacy({})
  assert.deepEqual(out.map((item) => item.id).sort(), ['calendar', 'downloads', 'greeting', 'recent', 'requests', 'searchbar', 'trending'])
  assert.deepEqual(byId(out).greeting, { id: 'greeting', x: 0, y: 0, w: 12, h: 1 })
  assert.deepEqual(byId(out).searchbar, { id: 'searchbar', x: 0, y: 1, w: 12, h: 1 })
  assertNoOverlap(out)
})

test('the old greeting-and-search widget becomes a greeting above a search bar, in the same place', () => {
  assert.deepEqual(normalizeLayout([{ id: 'search', x: 0, y: 0, w: 12, h: 2 }, { id: 'recent', x: 0, y: 2, w: 12, h: 3 }], 'desktop'), [
    { id: 'greeting', x: 0, y: 0, w: 12, h: 1 },
    { id: 'searchbar', x: 0, y: 1, w: 12, h: 1 },
    { id: 'recent', x: 0, y: 2, w: 12, h: 3 },
  ])
  // On one row the greeting keeps the left half.
  assert.deepEqual(normalizeLayout([{ id: 'search', x: 0, y: 0, w: 12, h: 1 }], 'desktop'), [
    { id: 'greeting', x: 0, y: 0, w: 6, h: 1 },
    { id: 'searchbar', x: 6, y: 0, w: 6, h: 1 },
  ])
})

test('deriveLayout keeps reading order on phone', () => {
  const desktop = fromLegacy({})
  for (const bp of ['phone', 'tablet']) {
    const cols = bp === 'phone' ? 4 : 8
    const out = deriveLayout(desktop, bp)
    assert.deepEqual(readingOrder(out), readingOrder(desktop))
    assertNoOverlap(out, cols)
  }
})

test('collapseEmptyRows closes rows left by hidden widgets', () => {
  const out = byId(
    collapseEmptyRows([
      { id: 'search', x: 0, y: 0, w: 12, h: 2 },
      { id: 'recent', x: 0, y: 5, w: 6, h: 2 },
    ]),
  )
  assert.equal(out.search.y, 0)
  assert.deepEqual([out.recent.x, out.recent.y, out.recent.w], [0, 2, 6])
})

test('bpForWidth follows the existing breakpoints', () => {
  assert.equal(bpForWidth(719), 'phone')
  assert.equal(bpForWidth(720), 'tablet')
  assert.equal(bpForWidth(1199), 'tablet')
  assert.equal(bpForWidth(1200), 'desktop')
})

test('the newer widgets wait in Add widget instead of joining an existing Home', () => {
  for (const id of ['playing', 'storage', 'server', 'attention', 'other']) {
    assert.ok(GRID_IDS.includes(id), `${id} is a widget`)
    assert.ok(!LEGACY_IDS.includes(id), `${id} is not part of the old Home`)
    assert.equal(fromLegacy({ order: ['search', id] }).some((item) => item.id === id), false)
  }
  assert.deepEqual(normalizeLayout([{ id: 'playing', x: 0, y: 0, w: 6, h: 3 }], 'desktop'), [{ id: 'playing', x: 0, y: 0, w: 6, h: 3 }])
})

test('every widget starts at a size it allows, on every screen size', () => {
  for (const id of GRID_IDS) {
    for (const [bp, { cols }] of Object.entries(BREAKPOINTS)) {
      const [w, h] = WIDGETS[id].size[bp]
      assert.deepEqual(fitItem({ id, x: 0, y: 0, w, h }, cols), { id, x: 0, y: 0, w, h }, `${id} on ${bp}`)
    }
  }
})
