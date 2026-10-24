<script setup>
import { onMounted, ref } from 'vue'
import { apiError, apiJson, applySession } from './api.js'
import { brandLogoUrl, brandLoginMessage, brandTitle } from './branding.js'
import { useToasts } from './useToasts.js'
import AppLoader from './AppLoader.vue'
import LanguageSelect from './LanguageSelect.vue'
import { t } from './i18n/index.js'

const emit = defineEmits(['status', 'session'])
const { showToast } = useToasts()

const authStatus = ref({
  setup_required: false,
  authenticated: false,
  username: null,
})
const authReady = ref(false)
const authStatusError = ref('')
const authForm = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})
const authError = ref('')
const authLoading = ref(false)

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function checkAuthStatus({ retries = 6 } = {}) {
  authReady.value = false
  authStatusError.value = ''
  let lastError = ''
  for (let attempt = 0; attempt < retries; attempt += 1) {
    if (attempt) await sleep(Math.min(400 * 2 ** (attempt - 1), 2000))
    try {
      const { res, data } = await apiJson('/api/auth/status')
      if (res.ok) {
        authStatus.value = data
        applySession(data)
        emit('status', data)
        if (data.authenticated) emit('session', data)
        authReady.value = true
        return
      }
      lastError = apiError(data, t('Could not reach the manager (HTTP {status}).', { status: res.status }))
    } catch (err) {
      lastError = err?.message || t('Could not reach the manager API.')
      console.error('Failed to check auth status:', err)
    }
  }
  authStatusError.value = lastError || t('Could not reach the manager API.')
  authReady.value = true
}

async function handleSetup() {
  authError.value = ''
  if (authForm.value.password.length < 8) {
    authError.value = t('Password must be at least 8 characters long.')
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(authForm.value.email.trim())) {
    authError.value = t('A valid email address is required.')
    return
  }
  if (authForm.value.password !== authForm.value.confirmPassword) {
    authError.value = t('Passwords do not match.')
    return
  }

  authLoading.value = true
  try {
    const { res, data } = await apiJson('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify({
        username: authForm.value.username.trim() || 'admin',
        email: authForm.value.email.trim(),
        password: authForm.value.password,
      }),
    })

    if (!res.ok) {
      authError.value = apiError(data, t('Setup failed.'))
      return
    }

    applySession(data)
    authForm.value.password = ''
    authForm.value.confirmPassword = ''
    showToast(t('Admin setup completed successfully! Welcome to AIO Media Server Manager.'), 'success')
    emit('session', data)
  } catch (err) {
    authError.value = t('Network error during setup: {message}', { message: err.message })
  } finally {
    authLoading.value = false
  }
}

async function handleLogin() {
  authError.value = ''
  authLoading.value = true
  try {
    const { res, data } = await apiJson('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        username: authForm.value.username.trim(),
        password: authForm.value.password,
      }),
    })

    if (!res.ok) {
      authError.value = apiError(data, t('Invalid username or password.'))
      return
    }

    applySession(data)
    authForm.value.password = ''
    showToast(t('Welcome back, {name}!', { name: data.username }), 'success')
    emit('session', data)
  } catch (err) {
    authError.value = t('Login error: {message}', { message: err.message })
  } finally {
    authLoading.value = false
  }
}

onMounted(() => {
  checkAuthStatus()
})
</script>

<template>
      <div v-if="authReady" class="auth-language">
        <LanguageSelect />
      </div>
      <section v-if="!authReady" class="auth-card-wrapper animate-fade">
        <AppLoader label="Connecting to the manager" />
      </section>
      <section v-else-if="authStatusError" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-header-accent">
            <h2>{{ $t('Manager unreachable') }}</h2>
            <p>{{ authStatusError }}</p>
          </div>
          <button type="button" class="ui-btn ui-btn-primary btn-block" @click="checkAuthStatus({ retries: 6 })">
            {{ $t('Retry connection') }}
          </button>
        </div>
      </section>
      <!-- 1. First-run Admin Setup View -->
      <section v-else-if="authStatus.setup_required" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-glow"></div>
          <div class="card-header-accent">
            <img
              :src="brandLogoUrl"
              :alt="brandTitle"
              class="auth-logo"
            />
            <span class="accent-badge">{{ $t('SETUP') }}</span>
            <h2>{{ $t('Create administrator') }}</h2>
            <p>{{ $t('Create the local admin account that protects the dashboard and API.') }}</p>
          </div>

          <form @submit.prevent="handleSetup" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label class="ui-field">{{ $t('Username') }}
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                autocomplete="username"
                class="ui-input font-mono"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">{{ $t('Email address') }}
              <input
                v-model="authForm.email"
                type="email"
                placeholder="you@example.com"
                required
                autocomplete="email"
                class="ui-input"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">{{ $t('Password (minimum 8 characters)') }}
              <input
                v-model="authForm.password"
                type="password"
                placeholder="••••••••••••"
                required
                class="ui-input"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">{{ $t('Confirm password') }}
              <input
                v-model="authForm.confirmPassword"
                type="password"
                placeholder="••••••••••••"
                required
                class="ui-input"
              />
              </label>
            </div>

            <button type="submit" :disabled="authLoading" class="ui-btn ui-btn-primary btn-block">
              <span v-if="authLoading" class="spinner"></span>
              <span v-else>{{ $t('Create account') }}</span>
            </button>
          </form>
        </div>
      </section>

      <!-- 2. Login View (when not authenticated & setup done) -->
      <section v-else-if="!authStatus.authenticated" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-glow"></div>
          <div class="card-header-accent">
            <img
              :src="brandLogoUrl"
              :alt="brandTitle"
              class="auth-logo"
            />
            <h2>{{ $t('Sign in') }}</h2>
            <p>{{ $t('Use the administrator username and password.') }}</p>
            <p v-if="brandLoginMessage" class="auth-personal-message">{{ brandLoginMessage }}</p>
          </div>

          <form @submit.prevent="handleLogin" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label class="ui-field">{{ $t('Username') }}
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                autofocus
                autocomplete="username"
                class="ui-input font-mono"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">{{ $t('Password') }}
              <input
                v-model="authForm.password"
                type="password"
                placeholder="••••••••••••"
                required
                class="ui-input"
              />
              </label>
            </div>

            <button type="submit" :disabled="authLoading" class="ui-btn ui-btn-primary btn-block">
              <span v-if="authLoading" class="spinner"></span>
              <span v-else>{{ $t('Sign in') }}</span>
            </button>
          </form>
        </div>
      </section>
</template>
