<script setup>
import { ref, watch } from 'vue'
import HomePoster from './HomePoster.vue'

const props = defineProps({
  title: String,
  poster: String,
  mediaType: String,
  meta: String,
  tone: String,
  actionLabel: String,
  href: String,
})
const emit = defineEmits(['open'])
const missing = ref(false)
watch(() => props.poster, () => { missing.value = false })
</script>

<template>
  <component :is="href ? 'a' : actionLabel ? 'button' : 'div'" class="home-tile"
             :type="!href && actionLabel ? 'button' : undefined"
             :href="href" :target="href ? '_blank' : undefined" :rel="href ? 'noopener noreferrer' : undefined" :aria-label="actionLabel || undefined"
             @click="actionLabel && emit('open')">
    <span class="home-tile-art">
      <HomePoster v-if="poster && !missing" :key="poster" :src="poster" class="home-tile-poster" @error="missing = true" />
      <span v-else class="home-tile-fallback" aria-hidden="true">{{ title?.charAt(0) || '#' }}</span>
      <span v-if="mediaType" class="media-badge">{{ $t(mediaType === 'tv' ? 'Series' : 'Movie') }}</span>
    </span>
    <span class="home-tile-title">{{ title }}</span>
    <span v-if="meta" class="home-tile-meta home-req-status" :class="tone" :title="meta">{{ meta }}</span>
  </component>
</template>

<style scoped>
a.home-tile { color: inherit; text-decoration: none; }
button.home-tile { border: 0; background: none; padding: 0; font: inherit; text-align: start; cursor: pointer; }
</style>
