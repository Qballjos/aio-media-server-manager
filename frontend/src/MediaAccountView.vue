<script setup>
import { ref } from 'vue'
import SupportSettings from './settings/SupportSettings.vue'
import MediaDiscovery from './MediaDiscovery.vue'
import LanguageSelect from './LanguageSelect.vue'
import { getThemePreference, setThemePreference } from './theme.js'

defineProps({ settings: Boolean, support: Boolean, accountId: String })

const theme = ref(getThemePreference())
const themes = { system: 'System', light: 'Light', dark: 'Dark' }

function chooseTheme(value) {
  theme.value = setThemePreference(value)
}
</script>

<template>
  <section v-if="settings" class="member-page glass-card">
    <h2>{{ $t('Settings') }}</h2>
    <nav class="member-themes" :aria-label="$t('Settings sections')">
      <RouterLink :to="{ name: 'settings', params: { section: 'account' } }" class="ui-btn ui-btn-ghost">{{ $t('Profile') }}</RouterLink>
      <RouterLink :to="{ name: 'settings', params: { section: 'support' } }" class="ui-btn ui-btn-ghost">{{ $t('Support') }}</RouterLink>
    </nav>
    <SupportSettings v-if="support" class="member-support" />
    <template v-else>
      <dl>
        <dt>{{ $t('Media account ID') }}</dt>
        <dd>{{ accountId }}</dd>
      </dl>
      <h3>{{ $t('Language') }}</h3>
      <LanguageSelect />
      <h3>{{ $t('Theme') }}</h3>
      <div class="member-themes" role="group" :aria-label="$t('Theme')">
        <button v-for="(label, value) in themes" :key="value" type="button"
                class="theme-option" :class="{ 'is-active': theme === value }"
                :aria-pressed="theme === value" @click="chooseTheme(value)">{{ $t(label) }}</button>
      </div>
    </template>
  </section>
  <MediaDiscovery v-else />
</template>

<style scoped>
.member-page { max-inline-size: 42rem; margin-inline: auto; padding: 1.25rem; }
.member-page h2 { margin-block-start: 0; }
.member-page dd { margin-inline-start: 0; overflow-wrap: anywhere; }
.member-support { margin-block-start: 1rem; }
.member-themes { display: flex; flex-wrap: wrap; gap: .5rem; }
</style>
