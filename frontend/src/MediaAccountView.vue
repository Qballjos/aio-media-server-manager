<script setup>
import StreamingSettings from './settings/StreamingSettings.vue'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SettingsSidebar from './SettingsSidebar.vue'
import SupportSettings from './settings/SupportSettings.vue'
import MemberAppearance from './settings/MemberAppearance.vue'
import MediaDiscovery from './MediaDiscovery.vue'
import { MEMBER_SETTINGS_GROUPS, MEMBER_SETTINGS_PAGES } from './settingsNavigation.js'
import { apiJson } from './api.js'
import { homeEditing } from './homeLayout.js'

const emit = defineEmits(['session'])
const props = defineProps({ settings: Boolean, section: String, accountId: String })
const router = useRouter()
const page = computed(() => MEMBER_SETTINGS_PAGES.find(item => item.id === props.section) || MEMBER_SETTINGS_PAGES[0])

const profile = ref(null)
const displayName = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
const avatarBusy = ref(false)
const avatarError = ref('')
const avatarNotice = ref('')

async function loadProfile() {
  loading.value = true
  error.value = ''
  try {
    const { res, data } = await apiJson('/api/media-discovery/profile')
    if (!res.ok) throw new Error()
    profile.value = data
    displayName.value = data.display_name
    emit('session', { username: data.username, avatar_url: data.avatar_url || null })
  } catch (_) {
    error.value = 'Could not load your profile.'
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    const { res, data } = await apiJson('/api/media-discovery/profile', {
      method: 'PATCH',
      body: JSON.stringify({ display_name: displayName.value }),
    })
    if (!res.ok) throw new Error()
    profile.value = { ...profile.value, display_name: data.display_name }
    displayName.value = data.display_name
    saved.value = true
  } catch (_) {
    error.value = 'Could not update account.'
  } finally {
    saving.value = false
  }
}

async function updateAvatar(file) {
  const uploading = Boolean(file)
  avatarBusy.value = true
  avatarError.value = ''
  avatarNotice.value = ''
  try {
    const { res, data } = await apiJson('/api/media-discovery/profile/avatar', uploading ? {
      method: 'PUT', body: file,
    } : { method: 'DELETE' })
    if (!res.ok) throw new Error()
    profile.value = { ...profile.value, avatar_url: data.avatar_url }
    emit('session', { avatar_url: data.avatar_url })
    avatarNotice.value = uploading ? 'Profile image updated.' : 'Profile image removed.'
  } catch (_) {
    avatarError.value = uploading ? 'Could not upload profile image.' : 'Could not remove profile image.'
  } finally {
    avatarBusy.value = false
  }
}

function chooseAvatar(event) {
  const input = event.target
  const file = input.files?.[0]
  input.value = ''
  if (file) updateAvatar(file)
}

onMounted(loadProfile)

async function arrangeHome() {
  await router.push({ name: 'home' })
  await nextTick()
  homeEditing.value = true
}
</script>

<template>
  <section v-if="settings" class="settings-page glass-card animate-fade" :aria-label="$t('Settings')">
    <SettingsSidebar :section="page.id" :navigation="MEMBER_SETTINGS_GROUPS" />
    <div class="settings-content">
      <header class="settings-header">
        <h2 class="section-title">{{ $t(page.label) }}</h2>
        <p class="section-subtitle">{{ $t(page.description) }}</p>
      </header>
      <SupportSettings v-if="page.id === 'support'" class="settings-card" />
      <MemberAppearance v-else-if="page.id === 'visuals'" />
      <div v-else-if="page.id === 'homepage'" class="glass-card settings-card">
        <button type="button" class="ui-btn ui-btn-ghost" @click="arrangeHome">{{ $t('Edit the Home layout') }}</button>
      </div>
      <div v-else class="glass-card settings-card settings-profile-card">
        <p v-if="loading" role="status">{{ $t('Loading…') }}</p>
        <template v-else-if="profile">
          <div class="brand-asset-list account-avatar-block" :aria-busy="avatarBusy">
            <div class="brand-asset-row">
              <div class="account-avatar-preview" :class="{ 'has-image': profile.avatar_url }" aria-hidden="true">
                <img v-if="profile.avatar_url" :src="profile.avatar_url" alt="" />
                <span v-else>{{ (profile.username || 'A').charAt(0).toUpperCase() }}</span>
              </div>
              <div class="brand-asset-copy">
                <strong>{{ $t('Profile image') }}</strong>
                <span>{{ $t('PNG, JPEG, WebP or GIF, up to 2 MB.') }}</span>
              </div>
              <div class="brand-asset-actions">
                <label class="ui-btn ui-btn-ghost brand-upload-btn">
                  {{ $t(avatarBusy ? 'Saving…' : 'Upload') }}
                  <input type="file" accept="image/png,image/jpeg,image/webp,image/gif"
                         :aria-label="$t('Upload profile image')" :disabled="avatarBusy" @change="chooseAvatar" />
                </label>
                <button v-if="profile.avatar_url" type="button" class="ui-btn ui-btn-ghost"
                        :disabled="avatarBusy" @click="updateAvatar()">{{ $t('Remove') }}</button>
              </div>
            </div>
            <p v-if="avatarError" role="alert">{{ $t(avatarError) }}</p>
            <p v-else-if="avatarNotice" role="status">{{ $t(avatarNotice) }}</p>
          </div>
          <form class="form-stack profile-form" @submit.prevent="saveProfile">
            <label class="ui-field">{{ $t('Username') }}
              <input class="ui-input" :value="profile.username || $t('Unavailable')" readonly />
            </label>
            <label class="ui-field">{{ $t('Display name') }}
              <input v-model="displayName" class="ui-input" maxlength="80" autocomplete="nickname"
                     :placeholder="profile.username" :disabled="saving" @input="saved = false" />
            </label>
            <button type="submit" class="ui-btn ui-btn-primary" :disabled="saving">{{ $t(saving ? 'Saving…' : 'Save profile') }}</button>
          </form>
        </template>
        <p v-if="error" role="alert">{{ $t(error) }}</p>
        <p v-else-if="saved" role="status">{{ $t('Account updated.') }}</p>
      </div>
      <StreamingSettings v-if="page.id === 'account'" scope="member" />
    </div>
  </section>
  <MediaDiscovery v-else :account-id="accountId" :display-name="profile?.display_name || profile?.username" />
</template>

<style scoped src="./settingsPanel.css"></style>
