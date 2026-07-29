<script setup lang="ts">
import AppCard from "@/components/AppCard.vue";

/**
 * The list-page card for a public-facing entity — Events, Forms,
 * Datepolls, Chores. All four rendered the same three-part shape
 * (title + meta + public link, an actions row, and a count above a
 * QR thumbnail) as four separate copies of the same grid; this is
 * that shape, once.
 *
 * The layout reads top-down: what it is, where it lives publicly,
 * then what you can do with it.
 *
 *   ┌──────────────────────────────────────┐
 *   │ Title  [Chapter]              ┌────┐ │
 *   │ meta lines                    │ QR │ │
 *   │ https://…/e/abc12345    copy  └────┘ │
 *   │                                      │
 *   │ [Details] [Archive]      12 attendees │
 *   └──────────────────────────────────────┘
 *
 * The QR is a share artifact rather than list content, so it takes
 * the corner instead of a share of the reading width, and it drops
 * out entirely on phones (see the media query).
 */
defineProps<{
  /** QR thumbnail source. Absent on cards with no public URL yet —
   * an event whose occurrences have all passed, say. */
  qrSrc?: string;
  /** Tooltip + aria-label for the QR copy button. */
  qrLabel?: string;
}>();

defineEmits<{ "copy-qr": [] }>();
</script>

<template>
  <AppCard :stack="false" class="entity-card">
    <div class="entity-body">
      <div class="entity-text">
        <div class="entity-title"><slot name="title" /></div>
        <div v-if="$slots.meta" class="entity-meta"><slot name="meta" /></div>
        <div v-if="$slots.link" class="entity-link"><slot name="link" /></div>
      </div>
      <button
        v-if="qrSrc"
        type="button"
        class="qr-button"
        v-tooltip.top="qrLabel"
        :aria-label="qrLabel"
        @click="$emit('copy-qr')"
      >
        <img :src="qrSrc" alt="" class="qr" />
      </button>
    </div>

    <div class="entity-footer">
      <div class="entity-actions"><slot name="actions" /></div>
      <div v-if="$slots.count" class="entity-count muted"><slot name="count" /></div>
    </div>
  </AppCard>
</template>

<style scoped>
.entity-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
/* Text column + QR. ``align-items: start`` anchors the QR to the
 * top-right corner rather than stretching it down a card whose
 * height it doesn't control. */
.entity-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1.25rem;
  align-items: start;
}
.entity-text {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}
/* Slot content carries the calling page's scope id, not this
 * component's, so the heading / paragraph resets have to reach
 * through ``:deep``. Scoped to the wrapper element so they can't
 * touch anything else on the card. */
.entity-title :deep(h3) {
  margin: 0;
}
.entity-meta {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}
.entity-meta :deep(p) {
  margin: 0;
  font-size: 0.875rem;
}
.entity-link {
  margin-top: 0.125rem;
}

/* One baseline for everything actionable, with the count as the
 * right-hand summary figure. Wraps on the narrowest screens; the
 * ``margin-left: auto`` keeps the count right-aligned either way,
 * so the card never grows a third alignment. */
.entity-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
}
.entity-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.entity-count {
  margin-left: auto;
  white-space: nowrap;
}

/* The QR is 96px of the highest-contrast pixels on the page, and
 * on a phone it is also the least useful thing there: you cannot
 * scan it with the device already displaying it, and pasting an
 * image out of the clipboard is a desktop job. Stacked under the
 * text it left a block dangling in a corner with nothing aligned
 * to it, which is what made these cards read as disorganised. The
 * same QR, full size, is on the entity's details page. */
@media (max-width: 540px) {
  .entity-body {
    grid-template-columns: minmax(0, 1fr);
  }
  .qr-button {
    display: none;
  }
}
</style>
