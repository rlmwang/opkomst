<script setup lang="ts">
import { computed } from "vue";
import { type Locale, GITHUB_URL, chromeStrings } from "./strings";

/** The open-source / privacy disclosure card, shared by the public
 *  mini-apps. Collapsible ``<details>`` with the GitHub link — the
 *  project invariant that every public page discloses the source. */
const props = defineProps<{ locale: Locale }>();
const c = computed(() => chromeStrings(props.locale));
</script>

<template>
  <div class="card">
    <details>
      <summary>{{ c.explainerTitle }}</summary>
      <p class="body">
        {{ c.explainerBody }}
        <a :href="GITHUB_URL" target="_blank" rel="noopener">{{ c.explainerLink }}</a>
      </p>
    </details>
  </div>
</template>

<style scoped>
summary { cursor: pointer; font-weight: 600; }
.body { margin: 0.5rem 0 0; color: var(--brand-text-muted); }
</style>
