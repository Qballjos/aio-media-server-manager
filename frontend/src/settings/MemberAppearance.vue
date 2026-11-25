<script setup>
import { computed, ref } from 'vue'
import AppearancePreview from './AppearancePreview.vue'
import LanguageSelect from '../LanguageSelect.vue'
import { ACCENT_PRESETS, applyAccentColor, brandAccent, DEFAULT_ACCENT } from '../branding.js'
import { applyWallpaper, cacheWallpaperImageUrl, clearWallpaperImage, encodeWallpaperFile, setWallpaperPreference, wallpaperCss, wallpaperState } from '../background.js'
import { DISPLAY_SIZES, displaySize, setDisplaySize } from '../displaySize.js'
import { GLASS_DEFAULTS, GLASS_RANGES, applyGlass, glass } from '../glass.js'
import { THEME_OPTIONS, getThemePreference, setThemePreference } from '../theme.js'
import { THEMES } from '../themes.js'

const mode = ref(getThemePreference())
const expanded = ref(false)
const error = ref(false)
const busy = ref(false)
const selection = computed(() => THEMES.find(theme => theme.wallpaper === wallpaperState.value.preset)?.id)
const sliders = { alpha: 'Transparency', blur: 'Blur', depth: 'Depth', wallpaperBlur: 'Wallpaper blur' }

function chooseMode(value) {
  mode.value = setThemePreference(value)
}

function chooseTheme(theme) {
  chooseMode(theme.mode)
  setWallpaperPreference(theme.wallpaper)
  applyAccentColor(theme.accent)
  applyGlass(theme.glass)
}

async function loadWallpaper(event) {
  const file = event.target.files?.[0]
  if (!file || busy.value) return
  busy.value = true
  error.value = false
  try {
    const blob = await encodeWallpaperFile(file)
    const reader = new FileReader()
    const image = await new Promise((resolve, reject) => {
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })
    cacheWallpaperImageUrl(image)
    setWallpaperPreference('personal')
    applyWallpaper('personal', image)
  } catch (_) {
    error.value = true
  } finally {
    busy.value = false
    event.target.value = ''
  }
}
</script>

<template>
  <AppearancePreview @select-glass="applyGlass" />
  <div class="glass-card settings-card">
    <div class="settings-card-head"><h3>{{ $t('Language') }}</h3></div>
    <LanguageSelect />
  </div>
  <div class="glass-card settings-card">
    <div class="settings-card-head"><h3>{{ $t('Themes') }}</h3></div>
    <div class="theme-gallery" :class="{ 'is-expanded': expanded }" role="group" :aria-label="$t('Themes')">
      <button v-for="theme in THEMES" :key="theme.id" type="button" class="theme-card"
              :class="{ 'is-active': selection === theme.id }" :aria-pressed="selection === theme.id" @click="chooseTheme(theme)">
        <span class="theme-card-art" :style="{ background: wallpaperCss(theme.wallpaper, 'dark') }">
          <span class="theme-card-day" :style="{ background: wallpaperCss(theme.wallpaper, 'light') }" />
          <span class="theme-card-dots" aria-hidden="true">
            <span v-for="color in [theme.accent, '#121628', '#ffffff', '#f59e0b']" :key="color" :style="{ background: color }" />
          </span>
        </span>
        <span class="theme-card-name">{{ $t(theme.name) }}</span>
      </button>
    </div>
    <button type="button" class="ui-btn ui-btn-ghost theme-gallery-more" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? $t('Show fewer themes') : $t('Show all {count} themes', { count: THEMES.length }) }}
    </button>
  </div>
  <div class="glass-card settings-card">
    <div class="settings-card-head"><h3>{{ $t('Color mode') }}</h3></div>
    <div class="theme-picker" role="group" :aria-label="$t('Color mode')">
      <button v-for="[value, label] in THEME_OPTIONS" :key="value" type="button" class="theme-option"
              :class="{ 'is-active': mode === value }" :aria-pressed="mode === value" @click="chooseMode(value)">{{ $t(label) }}</button>
    </div>
  </div>
  <div class="glass-card settings-card">
    <div class="settings-card-head"><h3>{{ $t('Display size') }}</h3></div>
    <div class="theme-picker" role="group" :aria-label="$t('Display size')">
      <button v-for="item in DISPLAY_SIZES" :key="item.value" type="button" class="theme-option"
              :class="{ 'is-active': displaySize === item.value }" :aria-pressed="displaySize === item.value"
              @click="setDisplaySize(item.value)">{{ $t(item.label) }}</button>
    </div>
  </div>
  <div class="glass-card settings-card">
    <div class="settings-card-head"><h3>{{ $t('Background and transparency') }}</h3></div>
    <div class="wallpaper-personal-actions">
      <label class="ui-field">{{ $t('Personal background image') }}
        <input type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy" @change="loadWallpaper" />
      </label>
      <button v-if="wallpaperState.image" type="button" class="ui-btn ui-btn-ghost" @click="clearWallpaperImage">{{ $t('Remove') }}</button>
    </div>
    <p v-if="error" class="ui-alert ui-alert-error" role="alert">{{ $t('Could not save background image.') }}</p>
    <details>
      <summary>{{ $t('Advanced') }}</summary>
      <div class="glass-sliders">
        <label v-for="(label, key) in sliders" :key="key" class="glass-slider">
          <span class="glass-slider-head"><span>{{ $t(label) }}</span><output>{{ key === 'alpha' ? Math.round((1 - glass.alpha) * 100) + '%' : glass[key] }}</output></span>
          <input type="range" :min="key === 'alpha' ? 1 - GLASS_RANGES.alpha[1] : GLASS_RANGES[key][0]" :max="key === 'alpha' ? 1 - GLASS_RANGES.alpha[0] : GLASS_RANGES[key][1]" :step="GLASS_RANGES[key][2]"
                 :value="key === 'alpha' ? 1 - glass.alpha : glass[key]" @input="applyGlass({ [key]: key === 'alpha' ? 1 - Number($event.target.value) : Number($event.target.value) })" />
        </label>
      </div>
      <button type="button" class="ui-btn ui-btn-ghost" @click="applyGlass(GLASS_DEFAULTS)">{{ $t('Reset to defaults') }}</button>
      <div class="theme-accent">
        <div class="theme-accent-copy">
          <strong>{{ $t('Accent colour') }}</strong>
          <span>{{ $t('Used for links and keyboard focus.') }}</span>
        </div>
        <div class="accent-presets" role="group" :aria-label="$t('Accent colour')">
          <button v-for="[color, label] in ACCENT_PRESETS" :key="color" type="button" class="accent-preset"
                  :class="{ 'is-active': brandAccent === color }" :aria-pressed="brandAccent === color"
                  :aria-label="$t(label)" :title="$t(label)" :style="{ '--accent-swatch': color, backgroundColor: color }"
                  @click="applyAccentColor(color)" />
        </div>
        <div class="wallpaper-personal-actions">
          <label class="ui-field">{{ $t('Accent colour') }}
            <input type="color" :value="brandAccent" @input="applyAccentColor($event.target.value)" />
          </label>
          <button type="button" class="ui-btn ui-btn-ghost" @click="applyAccentColor(DEFAULT_ACCENT)">{{ $t('Reset') }}</button>
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped src="../settingsPanel.css"></style>
