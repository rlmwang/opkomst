<script setup lang="ts">
/** A single centered card for the standalone screens every public
 *  mini-app shows: loading, "no longer available", load-failed, and
 *  the post-submit thank-you. One component so these screens look and
 *  read the same across all three. */
defineProps<{ title?: string; message: string }>();
</script>

<template>
  <div class="card notice">
    <h2 v-if="title">{{ title }}</h2>
    <p class="muted">{{ message }}</p>
  </div>
</template>

<style scoped>
.notice { text-align: center; }
.notice h2 { margin: 0 0 0.5rem; }
.muted { color: var(--brand-text-muted); margin: 0; }
</style>
