<script lang="ts">
import { brand } from "@/lib/branding";
import { type Locale, GITHUB_ISSUE_URL, GITHUB_URL, chromeStrings } from "./strings";

/** The open-source and privacy disclosure card, shared by the public
 *  mini-apps. A collapsible ``<details>`` with the GitHub link: the
 *  project invariant that every public page discloses the source. */
const { locale }: { locale: Locale } = $props();
const c = $derived(chromeStrings(locale));
// Without a configured network the slot is a static image this app
// serves, and ``explainerBody`` is true exactly as written.
const advertising = Boolean(brand().ads?.client_id);
</script>

<div class="card">
  <details>
    <summary>{c.explainerTitle}</summary>
    <p class="body">
      {c.explainerBody}
      <a href={GITHUB_URL} target="_blank" rel="noopener">{c.explainerLink}</a>
    </p>
    {#if advertising}<p class="body">{c.adDisclosure}</p>{/if}
    <p class="body">
      <a href="/privacy">{c.privacyLink}</a>
      &middot;
      <a href={GITHUB_ISSUE_URL} target="_blank" rel="noopener">{c.feedbackLink}</a>
    </p>
  </details>
</div>

<style>
summary { cursor: pointer; font-weight: 600; }
.body { margin: 0.5rem 0 0; color: var(--brand-text-muted); }
</style>
