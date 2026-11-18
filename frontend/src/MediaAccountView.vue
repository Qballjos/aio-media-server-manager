<script setup>
import { computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import SettingsSidebar from './SettingsSidebar.vue'
import SupportSettings from './settings/SupportSettings.vue'
import MemberAppearance from './settings/MemberAppearance.vue'
import MediaDiscovery from './MediaDiscovery.vue'
import { MEMBER_SETTINGS_GROUPS, MEMBER_SETTINGS_PAGES } from './settingsNavigation.js'
import { homeEditing } from './homeLayout.js'

const props = defineProps({ settings: Boolean, section: String, accountId: String })
const router = useRouter()
const page = computed(() => MEMBER_SETTINGS_PAGES.find(item => item.id === props.section) || MEMBER_SETTINGS_PAGES[0])

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
      <div v-else class="glass-card settings-card">
        <dl class="member-profile">
          <dt>{{ $t('Media account ID') }}</dt>
          <dd>{{ accountId }}</dd>
        </dl>
      </div>
    </div>
  </section>
  <MediaDiscovery v-else :account-id="accountId" />
</template>

<style scoped src="./settingsPanel.css"></style>
<style scoped>
.member-profile { margin: 0; }
.member-profile dd { margin-inline-start: 0; overflow-wrap: anywhere; }
</style>
