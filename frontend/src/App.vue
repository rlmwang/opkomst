<script setup lang="ts">
import ConfirmDialog from "primevue/confirmdialog";
import Toast from "primevue/toast";
import { ref } from "vue";
import { useRouter } from "vue-router";
import AdSlot from "@/public_shared/AdSlot.vue";
import SiteFooter from "@/components/SiteFooter.vue";
import { useI18n } from "vue-i18n";

// Auth bootstrapping lives in the router guard — it's the one
// place that knows which routes need auth state. App.vue used to
// also call ``auth.fetchMe()`` on mount, which raced with the
// guard's call on every initial load and produced the
// ``GET /api/v1/auth/me`` doubling visible in prod logs (and an
// extra needless request on public routes that don't need auth
// state at all).

// First paint shows only the page background until the initial
// navigation settles: the guard awaits ``auth.fetchMe()`` (a /me
// round-trip, slow on a cold backend) and then the route's lazy
// chunk loads, during which ``<router-view>`` is empty. Show a
// loading indicator over that gap instead of a blank page. A short
// delay keeps fast loads from flashing the spinner.
const router = useRouter();
const { locale } = useI18n();
const ready = ref(false);
const showLoader = ref(false);
const timer = window.setTimeout(() => {
  if (!ready.value) showLoader.value = true;
}, 150);
router.isReady().finally(() => {
  ready.value = true;
  window.clearTimeout(timer);
});
</script>

<template>
  <Toast position="top-center" />
  <!-- Match AppDialog's default width so confirmation dialogs and
       form dialogs sit at exactly the same size, regardless of how
       long the message text happens to be. -->
  <ConfirmDialog :style="{ width: '420px' }" />

  <router-view />

  <!-- The colophon: the written pages, the policy and the source. Only
       on the house brand; an organisation's pages are theirs. -->
  <SiteFooter />

  <!-- Advertising, on the pages that carry any. ``AdSlot`` decides:
       an organisation's app gets nothing at all. -->
  <AdSlot :locale="(locale as 'nl' | 'en')" />

  <Transition name="app-loading-fade">
    <div v-if="!ready && showLoader" class="app-loading" role="status" aria-label="Laden…">
      <span class="app-loading-spinner" />
    </div>
  </Transition>
</template>

<style scoped>
.app-loading {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-bg);
  z-index: 9999;
}
.app-loading-spinner {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  border: 3px solid color-mix(in srgb, var(--brand-red) 25%, transparent);
  border-top-color: var(--brand-red);
  animation: app-loading-spin 0.8s linear infinite;
}
@keyframes app-loading-spin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .app-loading-spinner { animation: none; }
}
.app-loading-fade-leave-active { transition: opacity 200ms ease; }
.app-loading-fade-leave-to { opacity: 0; }
</style>
