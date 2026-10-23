import assert from 'node:assert/strict'
import test from 'node:test'
import { attentionMood, serverMood, storageMood } from '../src/statusMood.js'

test('the server line names what is under strain', () => {
  assert.deepEqual(serverMood({ cpu_percent: 12, memory_percent: 40, temperature: 41 }), { level: 'ok', text: 'Running smoothly' })
  assert.deepEqual(serverMood({ cpu_percent: 75, memory_percent: 40, temperature: null }), { level: 'warn', text: 'CPU is busy' })
  assert.deepEqual(serverMood({ cpu_percent: 75, memory_percent: 95, temperature: 41 }), { level: 'crit', text: 'Memory is almost full' })
  assert.deepEqual(serverMood({ cpu_percent: 10, memory_percent: 20, temperature: 86 }), { level: 'crit', text: 'Running hot' })
})

test('storage and attention lines', () => {
  assert.equal(storageMood(18).text, 'Plenty of space')
  assert.equal(storageMood(85).level, 'warn')
  assert.equal(storageMood(93).text, 'Almost full')
  assert.deepEqual(attentionMood([]), { level: 'ok', text: 'All clear' })
  assert.deepEqual(attentionMood([{ level: 'info' }]), { level: 'ok', text: '1 thing to look at' })
  assert.deepEqual(attentionMood([{ level: 'warning' }, { level: 'problem' }]), { level: 'crit', text: '2 things need a look' })
})
