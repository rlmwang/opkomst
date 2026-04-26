<script setup lang="ts">
import logoUrl from "@/assets/rsp-logo.png";

defineProps<{
  /** Optional inner-app target for the wordmark (e.g. "/" for the
   * dashboard header). When omitted, the wordmark renders as plain
   * text — used on the public event page. */
  to?: string;
}>();
</script>

<template>
  <div class="brand-mark">
    <a
      href="https://rsp.nu"
      target="_blank"
      rel="noopener"
      class="party-logo-link"
      aria-label="Revolutionair Socialistische Partij — rsp.nu"
      title="Revolutionair Socialistische Partij — rsp.nu"
    >
      <img :src="logoUrl" alt="" class="party-logo" />
    </a>
    <router-link v-if="to" :to="to" class="wordmark">opkomst</router-link>
    <span v-else class="wordmark">opkomst</span>
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
  height: 32px;
  width: 32px;
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
</style>
