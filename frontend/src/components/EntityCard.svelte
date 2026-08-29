<script lang="ts">
import type { Snippet } from "svelte";

import AppCard from "@/components/AppCard.svelte";
import ShareStub from "@/components/ShareStub.svelte";

/**
 * The list-page card for a public-facing entity — Events, Forms,
 * Datepolls, Chores. All four rendered the same shape as four separate
 * copies of the same grid; this is that shape, once.
 *
 *   ┌───────────────────────┊──────────────┐
 *   │ Title  [Chapter]      ┊ https://…/e/…│
 *   │ meta lines            ┊    ┌────┐    │
 *   │                       ┊    │ QR │    │
 *   │ [Details] [Archive]   ┊    └────┘    │
 *   └───────────────────────┊──────────────┘
 *
 * Two columns: the card's own text (what it is, then what you can do
 * with it) and the tear-off ``ShareStub`` — the same component the
 * details header uses, so a list card and a details page perforate
 * alike.
 */
const {
  publicUrl,
  qrSrc,
  copyLinkLabel,
  qrLabel,
  title,
  meta,
  actions,
  count,
  oncopyLink,
  oncopyQr,
}: {
  /** The public URL. Absent on an entity with no live page yet, an
   *  event whose occurrences have all passed say. */
  publicUrl?: string;
  /** QR thumbnail source. */
  qrSrc?: string;
  /** Tooltip and aria-label for the copy-link button. */
  copyLinkLabel: string;
  /** Tooltip and aria-label for the QR. */
  qrLabel: string;
  title: Snippet;
  meta?: Snippet;
  actions?: Snippet;
  count?: Snippet;
  oncopyLink: () => void;
  oncopyQr: () => void;
} = $props();
</script>

<AppCard stack={false} class="entity-card">
  <div class="entity-main">
    <div class="entity-text">
      <div class="entity-title">{@render title()}</div>
      {#if meta}<div class="entity-meta">{@render meta()}</div>{/if}
    </div>

    <div class="entity-footer">
      <div class="entity-actions">{#if actions}{@render actions()}{/if}</div>
      {#if count}<div class="entity-count muted">{@render count()}</div>{/if}
    </div>
  </div>

  {#if publicUrl || qrSrc}
    <ShareStub
      {publicUrl}
      {qrSrc}
      {copyLinkLabel}
      copyQrLabel={qrLabel}
      {oncopyLink}
      {oncopyQr}
    />
  {/if}
</AppCard>

<style>
/* Text column + stub column, one row, so the stub stretches to the
 * card's full height and its tear-line with it. */
:global(.entity-card) {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1.25rem;
}
/* The card's own content: what it is on top, what you can do with it at
 * the bottom, whatever height the stub turns out to set. */
.entity-main {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}
.entity-text {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}
/* Slot content carries the calling page's scope id, not this
 * component's, so the heading / paragraph resets have to reach through
 * ``:deep``. Scoped to the wrapper element so they can't touch anything
 * else on the card. */
.entity-title :global(h3) {
  margin: 0;
}
.entity-meta {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}
.entity-meta :global(p) {
  margin: 0;
  font-size: 0.875rem;
}

/* One baseline for everything actionable, at the bottom of the column,
 * with the count as the right-hand summary figure. */
.entity-footer {
  margin-top: auto;
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

/* One column on a phone; the stub's own media query flips it to the
 * bottom strip. */
@media (max-width: 480px) {
  :global(.entity-card) {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
