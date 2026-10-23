<script setup>
/**
 * The wallpaper behind the glass: a base colour plus three layers of soft colour fields that
 * move at different speeds with the pointer and the scroll position (parallax). The preset
 * and the personal image come from background.js, the depth from glass.js.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { blobsCss, paletteFor, wallpaperState } from './background.js'
import { glass } from './glass.js'

const theme = ref(typeof document !== 'undefined' ? document.documentElement.getAttribute('data-theme') || 'dark' : 'dark')
const mx = ref(0)
const my = ref(0)
const sy = ref(0)
let observer = null
let frame = 0
let reduceMotion = false

const palette = computed(() => paletteFor(wallpaperState.value.preset, theme.value, wallpaperState.value.image))

function shift(fx, fy, fs) {
  const d = glass.value.depth
  const x = reduceMotion ? 0 : -mx.value * fx * d
  const y = (reduceMotion ? 0 : -my.value * fy * d) - sy.value * fs * d
  return `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`
}

const layers = computed(() => {
  const p = palette.value
  const out = []
  if (p.image) {
    out.push({ id: 'image', style: { backgroundImage: `url("${p.image}")`, backgroundSize: 'cover', backgroundPosition: 'center', filter: p.blur && glass.value.wallpaperBlur ? `blur(${glass.value.wallpaperBlur}px)` : 'none', transform: shift(8, 6, 0.05) } })
    out.push({ id: 'tint', style: { background: p.tint, transform: 'none' } })
    return out
  }
  out.push({ id: 'far', style: { background: blobsCss(p.far), transform: shift(10, 8, 0.06) } })
  out.push({ id: 'mid', style: { background: blobsCss(p.mid), transform: shift(22, 16, 0.14) } })
  out.push({ id: 'near', style: { background: blobsCss(p.near), transform: shift(36, 26, 0.24) } })
  return out
})

function onMove(event) {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    mx.value = (event.clientX / window.innerWidth - 0.5) * 2
    my.value = (event.clientY / window.innerHeight - 0.5) * 2
  })
}
function onScroll() {
  sy.value = window.scrollY || 0
}

onMounted(() => {
  reduceMotion = !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  observer = new MutationObserver(() => {
    theme.value = document.documentElement.getAttribute('data-theme') || 'dark'
  })
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  window.addEventListener('mousemove', onMove, { passive: true })
  window.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => {
  observer?.disconnect()
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('scroll', onScroll)
  if (frame) cancelAnimationFrame(frame)
})
</script>

<template>
  <div class="wallpaper" aria-hidden="true" :style="{ background: palette.base }">
    <div v-for="layer in layers" :key="layer.id" class="wallpaper-layer" :style="layer.style"></div>
  </div>
</template>

<style scoped>
.wallpaper {
  position: fixed;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}
.wallpaper-layer {
  position: absolute;
  inset: -14%;
  background-repeat: no-repeat;
  background-size: 100% 100%;
  will-change: transform;
  transition: transform 160ms ease-out;
}
</style>
