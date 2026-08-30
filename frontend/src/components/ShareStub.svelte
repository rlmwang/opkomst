<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import { tip } from "@/lib/tooltip";

/**
 * The ticket stub: the public URL and its QR, the two things an organiser
 * hands to somebody else, kept together behind a dotted tear-line. Used
 * by both cards that surface a public link — the list card
 * (``EntityCard``) and the details header (``DetailHeaderCard``) — so the
 * perforation, the orientation flip and the copy affordances are one
 * implementation rather than two that drift.
 *
 *   wide                      narrow
 *   ┊ https://…/e/abc12345    ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
 *   ┊      ┌────┐             https://…/e/…   ┌────┐
 *   ┊      │ QR │                             │ QR │
 *   ┊      └────┘                             └────┘
 *
 * It expects to be a grid item of a card whose other column is the card's
 * own text; it stretches to that row, so the tear-line runs the full
 * height of the card. The negative margins carry it through the card's
 * padding, edge to edge, the way a ticket is actually perforated.
 */
const {
  publicUrl,
  qrSrc,
  copyLinkLabel,
  copyQrLabel,
  oncopyLink,
  oncopyQr,
}: {
  /** The public URL. Absent on an entity with no live page yet, an
   *  event whose occurrences have all passed say, in which case the
   *  stub shows the QR alone. */
  publicUrl?: string;
  /** QR thumbnail source. */
  qrSrc?: string;
  /** Tooltip and aria-label for the copy-link button. */
  copyLinkLabel: string;
  /** Tooltip and aria-label for the QR. */
  copyQrLabel: string;
  oncopyLink: () => void;
  oncopyQr: () => void;
} = $props();
</script>

<div class="share-stub">
  {#if publicUrl}
    <div class="link-row">
      <a href={publicUrl} target="_blank" rel="noopener">{publicUrl}</a>
      <span use:tip={copyLinkLabel}>
        <AppButton icon="copy" size="small" severity="secondary" text onclick={oncopyLink} />
      </span>
    </div>
  {/if}
  {#if qrSrc}
    <button
      type="button"
      class="qr-button"
      use:tip={copyQrLabel}
      aria-label={copyQrLabel}
      onclick={oncopyQr}
    >
      <img src={qrSrc} alt="" class="qr" />
    </button>
  {/if}
</div>

<style>
/* The URL row and the QR thumbnail themselves. They live here rather
 * than in ``theme.css`` because this is the only thing that renders
 * them. */
.link-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
}
.link-row a {
  font-size: 0.9375rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.qr-button {
  line-height: 0;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  border-radius: 6px;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.qr-button:hover {
  transform: scale(1.03);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.qr-button:focus-visible {
  outline: 2px solid var(--brand-red);
  outline-offset: 2px;
  border-radius: 8px;
}
.qr {
  width: 96px;
  height: 96px;
  background: white;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  padding: 4px;
  display: block;
}

/* Column 2 of the card's grid, stretched to the single row the card
 * lays out, so the tear-line runs its full height. The negative block
 * margins carry the border out to the card's edges; the matching block
 * padding puts the card's own inset back inside, so on a short card,
 * where the stub is what sets the height, the QR doesn't sit on the
 * card's bottom edge. */
.share-stub {
  align-self: stretch;
  margin-block: -1.25rem;
  padding-block: 1.25rem;
  padding-left: 1.25rem;
  border-left: 1px dashed var(--brand-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-width: 0;
  max-width: 16rem;
}
.share-stub > .qr-button {
  flex: none;
}
/* The URL and its copy button centre as a pair, so the QR under them
 * lines up with what you read rather than with the row's edges. */
.share-stub > .link-row {
  max-width: 100%;
  justify-content: center;
}

/* Below 480px the card's padding drops to 1rem (theme.css) and the card
 * goes single-column, so the stub tears off along the bottom instead:
 * the perforation runs across the card, link beside QR. */
@media (max-width: 480px) {
  .share-stub {
    margin: 0 -1rem -1rem;
    padding: 0.875rem 1rem 1rem;
    border-left: 0;
    border-top: 1px dashed var(--brand-border);
    flex-direction: row;
    justify-content: space-between;
    max-width: none;
  }
}
</style>
