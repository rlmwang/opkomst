<script lang="ts">
/**
 * An anchored panel with whatever the caller puts in it. Replaces
 * PrimeVue's ``Popover``: the header's navigation menu and the recover
 * links pill.
 *
 * Imperative on purpose, the way the two call sites already use it: the
 * button that opens it calls ``toggle(event)`` on a template ref, and
 * the panel hangs under whichever element was pressed.
 *
 * Aura's geometry: a 10px gap under the anchor with an arrow in it,
 * 0.75rem of padding, a 6px radius and the popover shadow. Placement,
 * teleporting and dismissal are ``composables/useOverlayPanel``'s,
 * shared with the overlay lists.
 */
import type { Snippet } from "svelte";

import { tick } from "svelte";
import { useOverlayPanel } from "@/composables/useOverlayPanel.svelte";

const {
  onshow,
  onhide,
  children,
}: { onshow?: () => void; onhide?: () => void; children: Snippet } = $props();

const GUTTER = 10;

// Held whole, not destructured: every field is a getter.
const overlay = useOverlayPanel({ matchAnchorWidth: false, gutter: GUTTER });

// The arrow points at the middle of the button that opened the panel,
// which is not the middle of the panel once it has been kept inside the
// viewport.
let arrowLeft = $state(`${GUTTER}px`);
function placeArrow(): void {
  const box = overlay.anchor?.getBoundingClientRect();
  const el = overlay.panel?.getBoundingClientRect();
  if (!box || !el) return;
  const centre = box.left + box.width / 2 - el.left;
  arrowLeft = `${Math.max(GUTTER + 2, Math.min(centre, el.width - GUTTER - 2))}px`;
}

export function show(event: Event): void {
  overlay.show((event.currentTarget ?? event.target) as HTMLElement);
  onshow?.();
  // ``tick`` and not a frame: it resolves once the DOM is updated and
  // before the browser paints, so the panel is never drawn unplaced.
  void tick().then(() => {
    overlay.place();
    placeArrow();
  });
}

export function hide(): void {
  if (!overlay.open) return;
  overlay.hide();
  onhide?.();
}

export function toggle(event: Event): void {
  if (overlay.open) hide();
  else show(event);
}

/** The composable hands back a style object; an element wants a string. */
function styleOf(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`)}: ${v}`)
    .join("; ");
}

// A press outside closes the panel from inside the composable, so the
// host has to hear about that too.
let wasOpen = overlay.open;
$effect(() => {
  if (wasOpen && !overlay.open) onhide?.();
  wasOpen = overlay.open;
});

function portal(node: HTMLElement) {
  document.body.appendChild(node);
  return {
    destroy() {
      node.remove();
    },
  };
}
</script>

{#if overlay.open}
  <div use:portal style="display: contents">
    <div
      bind:this={overlay.panel}
      class="pop"
      class:pop-flipped={overlay.flipped}
      style="{styleOf(overlay.style)}; --pop-arrow-left: {arrowLeft}"
      role="dialog"
    >
      <div class="pop-content">{@render children()}</div>
    </div>
  </div>
{/if}

<style>
/* Teleported to the body, so no scope attribute can reach it. */
.pop {
  background: var(--brand-surface);
  color: var(--brand-text);
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.1),
    0 2px 4px -2px rgba(0, 0, 0, 0.1);
  z-index: 1100;
}
.pop-content {
  padding: 0.75rem;
}
/* The arrow: a border triangle in the panel's own colour, over a
 * one-pixel-larger one in the border colour. */
.pop::before,
.pop::after {
  content: " ";
  position: absolute;
  bottom: 100%;
  left: var(--pop-arrow-left);
  height: 0;
  width: 0;
  pointer-events: none;
  border-style: solid;
  border-color: transparent;
}
.pop::after {
  border-width: 8px;
  margin-left: -8px;
  border-bottom-color: var(--brand-surface);
}
.pop::before {
  border-width: 10px;
  margin-left: -10px;
  border-bottom-color: var(--brand-border);
}
.pop-flipped::before,
.pop-flipped::after {
  bottom: auto;
  top: 100%;
}
.pop-flipped::after {
  border-bottom-color: transparent;
  border-top-color: var(--brand-surface);
}
.pop-flipped::before {
  border-bottom-color: transparent;
  border-top-color: var(--brand-border);
}
</style>
