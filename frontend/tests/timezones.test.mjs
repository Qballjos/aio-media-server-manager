import test from 'node:test'
import assert from 'node:assert/strict'
import { timezoneChoices } from '../src/timezones.js'

test('timezone list leads with UTC and keeps an unusual current value', () => {
  const options = timezoneChoices('Pacific/Honolulu')
  assert.equal(options[0].value, 'UTC')
  assert.ok(options.length > 6)
  assert.ok(options.some((opt) => opt.value === 'Europe/Amsterdam'))
  assert.ok(options.some((opt) => opt.value === 'Pacific/Honolulu'))
  const york = options.find((opt) => opt.value === 'America/New_York')
  assert.equal(york.label, 'America/New York')
})
