<script setup lang="ts">
/** Renders whatever ``useConfirms().ask`` last asked (``lib/confirms``).
 *  Mounted once in ``App.vue``, the way PrimeVue's ConfirmDialog was. */
import { computed } from "vue";

import AppButton from "@/components/AppButton.vue";
import AppDialog from "@/components/AppDialog.vue";
import { useConfirmRequest } from "@/lib/confirms";

const { state, accept, reject } = useConfirmRequest();
const open = computed({
  get: () => state.request !== null,
  // The dialog closes itself on Escape and on the close button; either
  // is a decision not to go ahead.
  set: (v: boolean) => {
    if (!v) reject();
  },
});
</script>

<template>
  <AppDialog v-if="state.request" v-model:visible="open" :header="state.request.header">
    <p class="confirm-message">
      <i v-if="state.request.icon" :class="state.request.icon" aria-hidden="true"></i>
      <span>{{ state.request.message }}</span>
    </p>
    <template #footer>
      <AppButton :label="state.request.rejectLabel" severity="secondary" text @click="reject" />
      <AppButton :label="state.request.acceptLabel" @click="accept" />
    </template>
  </AppDialog>
</template>

<style scoped>
.confirm-message {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0;
}
</style>
