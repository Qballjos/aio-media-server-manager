<script>
import { shallowRef } from 'vue'

// Keep the one-time result available when navigating away while enable is in flight.
const pendingRecovery = shallowRef(null)
</script>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { apiJson, applySession, getAuthToken } from '../api.js'
import { t } from '../i18n/index.js'

const emit = defineEmits(['changed'])
const path = '/api/auth/two-factor'
const enabled = ref(null)
const enrollment = ref(null)
const recovery = computed(() => {
  const pending = pendingRecovery.value
  return pending?.token === getAuthToken() ? pending.codes : []
})
const qr = ref('')
const password = ref('')
const code = ref('')
const busy = ref(false)
const error = ref('')
const confirmation = ref(null)

async function send(action, body) {
  const options = body ? { method: 'POST', body: JSON.stringify(body) } : {}
  const { res, data } = await apiJson(path + action, options)
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? t(data.detail) : t('Could not update two-factor authentication.'))
  return data
}

async function run(operation) {
  busy.value = true
  error.value = ''
  try {
    await operation()
  } catch (err) {
    error.value = err.message || t('Could not update two-factor authentication.')
  } finally {
    busy.value = false
  }
}

function load() {
  return run(async () => {
    enabled.value = (await send('')).enabled
  })
}

async function start() {
  await run(async () => {
    enrollment.value = await send('/setup', { password: password.value })
    password.value = ''
    await nextTick()
    confirmation.value?.focus()
    try {
      const { default: QRCode } = await import('qrcode')
      const image = await QRCode.toDataURL(enrollment.value.uri, { scale: 5 })
      if (enrollment.value) qr.value = image
    } catch {
      // Manual enrollment remains available if local QR rendering fails.
    }
  })
}

function acknowledgeRecovery() {
  enabled.value = true
  pendingRecovery.value = null
}

function clearSetup() {
  enrollment.value = null
  qr.value = ''
  code.value = ''
}

function enable() {
  return run(async () => {
    const data = await send('/enable', { enrollment: enrollment.value.enrollment, code: code.value })
    applySession(data)
    enabled.value = true
    emit('changed')
    pendingRecovery.value = { token: data.access_token, codes: data.recovery_codes }
    clearSetup()
  })
}

function disable() {
  return run(async () => {
    const data = await send('/disable', { password: password.value, code: code.value })
    applySession(data)
    enabled.value = false
    emit('changed')
    password.value = ''
    code.value = ''
  })
}

onMounted(load)
</script>

<template>
  <section class="glass-card settings-card">
    <div class="settings-card-head">
      <h3>{{ $t('Two-factor authentication') }}</h3>
      <p v-if="enabled !== null" role="status">
        {{ enabled || recovery.length ? $t('Two-factor authentication is enabled.') : $t('Protect your manager login with an authenticator app.') }}
      </p>
    </div>

    <p v-if="error" class="alert-banner alert-error" role="alert">{{ error }}</p>

    <button v-if="enabled === null && !recovery.length" type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="load">
      {{ busy ? $t('Loading…') : $t('Try again') }}
    </button>

    <div v-else-if="recovery.length" class="form-stack">
      <label class="ui-field">{{ $t('Recovery codes') }}
        <textarea class="ui-input" rows="10" readonly :value="recovery.join('\n')" aria-describedby="recovery-help"></textarea>
      </label>
      <p id="recovery-help">{{ $t('Store these codes safely. Each code works once and is shown only now.') }}</p>
      <button type="button" class="ui-btn ui-btn-primary" @click="acknowledgeRecovery">{{ $t('I saved my recovery codes') }}</button>
    </div>

    <form v-else-if="enrollment" class="form-stack" @submit.prevent="enable">
      <p>{{ $t('Scan this QR code with your authenticator app or enter the setup key manually.') }}</p>
      <img v-if="qr" :src="qr" :alt="$t('Authenticator setup QR code')" width="180" height="180" />
      <label class="ui-field">{{ $t('Setup key') }}
        <input class="ui-input" :value="enrollment.secret" readonly autocomplete="off" spellcheck="false" />
      </label>
      <label class="ui-field">{{ $t('Authenticator code') }}
        <input ref="confirmation" v-model="code" class="ui-input" inputmode="numeric" autocomplete="one-time-code"
               pattern="[0-9]{6}" maxlength="6" required />
      </label>
      <button class="ui-btn ui-btn-primary" type="submit" :disabled="busy">{{ busy ? $t('Saving…') : $t('Enable two-factor authentication') }}</button>
      <button class="ui-btn ui-btn-ghost" type="button" :disabled="busy" @click="clearSetup(); error = ''">{{ $t('Cancel') }}</button>
    </form>

    <form v-else class="form-stack" @submit.prevent="enabled ? disable() : start()">
      <label class="ui-field">{{ $t('Current password') }}
        <input v-model="password" type="password" class="ui-input" autocomplete="current-password" required />
      </label>
      <label v-if="enabled" class="ui-field">{{ $t('Authenticator or recovery code') }}
        <input v-model="code" class="ui-input" autocomplete="one-time-code" autocapitalize="off" spellcheck="false" maxlength="128" required />
      </label>
      <button class="ui-btn ui-btn-primary" type="submit" :disabled="busy">
        {{ busy ? $t('Saving…') : enabled ? $t('Disable two-factor authentication') : $t('Set up authenticator') }}
      </button>
    </form>
  </section>
</template>

<style scoped src="./settingsForms.css"></style>
