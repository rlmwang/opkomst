<script setup lang="ts">
/**
 * The Buy Me a Coffee and Patreon buttons, wherever they are asked for.
 * Renders nothing at all unless the deployment has configured a URL for
 * them, and nothing on a page an organisation owns, because
 * ``brand().ads`` is null there and it is their page to ask on, not
 * ours.
 *
 * The artwork is each service's own button, committed to
 * ``brands/opkomst/`` and served from this app rather than from their
 * CDNs, wrapped in an ordinary link. No embed widget, no third-party
 * request, no CSP hole.
 */
import { computed } from "vue";
import { supportLinks } from "./support";

const links = computed(() => supportLinks());
</script>

<template>
  <div v-if="links.length > 0" class="support-buttons">
    <a
      v-for="s in links"
      :key="s.url"
      :href="s.url"
      target="_blank"
      rel="noopener"
      class="support-button"
    >
      <img :src="s.button" :alt="s.label" />
    </a>
  </div>
</template>

<style scoped>
.support-buttons {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
/* Each service's own button, at its own aspect ratio, scaled to fit and
 * never cropped or recoloured, which is what both brand guidelines ask
 * for. Sized well under the primary action opposite it: this is an
 * aside, and the confirm button is the thing to press. */
.support-button {
  display: block;
  line-height: 0;
  opacity: 0.75;
  transition: opacity 120ms ease;
}
.support-button img {
  display: block;
  width: auto;
  height: 26px;
}
.support-button:hover {
  opacity: 1;
}
</style>
