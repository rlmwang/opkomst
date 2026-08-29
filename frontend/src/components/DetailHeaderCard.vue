<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import { useI18n } from "@/i18n";
import type { RouteLocationRaw } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import ShareStub from "@/components/ShareStub.vue";

// The standardized overview header for the four admin details pages
// (event / form / datepoll / roster). Placement and styling are shared;
// content differences ride in props and the ``#meta`` slot. The
// description is the same sanitized ``.richtext`` body organisers author
// in the editor and visitors see on the public page, rendered here with
// ``v-html`` (safe: sanitized server-side on write).
//
// Two columns, the same anatomy as the list card: everything the
// organiser reads on the left, the tear-off ``ShareStub`` on the right.
defineProps<{
  title: string;
  chapterName?: string | null;
  imageUrl?: string | null;
  imageArtist?: string | null;
  imageHref?: string | null;
  descriptionHtml?: string | null;
  qrSrc: string;
  publicUrl: string;
  editTo: RouteLocationRaw;
}>();

const emit = defineEmits<{ copyQr: []; copyLink: [] }>();
const { t } = useI18n();
</script>

<template>
  <AppCard :stack="false" class="overview">
    <div class="overview-main">
      <h1>
        {{ title }}
        <span v-if="chapterName" class="chapter-chip">{{ chapterName }}</span>
      </h1>
      <figure v-if="imageUrl" class="detail-image">
        <a v-if="imageHref" :href="imageHref" target="_blank" rel="noopener">
          <img :src="imageUrl" :alt="title" />
        </a>
        <img v-else :src="imageUrl" :alt="title" />
        <figcaption v-if="imageArtist" class="muted">
          {{ t("common.imageCredit") }}
          <a :href="`https://instagram.com/${imageArtist}`" target="_blank" rel="noopener">@{{ imageArtist }}</a>
        </figcaption>
      </figure>
      <slot name="meta" />
      <div v-if="descriptionHtml" class="richtext" v-html="descriptionHtml"></div>
      <div class="edit-row">
        <router-link :to="editTo">
          <AppButton :label="t('common.edit')" icon="pencil" size="small" severity="secondary" />
        </router-link>
      </div>
    </div>

    <ShareStub
      :public-url="publicUrl"
      :qr-src="qrSrc"
      :copy-link-label="t('common.copyLink')"
      :copy-qr-label="t('common.copyQr')"
      @copy-link="emit('copyLink')"
      @copy-qr="emit('copyQr')"
    />
  </AppCard>
</template>

<style scoped>
/* Text column + stub column, one row, so the stub stretches to the
 * card's full height and its tear-line with it. */
.overview {
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
  .overview {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
