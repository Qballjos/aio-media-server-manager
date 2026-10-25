<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { LOCALES, setLocale } from './i18n/index.js'
import { saveLocaleToProfile } from './visualsProfile.js'

const props = defineProps({
  persist: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
  codes: { type: Boolean, default: false },
})

const SHORT = { en: 'en', nl: 'nl', de: 'du', fr: 'fr' }

const { t, locale } = useI18n()
const open = ref(false)

async function choose(code) {
  setLocale(code)
  open.value = false
  if (!props.persist) return
  try {
    await saveLocaleToProfile(code)
  } catch (_) {}
}
</script>

<template>
  <div v-if="codes" class="locale-dock">
    <div v-if="open" class="locale-pop" role="listbox" :aria-label="t('Language')">
      <button
        v-for="item in LOCALES"
        :key="item.code"
        type="button"
        class="locale-code"
        :class="{ 'is-active': locale === item.code }"
        :aria-selected="locale === item.code"
        :lang="item.code"
        @click="choose(item.code)"
      >
        {{ SHORT[item.code] }}
      </button>
    </div>
    <button
      type="button"
      class="locale-dock-btn"
      :aria-expanded="open"
      :aria-label="t('Language')"
      @click="open = !open"
    >
      {{ SHORT[locale] || locale }}
    </button>
  </div>
  <div v-else class="language-picker" :class="{ 'is-compact': compact }" role="group" :aria-label="t('Language')">
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

<style scoped>
.locale-dock {
  position: fixed;
  right: max(0.85rem, env(safe-area-inset-right));
  bottom: max(0.85rem, env(safe-area-inset-bottom));
  z-index: 40;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.locale-dock-btn,
.locale-code {
  appearance: none;
  border: 1px solid var(--border-subtle);
  background: var(--menu-bg, var(--pill-bg));
  color: var(--text-main);
  font: inherit;
  font-size: var(--text-kicker);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: lowercase;
  cursor: pointer;
}

.locale-dock-btn {
  min-height: 2rem;
  padding: 0 0.75rem;
  border-radius: 999px;
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
}

.locale-pop {
  display: grid;
  gap: 0.2rem;
  margin-bottom: 0.4rem;
  padding: 0.3rem;
  border-radius: 14px;
  background: var(--menu-bg);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-card);
}

.locale-code {
  min-width: 3.2rem;
  min-height: 1.9rem;
  padding: 0 0.55rem;
  border-radius: 10px;
  background: transparent;
}

.locale-code.is-active,
.locale-dock-btn[aria-expanded='true'] {
  color: var(--text-heading);
  border-color: rgba(var(--color-primary-rgb), 0.55);
  background: var(--pill-active);
}
</style>
