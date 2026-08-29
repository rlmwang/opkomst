<script lang="ts" module>
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

<script lang="ts">
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
import { onMount } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppIcon from "@/components/AppIcon.svelte";
import { t } from "@/i18n.svelte";

const {
  value,
  onselect,
}: {
  /** The currently selected emoji (value mode); omit for insert mode. */
  value?: string | null;
  onselect: (emoji: string) => void;
} = $props();

let open = $state(false);
let root = $state<HTMLElement | null>(null);

function toggle(): void {
  open = !open;
}

function pick(emoji: string): void {
  onselect(emoji);
  open = false;
}

onMount(() => {
  const onDocClick = (e: MouseEvent) => {
    if (open && root && !root.contains(e.target as Node)) open = false;
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") open = false;
  };
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
  return () => {
    document.removeEventListener("click", onDocClick);
    document.removeEventListener("keydown", onKey);
  };
});
</script>

<span bind:this={root} class="emoji-picker">
  <AppButton
    type="button"
    severity="secondary"
    text
    size="small"
    ariaLabel={t("chore.edit.pickEmoji")}
    class="emoji-trigger{value ? '' : ' is-empty'}"
    onclick={toggle}
  >
    {#if value}
      <span class="emoji-current">{value}</span>
    {:else}
      <AppIcon name="face-smile" />
    {/if}
  </AppButton>
  {#if open}
    <div class="emoji-panel" role="dialog">
      <div class="emoji-grid">
        {#each EMOJIS as e (e)}
          <button
            type="button"
            class="emoji-cell"
            class:selected={e === value}
            title={e}
            onclick={() => pick(e)}
          >
            {e}
          </button>
        {/each}
      </div>
    </div>
  {/if}
</span>

<style>
.emoji-picker {
  position: relative;
  display: inline-block;
}
:global(.emoji-trigger) {
  font-size: 1.1rem;
  line-height: 1;
}
:global(.emoji-trigger.is-empty) {
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
