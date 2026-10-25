<script setup>
/** The bar above the dock while arranging Home: which screen size to arrange, Add widget, Done, and an Undo note after a removal. */
import { ref, watch } from 'vue'
import { BREAKPOINTS } from './homeGrid.js'

const props = defineProps({
  bp: { type: String, required: true },
  /** Screen sizes this window can show, smallest first; one means there is nothing to switch. */
  previewOptions: { type: Array, default: () => [] },
  notOn: { type: Number, default: 0 },
  toast: { type: Object, default: null },
  /** Height of the dock below the bar, in px (0 when the dock is hidden). */
  dockOffset: { type: Number, default: 0 },
  /** Goes up on every save. */
  saves: { type: Number, default: 0 },
})
const emit = defineEmits(['preview', 'add', 'done', 'undo'])

const ICONS = {
  phone: 'M7 3h10a2.5 2.5 0 0 1 2.5 2.5v13A2.5 2.5 0 0 1 17 21H7a2.5 2.5 0 0 1-2.5-2.5v-13A2.5 2.5 0 0 1 7 3zM11 18h2',
  tablet: 'M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM11 18h2',
  desktop: 'M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 20h6M12 16v4',
}

const saved = ref(false)
let savedTimer = null
watch(
  () => props.saves,
  () => {
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => {
      saved.value = false
    }, 1400)
  },
)
</script>

<template>
  <Teleport to=".app-container">
    <div class="home-edit" :style="{ '--edit-dock': `${dockOffset}px` }">
      <div v-if="toast" class="home-edit-toast glass-pill" role="status">
        <span>{{ toast.text }}</span>
        <button type="button" class="ui-btn ui-btn-ghost" @click="emit('undo')">{{ $t('Undo') }}</button>
      </div>
      <div class="home-edit-bar glass-pill" role="toolbar" :aria-label="$t('Arrange Home')">
        <div v-if="previewOptions.length > 1" class="home-edit-sizes" role="group" :aria-label="$t('Screen size to arrange')">
          <button
            v-for="size in previewOptions"
            :key="size"
            type="button"
            :aria-pressed="size === bp"
            :title="$t('{label} layout · {count} columns', { label: $t(BREAKPOINTS[size].label), count: BREAKPOINTS[size].cols })"
            :aria-label="$t('{label} layout', { label: $t(BREAKPOINTS[size].label) })"
            @click="emit('preview', size)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="ICONS[size]" /></svg>
          </button>
        </div>
        <button v-if="notOn" type="button" class="home-edit-noton" @click="emit('add')">{{ $t('{count} not on {size}', { count: notOn, size: $t(BREAKPOINTS[bp].label) }) }}</button>
        <button type="button" class="ui-btn ui-btn-primary" @click="emit('add')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          {{ $t('Add widget') }}
        </button>
        <button type="button" class="ui-btn ui-btn-ghost" @click="emit('done')">{{ $t('Done') }}</button>
        <span class="home-edit-saved" :class="{ 'is-on': saved }" aria-hidden="true">{{ $t('Saved') }}</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.home-edit {
  position: fixed;
  left: 50%;
  bottom: calc(var(--edit-dock) + 1.75rem + env(safe-area-inset-bottom, 0px));
  transform: translateX(-50%);
  z-index: 41;
  width: max-content;
  max-width: calc(100% - 2rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
}
.home-edit-bar {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem;
  border-radius: 1.6rem;
  background: var(--control-bg);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
}
.home-edit-bar .ui-btn svg {
  width: 1rem;
  height: 1rem;
}
.home-edit-sizes {
  display: flex;
  gap: 0.15rem;
  padding: 0.2rem;
  border-radius: 999px;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
}
.home-edit-sizes button {
  width: 2.5rem;
  height: calc(var(--btn-h) - 0.4rem);
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.home-edit-sizes button[aria-pressed='true'] {
  background: var(--pill-active);
  color: var(--text-heading);
  box-shadow: inset 0 1px 0 var(--glass-highlight);
}
.home-edit-sizes svg {
  width: 1.1rem;
  height: 1.1rem;
}
.home-edit-noton {
  min-height: calc(var(--btn-h) - 0.5rem);
  padding: 0 0.85rem;
  border: 1px solid color-mix(in srgb, var(--color-warning) 45%, transparent);
  border-radius: 999px;
  background: var(--color-warning-bg);
  color: var(--color-warning-fg);
  font: inherit;
  font-size: var(--text-body);
  font-weight: 700;
  cursor: pointer;
}
.home-edit-saved {
  position: absolute;
  right: 1rem;
  top: -1.4rem;
  font-size: var(--text-kicker);
  font-weight: 600;
  color: var(--color-success-fg);
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}
.home-edit-saved.is-on {
  opacity: 1;
}
.home-edit-toast {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.3rem 0.35rem 0.3rem 1rem;
  background: var(--control-bg);
  font-size: var(--text-body);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
}
@media (prefers-reduced-motion: reduce) {
  .home-edit-saved {
    transition: none;
  }
}
</style>
