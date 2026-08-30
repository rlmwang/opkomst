<script lang="ts">
import type { Snippet } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import ShareStub from "@/components/ShareStub.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { t } from "@/i18n.svelte";

// The standardized overview header for the four admin details pages
// (event / form / datepoll / roster). Placement and styling are shared;
// content differences ride in props and the ``meta`` snippet. The
// description is the same sanitized ``.richtext`` body organisers author
// in the editor and visitors see on the public page, rendered here with
// ``{@html}`` (safe: sanitized server-side on write).
//
// Two columns, the same anatomy as the list card: everything the
// organiser reads on the left, the tear-off ``ShareStub`` on the right.
const {
  title,
  chapterName,
  imageUrl,
  imageArtist,
  imageHref,
  descriptionHtml,
  qrSrc,
  publicUrl,
  editTo,
  meta,
  oncopyQr,
  oncopyLink,
}: {
  title: string;
  chapterName?: string | null;
  imageUrl?: string | null;
  imageArtist?: string | null;
  imageHref?: string | null;
  descriptionHtml?: string | null;
  qrSrc: string;
  publicUrl: string;
  editTo: string;
  meta?: Snippet;
  oncopyQr: () => void;
  oncopyLink: () => void;
} = $props();
</script>

<AppCard stack={false} class="overview">
  <div class="overview-main">
    <h1>
      {title}
      {#if chapterName}<span class="chapter-chip">{chapterName}</span>{/if}
    </h1>
    {#if imageUrl}
      <figure class="detail-image">
        {#if imageHref}
          <a href={imageHref} target="_blank" rel="noopener">
            <img src={imageUrl} alt={title} />
          </a>
        {:else}
          <img src={imageUrl} alt={title} />
        {/if}
        {#if imageArtist}
          <figcaption class="muted">
            {t("common.imageCredit")}
            <a href="https://instagram.com/{imageArtist}" target="_blank" rel="noopener"
              >@{imageArtist}</a
            >
          </figcaption>
        {/if}
      </figure>
    {/if}
    {#if meta}{@render meta()}{/if}
    {#if descriptionHtml}<div class="richtext">{@html descriptionHtml}</div>{/if}
    <div class="edit-row">
      <RouterLink to={editTo}>
        <AppButton label={t("common.edit")} icon="pencil" size="small" severity="secondary" />
      </RouterLink>
    </div>
  </div>

  <ShareStub
    {publicUrl}
    {qrSrc}
    copyLinkLabel={t("common.copyLink")}
    copyQrLabel={t("common.copyQr")}
    oncopyLink={oncopyLink}
    oncopyQr={oncopyQr}
  />
</AppCard>

<style>
/* Text column + stub column, one row, so the stub stretches to the
 * card's full height and its tear-line with it. */
:global(.overview) {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1.25rem;
}
/* Title, image, meta, description, and the edit button on the card's
 * bottom-left, whatever height the stub turns out to set. */
.overview-main {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}
.overview-main h1 {
  margin: 0;
  overflow-wrap: anywhere;
}
.edit-row {
  margin-top: auto;
  padding-top: 0.25rem;
}

/* The image the organiser uploaded, at the poster's own 4:5. */
.detail-image {
  margin: 0;
}
.detail-image img {
  display: block;
  max-width: 200px;
  aspect-ratio: 4 / 5;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--brand-border);
}
.detail-image figcaption {
  margin-top: 0.375rem;
  font-size: 0.8125rem;
}

/* One column on a phone; the stub's own media query flips it to the
 * bottom strip. */
@media (max-width: 480px) {
  :global(.overview) {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
