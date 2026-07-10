<script setup lang="ts">
import Button from "primevue/button";
import { useI18n } from "vue-i18n";
import type { RouteLocationRaw } from "vue-router";
import AppCard from "@/components/AppCard.vue";

// The standardized overview header for the four admin details pages
// (event / form / datepoll / roster). Placement and styling are shared;
// content differences ride in props and the ``#meta`` slot. The
// description is the same sanitized ``.richtext`` body organisers author
// in the editor and visitors see on the public page, rendered here with
// ``v-html`` (safe: sanitized server-side on write).
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
    <div class="overview-body">
      <div class="overview-text">
        <slot name="meta" />
        <div v-if="descriptionHtml" class="richtext" v-html="descriptionHtml"></div>
        <button
          type="button"
          class="qr-button"
          v-tooltip.top="t('common.copyQr')"
          :aria-label="t('common.copyQr')"
          @click="emit('copyQr')"
        >
          <img :src="qrSrc" alt="" class="qr" />
        </button>
        <div class="link-row">
          <a :href="publicUrl" target="_blank" rel="noopener">{{ publicUrl }}</a>
          <Button
            icon="pi pi-copy"
            size="small"
            severity="secondary"
            text
            v-tooltip.top="t('common.copyLink')"
            :aria-label="t('common.copyLink')"
            @click="emit('copyLink')"
          />
        </div>
        <div>
          <router-link :to="editTo">
            <Button :label="t('common.edit')" icon="pi pi-pencil" size="small" severity="secondary" />
          </router-link>
        </div>
      </div>
    </div>
  </AppCard>
</template>
