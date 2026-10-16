<script setup>
/** The handle shown on a Home block in edit mode: name, width (cards only), move up/down, hide/show. */
defineProps({
  label: { type: String, required: true },
  hidden: { type: Boolean, default: false },
  first: { type: Boolean, default: false },
  last: { type: Boolean, default: false },
  sizable: { type: Boolean, default: false },
  /** 0 = share the row with its neighbours, 4 = a third, 6 = half, 12 = the full row. */
  size: { type: Number, default: 0 },
})
defineEmits(['move', 'toggle', 'resize'])
const SIZE_LABELS = { 0: 'Auto', 4: '⅓', 6: '½', 12: 'Full' }
const SIZE_NEXT = { 0: 'a third', 4: 'half', 6: 'the full row', 12: 'automatic' }
</script>

<template>
  <div class="home-block-tools glass-pill">
    <span class="home-block-grip" aria-hidden="true">⠿</span>
    <span class="home-block-name">{{ label }}<em v-if="hidden"> · hidden</em></span>
    <button
      v-if="sizable"
      type="button"
      class="home-block-size"
      :title="`Width: ${SIZE_LABELS[size]} — click for ${SIZE_NEXT[size]}`"
      :aria-label="`Width ${SIZE_LABELS[size]}, make it ${SIZE_NEXT[size]}`"
      @click="$emit('resize')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 12h16M7 8l-3 4 3 4M17 8l3 4-3 4" /></svg>{{ SIZE_LABELS[size] }}
    </button>
    <button type="button" :disabled="first" :aria-label="`Move ${label} up`" @click="$emit('move', -1)">↑</button>
    <button type="button" :disabled="last" :aria-label="`Move ${label} down`" @click="$emit('move', 1)">↓</button>
    <button type="button" :aria-pressed="hidden" :aria-label="hidden ? `Show ${label}` : `Hide ${label}`" @click="$emit('toggle')">
      {{ hidden ? 'Show' : 'Hide' }}
    </button>
  </div>
</template>

<style scoped>
.home-block-tools {
  position: absolute;
  top: 0.55rem;
  right: 0.55rem;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.3rem 0.2rem 0.7rem;
  background: var(--pill-active);
  font-size: var(--btn-font);
  cursor: grab;
}
.home-block-grip {
  color: var(--text-dim);
}
.home-block-name {
  font-weight: 600;
  margin-right: 0.3rem;
}
.home-block-name em {
  font-style: normal;
  font-weight: 500;
  color: var(--text-dim);
}
.home-block-tools button {
  min-width: 2rem;
  height: 2rem;
  padding: 0 0.6rem;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-main);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.home-block-size {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}
.home-block-size svg {
  width: 14px;
  height: 14px;
}
.home-block-tools button:hover:not(:disabled) {
  background: var(--bg-surface-elevated);
}
.home-block-tools button:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
