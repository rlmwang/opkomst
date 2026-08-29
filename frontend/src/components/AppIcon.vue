<script setup lang="ts">
/**
 * The app's icons, drawn rather than typed. Replaces PrimeIcons, whose
 * 23 glyphs in use cost a 35 kB woff2 and an 85 kB ttf that both
 * shipped on every page.
 *
 * One 24-by-24 stroked path set, the same shape language ``DatePicker``
 * and ``RichTextField`` already draw their own arrows and toolbar in.
 * Every icon is decorative: the button or the label beside it carries
 * the meaning, so they are all ``aria-hidden``.
 *
 * The paths are ``./app-icons``, shared with the Svelte component that
 * draws the same set while the app crosses over.
 */
import { computed } from "vue";

import { PATHS, type IconName } from "./app-icons";

export type { IconName };

const props = withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 16 });

const paths = computed(() => PATHS[props.name] ?? []);
</script>

<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<style scoped>
.app-icon {
  flex: 0 0 auto;
  display: block;
}
</style>
