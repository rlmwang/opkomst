<script setup lang="ts">
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
import { nextTick, ref, watch } from "vue";

import { useOverlayPanel } from "@/composables/useOverlayPanel";

const emit = defineEmits<{ show: []; hide: [] }>();

const GUTTER = 10;

const {
  anchor,
  panel,
  open,
  style: panelStyle,
  flipped,
  show: openPanel,
  hide,
  place,
} = useOverlayPanel({ matchAnchorWidth: false, gutter: GUTTER });

// The arrow points at the middle of the button that opened the panel,
// which is not the middle of the panel once it has been kept inside the
// viewport.
const arrowLeft = ref(`${GUTTER}px`);
function placeArrow(): void {
  const box = anchor.value?.getBoundingClientRect();
  const el = panel.value?.getBoundingClientRect();
  if (!box || !el) return;
  const centre = box.left + box.width / 2 - el.left;
  arrowLeft.value = `${Math.max(GUTTER + 2, Math.min(centre, el.width - GUTTER - 2))}px`;
}

function show(event: Event): void {
  openPanel((event.currentTarget ?? event.target) as HTMLElement);
}

function toggle(event: Event): void {
  if (open.value) hide();
  else show(event);
}

watch(open, (isOpen) => {
  if (isOpen) {
    emit("show");
    void nextTick(() => {
      place();
      placeArrow();
    });
  } else {
    emit("hide");
  }
});

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== "Escape") return;
  event.preventDefault();
  hide();
  anchor.value?.focus();
}

defineExpose({ toggle, show, hide });
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      ref="panel"
      class="pop"
      :class="{ 'pop-flipped': flipped }"
      :style="{ ...panelStyle, '--pop-arrow-left': arrowLeft }"
      role="dialog"
      @keydown="onKeydown"
    >
      <div class="pop-content"><slot /></div>
    </div>
  </Teleport>
</template>

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
