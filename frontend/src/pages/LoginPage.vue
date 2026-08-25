<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import LoginForm from "@/components/LoginForm.vue";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const sent = ref(false);

onMounted(() => {
  if (auth.isAuthenticated) void router.replace("/");
});
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard>
      <template v-if="!sent">
        <h1>{{ t("auth.login") }}</h1>
        <p class="muted">{{ t("auth.linkIntro") }}</p>
      </template>
      <LoginForm :sent-title="t('auth.linkSentTitle')" @sent="sent = true" />
    </AppCard>
  </div>
</template>
