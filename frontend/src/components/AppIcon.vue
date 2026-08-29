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
 * Adding one is a line in ``PATHS``. Nothing else knows the drawing.
 */
import { computed } from "vue";

export type IconName =
  | "archive"
  | "arrow-down"
  | "arrow-up"
  | "bars"
  | "check"
  | "chevron-down"
  | "copy"
  | "download"
  | "exclamation-triangle"
  | "eye"
  | "face-smile"
  | "info-circle"
  | "link"
  | "pencil"
  | "plus"
  | "refresh"
  | "replay"
  | "search"
  | "send"
  | "sign-out"
  | "trash"
  | "upload"
  | "user-plus";

const PATHS: Record<IconName, string[]> = {
  archive: ["M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8", "M2 3h20v5H2z", "M10 12h4"],
  "arrow-down": ["M12 5v14", "M19 12l-7 7-7-7"],
  "arrow-up": ["M12 19V5", "M5 12l7-7 7 7"],
  bars: ["M3 6h18", "M3 12h18", "M3 18h18"],
  check: ["M20 6L9 17l-5-5"],
  "chevron-down": ["M6 9l6 6 6-6"],
  copy: [
    "M9 9h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V11a2 2 0 0 1 2-2z",
    "M5 15H4a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1",
  ],
  download: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"],
  "exclamation-triangle": [
    "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z",
    "M12 9v4",
    "M12 17h.01",
  ],
  eye: ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"],
  "face-smile": [
    "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z",
    "M8 14s1.5 2 4 2 4-2 4-2",
    "M9 9h.01",
    "M15 9h.01",
  ],
  "info-circle": ["M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z", "M12 16v-4", "M12 8h.01"],
  link: [
    "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71",
    "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  ],
  pencil: ["M12 20h9", "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"],
  plus: ["M12 5v14", "M5 12h14"],
  refresh: ["M21 2v6h-6", "M3 12a9 9 0 0 1 15-6.7L21 8", "M3 22v-6h6", "M21 12a9 9 0 0 1-15 6.7L3 16"],
  replay: ["M3 12a9 9 0 1 0 3-6.7L3 8", "M3 3v5h5"],
  search: ["M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16z", "M21 21l-4.35-4.35"],
  send: ["M22 2 11 13", "M22 2l-7 20-4-9-9-4 20-7z"],
  "sign-out": ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
  trash: [
    "M3 6h18",
    "M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2",
    "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
  ],
  upload: ["M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4", "M17 8l-5-5-5 5", "M12 3v12"],
  "user-plus": [
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
    "M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
    "M19 8v6",
    "M22 11h-6",
  ],
};

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
