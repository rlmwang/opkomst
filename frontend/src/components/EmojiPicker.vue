<script setup lang="ts">
/**
 * Tiny emoji picker. A button that toggles a small popover grid
 * of curated emojis. Clicking an emoji emits ``select`` with the
 * character so the parent can insert it at the right place.
 *
 * Deliberately not a full Unicode picker. The blast tool is used
 * a handful of times a year; 80 commonly-used emojis cover the
 * organising-context vocabulary (rose, raised fist, megaphone,
 * NL flag, etc.) without dragging in 30KB of library code or a
 * search UI nobody asked for.
 */
import Button from "primevue/button";
import { onBeforeUnmount, onMounted, ref } from "vue";

const emit = defineEmits<{
  select: [emoji: string];
}>();

// Single flat grid, loosely grouped by use-case. Order is stable
// so the user can build muscle-memory positions over time.
const EMOJIS = [
  // Faces.
  "😀", "😄", "😁", "😊", "😂", "🤣", "😅", "😉",
  "😍", "🥰", "😘", "😎", "🤔", "😴", "🥳", "🤩",
  "😢", "😭", "😡", "🤯", "🙄", "😬", "😇", "🤗",
  // Reactions.
  "❤️", "💔", "💯", "👍", "👎", "👏", "🙏", "🙌",
  "💪", "✊", "🤝", "👋", "✨", "🔥", "⭐", "🎉",
  "✅", "❌", "⚠️", "❓", "❗", "💡", "👀", "🤞",
  // Organising / political.
  "🌹", "🚩", "🏳️‍🌈", "☮️", "🌍", "🇳🇱", "🇪🇺", "📣",
  "📢", "📅", "📍", "📌", "📝", "🔔", "⏰", "🎈",
  // Misc useful.
  "🎁", "☕", "🍻", "🥁", "📷", "💬", "📨", "✉️",
];

const open = ref(false);
const root = ref<HTMLElement | null>(null);

function toggle(): void {
  open.value = !open.value;
}

function pick(emoji: string): void {
  emit("select", emoji);
  open.value = false;
}

function onDocClick(e: MouseEvent): void {
  if (!open.value) return;
  if (root.value && !root.value.contains(e.target as Node)) {
    open.value = false;
  }
}

function onKey(e: KeyboardEvent): void {
  if (e.key === "Escape") open.value = false;
}

onMounted(() => {
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKey);
});
</script>

<template>
  <span ref="root" class="emoji-picker">
    <Button
      type="button"
      severity="secondary"
      text
      size="small"
      :aria-label="'emoji'"
      :aria-expanded="open"
      class="emoji-trigger"
      @click="toggle"
    >
      😀
    </Button>
    <div v-if="open" class="emoji-panel" role="dialog">
      <button
        v-for="e in EMOJIS"
        :key="e"
        type="button"
        class="emoji-cell"
        :title="e"
        @click="pick(e)"
      >
        {{ e }}
      </button>
    </div>
  </span>
</template>

<style scoped>
.emoji-picker {
  position: relative;
  display: inline-block;
}
.emoji-trigger {
  font-size: 1.1rem;
  line-height: 1;
}
.emoji-panel {
  position: absolute;
  top: calc(100% + 0.25rem);
  left: 0;
  z-index: 10;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
  padding: 0.4rem;
  display: grid;
  grid-template-columns: repeat(8, 2rem);
  gap: 0.15rem;
  max-width: calc(8 * 2.15rem + 0.8rem);
}
.emoji-cell {
  width: 2rem;
  height: 2rem;
  font-size: 1.15rem;
  line-height: 1;
  background: transparent;
  border: 0;
  border-radius: 0.25rem;
  cursor: pointer;
  padding: 0;
}
.emoji-cell:hover,
.emoji-cell:focus-visible {
  background: var(--brand-bg);
  outline: none;
}
</style>
