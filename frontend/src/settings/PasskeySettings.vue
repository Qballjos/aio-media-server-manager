<script setup>
import { onMounted, ref } from 'vue'
import { canUsePasskeys, requestPasskey, usePasskey } from '../passkeys.js'

const supported = canUsePasskeys()
const origin = ref(null)
const configured = ref(false)
const twoFactor = ref(false)
const password = ref('')
const code = ref('')
const busy = ref(false)
const error = ref('')

async function run(operation) {
  busy.value = true
  error.value = ''
  try {
    await operation()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

function load() {
  return run(async () => {
    const data = await requestPasskey('')
    origin.value = data.origin
    twoFactor.value = data.two_factor_enabled
    configured.value = true
  })
}

function save() {
  const credentials = { password: password.value, code: code.value }
  password.value = ''
  code.value = ''
  return run(async () => {
    const data = origin.value
      ? await requestPasskey('/remove', credentials)
      : await usePasskey('register', credentials)
    origin.value = data.origin
  })
}

onMounted(load)
</script>

<template>
  <section class="glass-card settings-card">
    <div class="settings-card-head">
      <h3>{{ $t('Passkey') }}</h3>
      <p v-if="origin" role="status">{{ $t('A passkey is registered for {origin}.', { origin }) }}</p>
      <p v-else>{{ $t('Sign in with Touch ID or another passkey.') }}</p>
      <p v-if="!supported && !origin">{{ $t('Open this dashboard at its HTTPS address in a browser that supports passkeys.') }}</p>
    </div>

    <p v-if="error" class="alert-banner alert-error" role="alert">{{ error }}</p>

    <button v-if="!configured" type="button" class="ui-btn ui-btn-ghost" :disabled="busy" @click="load">
      {{ busy ? $t('Loading…') : $t('Try again') }}
    </button>

    <form v-else-if="supported || origin" class="form-stack" @submit.prevent="save">
      <label class="ui-field">{{ $t('Current password') }}
        <input v-model="password" type="password" class="ui-input" autocomplete="current-password" required />
      </label>
      <label v-if="twoFactor" class="ui-field">{{ $t('Authenticator or recovery code') }}
        <input v-model="code" class="ui-input" autocomplete="one-time-code" autocapitalize="off" spellcheck="false" maxlength="128" required />
      </label>
      <button class="ui-btn ui-btn-primary" type="submit" :disabled="busy">
        {{ busy ? $t('Saving…') : origin ? $t('Remove passkey') : $t('Add passkey') }}
      </button>
    </form>
  </section>
</template>

<style scoped src="./settingsForms.css"></style>
