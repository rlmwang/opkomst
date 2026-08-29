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
import { GITHUB_ISSUE_URL, GITHUB_URL } from "@/public_shared/strings";

const { t } = useI18n();
const route = useRoute();

const PAGES = [
  { slug: "aanmeldpagina-voor-je-evenement", title: "Aanmeldpagina voor je evenement, zonder kosten per aanmelding" },
  { slug: "datumplanner-zonder-account", title: "Datumplanner zonder account of cookies" },
  { slug: "aanmeldformulier-zonder-google", title: "Aanmeldformulier maken zonder Google Forms" },
  { slug: "wat-gebeurt-er-met-je-mailadres", title: "Wat er met je e-mailadres gebeurt" },
  { slug: "pubquiz-maken-zonder-account", title: "Pubquiz maken zonder account of abonnement" },
  { slug: "kieskompas-maken-zonder-onderzoeksbureau", title: "Een kieskompas maken voor je eigen groep" },
  { slug: "vrijwilligers-inroosteren", title: "Vrijwilligers inroosteren zonder spreadsheet" },
  { slug: "wat-mag-je-bewaren-van-deelnemers", title: "Wat mag je bewaren van je deelnemers?" },
  { slug: "ledenvergadering-voorbereiden", title: "Een ledenvergadering voorbereiden" },
  { slug: "gratis-alternatief-voor-eventbrite", title: "Gratis alternatief voor Eventbrite" },
];

// The landing page and the four things it offers to make. The same
// five paths the server writes a title and description for
// (``routers/spa.py``), for the same reason: they are the pages a
// stranger arrives on.
const LANDING_PATHS = ["/", "/event/new", "/form/new", "/datepoll/new", "/chore/new"];

const show = computed(() => isPersonalApp() && LANDING_PATHS.includes(route.path));

// The rule above the links is the width of the page's own content, so
// it lines up with whatever horizontal line the page already has: the
// landing page's "of log in" divider inside its wide column, the four
// create pages' 720px form column. Wearing the page's own container
// class is what keeps the two in step when either width changes.
const column = computed(() => (route.path === "/" ? "container-wide" : "container"));
</script>

<template>
  <footer v-if="show" class="site-footer">
    <div :class="column">
      <nav class="footer-links" :aria-label="t('footer.label')">
        <a href="/privacy">{{ t("footer.privacy") }}</a>
        <a href="/voorwaarden">{{ t("footer.terms") }}</a>
        <a :href="GITHUB_URL" target="_blank" rel="noopener">{{ t("footer.source") }}</a>
        <a :href="GITHUB_ISSUE_URL" target="_blank" rel="noopener">{{ t("footer.feedback") }}</a>
        <!-- Numbered rather than named, and last: the footer is here so
           a crawler finds the written pages from every app page, while
           a reader wants the policy, the source and the way to report
           something. The title still travels, as the link's own
           label. -->
        <span class="blogs">
          {{ t("footer.blogs") }}
          <a
            v-for="(page, i) in PAGES"
            :key="page.slug"
            :href="`/${page.slug}`"
            :title="page.title"
            :aria-label="page.title"
          >{{ i + 1 }}</a>
        </span>
      </nav>
    </div>
  </footer>
</template>

<style scoped>
/* One wrapping row of short names, in the muted treatment the
 * disclosure card uses. A colophon competes with nothing above it.
 *
 * The rule sits on the links rather than on the footer, so it stops
 * where the page's content stops instead of running out to the edges
 * of the window. */
.site-footer {
  margin-top: 1.5rem;
}
.footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--brand-border);
}
/* Right-hand end of the row: the named links are what a reader is
 * looking for, the numbered list is for a crawler. Wrapping on a narrow
 * screen drops it onto its own line, still at the right. */
.blogs {
  margin-left: auto;
  display: inline-flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--brand-text-muted);
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
