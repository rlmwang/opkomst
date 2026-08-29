<script lang="ts">
/**
 * The colophon: where the written pages, the policy and the source
 * live. Shared by the organiser app (through `SiteFooter`, which
 * decides on which of its pages it belongs) and by every public
 * mini-app, so a stranger who lands on a sign-up link has the same way
 * to find out what this is.
 *
 * A footer rather than a nav bar, and below the content rather than
 * beside it, because these are places a reader goes *instead of* the
 * task rather than during it (`docs/focus.md`). It is also where a
 * crawler looks for the site graph.
 *
 * It stays quiet: each written page is a number rather than the
 * sentence-long title a search result needs, with the title travelling
 * as the link's own label.
 *
 * The blogs are the one part an organisation's pages leave out: the
 * policy, the source and the way to report something belong on every
 * page, while a list of our essays is not part of their identity.
 *
 * The page list is duplicated from `backend/services/content.py`, which
 * is the canonical one. `tests/test_content.py` fails if the two ever
 * disagree, so the duplication cannot rot silently: the alternative was
 * shipping the list through the brand payload, which would have made
 * brand data out of something that is not.
 */
import { isPersonalApp } from "@/lib/branding";
import { type Locale, GITHUB_ISSUE_URL, GITHUB_URL, chromeStrings } from "./strings";

const {
  locale,
  column,
}: {
  locale: Locale;
  /** The width the footer's rule should match: the page's own column.
   *  The mini-apps sit inside their container already, so they pass
   *  nothing and the rule fills whatever holds it. */
  column?: string;
} = $props();

const c = $derived(chromeStrings(locale));

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

/** The written pages are ours, so they show on our own brand only. */
const house = isPersonalApp();
</script>

<footer class="site-footer">
  <div class={column}>
    <nav class="footer-links" aria-label={c.footerLabel}>
      <a href="/privacy">{c.footerPrivacy}</a>
      <a href="/voorwaarden">{c.footerTerms}</a>
      <a href={GITHUB_URL} target="_blank" rel="noopener">{c.footerSource}</a>
      <a href={GITHUB_ISSUE_URL} target="_blank" rel="noopener">{c.footerFeedback}</a>
      <!-- Numbered rather than named, and last: the footer is here so
           a crawler finds the written pages from every app page, while
           a reader wants the policy, the source and the way to report
           something. The title still travels, as the link's own
           label. -->
      {#if house}
        <span class="blogs">
          {c.footerBlogs}
          {#each PAGES as page, i (page.slug)}
            <a href="/{page.slug}" title={page.title} aria-label={page.title}>{i + 1}</a>
          {/each}
        </span>
      {/if}
    </nav>
  </div>
</footer>

<style>
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
