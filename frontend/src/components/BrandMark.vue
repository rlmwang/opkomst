<script setup lang="ts">
import logoUrl from "@/assets/rsp-logo.png";
import { APP_NAME } from "@/lib/branding";

defineProps<{
  /** Optional inner-app target for the wordmark (e.g. "/" for the
   * dashboard header). When omitted, the wordmark renders as plain
   * text — used on the admin pages where the brand is contextual,
   * not navigational. */
  to?: string;
  /** Public-facing mode (event signup, feedback form). Both logo
   * and wordmark wrap a single external link to rsp.nu, and the
   * wordmark reads "RSP" rather than the app domain — public
   * visitors associate with the party, not the tooling. */
  publicLink?: boolean;
}>();
</script>

<template>
  <a
    v-if="publicLink"
    href="https://rsp.nu"
    target="_blank"
    rel="noopener"
    class="brand-mark public-link"
    aria-label="Revolutionair Socialistische Partij — rsp.nu"
  >
    <img :src="logoUrl" alt="" class="party-logo" />
    <span class="wordmark">RSP</span>
  </a>
  <div v-else class="brand-mark">
    <a
      href="https://rsp.nu"
      target="_blank"
      rel="noopener"
      class="party-logo-link"
      aria-label="Revolutionair Socialistische Partij — rsp.nu"
    >
      <img :src="logoUrl" alt="" class="party-logo" />
    </a>
    <router-link v-if="to" :to="to" class="wordmark">{{ APP_NAME }}</router-link>
    <span v-else class="wordmark">{{ APP_NAME }}</span>
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
