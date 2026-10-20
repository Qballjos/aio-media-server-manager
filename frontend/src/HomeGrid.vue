<script setup>
/**
 * Home's widget grid. Each named slot is a widget, placed on square cells. In edit mode a widget follows the pointer
 * (mouse anywhere, touch on its grip), a marker shows where it lands and the widgets it touches move aside; the corner
 * resizes it and the keyboard does both. The parent saves what `change` hands it.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { BREAKPOINTS, WIDGETS, resolve } from './homeGrid.js'

const props = defineProps({
  layout: { type: Array, required: true },
  bp: { type: String, required: true },
  editing: { type: Boolean, default: false },
  /** A widget to light up for a moment, e.g. one just added. */
  highlight: { type: String, default: '' },
  /** A widget whose content may spill over the others (open search results). */
  raise: { type: String, default: '' },
  /** Pixels at the bottom of the window covered by the dock and edit bar; dragging there scrolls the page. */
  bottomInset: { type: Number, default: 160 },
})
const emit = defineEmits(['change', 'remove', 'open'])

const patternId = `hg-cells-${Math.random().toString(36).slice(2, 9)}`
const root = ref(null)
const width = ref(0)
const noAnim = ref(true)
const live = ref(null)
const active = ref(null)
const float = ref(null)
const marker = ref(null)
const said = ref('')

const cols = computed(() => BREAKPOINTS[props.bp]?.cols || 12)
const gap = computed(() => BREAKPOINTS[props.bp]?.gap || 16)
const cell = computed(() => (width.value > 0 ? (width.value - (cols.value - 1) * gap.value) / cols.value : 0))
const pitch = computed(() => cell.value + gap.value)
// Cells are square until a row would pass MAX_ROW; on wide screens they get wider instead of taller.
const MAX_ROW = 104
const rowCell = computed(() => Math.min(cell.value, MAX_ROW))
const rowPitch = computed(() => rowCell.value + gap.value)
const shown = computed(() => live.value || props.layout)
const rowCount = computed(() => shown.value.reduce((most, item) => Math.max(most, item.y + item.h), 0) + (props.editing ? 3 : 0))
const height = computed(() => (rowCount.value ? rowCount.value * rowPitch.value - gap.value : 0))

const span = (n) => n * cell.value + (n - 1) * gap.value
const spanRows = (n) => n * rowCell.value + (n - 1) * gap.value
const clamp = (value, low, high) => Math.max(low, Math.min(high, value))
const label = (id) => WIDGETS[id]?.label || id

function box(item) {
  return { x: item.x * pitch.value, y: item.y * rowPitch.value, w: span(item.w), h: spanRows(item.h) }
}

function itemStyle(item) {
  const own = float.value && active.value?.id === item.id
  const b = own ? float.value : box(item)
  const lift = own && active.value.kind === 'drag' ? ' scale(1.03)' : ''
  return { width: `${b.w}px`, height: `${b.h}px`, transform: `translate3d(${b.x}px, ${b.y}px, 0)${lift}` }
}

const markerStyle = computed(() => {
  if (!marker.value) return {}
  const b = box(marker.value)
  return { width: `${b.w}px`, height: `${b.h}px`, transform: `translate3d(${b.x}px, ${b.y}px, 0)` }
})

function itemLabel(item) {
  return `${label(item.id)}, ${item.w} by ${item.h}, column ${item.x + 1}, row ${item.y + 1}`
}

/** Jumps from a new screen size or window width are not moves; only animate what the user does. */
function settle() {
  noAnim.value = true
  nextTick(() => requestAnimationFrame(() => requestAnimationFrame(() => {
    noAnim.value = false
  })))
}

let observer = null
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    const next = Math.round(entry.contentRect.width)
    if (next !== width.value) {
      width.value = next
      settle()
    }
  })
  observer.observe(root.value)
  width.value = Math.round(root.value.getBoundingClientRect().width)
  settle()
})
onUnmounted(() => {
  observer?.disconnect()
  finish()
})
watch(() => props.bp, settle)
watch(() => props.editing, (on) => {
  if (!on && act) end(false)
})

// ---- pointer: drag, resize, tap ----
let act = null
let base = null

function onDown(event, id) {
  if (!props.editing || act || event.button > 0) return
  if (event.target.closest('.hg-x')) return
  const kind = event.target.closest('[data-rz]') ? 'resize' : event.target.closest('[data-grip]') ? 'drag' : 'pending'
  const mouse = event.pointerType === 'mouse'
  act = { id, el: event.currentTarget, pid: event.pointerId, sx: event.clientX, sy: event.clientY, lx: event.clientX, ly: event.clientY, mouse, kind }
  // Touch on the widget itself stays a scroll; only the grip and the corner take the finger.
  if (kind !== 'pending' || mouse) event.preventDefault()
  if (kind === 'drag') beginDrag()
  else if (kind === 'resize') beginResize()
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onCancel)
}

function capture() {
  try {
    act.el.setPointerCapture(act.pid)
  } catch (_) {
    /* the window listeners still follow the pointer */
  }
}

function start(kind) {
  base = props.layout.map((item) => ({ ...item }))
  act.kind = kind
  act.orig = base.find((item) => item.id === act.id)
  act.target = { ...act.orig }
  act.scroll0 = window.scrollY
  live.value = base
  active.value = { id: act.id, kind }
  marker.value = act.target
  capture()
  autoScroll()
}

function beginDrag() {
  const rect = act.el.getBoundingClientRect()
  act.offX = act.lx - rect.left
  act.offY = act.ly - rect.top
  start('drag')
  float.value = box(act.orig)
  updateDrag()
}

function updateDrag() {
  const rootRect = root.value.getBoundingClientRect()
  const x = act.lx - rootRect.left - act.offX
  const y = act.ly - rootRect.top - act.offY
  float.value = { ...float.value, x, y }
  const tx = clamp(Math.round(x / pitch.value), 0, cols.value - act.orig.w)
  const ty = Math.max(0, Math.round(y / rowPitch.value))
  if (tx === act.target.x && ty === act.target.y) return
  act.target = { ...act.orig, x: tx, y: ty }
  live.value = resolve(base, act.id, act.target, cols.value, act.orig)
  marker.value = act.target
}

function beginResize() {
  act.w0 = act.el.offsetWidth
  act.h0 = act.el.offsetHeight
  start('resize')
  float.value = box(act.orig)
}

function limits(id, x) {
  const spec = WIDGETS[id]
  const room = cols.value - x
  return {
    minW: Math.min(spec?.min[0] || 1, room),
    maxW: Math.min(spec?.max[0] || cols.value, room),
    minH: spec?.min[1] || 1,
    maxH: spec?.max[1] || 12,
  }
}

function updateResize() {
  const { minW, maxW, minH, maxH } = limits(act.id, act.orig.x)
  const dx = act.lx - act.sx
  const dy = act.ly - act.sy + (window.scrollY - act.scroll0)
  const w = clamp(act.w0 + dx, span(minW), span(maxW))
  const h = clamp(act.h0 + dy, spanRows(minH), spanRows(maxH))
  float.value = { ...float.value, w, h }
  const cw = clamp(Math.round((w + gap.value) / pitch.value), minW, maxW)
  const ch = clamp(Math.round((h + gap.value) / rowPitch.value), minH, maxH)
  if (cw === act.target.w && ch === act.target.h) return
  act.target = { ...act.orig, w: cw, h: ch }
  live.value = resolve(base, act.id, act.target, cols.value, null)
  marker.value = act.target
}

function onMove(event) {
  if (!act || event.pointerId !== act.pid) return
  act.lx = event.clientX
  act.ly = event.clientY
  if (act.kind === 'pending') {
    if (Math.hypot(event.clientX - act.sx, event.clientY - act.sy) > 6) {
      if (act.mouse) beginDrag()
      else finish()
    }
    return
  }
  if (act.kind === 'drag') updateDrag()
  else updateResize()
}

function onUp(event) {
  if (!act || event.pointerId !== act.pid) return
  if (act.kind === 'pending') {
    const id = act.id
    finish()
    emit('open', id)
    return
  }
  end(true)
}

function onCancel(event) {
  if (!act || event.pointerId !== act.pid) return
  if (act.kind === 'pending') finish()
  else end(false)
}

function end(commit) {
  const { id, kind } = act
  const result = live.value
  finish()
  if (!commit || !result) return
  const moved = result.some((entry) => {
    const was = props.layout.find((other) => other.id === entry.id)
    return !was || was.x !== entry.x || was.y !== entry.y || was.w !== entry.w || was.h !== entry.h
  })
  if (!moved) return
  emit('change', result)
  const item = result.find((entry) => entry.id === id)
  said.value = kind === 'drag' ? `${label(id)} moved to column ${item.x + 1}, row ${item.y + 1}` : `${label(id)} is now ${item.w} by ${item.h}`
}

function finish() {
  act = null
  base = null
  live.value = null
  active.value = null
  float.value = null
  marker.value = null
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('pointercancel', onCancel)
}

/** Hold a widget still near the top of the window or just above the dock and the page scrolls along. */
function autoScroll() {
  let since = 0
  const tick = (time) => {
    if (!act || act.kind === 'pending') return
    const zone = 72
    const bottom = window.innerHeight - props.bottomInset
    const dir = act.ly < zone ? -1 : act.ly > bottom - zone ? 1 : 0
    if (!dir) since = 0
    else if (!since) since = time
    else if (time - since > 260) {
      const before = window.scrollY
      window.scrollBy(0, dir * 12)
      if (window.scrollY !== before) {
        if (act.kind === 'drag') updateDrag()
        else updateResize()
      }
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

function onEscape(event) {
  if (event.key === 'Escape' && act && act.kind !== 'pending') {
    event.preventDefault()
    event.stopPropagation()
    end(false)
  }
}
onMounted(() => window.addEventListener('keydown', onEscape, true))
onUnmounted(() => window.removeEventListener('keydown', onEscape, true))

// ---- keyboard: arrows move, Shift + arrows resize, Delete removes, Enter opens ----
const STEPS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }

function onKey(event, id) {
  if (!props.editing || act || event.target !== event.currentTarget) return
  const item = props.layout.find((entry) => entry.id === id)
  if (!item) return
  const step = STEPS[event.key]
  if (step) {
    event.preventDefault()
    const next = { ...item }
    if (event.shiftKey) {
      const { minW, maxW, minH, maxH } = limits(id, item.x)
      next.w = clamp(item.w + step[0], minW, maxW)
      next.h = clamp(item.h + step[1], minH, maxH)
    } else {
      next.x = clamp(item.x + step[0], 0, cols.value - item.w)
      next.y = Math.max(0, item.y + step[1])
    }
    if (next.x === item.x && next.y === item.y && next.w === item.w && next.h === item.h) return
    emit('change', resolve(props.layout, id, next, cols.value, event.shiftKey ? null : item))
    said.value = event.shiftKey ? `${label(id)} is now ${next.w} by ${next.h}` : `${label(id)} moved to column ${next.x + 1}, row ${next.y + 1}`
  } else if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    emit('remove', id)
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    emit('open', id)
  }
}
</script>

<template>
  <div
    ref="root"
    class="hg"
    :class="{ 'is-editing': editing, 'no-anim': noAnim, 'is-busy': !!active }"
    :style="{ height: `${height}px` }"
  >
    <svg v-if="editing && cell > 0" class="hg-cells" :width="width" :height="height" aria-hidden="true">
      <defs>
        <pattern :id="patternId" patternUnits="userSpaceOnUse" :width="pitch" :height="rowPitch">
          <rect class="hg-cell" x="0.75" y="0.75" :width="cell - 1.5" :height="rowCell - 1.5" rx="18" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" :fill="`url(#${patternId})`" />
    </svg>
    <div class="hg-marker" :class="{ 'is-on': marker, 'is-sizing': active?.kind === 'resize' }" :style="markerStyle" aria-hidden="true">
      <span v-if="marker">{{ marker.w }} × {{ marker.h }}</span>
    </div>
    <div
      v-for="item in shown"
      :key="item.id"
      class="hg-item"
      :class="{
        'is-lifted': active?.id === item.id && active.kind === 'drag',
        'is-resizing': active?.id === item.id && active.kind === 'resize',
        'is-new': highlight === item.id,
        'is-raised': raise === item.id,
      }"
      :style="itemStyle(item)"
      :data-widget="item.id"
      :tabindex="editing ? 0 : undefined"
      :aria-label="editing ? itemLabel(item) : undefined"
      @pointerdown="onDown($event, item.id)"
      @keydown="onKey($event, item.id)"
    >
      <div class="hg-body"><slot :name="item.id" /></div>
      <template v-if="editing">
        <button type="button" class="hg-x" tabindex="-1" :aria-label="`Remove ${label(item.id)}`" :title="`Remove ${label(item.id)}`" @click.stop="emit('remove', item.id)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
        <span class="hg-grip" data-grip :title="`Move ${label(item.id)}`" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="6" r="1.7" /><circle cx="15" cy="6" r="1.7" /><circle cx="9" cy="12" r="1.7" /><circle cx="15" cy="12" r="1.7" /><circle cx="9" cy="18" r="1.7" /><circle cx="15" cy="18" r="1.7" /></svg>
        </span>
        <span class="hg-rz" data-rz :title="`Resize ${label(item.id)}`" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M8 19L19 8M14 19l5-5" /></svg>
        </span>
      </template>
    </div>
    <p class="hg-sr" aria-live="polite">{{ said }}</p>
  </div>
</template>

<style scoped>
.hg {
  position: relative;
  width: 100%;
  min-width: 0;
}
.hg.is-editing {
  user-select: none;
  -webkit-user-select: none;
}
.hg-cells {
  position: absolute;
  inset: 0 auto auto 0;
  pointer-events: none;
}
.hg-cell {
  fill: none;
  stroke: var(--border-strong);
  stroke-width: 1.2;
  stroke-dasharray: 4 6;
}
.hg-item {
  position: absolute;
  top: 0;
  left: 0;
  transition: transform 0.34s cubic-bezier(0.2, 0.85, 0.25, 1.08), width 0.26s ease, height 0.26s ease;
  will-change: transform;
}
.hg.no-anim .hg-item,
.hg-item.is-lifted,
.hg-item.is-resizing {
  transition: none;
}
.hg-item.is-raised {
  z-index: 20;
}
.hg-body {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.hg-body > :deep(*) {
  flex: 1 1 auto;
  min-height: 0;
}
.hg.is-editing .hg-item {
  cursor: grab;
}
.hg.is-editing .hg-item:focus-visible {
  outline: 2px solid var(--border-active);
  outline-offset: 4px;
  border-radius: var(--radius-glass);
}
/* In edit mode a widget is something to arrange, not to use. */
.hg.is-editing .hg-body {
  pointer-events: none;
}
.hg.is-editing .hg-body::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: var(--radius-glass);
  background: rgb(0 0 0 / 0.1);
  pointer-events: none;
}
.hg-item.is-lifted {
  z-index: 30;
  cursor: grabbing;
}
.hg-item.is-lifted .hg-body,
.hg-item.is-resizing .hg-body {
  border-radius: var(--radius-glass);
  box-shadow: 0 0 0 1px rgba(var(--color-primary-rgb), 0.55), 0 40px 80px -24px rgb(0 0 0 / 0.6);
}
.hg-item.is-lifted .hg-body::after,
.hg-item.is-resizing .hg-body::after {
  background: transparent;
}
.hg-item.is-resizing {
  z-index: 30;
}
.hg-item.is-new .hg-body {
  border-radius: var(--radius-glass);
  animation: hg-new 1.8s ease-out;
}
@keyframes hg-new {
  0%,
  60% {
    box-shadow: 0 0 0 2px var(--color-primary);
  }
  100% {
    box-shadow: 0 0 0 2px transparent;
  }
}
.hg-marker {
  position: absolute;
  top: 0;
  left: 0;
  display: grid;
  place-items: center;
  border-radius: var(--radius-glass);
  background: rgba(var(--color-primary-rgb), 0.08);
  border: 1.5px solid rgba(var(--color-primary-rgb), 0.55);
  opacity: 0;
  pointer-events: none;
  transition: transform 0.18s ease, width 0.18s ease, height 0.18s ease, opacity 0.15s;
}
.hg-marker.is-on {
  opacity: 1;
}
.hg-marker span {
  opacity: 0;
  padding: 0.3rem 0.7rem;
  border-radius: 999px;
  background: var(--control-bg);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
}
.hg-marker.is-sizing span {
  opacity: 1;
}
.hg-x,
.hg-grip,
.hg-rz {
  position: absolute;
  z-index: 3;
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--text-main);
  background: var(--control-bg);
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  box-shadow: var(--glass-shadow);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.hg-x {
  top: -10px;
  left: -10px;
  width: 28px;
  height: 28px;
  cursor: pointer;
}
.hg-x:hover {
  color: var(--color-danger-fg);
  border-color: var(--color-danger);
}
.hg-x svg {
  width: 13px;
  height: 13px;
}
.hg-grip {
  top: 50%;
  left: 50%;
  width: 46px;
  height: 46px;
  margin: -23px 0 0 -23px;
  cursor: grab;
  touch-action: none;
}
.hg-grip svg {
  width: 20px;
  height: 20px;
}
.hg-rz {
  right: -8px;
  bottom: -8px;
  width: 26px;
  height: 26px;
  cursor: nwse-resize;
  touch-action: none;
}
.hg-rz::before {
  content: '';
  position: absolute;
  inset: -12px;
}
.hg-rz svg {
  width: 12px;
  height: 12px;
}
.hg-item.is-lifted :is(.hg-x, .hg-rz),
.hg-item.is-resizing :is(.hg-x, .hg-grip) {
  opacity: 0;
}
.hg.is-busy .hg-item:not(.is-lifted):not(.is-resizing) :is(.hg-x, .hg-grip, .hg-rz) {
  opacity: 0.35;
}
.hg-sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  .hg-item,
  .hg-marker {
    transition: none;
  }
  .hg-item.is-new .hg-body {
    animation: none;
  }
}
</style>
