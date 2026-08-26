<script setup lang="ts">
import { brand } from "@/lib/branding";

/**
 * Whose page this is, in the header: the organisation's logo, a small
 * eyebrow over the page's own name, and an optional line under it.
 *
 * One component so an organisation's front page and one of its chapters'
 * agendas wear the same header — logo left, identity beside it, the
 * deepest level as the ``h1``:
 *
 *     [logo] RSP          [logo] RSP
 *            (front page)        Utrecht
 *                                       (chapter agenda)
 */

defineProps<{
  /** Small line above the title. Omitted when the title *is* the
   * organisation. */
  eyebrow?: string;
  title: string;
  /** Optional line under the title — the house brand's tagline on the
   * personal front page. A chapter agenda names the chapter and stops
   * there. */
  subtitle?: string | null;
}>();

const b = brand();
</script>

<template>
  <div class="identity">
    <a
      v-if="b.logo_url"
      class="identity__logo"
      :href="b.org_url"
      target="_blank"
      rel="noopener"
      :aria-label="`${b.org_name}, ${b.org_url.replace('https://', '')}`"
    ><img :src="b.logo_url" alt="" /></a>
    <div class="identity__text">
      <span v-if="eyebrow" class="identity__eyebrow">{{ eyebrow }}</span>
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="muted identity__subtitle">{{ subtitle }}</p>
    </div>
  </div>
</template>

<style scoped>
.identity {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-width: 0;
}
.identity__logo {
  display: block;
  flex: none;
}
.identity__logo img {
  height: 60px;
  width: 60px;
  object-fit: contain;
  display: block;
}
.identity__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.identity__eyebrow {
  font-weight: 700;
  font-size: 0.8125rem;
  letter-spacing: 0.5px;
  line-height: 1.2;
  color: var(--brand-red);
}
.identity__text h1 {
  margin: 0.0625rem 0 0;
  font-size: 1.5rem;
  line-height: 1.15;
}
.identity__subtitle {
  margin: 0.125rem 0 0;
  font-size: 0.9375rem;
}
</style>
