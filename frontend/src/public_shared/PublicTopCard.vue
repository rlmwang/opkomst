<script setup lang="ts">
import PublicHero from "./PublicHero.vue";

// The shared header that sits above the fold on every public entity page
// (and, via the same props, the admin details pages): the 4:5 hero with
// attribution, the title, the sanitized rich-text details, and slots for
// entity-specific meta rows and actions. One component so the same
// information places and styles identically everywhere; content
// differences live in the ``meta`` / ``actions`` slots.
//
// ``descriptionHtml`` is pre-sanitized server-side; rendering it with
// ``v-html`` is safe on that guarantee (see services/sanitize.py).
defineProps<{
  title: string | null;
  imageUrl?: string | null;
  artist?: string | null;
  creditLabel?: string;
  descriptionHtml?: string | null;
}>();
</script>

<template>
  <div class="card top-card">
    <PublicHero
      :image-url="imageUrl ?? null"
      :artist="artist ?? null"
      :credit-label="creditLabel ?? ''"
    />
    <div class="top-card-body">
      <h1 v-if="title" class="top-card-title">{{ title }}</h1>
      <slot name="title-extra" />
      <div v-if="descriptionHtml" class="richtext" v-html="descriptionHtml"></div>
      <dl v-if="$slots.meta" class="top-card-meta">
        <slot name="meta" />
      </dl>
    </div>
    <slot name="actions" />
  </div>
</template>

<style scoped>
.top-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
/* Frame the hero inside the card (cancel its own bottom margin). */
.top-card :deep(.hero) {
  margin-bottom: 0;
}
.top-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.top-card-title {
  margin: 0;
  font-size: 1.5rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.top-card-meta {
  display: grid;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
}
</style>
