<script setup>
/** The sheet over Home while arranging it: pick a widget to add, or set one widget's size and remove it. */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { BREAKPOINTS, WIDGETS } from './homeGrid.js'

const props = defineProps({
  mode: { type: String, required: true },
  bp: { type: String, required: true },
  /** The widget whose sheet this is (mode 'widget'). */
  item: { type: Object, default: null },
  /** Widgets not on this screen size (mode 'add'). */
  missing: { type: Array, default: () => [] },
  /** Per missing widget, the other screen sizes it is on. */
  elsewhere: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['add', 'resize', 'remove', 'close'])

const everySize = ref(false)
const closeButton = ref(null)
const size = BREAKPOINTS[props.bp]

/** The widget's presets as they fit this screen size, each once. */
const presets = computed(() => {
  if (!props.item) return []
  const spec = WIDGETS[props.item.id]
  const seen = new Set()
  return spec.presets
    .map(([w, h, name]) => [Math.max(Math.min(w, size.cols), Math.min(spec.min[0], size.cols)), h, name])
    .filter(([w, h]) => {
      const key = `${w}x${h}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
})

function startSize(id) {
  const [w, h] = WIDGETS[id].size[props.bp]
  return `${w} × ${h}`
}

function onKey(event) {
  if (event.key !== 'Escape') return
  event.preventDefault()
  event.stopPropagation()
  emit('close')
}
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  closeButton.value?.focus()
})
onUnmounted(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <Teleport to=".app-container">
    <div class="home-sheet-layer" @click.self="emit('close')">
      <div
        class="home-sheet glass-card"
        role="dialog"
        aria-modal="true"
        :aria-label="mode === 'add' ? $t('Add widget') : $t('{name} settings', { name: WIDGETS[item.id].label })"
      >
        <div class="home-sheet-head">
          <h3>{{ mode === 'add' ? $t('Add widget') : $t(WIDGETS[item.id].label) }}</h3>
          <span class="home-sheet-dim">{{ mode === 'add' ? $t('{size} · {count} columns', { size: $t(size.label), count: size.cols }) : `${item.w} × ${item.h}` }}</span>
          <button ref="closeButton" type="button" class="ui-btn ui-btn-ghost ui-btn-icon" :aria-label="$t('Close')" @click="emit('close')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>

        <template v-if="mode === 'add'">
          <div class="home-sheet-section">
            <span class="home-sheet-label">{{ $t('Add to') }}</span>
            <div class="home-sheet-options" role="group" :aria-label="$t('Add to')">
              <button type="button" class="home-sheet-option" :class="{ 'is-on': !everySize }" :aria-pressed="!everySize" @click="everySize = false">
                {{ $t('This size') }}<small>{{ $t('{size} only', { size: $t(size.label) }) }}</small>
              </button>
              <button type="button" class="home-sheet-option" :class="{ 'is-on': everySize }" :aria-pressed="everySize" @click="everySize = true">
                {{ $t('Every size') }}<small>{{ $t('Phone, Tablet and Desktop') }}</small>
              </button>
            </div>
          </div>
          <div class="home-sheet-section">
            <span class="home-sheet-label">{{ $t('Widgets') }}</span>
            <div v-if="missing.length" class="home-sheet-pick">
              <button v-for="id in missing" :key="id" type="button" class="home-sheet-row" @click="emit('add', id, everySize)">
                <span class="home-sheet-row-text">
                  <strong>{{ $t(WIDGETS[id].label) }}</strong>
                  <span>{{ elsewhere[id]?.length ? $t('On {sizes}', { sizes: elsewhere[id].map((label) => $t(label)).join(', ') }) : $t('Not on any screen size yet') }}</span>
                </span>
                <span class="home-sheet-dim">{{ startSize(id) }}</span>
              </button>
            </div>
            <p v-else class="home-sheet-note">{{ $t('Every widget is already on this screen size.') }}</p>
          </div>
        </template>

        <template v-else>
          <div class="home-sheet-section">
            <span class="home-sheet-label">{{ $t('Size on {size}', { size: $t(size.label) }) }}</span>
            <div class="home-sheet-options">
              <button
                v-for="[w, h, name] in presets"
                :key="`${w}x${h}`"
                type="button"
                class="home-sheet-option"
                :class="{ 'is-on': item.w === w && item.h === h }"
                :aria-pressed="item.w === w && item.h === h"
                @click="emit('resize', w, h)"
              >
                {{ $t(name) }}<small>{{ w }} × {{ h }}</small>
              </button>
            </div>
            <p class="home-sheet-note">{{ $t('Or drag the corner of the widget for any size in between.') }}</p>
          </div>
          <button type="button" class="ui-btn ui-btn-ghost home-sheet-remove" @click="emit('remove')">{{ $t('Remove from {size}', { size: $t(size.label) }) }}</button>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.home-sheet-layer {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 1.5rem;
  background: rgb(0 0 0 / 0.35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.home-sheet {
  width: min(28rem, 100%);
  max-height: calc(100dvh - 3rem);
  overflow-y: auto;
  padding: 1.15rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.home-sheet-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.home-sheet-head h3 {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 1.1rem;
  font-weight: 800;
}
.home-sheet-dim {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--text-muted);
  white-space: nowrap;
}
.home-sheet-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.home-sheet-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.home-sheet-options {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.home-sheet-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  padding: 0.5rem 0.8rem;
  border: 1px solid var(--border-subtle);
  border-radius: 0.8rem;
  background: var(--bg-surface);
  color: var(--text-main);
  font: inherit;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
}
.home-sheet-option small {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-muted);
}
.home-sheet-option.is-on {
  border-color: rgba(var(--color-primary-rgb), 0.7);
  background: rgba(var(--color-primary-rgb), 0.14);
}
.home-sheet-pick {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.home-sheet-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--border-subtle);
  border-radius: 0.9rem;
  background: var(--bg-surface);
  color: var(--text-main);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.home-sheet-row:hover,
.home-sheet-option:hover {
  border-color: var(--border-hover);
}
.home-sheet-row-text {
  flex: 1;
  min-width: 0;
  display: grid;
}
.home-sheet-row-text span {
  font-size: 0.8rem;
  color: var(--text-muted);
}
.home-sheet-note {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-muted);
}
.home-sheet-remove {
  align-self: flex-start;
  color: var(--color-danger-fg);
}
@media (max-width: 719px) {
  .home-sheet-layer {
    place-items: end center;
    padding: 0;
  }
  .home-sheet {
    width: 100%;
    border-radius: var(--radius-glass) var(--radius-glass) 0 0;
    padding-bottom: calc(1.15rem + env(safe-area-inset-bottom, 0px));
  }
}
</style>
