import { test } from 'node:test'
import assert from 'node:assert/strict'
import { displaySize, setDisplaySize, initDisplaySize } from '../src/displaySize.js'

test('display size restores supported browser preferences and safely resets invalid values', () => {
  const values = new Map([['amm-display-size', 'compact']])
  const css = new Map()
  globalThis.localStorage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  globalThis.document = { documentElement: { style: { setProperty: (key, value) => css.set(key, value) } } }
  initDisplaySize()
  assert.equal(displaySize.value, 'compact')
  assert.equal(css.get('--display-scale'), '0.85')
  setDisplaySize('large')
  assert.equal(values.get('amm-display-size'), 'large')
  assert.equal(css.get('--display-scale'), '1.1')
  setDisplaySize('invalid')
  assert.equal(displaySize.value, 'standard')
  assert.equal(css.get('--display-scale'), '1')
  globalThis.localStorage = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') } }
  assert.doesNotThrow(initDisplaySize)
  assert.doesNotThrow(() => setDisplaySize('small'))
  assert.equal(displaySize.value, 'small')
  delete globalThis.localStorage
  delete globalThis.document
})
