<script setup lang="ts">
import logoUrl from "@/assets/rsp-logo.png";

// Public-bundle copy of ``components/BrandMark.vue``, public-link
// shape only: this mini-app is rendered on every public event
// page and never has internal navigation, so we always wrap the
// whole brand-mark in a single external link to rsp.nu and
// read the wordmark as "RSP" — public visitors associate with
// the party, not the tooling.
</script>

<template>
  <a
    href="https://rsp.nu"
    target="_blank"
    rel="noopener"
    class="brand-mark"
    aria-label="Revolutionair Socialistische Partij — rsp.nu"
  >
    <img :src="logoUrl" alt="" class="party-logo" />
    <span class="wordmark">RSP</span>
  </a>
</template>

<style scoped>
.brand-mark {
  display: inline-flex;
  align-items: center;
  gap: 0.625rem;
  text-decoration: none;
  color: inherit;
}
.brand-mark:hover .wordmark {
  text-decoration: underline;
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
}
</style>
