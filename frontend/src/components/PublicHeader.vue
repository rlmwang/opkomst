<script setup lang="ts">
import BrandMark from "@/components/BrandMark.vue";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";
</script>

<template>
  <header class="public-header">
    <BrandMark public-link />
    <LanguageSwitcher />
  </header>
</template>

<style scoped>
.public-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 0;
}
</style>
