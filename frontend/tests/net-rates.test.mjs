import assert from 'node:assert/strict'
import test from 'node:test'
import { addNetSample } from '../src/netRates.js'

test('two samples give bytes per second down and up', () => {
  let history = addNetSample([], { at: 100, rx: 1_000_000, tx: 50_000 })
  history = addNetSample(history, { at: 110, rx: 21_000_000, tx: 150_000 })
  assert.deepEqual(history, [
    { at: 100, rx: 1_000_000, tx: 50_000, rxRate: null, txRate: null },
    { at: 110, rx: 21_000_000, tx: 150_000, rxRate: 2_000_000, txRate: 10_000 },
  ])
})

test('a counter that went backwards starts the graph over instead of spiking', () => {
  let history = addNetSample([], { at: 100, rx: 9_000_000, tx: 9_000 })
  history = addNetSample(history, { at: 110, rx: 9_500_000, tx: 9_500 })
  history = addNetSample(history, { at: 120, rx: 1_000, tx: 10 })
  assert.deepEqual(history, [{ at: 120, rx: 1_000, tx: 10, rxRate: null, txRate: null }])
})

test('the same sample twice adds nothing', () => {
  const history = addNetSample([], { at: 100, rx: 10, tx: 10 })
  assert.equal(addNetSample(history, { at: 100, rx: 10, tx: 10 }), history)
})

test('history keeps only the most recent points', () => {
  let history = []
  for (let i = 0; i < 40; i++) history = addNetSample(history, { at: i * 10, rx: i * 1000, tx: i * 100 }, 30)
  assert.equal(history.length, 30)
  assert.equal(history[0].at, 100)
  assert.equal(history.at(-1).rxRate, 100)
})
