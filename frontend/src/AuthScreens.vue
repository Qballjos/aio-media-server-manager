<script setup>
import { onMounted, ref } from 'vue'
import { apiError, apiJson, applySession } from './api.js'
import { useToasts } from './useToasts.js'

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
  username: 'admin',
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
      lastError = apiError(data, `Could not reach the manager (HTTP ${res.status}).`)
    } catch (err) {
      lastError = err?.message || 'Could not reach the manager API.'
      console.error('Failed to check auth status:', err)
    }
  }
  authStatusError.value = lastError || 'Could not reach the manager API.'
  authReady.value = true
}

async function handleSetup() {
  authError.value = ''
  if (authForm.value.password.length < 8) {
    authError.value = 'Password must be at least 8 characters long.'
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(authForm.value.email.trim())) {
    authError.value = 'A valid email address is required.'
    return
  }
  if (authForm.value.password !== authForm.value.confirmPassword) {
    authError.value = 'Passwords do not match.'
    return
  }

  authLoading.value = true
  try {
    const { res, data } = await apiJson('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify({
        username: authForm.value.username,
        email: authForm.value.email.trim(),
        password: authForm.value.password,
      }),
    })

    if (!res.ok) {
      authError.value = apiError(data, 'Setup failed.')
      return
    }

    applySession(data)
    authForm.value.password = ''
    authForm.value.confirmPassword = ''
    showToast('Admin setup completed successfully! Welcome to AIO Media Manager.', 'success')
    emit('session', data)
  } catch (err) {
    authError.value = 'Network error during setup: ' + err.message
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
        username: authForm.value.username,
        password: authForm.value.password,
      }),
    })

    if (!res.ok) {
      authError.value = apiError(data, 'Invalid username or password.')
      return
    }

    applySession(data)
    authForm.value.password = ''
    showToast(`Welcome back, ${data.username}!`, 'success')
    emit('session', data)
  } catch (err) {
    authError.value = 'Login error: ' + err.message
  } finally {
    authLoading.value = false
  }
}

onMounted(() => {
  checkAuthStatus()
})
</script>

<template>
      <section v-if="!authReady" class="auth-card-wrapper animate-fade">
        <p class="wizard-muted" style="text-align:center;color:#94a3b8;">Connecting to manager…</p>
      </section>
      <section v-else-if="authStatusError" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-header-accent">
            <h2>Manager unreachable</h2>
            <p>{{ authStatusError }}</p>
          </div>
          <button type="button" class="ui-btn ui-btn-primary btn-block" @click="checkAuthStatus({ retries: 6 })">
            Retry connection
          </button>
        </div>
      </section>
      <!-- 1. First-run Admin Setup View -->
      <section v-else-if="authStatus.setup_required" class="auth-card-wrapper animate-fade">
        <div class="glass-card auth-card">
          <div class="card-glow"></div>
          <div class="card-header-accent">
            <img
              src="/logo-aio-media-manager.png"
              alt="AIO Media Server Manager"
              class="auth-logo"
            />
            <span class="accent-badge">INITIAL SETUP</span>
            <h2>Create Administrator</h2>
            <p>Welcome! Set up the initial administrator account to protect and manage your server.</p>
          </div>

          <form @submit.prevent="handleSetup" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label class="ui-field">Administrator Username
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                class="ui-input font-mono"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">Email address
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
              <label class="ui-field">Admin Password (minimum 8 characters)
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
              <label class="ui-field">Confirm Password
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
              <span v-else>Initialize System & Log In</span>
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
              src="/logo-aio-media-manager.png"
              alt="AIO Media Server Manager"
              class="auth-logo"
            />
            <span class="accent-badge">SIGN IN</span>
            <h2>Manager Access</h2>
            <p>Enter your administrator credentials to manage services and server config.</p>
          </div>

          <form @submit.prevent="handleLogin" class="auth-form">
            <div v-if="authError" class="alert-banner alert-error">
              {{ authError }}
            </div>

            <div class="form-group">
              <label class="ui-field">Username
              <input
                v-model="authForm.username"
                type="text"
                placeholder="admin"
                required
                autofocus
                class="ui-input font-mono"
              />
              </label>
            </div>

            <div class="form-group">
              <label class="ui-field">Password
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
              <span v-else>Authenticate Session</span>
            </button>
          </form>
        </div>
      </section>
</template>
