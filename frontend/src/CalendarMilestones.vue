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
      :class="milestone"
      fill="currentColor"
      role="img"
      :aria-label="$t(labels[milestone])"
    >
      <title>{{ $t(labels[milestone]) }}</title>
      <circle cx="12" cy="12" r="11" />
      <path v-if="milestone.endsWith('-premiere')" d="M9 7v10l8-5Z" />
      <rect v-else-if="milestone === 'series-finale'" x="8" y="8" width="8" height="8" rx="1" />
      <path v-else d="M8 8h3v8H8z M13 8h3v8h-3z" />
    </svg>
  </span>
</template>

<style scoped>
.cal-milestones {
  display: inline-flex;
  flex: none;
  flex-wrap: wrap;
  justify-content: flex-end;
  max-width: 100%;
  margin-inline-start: auto;
  gap: 0.15rem;
}
.cal-milestones svg {
  width: 0.875rem;
  height: 0.875rem;
  color: #62a5f5;
}
.cal-milestones .season-finale {
  color: #ffbc20;
}
.cal-milestones .series-finale {
  color: #ff5b60;
}
.cal-milestones path,
.cal-milestones rect {
  fill: #171b25;
}
</style>
