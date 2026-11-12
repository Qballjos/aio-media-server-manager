import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

function accountForms() {
  const source = readFileSync(new URL('../src/SettingsPanel.vue', import.meta.url), 'utf8')
  const script = source.slice(source.indexOf('async function saveAccount()'), source.indexOf('async function runUpdateCheck()'))
  const requests = []
  const state = {
    saving: { value: false }, passwordSaving: { value: false },
    error: { value: '' }, notice: { value: '' },
    form: { value: { username: 'admin', first_name: 'Jozef', last_name: 'Ball', email: 'admin@example.com' } },
    passwordForm: { value: { current_password: 'current-secret', new_password: 'new-secret', confirm_password: 'new-secret' } },
    apiRequest: async (url, options) => { requests.push({ url, body: JSON.parse(options.body) }); return { ok: true } },
    readJson: async () => ({}), emit: () => {}, t: text => text,
    apiError: (_, fallback) => fallback, applyProfileAvatar: () => {},
  }
  const handlers = runInNewContext(`${script}; ({saveAccount, savePassword})`, state)
  return { ...state, ...handlers, requests }
}

test('profile save sends personal details without password fields', async () => {
  const form = accountForms()
  await form.saveAccount()
  assert.deepEqual(form.requests, [{ url: '/api/auth/profile', body: {
    username: 'admin', first_name: 'Jozef', last_name: 'Ball', email: 'admin@example.com',
  } }])
  assert.equal(form.passwordForm.value.current_password, 'current-secret')
})

test('password form rejects mismatch then submits only passwords and clears secrets', async () => {
  const form = accountForms()
  form.passwordForm.value.confirm_password = 'different'
  await form.savePassword()
  assert.equal(form.requests.length, 0)
  assert.equal(form.error.value, 'New passwords do not match.')
  form.passwordForm.value.confirm_password = 'new-secret'
  await form.savePassword()
  assert.deepEqual(form.requests, [{ url: '/api/auth/account', body: {
    current_password: 'current-secret', new_password: 'new-secret',
  } }])
  assert.equal(form.passwordForm.value.current_password, '')
  assert.equal(form.form.value.first_name, 'Jozef')
})
