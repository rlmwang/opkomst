<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const error = ref<string | null>(null);

onMounted(async () => {
  const token = (route.query.token as string | undefined) ?? "";
  if (!token) {
    error.value = t("auth.linkExpired");
    return;
  }
  try {
    await auth.redeem(token);
    void router.replace("/events");
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 410
        ? t("auth.linkExpired")
        : t("auth.loginFailed");
  }
});
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard v-if="error">
      <h1>{{ t("auth.linkExpiredTitle") }}</h1>
      <p class="muted">{{ error }}</p>
      <p>
        <router-link to="/login">{{ t("auth.requestNewLink") }}</router-link>
      </p>
    </AppCard>
    <AppCard v-else>
      <p class="muted">{{ t("auth.signingIn") }}</p>
    </AppCard>
  </div>
</template>
