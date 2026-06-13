<script setup lang="ts">
/** Shared 4:5 hero image + optional artist credit for the public
 *  mini-apps. Renders nothing when there's no image. ``creditLabel``
 *  is passed in (the mini-apps have no vue-i18n) — e.g. "Ontwerp:". */
defineProps<{
  imageUrl: string | null;
  artist: string | null;
  creditLabel: string;
}>();
</script>

<template>
  <figure v-if="imageUrl" class="hero">
    <img :src="imageUrl" alt="" class="hero-img" />
    <figcaption v-if="artist" class="credit">
      {{ creditLabel }}
      <a :href="`https://instagram.com/${artist}`" target="_blank" rel="noopener">@{{ artist }}</a>
    </figcaption>
  </figure>
</template>

<style scoped>
.hero { margin: 0; }
.hero-img {
  display: block;
  width: 100%;
  max-height: 400px;
  aspect-ratio: 4 / 5;
  object-fit: cover;
  border-radius: 12px;
  border: 1px solid var(--brand-border);
}
.credit { margin-top: 0.375rem; font-size: 0.8125rem; color: var(--brand-text-muted); }
.credit a { color: inherit; }
</style>
