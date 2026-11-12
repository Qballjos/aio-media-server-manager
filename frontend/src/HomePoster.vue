<script setup>
import { ref } from 'vue'
import { useVisiblePoster } from './composables/useVisiblePoster.js'

defineProps({ src: { type: String, required: true } })
const image = ref(null)
const visible = useVisiblePoster(image)
</script>

<template>
  <img ref="image" :src="visible ? src : undefined" decoding="async" alt="" />
</template>
