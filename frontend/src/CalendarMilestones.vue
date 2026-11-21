<script setup>
defineProps({ milestones: Array })

const labels = {
  'series-premiere': 'Series premiere',
  'season-premiere': 'Season premiere',
  'series-finale': 'Series finale',
  'season-finale': 'Season finale',
}
</script>

<template>
  <span v-if="milestones?.length" class="cal-milestones">
    <svg
      v-for="milestone in milestones"
      :key="milestone"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      role="img"
      :aria-label="$t(labels[milestone])"
    >
      <title>{{ $t(labels[milestone]) }}</title>
      <path v-if="milestone.endsWith('-premiere')" d="M7 4l14 8-14 8Z" />
      <path v-else d="M5 21V3m0 1c5-4 9 4 15 0v10c-6 4-10-4-15 0" />
    </svg>
  </span>
</template>

<style scoped>
.cal-milestones {
  display: inline-flex;
  flex: none;
  gap: 0.15rem;
  color: var(--text-main);
}
.cal-milestones svg {
  width: 0.875rem;
  height: 0.875rem;
}
</style>
