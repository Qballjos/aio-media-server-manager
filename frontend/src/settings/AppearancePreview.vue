<script setup>
import { computed } from 'vue'
import { wallpaperCss, wallpaperState } from '../background.js'
import { GLASS_PRESETS, glass } from '../glass.js'
import { resolvedTheme } from '../theme.js'

defineEmits(['select-glass'])
const selected = computed(() => GLASS_PRESETS.find(({ alpha, blur, depth }) =>
  Math.abs(glass.value.alpha - alpha) < 0.001 && glass.value.blur === blur && glass.value.depth === depth,
))
const background = computed(() => {
  const { preset, image } = wallpaperState.value
  return preset === 'personal' && image
    ? `url("${image}") center / cover`
    : wallpaperCss(preset, resolvedTheme.value)
})
</script>

<template>
  <section class="glass-card settings-card">
    <div class="settings-card-head"><h3>{{ $t('Appearance preview') }}</h3></div>
    <div class="appearance-preview" :style="{ background }" aria-hidden="true">
      <div class="glass-pill appearance-preview-nav">
        <span class="material-selected">{{ $t('Home') }}</span>
        <span>{{ $t('Catalog') }}</span><span>{{ $t('Settings') }}</span>
      </div>
      <div class="material-content appearance-preview-widget">
        <strong>{{ $t('Now playing') }}</strong>
        <span class="appearance-preview-progress"></span>
      </div>
      <div class="glass-chrome appearance-preview-dock">
        <img v-for="icon in ['jellyfin', 'sonarr', 'radarr']" :key="icon" :src="`/app-icons/${icon}.svg`" alt="" />
      </div>
    </div>
    <div class="theme-picker" role="group" :aria-label="$t('Glass style')">
      <button v-for="preset in GLASS_PRESETS" :key="preset.label" type="button" class="theme-option"
        :class="{ 'is-active': selected === preset }" :aria-pressed="selected === preset"
        @click="$emit('select-glass', { alpha: preset.alpha, blur: preset.blur, depth: preset.depth })">
        {{ $t(preset.label) }}
      </button>
      <span v-if="!selected" class="appearance-custom">{{ $t('Custom') }}</span>
    </div>
  </section>
</template>

<style scoped>
.appearance-preview { display:grid; gap:.65rem; justify-items:center; padding:1rem .6rem; border-radius:var(--radius-tile); }
.appearance-preview-nav, .appearance-preview-dock { display:flex; align-items:center; gap:.35rem; padding:.25rem; max-width:100%; }
.appearance-preview-nav { justify-content:center; flex-wrap:wrap; }
.appearance-preview + .theme-picker { margin-top:.75rem; }
.appearance-preview-nav span { font-size:var(--text-kicker); padding:.2rem .35rem; border-radius:var(--radius-control); }
.appearance-preview-widget { display:grid; gap:.6rem; width:min(100%, 20rem); padding:.75rem; border-radius:var(--radius-inset); }
.appearance-preview-progress { height:.25rem; border-radius:var(--radius-control); background:linear-gradient(to right, var(--color-info) 60%, var(--switch-track) 60%); }
.appearance-preview-dock img { width:1.55rem; height:1.55rem; object-fit:contain; }
.appearance-custom { align-self:center; padding:.35rem; color:var(--text-muted); }
</style>
