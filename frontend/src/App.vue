<script setup lang="ts">
import ConfirmDialog from "primevue/confirmdialog";
import Toast from "primevue/toast";

// Auth bootstrapping lives in the router guard — it's the one
// place that knows which routes need auth state. App.vue used to
// also call ``auth.fetchMe()`` on mount, which raced with the
// guard's call on every initial load and produced the
// ``GET /api/v1/auth/me`` doubling visible in prod logs (and an
// extra needless request on public routes that don't need auth
// state at all).
</script>

<template>
  <Toast position="top-center" />
  <!-- Match AppDialog's default width so confirmation dialogs and
       form dialogs sit at exactly the same size, regardless of how
       long the message text happens to be. -->
  <ConfirmDialog :style="{ width: '420px' }" />

  <router-view />
</template>
