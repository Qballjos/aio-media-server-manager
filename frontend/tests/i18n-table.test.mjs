import test from 'node:test'
import assert from 'node:assert/strict'
import { TABLE } from '../src/i18n/locales/table.js'

test('every locale has a translation and the same placeholders', () => {
  for (const [key, values] of Object.entries(TABLE)) {
    assert.equal(values.length, 3, key)
    const placeholders = (text) => [...String(text).matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort()
    const expected = placeholders(key)
    for (const value of values) {
      assert.ok(value, key)
      assert.deepEqual(placeholders(value), expected, `${key} -> ${value}`)
      assert.equal(value.includes('|'), false, key)
      assert.equal(value.includes('@'), false, key)
    }
  }
})
