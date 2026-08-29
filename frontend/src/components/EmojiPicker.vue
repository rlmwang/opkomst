<script lang="ts">
// Flat grid (multiple of 8 wide), grouped by chore use-case. Order is
// stable so the user builds muscle-memory positions over time. Exported so
// the chore editor can auto-assign an unused emoji to a new chore.
export const EMOJIS = [
  // Cleaning / bathroom.
  "🧹", "🧽", "🧼", "🧺", "🪣", "🚿", "🛁", "🚽",
  // Waste / dishes.
  "🗑️", "♻️", "🧻", "🍽️", "🍴", "🧊", "🫧", "🛒",
  // Kitchen / food.
  "🍳", "🥘", "🍲", "☕", "🫖", "🥖", "🍻", "🥗",
  // Setup / tools.
  "🪑", "🚪", "🔑", "💡", "🔧", "🔨", "🧰", "📦",
  // Outdoors / care.
  "🌱", "🪴", "🌿", "🔥", "🧯", "👕", "🎵", "🥁",
  // Digital / social media / comms.
  "📱", "💻", "📸", "💬", "📧", "🌐", "🔗", "📊",
  // Admin / organising.
  "📋", "📝", "📅", "📣", "🔔", "⏰", "📍", "🎉",
  // Organising / reactions (for the message blast tool).
  "🌹", "🚩", "✊", "❤️", "👍", "🙌", "🙏", "✅",
] as const;

// The emoji a fresh chore starts with — every chore always carries one.
export const DEFAULT_CHORE_EMOJI = "🧹";

/** First curated emoji not already in ``used``; falls back to the default
 * when every option is taken (never, in practice — 64 options). */
export function firstUnusedEmoji(used: Iterable<string>): string {
  const taken = new Set(used);
  return EMOJIS.find((e) => !taken.has(e)) ?? DEFAULT_CHORE_EMOJI;
}
</script>

<script setup lang="ts">
/**
 * Tiny emoji picker. A trigger that toggles a small popover grid of
 * curated emojis; clicking one emits ``select`` with the character.
 *
 * Two modes, one component:
 * - **value mode** (chore editor): pass ``modelValue`` and the trigger
 *   shows the current emoji, highlighting it in the grid. A chore always
 *   carries one — ``DEFAULT_CHORE_EMOJI`` seeds a fresh chore, so there
 *   is no clear control.
 * - **insert mode** (WhatsApp blast): omit ``modelValue`` and the trigger
 *   shows a neutral face icon; ``select`` inserts at the cursor.
 *
 * Deliberately not a full Unicode picker. The vocabulary leads with
 * chores (cleaning, kitchen, tools, logistics) and rounds out with the
 * organising/comms staples the blast tool needs — no library, no search.
 */
import AppButton from "@/components/AppButton.vue";
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

defineProps<{
  /** The currently selected emoji (value mode); omit for insert mode. */
  modelValue?: string | null;
}>();

const emit = defineEmits<{
  select: [emoji: string];
}>();

const { t } = useI18n();

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
    <AppButton
      type="button"
      severity="secondary"
      text
      size="small"
      :aria-label="t('chore.edit.pickEmoji')"
      :aria-expanded="open"
      class="emoji-trigger"
      :class="{ 'is-empty': !modelValue }"
      @click="toggle"
    >
      <span v-if="modelValue" class="emoji-current">{{ modelValue }}</span>
      <AppIcon v-else name="face-smile" />
    </AppButton>
    <div v-if="open" class="emoji-panel" role="dialog">
      <div class="emoji-grid">
        <button
          v-for="e in EMOJIS"
          :key="e"
          type="button"
          class="emoji-cell"
          :class="{ selected: e === modelValue }"
          :title="e"
          @click="pick(e)"
        >
          {{ e }}
        </button>
      </div>
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
.emoji-trigger.is-empty {
  color: var(--brand-text-muted);
}
.emoji-current {
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
}
.emoji-grid {
  display: grid;
  grid-template-columns: repeat(8, 2rem);
  gap: 0.15rem;
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
.emoji-cell.selected {
  background: var(--brand-red);
}
</style>
