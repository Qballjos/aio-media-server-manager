import assert from 'node:assert/strict'
import test from 'node:test'
import { ACCENT_PRESETS, DEFAULT_ACCENT, applyAccentColor, deriveAccent } from '../src/branding.js'

function contrast(first, second) {
  const luminance = (hex) => {
    const [red, green, blue] = hex.slice(1).match(/../g).map((channel) => {
      const srgb = parseInt(channel, 16) / 255
      return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue
  }
  const a = luminance(first)
  const b = luminance(second)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

test('preset and custom accents keep button text and panel actions readable', () => {
  const colors = new Set([...ACCENT_PRESETS.map(([hex]) => hex), '#16a34a'])
  for (const red of ['00', '33', '66', '99', 'cc', 'ff']) {
    for (const green of ['00', '33', '66', '99', 'cc', 'ff']) {
      for (const blue of ['00', '33', '66', '99', 'cc', 'ff']) colors.add(`#${red}${green}${blue}`)
    }
  }
  for (const color of colors) {
    const accent = deriveAccent(color)
    assert.equal(accent.primary, color, 'the configured accent is preserved')
    for (const [role, background] of [['button', '#ffffff'], ['buttonHover', '#ffffff'], ['textLight', '#e2e8f0'], ['textDark', '#475569']]) {
      assert.ok(contrast(accent[role], background) >= 4.5, `${color}: ${role} (${accent[role]}) needs 4.5:1 contrast`)
    }
  }
})

test('readable accents stay unchanged and invalid colors retain the default', () => {
  assert.equal(deriveAccent('#123456').button, '#123456')
  assert.equal(deriveAccent('  ABCDEF ').primary, '#abcdef')
  for (const invalid of [null, '', '#123', 'not-a-color']) assert.equal(deriveAccent(invalid).primary, DEFAULT_ACCENT)
})

test('applying an accent exposes readable tokens while caching the original color', (t) => {
  const originalDocument = globalThis.document
  const originalStorage = globalThis.localStorage
  const properties = new Map()
  const cache = new Map()
  globalThis.document = { documentElement: { style: { setProperty: (name, value) => properties.set(name, value) } } }
  globalThis.localStorage = { setItem: (name, value) => cache.set(name, value) }
  t.after(() => {
    if (originalDocument === undefined) delete globalThis.document
    else globalThis.document = originalDocument
    if (originalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalStorage
  })

  const accent = deriveAccent('#16a34a')
  assert.equal(applyAccentColor('#16a34a'), '#16a34a')
  assert.equal(cache.get('amm-accent'), '#16a34a')
  assert.equal(properties.get('--color-primary'), '#16a34a')
  assert.equal(properties.get('--color-primary-button'), accent.button)
  assert.equal(properties.get('--color-primary-button-hover'), accent.buttonHover)
  assert.equal(properties.get('--color-primary-text-light'), accent.textLight)
  assert.equal(properties.get('--color-primary-text-dark'), accent.textDark)
})
