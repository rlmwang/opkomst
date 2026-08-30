<script lang="ts">
/** Shared 4:5 hero image and optional artist credit for the public
 *  mini-apps. Renders nothing when there is no image. ``creditLabel``
 *  is passed in (the mini-apps have no i18n), e.g. "Ontwerp:". */
const {
  imageUrl,
  artist,
  creditLabel,
}: { imageUrl: string | null; artist: string | null; creditLabel: string } = $props();
</script>

{#if imageUrl}
  <figure class="hero">
    <img src={imageUrl} alt="" class="hero-img" />
    {#if artist}
      <figcaption class="credit">
        {creditLabel}
        <a href="https://instagram.com/{artist}" target="_blank" rel="noopener">@{artist}</a>
      </figcaption>
    {/if}
  </figure>
{/if}

<style>
/* Bottom margin so the title beneath isn't cramped against the image.
 * The frame is a fixed 4:5 at every width — capped at 320×400 and centred,
 * matching the event page — so it looks identical on mobile and desktop and
 * creators can design to one 4:5 frame. (Was ``width:100% + max-height``,
 * which held 4:5 only on narrow phones and went letterbox-wide on desktop.) */
.hero {
  margin: 0 0 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.hero-img {
  width: 100%;
  max-width: 320px;
  aspect-ratio: 4 / 5;
  object-fit: cover;
  border-radius: 12px;
  border: 1px solid var(--brand-border);
}
.credit { margin-top: 0.375rem; font-size: 0.8125rem; color: var(--brand-text-muted); }
.credit a { color: inherit; }

/* On a short screen the 4:5 frame plus the header fills the viewport,
 * which puts the first form field below the fold on the page whose
 * whole point is that field. Cap the height there and let the crop take
 * the difference; the ratio still holds everywhere it fits. */
@media (max-height: 720px) {
  .hero-img {
    aspect-ratio: auto;
    height: 40vh;
    max-height: 400px;
  }
}
</style>
