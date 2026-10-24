<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: '' },
  options: { type: Array, default: () => [] },
  ariaLabel: { type: String, default: '' },
  id: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  /** field fills the form row. inline hugs its label. search sits in the Home search pill. */
  variant: { type: String, default: 'field' },
})

const emit = defineEmits(['update:modelValue', 'change'])

const open = ref(false)
const root = ref(null)
const button = ref(null)
const menu = ref(null)
const activeIndex = ref(-1)
const menuStyle = ref({})
const listId = `ui-select-${Math.random().toString(36).slice(2, 9)}`

const current = computed(
  () => props.options.find((opt) => opt.value === props.modelValue) || null,
)
const currentLabel = computed(() => current.value?.label || '')

function optionId(index) {
  return `${listId}-opt-${index}`
}

function place() {
  const el = button.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const gap = 6
  const width = Math.min(Math.max(rect.width, 168), window.innerWidth - 16)
  let left = rect.left
  if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - 8 - width)
  const below = window.innerHeight - rect.bottom
  const above = rect.top
  const openUp = below < 140 && above > below
  menuStyle.value = {
    left: `${left}px`,
    width: `${width}px`,
    top: openUp ? 'auto' : `${rect.bottom + gap}px`,
    bottom: openUp ? `${window.innerHeight - rect.top + gap}px` : 'auto',
  }
}

function onPlace() {
  if (open.value) place()
}

async function setOpen(next) {
  if (props.disabled) return
  open.value = next
  if (!next) return
  const idx = props.options.findIndex((opt) => opt.value === props.modelValue)
  activeIndex.value = idx >= 0 ? idx : 0
  await nextTick()
  place()
}

function toggle() {
  setOpen(!open.value)
}

function choose(opt) {
  if (!opt || opt.disabled) return
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
  open.value = false
  button.value?.focus()
}

function move(delta) {
  const count = props.options.length
  if (!count) return
  let index = activeIndex.value
  for (let step = 0; step < count; step += 1) {
    index = (index + delta + count) % count
    if (!props.options[index].disabled) {
      activeIndex.value = index
      menu.value?.querySelector(`#${optionId(index)}`)?.scrollIntoView({ block: 'nearest' })
      return
    }
  }
}

function onKey(event) {
  if (props.disabled) return
  if (event.key === 'Tab') {
    open.value = false
    return
  }
  if (!open.value) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setOpen(true)
    }
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    open.value = false
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    choose(props.options[activeIndex.value])
  } else if (event.key === 'Home') {
    event.preventDefault()
    activeIndex.value = 0
  } else if (event.key === 'End') {
    event.preventDefault()
    activeIndex.value = props.options.length - 1
  }
}

function onPointerDown(event) {
  if (root.value?.contains(event.target) || menu.value?.contains(event.target)) return
  open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown)
  window.addEventListener('resize', onPlace)
  window.addEventListener('scroll', onPlace, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  window.removeEventListener('resize', onPlace)
  window.removeEventListener('scroll', onPlace, true)
})

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) open.value = false
  },
)
</script>

<template>
  <div
    ref="root"
    class="ui-select"
    :class="[`is-${variant}`, { 'is-open': open, 'is-disabled': disabled }]"
  >
    <button
      :id="id || undefined"
      ref="button"
      type="button"
      class="ui-select-btn"
      :disabled="disabled"
      :aria-label="ariaLabel || undefined"
      aria-haspopup="listbox"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-controls="listId"
      :aria-activedescendant="open && activeIndex >= 0 ? optionId(activeIndex) : undefined"
      @click="toggle"
      @keydown="onKey"
    >
      <span class="ui-select-value">{{ currentLabel }}</span>
      <svg class="ui-select-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
    </button>
    <Teleport to="body">
      <div
        v-if="open"
        :id="listId"
        ref="menu"
        class="ui-select-menu"
        role="listbox"
        :aria-label="ariaLabel || undefined"
        :style="menuStyle"
      >
        <button
          v-for="(opt, index) in options"
          :id="optionId(index)"
          :key="`${index}-${opt.value}`"
          type="button"
          class="ui-select-option"
          role="option"
          :aria-selected="opt.value === modelValue ? 'true' : 'false'"
          :disabled="!!opt.disabled"
          :class="{ 'is-selected': opt.value === modelValue, 'is-active': index === activeIndex }"
          :title="opt.label"
          @mouseenter="activeIndex = index"
          @click="choose(opt)"
        >
          <span>{{ opt.label }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style>
.ui-select {
  position: relative;
  display: inline-flex;
  max-width: 100%;
  min-width: 0;
  vertical-align: middle;
}

.ui-select.is-field {
  display: flex;
  width: 100%;
}

.ui-select.is-search {
  display: flex;
  align-self: stretch;
  height: 100%;
}

.ui-select-btn {
  appearance: none;
  -webkit-appearance: none;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
  min-height: var(--btn-h);
  margin: 0;
  padding: 0.3rem 0.85rem 0.3rem 0.95rem;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-main);
  box-shadow: inset 0 1px 0 var(--glass-highlight);
  font-family: inherit;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.01em;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
}

.ui-select.is-inline {
  max-width: 100%;
}

.ui-select-btn:hover:not(:disabled),
.ui-select.is-open .ui-select-btn {
  background: var(--pill-active);
  border-color: var(--border-strong);
}

.ui-select.is-open .ui-select-btn {
  border-color: rgba(var(--color-primary-rgb), 0.55);
  box-shadow: inset 0 1px 0 var(--glass-highlight), 0 0 0 3px rgba(var(--color-primary-rgb), 0.2);
}

.ui-select-btn:focus {
  outline: none;
}

.ui-select-btn:focus-visible {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(var(--color-primary-rgb), 0.2);
}

.ui-select-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ui-select-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-select-chevron {
  flex: 0 0 auto;
  color: var(--text-muted);
  transition: transform 0.2s;
}

.ui-select.is-open .ui-select-chevron {
  transform: rotate(180deg);
}

.ui-select.is-search .ui-select-btn {
  height: 100%;
  min-height: 0;
  border: 0;
  border-radius: 999px 0 0 999px;
  background: transparent;
  box-shadow: none;
  font-size: var(--ui-select-font, 0.92rem);
  padding: 0 0.85rem 0 var(--ui-select-pad, 1.15rem);
}

.ui-select.is-search .ui-select-btn:hover:not(:disabled),
.ui-select.is-search.is-open .ui-select-btn,
.ui-select.is-search .ui-select-btn:focus-visible {
  background: var(--pill-active);
  border-color: transparent;
  box-shadow: none;
}

.ui-select-menu {
  position: fixed;
  z-index: 180;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin: 0;
  padding: 0.4rem;
  max-height: min(18rem, calc(100vh - 1rem));
  overflow: auto;
  overscroll-behavior: contain;
  border-radius: var(--radius-glass, 26px);
  background: var(--control-bg);
  border: 1px solid var(--border-subtle);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--pill-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--pill-saturate));
}

.ui-select-option {
  appearance: none;
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 2.15rem;
  margin: 0;
  padding: 0.35rem 0.9rem;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--text-main);
  font-family: inherit;
  font-size: 0.92rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.25;
  text-align: left;
  cursor: pointer;
}

.ui-select-option span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-select-option:hover:not(:disabled),
.ui-select-option.is-active:not(:disabled) {
  background: var(--pill-active);
  color: var(--text-heading);
}

.ui-select-option.is-selected {
  background: var(--pill-active);
  color: var(--text-heading);
  border-color: rgba(var(--color-primary-rgb), 0.55);
  box-shadow: inset 0 1px 0 var(--glass-highlight);
}

.ui-select-option:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ui-select-option:focus {
  outline: none;
}
</style>
