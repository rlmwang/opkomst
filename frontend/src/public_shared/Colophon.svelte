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
 * The blog is the one part an organisation's pages leave out: the
 * policy, the source and the way to report something belong on every
 * page, while our essays are not part of their identity.
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
      {#if house}
        <a href="/blog">{c.footerBlog}</a>
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
.footer-links a {
  color: var(--brand-text-muted);
  font-size: 0.8125rem;
  text-decoration: none;
}
.footer-links a:hover {
  text-decoration: underline;
}
</style>
