<script setup lang="ts">
import { watch } from "vue";
import BrandMark from "@/public/BrandMark.vue";
import type { Locale } from "./strings";

/** Page chrome shared by all three public mini-apps: the 720px
 *  ``container.stack`` wrapper and the header (BrandMark + language
 *  switcher). The page's own content goes in the default slot. The
 *  language is a two-way model so the host keeps a single ``locale``
 *  ref; this component owns the flag toggle and keeps
 *  ``document.documentElement.lang`` in sync. */
const locale = defineModel<Locale>("locale", { required: true });

watch(locale, (l) => {
  document.documentElement.lang = l;
}, { immediate: true });
</script>

<template>
  <div class="container stack">
    <header class="public-header">
      <BrandMark />
      <div class="lang-switcher" role="group" aria-label="Language">
        <button
          type="button"
          class="flag"
          :class="{ active: locale === 'nl' }"
          aria-label="Nederlands"
          title="Nederlands"
          @click="locale = 'nl'"
        >🇳🇱</button>
        <button
          type="button"
          class="flag"
          :class="{ active: locale === 'en' }"
          aria-label="English"
          title="English"
          @click="locale = 'en'"
        >🇬🇧</button>
      </div>
    </header>

    <slot />
  </div>
</template>

<style scoped>
/* ``.container`` and ``.stack`` come from the global theme.css that
 * every mini-app imports in its ``main.ts``. */
.public-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.lang-switcher {
  display: flex;
  gap: 0.25rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  padding: 0.25rem;
}
.flag {
  background: none;
  border: 2px solid transparent;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 999px;
  font-size: 1.1rem;
  line-height: 1;
  opacity: 0.4;
  filter: grayscale(0.6);
  transition: opacity 120ms, filter 120ms, border-color 120ms, background 120ms;
}
.flag:hover { opacity: 0.85; filter: grayscale(0.2); }
.flag.active {
  opacity: 1;
  filter: none;
  background: var(--brand-bg);
  border-color: var(--brand-red);
  box-shadow: 0 0 0 1px var(--brand-red);
}
</style>
