<script setup lang="ts">
import { brand, isPersonalApp } from "@/lib/branding";

/**
 * The organisation's logo and wordmark. One component for the admin
 * pages and the public mini-apps — both bundles can import from
 * ``public_shared`` — with the logo, the wordmark and the link target
 * all coming from the injected brand rather than from an asset import.
 */

defineProps<{
  /** Public-facing mode (event signup, feedback form). Both logo and
   * wordmark wrap a single external link to the organisation's own
   * site, and the wordmark reads as the organisation rather than the
   * app domain — public visitors associate with the organisation, not
   * the tooling. */
  publicLink?: boolean;
}>();

const b = brand();
// The house brand's ``org_url`` is this same site, so the mark points at
// the landing page on this host: an absolute URL would send a local or
// staging build to production. An organisation's site is somewhere else,
// and that is the only one that earns a new tab.
const house = isPersonalApp();
const href = house ? "/" : b.org_url;
</script>

<template>
  <a
    v-if="publicLink"
    :href="href"
    :target="house ? undefined : '_blank'"
    :rel="house ? undefined : 'noopener'"
    class="brand-mark public-link"
    :aria-label="`${b.org_name}, ${b.org_url.replace('https://', '')}`"
  >
    <img v-if="b.logo_url" :src="b.logo_url" alt="" class="party-logo" />
    <span class="wordmark">{{ b.wordmark }}</span>
  </a>
  <div v-else class="brand-mark">
    <a
      :href="href"
      :target="house ? undefined : '_blank'"
      :rel="house ? undefined : 'noopener'"
      class="party-logo-link"
      :aria-label="`${b.org_name}, ${b.org_url.replace('https://', '')}`"
    >
      <!-- A brand without a logo file (the house brand, worn by pages
           no organisation owns) renders its wordmark alone rather than
           a broken image. -->
      <img v-if="b.logo_url" :src="b.logo_url" alt="" class="party-logo" />
    </a>
    <!-- The admin header passes a router-link here so the wordmark
         navigates home; routing stays in the admin bundle, which is the
         only one that has a router. -->
    <slot name="wordmark"><span class="wordmark">{{ b.app_name }}</span></slot>
  </div>
</template>

<style scoped>
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
