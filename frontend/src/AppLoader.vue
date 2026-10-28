<script setup>
/** Full-page loading state: the header icon on a glass orb inside a spinning accent ring. */
import { brandHeaderUrl } from './branding.js'

defineProps({
  /** Read out by screen readers; nothing is shown as text. */
  label: { type: String, default: 'Loading' },
})
</script>

<template>
  <div class="app-loader" role="status" :aria-label="label">
    <span class="app-loader-ring" aria-hidden="true"></span>
    <span class="app-loader-orb" aria-hidden="true">
      <img :src="brandHeaderUrl" alt="" />
    </span>
  </div>
</template>

<style scoped>
.app-loader {
  position: relative;
  width: 6.5rem;
  height: 6.5rem;
}
.app-loader-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, transparent 0 40%, rgba(var(--color-primary-rgb), 0.15) 55%, var(--color-primary) 100%);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 4px), #000 calc(100% - 3.5px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 4px), #000 calc(100% - 3.5px));
  filter: drop-shadow(0 0 6px rgba(var(--color-primary-rgb), 0.55));
  animation: app-loader-spin 1.1s linear infinite;
}
.app-loader-orb {
  position: absolute;
  inset: 0.6rem;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--pill-bg);
  border: 1px solid var(--border-subtle);
  box-shadow: inset 0 1px 0 var(--glass-highlight), var(--glass-shadow);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  animation: app-loader-breathe 2.2s ease-in-out infinite;
}
.app-loader-orb img {
  width: 58%;
  height: 58%;
  object-fit: contain;
}
@keyframes app-loader-spin {
  to {
    transform: rotate(1turn);
  }
}
@keyframes app-loader-breathe {
  50% {
    transform: scale(0.94);
  }
}
@media (prefers-reduced-motion: reduce) {
  .app-loader-ring {
    animation: app-loader-fade 1.6s ease-in-out infinite alternate;
  }
  .app-loader-orb {
    animation: none;
  }
  @keyframes app-loader-fade {
    from {
      opacity: 0.35;
    }
  }
}
</style>
