<script setup>
defineProps({ streaming: Object, series: Boolean })
defineEmits(['setup'])
</script>

<template>
  <section v-if="streaming?.providers?.length" class="title-streaming" :aria-label="$t('Streaming availability')">
    <strong>{{ $t(series ? 'Streaming on' : 'Included with your subscriptions') }}</strong>
    <ul>
      <li v-for="provider in streaming.providers" :key="provider.id" :title="provider.name">
        <img v-if="provider.logo_url" class="provider-logo" :src="provider.logo_url" :alt="provider.name"
             width="44" height="44" referrerpolicy="no-referrer" @error="$event.target.hidden = true">
        <span class="provider-fallback">{{ provider.name }}</span>
      </li>
    </ul>
    <p v-if="series" class="home-muted">{{ $t('Season availability may vary.') }}</p>
    <div class="title-streaming-links">
      <a v-if="streaming.link" :href="streaming.link" target="_blank" rel="noopener noreferrer">
        {{ $t('Where to watch') }}
      </a>
      <small class="home-muted">{{ $t('Availability by JustWatch') }}</small>
    </div>
  </section>
  <RouterLink v-else-if="streaming?.configured === false" class="title-streaming-setup"
              :to="{ name: 'settings', params: { section: 'account' }, query: { streaming: '1' } }"
              @click="$emit('setup')">
    {{ $t('Set up streaming subscriptions') }}
  </RouterLink>
</template>

<style scoped>
.title-streaming { display: grid; gap: .45rem; padding-block-start: .75rem; border-block-start: 1px solid var(--border-subtle); }
.title-streaming ul, .title-streaming-links { display: flex; align-items: center; flex-wrap: wrap; gap: .45rem .8rem; }
.title-streaming ul, .title-streaming p { margin: 0; padding: 0; }
.title-streaming li { display: flex; align-items: center; min-inline-size: 0; overflow-wrap: anywhere; }
.provider-logo { inline-size: 2.75rem; block-size: 2.75rem; border-radius: var(--radius-inset); object-fit: contain; }
.provider-logo:not([hidden]) + .provider-fallback { display: none; }
.provider-fallback { padding: .35rem .6rem; border-radius: var(--radius-control); background: var(--bg-surface); }
.title-streaming a, .title-streaming-setup { color: var(--color-primary-text); text-decoration: underline; text-underline-offset: .15em; }
.title-streaming-setup { display: inline-block; justify-self: start; padding-block: .4rem; }
</style>
