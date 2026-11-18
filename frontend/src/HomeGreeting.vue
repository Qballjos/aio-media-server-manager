<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({ name: String, summary: String })
const { locale, t } = useI18n()
const todayLabel = computed(() => new Date().toLocaleDateString(locale.value, {
  weekday: 'long', day: 'numeric', month: 'long',
}))
const greeting = computed(() => {
  const hour = new Date().getHours()
  const phrase = t(hour < 6 ? 'Good night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening')
  return props.name ? `${phrase}, ${props.name}.` : `${phrase}.`
})
</script>

<template>
  <section class="home-hero" :aria-label="$t('Greeting')">
    <span class="home-hero-date">{{ todayLabel }}</span>
    <h2 class="home-hero-title">{{ greeting }}</h2>
    <p v-if="summary" class="home-hero-sub">{{ summary }}</p>
  </section>
</template>
