<script setup lang="ts">
/**
 * The colophon: where the written pages, the policy and the source
 * live. Only on house-brand pages, and only on the five pages a
 * stranger can land on.
 *
 * A footer rather than a nav bar, and below the content rather than
 * beside it, because these are places a reader goes *instead of* the
 * task rather than during it (`docs/focus.md`). It is also where a
 * crawler looks for the site graph.
 *
 * Two things keep it quiet. It names each page in two words rather
 * than repeating the sentence-long title a search result needs, and it
 * appears only where somebody might still be deciding what this is:
 * the root and the four create pages. An organiser halfway through
 * their own event has already decided, and a dashboard is not a place
 * to advertise reading material.
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
import { useRoute } from "vue-router";
import { isPersonalApp } from "@/lib/branding";
import { GITHUB_URL } from "@/public_shared/strings";

const { t } = useI18n();
const route = useRoute();

const PAGES = [
  { slug: "datumprikker-zonder-account", label: "Datumprikker" },
  { slug: "aanmeldformulier-zonder-google", label: "Aanmeldformulier" },
  { slug: "wat-gebeurt-er-met-je-mailadres", label: "E-mailadressen" },
  { slug: "vrijwilligers-inroosteren", label: "Vrijwilligersrooster" },
];

// The landing page and the four things it offers to make. The same
// five paths the server writes a title and description for
// (``routers/spa.py``), for the same reason: they are the pages a
// stranger arrives on.
const LANDING_PATHS = ["/", "/events/new", "/forms/new", "/datepolls/new", "/chores/new"];

const show = computed(() => isPersonalApp() && LANDING_PATHS.includes(route.path));
</script>

<template>
  <footer v-if="show" class="site-footer">
    <nav class="footer-links" :aria-label="t('footer.label')">
      <a v-for="page in PAGES" :key="page.slug" :href="`/${page.slug}`">{{ page.label }}</a>
      <a href="/privacy">{{ t("footer.privacy") }}</a>
      <a :href="GITHUB_URL" target="_blank" rel="noopener">{{ t("footer.source") }}</a>
    </nav>
  </footer>
</template>

<style scoped>
/* One wrapping row of short names, in the muted treatment the
 * disclosure card uses. A colophon competes with nothing above it. */
.site-footer {
  max-width: 720px;
  margin: 3rem auto 0;
  padding: 1.25rem 1rem 2rem;
  border-top: 1px solid var(--brand-border);
}
.footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 1.25rem;
}
.footer-links a {
  color: var(--brand-text-muted);
  font-size: 0.8125rem;
  text-decoration: none;
}
.footer-links a:hover {
  text-decoration: underline;
}
</style>
