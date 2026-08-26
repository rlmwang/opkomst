<script setup lang="ts">
/**
 * The colophon: where the written pages, the policy and the source
 * live. Only on house-brand pages, and only in the app.
 *
 * A footer rather than a nav bar, and below the content rather than
 * beside it, because these are places a reader goes *instead of* the
 * task rather than during it (`docs/focus.md`). It is also where a
 * crawler looks for the site graph.
 *
 * Not rendered on a brand an organisation owns: their pages carry their
 * own identity, and a list of our essays is not part of it. `brand()`
 * decides, the same test the ad slot uses.
 *
 * The page list is duplicated from `backend/services/content.py`, which
 * is the canonical one. `tests/test_content.py` fails if the two ever
 * disagree, so the duplication cannot rot silently: the alternative was
 * shipping the list through the brand payload, which would have made
 * brand data out of something that is not.
 */
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { brand, isPersonalApp } from "@/lib/branding";
import { GITHUB_URL } from "@/public_shared/strings";

const { t } = useI18n();

const PAGES = [
  { slug: "datumprikker-zonder-account", title: "Datumprikker zonder account of cookies" },
  { slug: "aanmeldformulier-zonder-google", title: "Aanmeldformulier maken zonder Google Forms" },
  { slug: "wat-gebeurt-er-met-je-mailadres", title: "Wat er met je e-mailadres gebeurt" },
  { slug: "vrijwilligers-inroosteren", title: "Vrijwilligers inroosteren zonder spreadsheet" },
];

const show = computed(() => isPersonalApp());
const b = brand();
</script>

<template>
  <footer v-if="show" class="site-footer">
    <nav class="footer-links" :aria-label="t('footer.label')">
      <a v-for="page in PAGES" :key="page.slug" :href="`/${page.slug}`">{{ page.title }}</a>
      <a href="/privacy">{{ t("footer.privacy") }}</a>
      <a :href="GITHUB_URL" target="_blank" rel="noopener">{{ t("footer.source") }}</a>
    </nav>
    <p class="footer-note muted">{{ b.app_name }}</p>
  </footer>
</template>

<style scoped>
/* Muted throughout, the same treatment the disclosure card uses: this
 * is a colophon and it competes with nothing above it. */
.site-footer {
  max-width: 720px;
  margin: 3rem auto 0;
  padding: 1.5rem 1rem 2rem;
  border-top: 1px solid var(--brand-border);
}
.footer-links {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.footer-links a {
  color: var(--brand-text-muted);
  font-size: 0.875rem;
  text-decoration: none;
  width: fit-content;
}
.footer-links a:hover {
  text-decoration: underline;
}
.footer-note {
  margin: 1rem 0 0;
}
</style>
