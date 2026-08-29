<script setup lang="ts">
/**
 * Where the colophon appears inside the organiser app. The colophon
 * itself is `public_shared/Colophon.vue`, shared with the public
 * mini-apps; this decides on which of the app's pages it belongs.
 *
 * It appears only where somebody might still be deciding what this is:
 * the root and the create pages. An organiser halfway through their own
 * event has already decided, and a dashboard is not a place to
 * advertise reading material.
 */
import { computed } from "vue";
import { useI18n } from "@/i18n";
import { useRoute } from "vue-router";

import Colophon from "@/public_shared/Colophon.vue";
import type { Locale } from "@/public_shared/strings";

const { locale } = useI18n();
const route = useRoute();

// The landing page and every create page. ``startable`` is the route
// meta the create pages already carry (they are the ones a signed-out
// visitor can use), so a new product gets the footer by existing
// rather than by being added to a second list here.
const show = computed(() => route.path === "/" || route.meta.startable === true);
</script>

<template>
  <Colophon v-if="show" :locale="(locale as Locale)" column="container-wide" />
</template>
