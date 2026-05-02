<script setup lang="ts">
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";

const { t } = useI18n();
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard :stack="false">
      <h1>{{ t("notFound.title") }}</h1>
      <p>{{ t("notFound.body") }}</p>
      <router-link to="/">{{ t("notFound.back") }}</router-link>
    </AppCard>
  </div>
</template>
