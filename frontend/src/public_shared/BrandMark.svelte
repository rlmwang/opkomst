<script lang="ts">
/**
 * The organisation's logo and wordmark. One component for the admin
 * pages and the public mini-apps — both bundles can import from
 * ``public_shared`` — with the logo, the wordmark and the link target
 * all coming from the injected brand rather than from an asset import.
 */
import type { Snippet } from "svelte";

import { brand, isPersonalApp } from "@/lib/branding";

const {
  publicLink,
  wordmark,
}: {
  /** Public-facing mode (event signup, feedback form). Both logo and
   *  wordmark wrap a single external link to the organisation's own
   *  site, and the wordmark reads as the organisation rather than the
   *  app domain: public visitors associate with the organisation, not
   *  the tooling. */
  publicLink?: boolean;
  /** The admin header passes a link here so the wordmark navigates
   *  home; routing stays in the admin bundle, which is the only one
   *  that has a router. */
  wordmark?: Snippet;
} = $props();

const b = brand();
const label = `${b.org_name}, ${b.org_url.replace("https://", "")}`;
const external = !isPersonalApp();
</script>

<!-- ``org_url`` is somewhere else for an organisation and is this same
     site for the house brand, so only the first deserves a new tab. -->
{#if publicLink}
  <a
    href={b.org_url}
    target={external ? "_blank" : undefined}
    rel={external ? "noopener" : undefined}
    class="brand-mark public-link"
    aria-label={label}
  >
    {#if b.logo_url}<img src={b.logo_url} alt="" class="party-logo" />{/if}
    <span class="wordmark">{b.wordmark}</span>
  </a>
{:else}
  <div class="brand-mark">
    <a
      href={b.org_url}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener" : undefined}
      class="party-logo-link"
      aria-label={label}
    >
      <!-- A brand without a logo file (the house brand, worn by pages
           no organisation owns) renders its wordmark alone rather than
           a broken image. -->
      {#if b.logo_url}<img src={b.logo_url} alt="" class="party-logo" />{/if}
    </a>
    {#if wordmark}{@render wordmark()}{:else}<span class="wordmark">{b.app_name}</span>{/if}
  </div>
{/if}

<style>
.brand-mark {
  display: inline-flex;
  align-items: center;
  gap: 0.625rem;
}
.party-logo-link {
  display: inline-flex;
  align-items: center;
  line-height: 0;
}
.party-logo {
  height: 60px;
  width: 60px;
  object-fit: contain;
  display: block;
}
.wordmark {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--brand-red);
  letter-spacing: 0.5px;
  line-height: 1;
  text-decoration: none;
}
/* Public-link mode wraps the whole brand-mark; clear the
 * inherited <a> styling so logo + wordmark read as one
 * affordance instead of an underlined block. */
.brand-mark.public-link {
  text-decoration: none;
  color: inherit;
}
.brand-mark.public-link:hover .wordmark {
  text-decoration: underline;
}
</style>
