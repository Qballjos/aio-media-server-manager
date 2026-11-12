<script setup>
import { useI18n } from 'vue-i18n'
import { ref, onMounted } from 'vue'
import { apiRequest, readJson, apiError } from '../api.js'
import UiSelect from '../UiSelect.vue'
import IncidentHistory from '../IncidentHistory.vue'
const { t } = useI18n()
const saving = ref(false), error = ref(''), notice = ref('')
// Settings → Notifications: the saved state (secrets only as "saved") and the editable form.
const notif = ref(null)
const notifForm = ref({
  discord: { enabled: false, webhook_url: '' },
  email: { enabled: false, host: '', port: 587, security: 'starttls', username: '', password: '', sender: '', recipients: '' },
  events: {},
})
const notifTesting = ref('')
const NOTIF_EVENT_NAMES = { backups: 'Backups and restore', update_failures: 'Update failures', apps: 'Apps', vpn: 'VPN', tunnel: 'Cloudflare tunnel', updates: 'Updates', disk: 'Storage' }

function fillNotifForm(data) {
  notif.value = data
  notifForm.value = {
    discord: { enabled: data.discord.enabled, webhook_url: '' },
    email: { ...data.email, password: '', recipients: (data.email.recipients || []).join(', ') },
    disk_alert_percent: data.disk_alert_percent ?? 90,
    disk_clear_percent: data.disk_clear_percent ?? 85,
    events: { ...data.events },
  }
}

async function loadNotifications() {
  try {
    const res = await apiRequest('/api/notifications')
    if (res.ok) fillNotifForm(await readJson(res))
  } catch (_) {
    /* the form still works without the saved values */
  }
}

/** Blank secret fields keep what is saved; "Remove" sends an empty string. */
async function saveNotifications(overrides = {}) {
  saving.value = true
  error.value = ''
  notice.value = ''
  const form = notifForm.value
  const body = {
    discord: { enabled: form.discord.enabled, webhook_url: form.discord.webhook_url.trim() || null },
    email: { ...form.email, password: form.email.password || null },
    events: form.events,
    disk_alert_percent: Number(form.disk_alert_percent ?? 90),
    disk_clear_percent: Number(form.disk_clear_percent ?? 85),
  }
  delete body.email.password_saved
  if (overrides.removeWebhook) Object.assign(body.discord, { webhook_url: '', enabled: false })
  if (overrides.removePassword) body.email.password = ''
  try {
    const res = await apiRequest('/api/notifications', { method: 'PUT', body: JSON.stringify(body) })
    const data = await readJson(res)
    if (!res.ok) {
      error.value = apiError(data, t('Could not save notifications.'))
      return false
    }
    fillNotifForm(data)
    notice.value = t('Notifications saved.')
    return true
  } catch (err) {
    error.value = err?.message || t('Could not save notifications.')
    return false
  } finally {
    saving.value = false
  }
}

async function testNotification(channel) {
  if (!(await saveNotifications())) return
  notifTesting.value = channel
  try {
    const res = await apiRequest('/api/notifications/test', { method: 'POST', body: JSON.stringify({ channel }) })
    const data = await readJson(res)
    if (!res.ok) error.value = apiError(data, t('Could not send the test message.'))
    else notice.value = channel === 'discord' ? t('Test message sent to Discord.') : t('Test e-mail sent.')
  } catch (err) {
    error.value = err?.message || t('Could not send the test message.')
  } finally {
    notifTesting.value = ''
  }
}


onMounted(loadNotifications)
</script>

<template>
  <div class="settings-section">
    <p v-if="error" class="ui-alert ui-alert-error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
      <IncidentHistory />
      <form class="glass-card settings-card form-stack" @submit.prevent="saveNotifications()">
        <h3>{{ $t('Storage warning thresholds') }}</h3>
        <label class="ui-field">{{ $t('Warn above (%)') }}<input class="ui-input" type="number" min="2" max="99" v-model.number="notifForm.disk_alert_percent" /></label>
        <label class="ui-field">{{ $t('Recovered below (%)') }}<input class="ui-input" type="number" min="1" :max="(notifForm.disk_alert_percent || 90) - 1" v-model.number="notifForm.disk_clear_percent" /></label>
        <button class="ui-btn ui-btn-primary" :disabled="saving">{{ $t('Save') }}</button>
      </form>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>{{ $t('Discord') }}</h3>
          <p>{{ $t("Messages go to a Discord channel through a webhook: in Discord open the channel's settings → Integrations → Webhooks → New Webhook, and copy its URL.") }}</p>
        </div>
        <form class="form-stack" @submit.prevent="saveNotifications()">
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>{{ $t('Send to Discord') }}</strong>
              <span>{{ notif?.discord.webhook_saved ? $t("A webhook is saved.") : $t("No webhook saved yet.") }}</span>
            </div>
            <button
              type="button"
              class="ui-switch"
              role="switch"
              :aria-checked="notifForm.discord.enabled ? 'true' : 'false'"
              @click="notifForm.discord.enabled = !notifForm.discord.enabled"
            >
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <label class="ui-field">{{ $t('Webhook URL') }}
            <input
              v-model="notifForm.discord.webhook_url"
              class="ui-input font-mono"
              type="password"
              autocomplete="off"
              :placeholder="notif?.discord.webhook_saved ? $t('Saved — leave blank to keep') : 'https://discord.com/api/webhooks/…'"
            />
          </label>
          <div class="notif-actions">
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">{{ saving ? $t('Saving…') : $t('Save') }}</button>
            <button type="button" class="ui-btn ui-btn-ghost" :disabled="saving || !!notifTesting" @click="testNotification('discord')">
              {{ notifTesting === 'discord' ? $t('Sending…') : $t("Send a test") }}
            </button>
            <button v-if="notif?.discord.webhook_saved" type="button" class="ui-btn ui-btn-ghost" :disabled="saving" @click="saveNotifications({ removeWebhook: true })">{{ $t('Remove webhook') }}</button>
          </div>
        </form>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>{{ $t('E-mail') }}</h3>
          <p>{{ $t('Messages go out through your own mail server or provider (SMTP). Gmail and Outlook need an app password.') }}</p>
        </div>
        <form class="form-stack" @submit.prevent="saveNotifications()">
          <div class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>{{ $t('Send e-mail') }}</strong>
              <span>{{ $t('To every address under To.') }}</span>
            </div>
            <button
              type="button"
              class="ui-switch"
              role="switch"
              :aria-checked="notifForm.email.enabled ? 'true' : 'false'"
              @click="notifForm.email.enabled = !notifForm.email.enabled"
            >
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
          <div class="usenet-pair">
            <label class="ui-field">{{ $t('SMTP server') }}
              <input v-model.trim="notifForm.email.host" class="ui-input font-mono" placeholder="smtp.example.com" autocomplete="off" />
            </label>
            <label class="ui-field">{{ $t('Port') }}
              <input v-model.number="notifForm.email.port" class="ui-input font-mono" type="number" min="1" max="65535" />
            </label>
          </div>
          <label class="ui-field">{{ $t('Security') }}
            <UiSelect
              v-model="notifForm.email.security"
              :options="[
                { value: 'starttls', label: $t('STARTTLS (usually port 587)') },
                { value: 'ssl', label: $t('SSL/TLS (usually port 465)') },
                { value: 'none', label: $t('None (local relay only)') },
              ]"
            />
          </label>
          <div class="usenet-pair">
            <label class="ui-field">{{ $t('Username') }}
              <input v-model.trim="notifForm.email.username" class="ui-input font-mono" autocomplete="off" />
            </label>
            <label class="ui-field">{{ $t('Password') }}
              <input
                v-model="notifForm.email.password"
                class="ui-input"
                type="password"
                autocomplete="new-password"
                :placeholder="notif?.email.password_saved ? $t('Saved — leave blank to keep') : ''"
              />
            </label>
          </div>
          <label class="ui-field">{{ $t('From') }}
            <input v-model.trim="notifForm.email.sender" class="ui-input font-mono" :placeholder="$t('Defaults to the username')" autocomplete="off" />
          </label>
          <label class="ui-field">To
            <input v-model="notifForm.email.recipients" class="ui-input font-mono" placeholder="you@example.com, family@example.com" autocomplete="off" />
          </label>
          <div class="notif-actions">
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">{{ saving ? $t('Saving…') : $t('Save') }}</button>
            <button type="button" class="ui-btn ui-btn-ghost" :disabled="saving || !!notifTesting" @click="testNotification('email')">
              {{ notifTesting === 'email' ? $t('Sending…') : $t("Send a test") }}
            </button>
            <button v-if="notif?.email.password_saved" type="button" class="ui-btn ui-btn-ghost" :disabled="saving" @click="saveNotifications({ removePassword: true })">{{ $t('Remove password') }}</button>
          </div>
        </form>
      </div>
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>{{ $t('What to send') }}</h3>
          <p>{{ $t('Checked every minute. Each problem is sent once, and again when it is solved.') }}</p>
        </div>
        <div class="form-stack">
          <div v-for="(label, key) in notif?.event_labels || {}" :key="key" class="ui-switch-row">
            <div class="ui-switch-copy">
              <strong>{{ $t(NOTIF_EVENT_NAMES[key] || key) }}</strong>
              <span>{{ label }}</span>
            </div>
            <button
              type="button"
              class="ui-switch"
              role="switch"
              :aria-checked="notifForm.events[key] ? 'true' : 'false'"
              :disabled="saving"
              @click="notifForm.events[key] = !notifForm.events[key]; saveNotifications()"
            >
              <span class="ui-switch-thumb"></span>
            </button>
          </div>
        </div>
      </div>
  </div>
</template>
<style scoped src="./settingsForms.css"></style>
<style scoped>.settings-section { display: contents; }</style>
