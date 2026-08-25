<script setup lang="ts">
import BrandMark from "@/public_shared/BrandMark.vue";
import LanguageSwitcher from "@/components/LanguageSwitcher.vue";

/** The public header for pages that carry no page-specific identity
 * (the feedback form). Pages that do — an organisation's front page, a
 * chapter's agenda — use ``PublicIdentity`` in the same
 * ``.public-header`` row instead. */
</script>

<template>
  <header class="public-header">
    <BrandMark public-link />
    <LanguageSwitcher />
  </header>
</template>
