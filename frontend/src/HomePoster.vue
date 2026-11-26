<script setup>
import { ref } from 'vue'
import { useVisiblePoster } from './composables/useVisiblePoster.js'

defineProps({ src: { type: String, required: true } })
const emit = defineEmits(['error'])
const image = ref(null)
const visible = useVisiblePoster(image)

function onError(event) {
  if (visible.value && image.value?.getAttribute('src')) emit('error', event)
}
</script>

<template>
  <img ref="image" :src.attr="visible ? src : null" decoding="async" @error="onError" alt="" />
</template>
