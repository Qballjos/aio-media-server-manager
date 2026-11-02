import test from 'node:test'
import assert from 'node:assert/strict'
import { localeFromLanguage } from '../src/i18n/index.js'

test('the system language is used when we ship it, otherwise English', () => {
  assert.equal(localeFromLanguage('nl-NL'), 'nl')
  assert.equal(localeFromLanguage('de_DE'), 'de')
  assert.equal(localeFromLanguage('fr'), 'fr')
  assert.equal(localeFromLanguage('en-GB'), 'en')
  assert.equal(localeFromLanguage('es-ES'), 'en')
  assert.equal(localeFromLanguage(''), 'en')
  assert.equal(localeFromLanguage(undefined), 'en')
})
