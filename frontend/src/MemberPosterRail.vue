<script setup>
import { ref } from 'vue'

defineProps({ title: String, hasItems: Boolean })
const rail = ref(null)
function scroll(direction) {
  const node = rail.value
  if (node) node.scrollBy({ left: direction * Math.max(node.clientWidth * .72, 232), behavior: 'smooth' })
}
</script>

<template>
  <section class="glass-card home-card" :aria-label="title">
    <div class="home-rail-head">
      <h3>{{ title }}</h3>
      <div class="home-rail-tools">
        <slot name="tools" />
        <div v-if="hasItems" class="home-rail-nav">
          <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Previous')" @click="scroll(-1)">‹</button>
          <button type="button" class="ui-btn ui-btn-ghost cal-nav-btn" :aria-label="$t('Next')" @click="scroll(1)">›</button>
        </div>
      </div>
    </div>
    <div v-if="hasItems" ref="rail" class="home-rail"><slot /></div>
    <slot name="status" />
  </section>
</template>
