<script setup>
import { useI18n } from 'vue-i18n'
import { LOCALES, setLocale } from './i18n/index.js'
import { saveLocaleToProfile } from './visualsProfile.js'

const props = defineProps({
  persist: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const { t, locale } = useI18n()

async function choose(code) {
  setLocale(code)
  if (!props.persist) return
  try {
    await saveLocaleToProfile(code)
  } catch (_) {}
}
</script>

<template>
  <div class="language-picker" :class="{ 'is-compact': compact }" role="group" :aria-label="t('Language')">
    <button
      v-for="item in LOCALES"
      :key="item.code"
      type="button"
      class="theme-option"
      :class="{ 'is-active': locale === item.code }"
      :aria-pressed="locale === item.code"
      :lang="item.code"
      @click="choose(item.code)"
    >
      {{ item.label }}
    </button>
  </div>
</template>
