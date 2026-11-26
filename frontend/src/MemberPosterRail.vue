<script setup>
import { ref, watch } from 'vue'

defineProps({ title: String, hasItems: Boolean, autoLoad: Boolean })
const emit = defineEmits(['load-more'])
const end = ref(null)

watch(end, (marker, _, onCleanup) => {
  if (!marker || typeof IntersectionObserver === 'undefined') return
  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting && end.value === marker) emit('load-more')
  })
  observer.observe(marker)
  onCleanup(() => observer.disconnect())
}, { flush: 'post' })

</script>

<template>
  <section class="glass-card home-card" :aria-label="title">
    <div class="home-rail-head">
      <h3>{{ title }}</h3>
    </div>
    <div v-if="hasItems || autoLoad" class="home-rail" role="group" :aria-label="title" :tabindex="hasItems ? 0 : undefined">
      <slot />
      <span v-if="autoLoad" ref="end" class="rail-end" aria-hidden="true"></span>
    </div>
    <slot name="status" />
  </section>
</template>

<style scoped>
.rail-end {
  flex: 0 0 1px;
  height: 1px;
}
</style>
