<script setup lang="ts">
import Button from "primevue/button";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();

const status = ref<"verifying" | "ok" | "error">("verifying");
const message = ref<string>("");

onMounted(async () => {
  const token = (route.query.token as string | undefined) ?? "";
  if (!token) {
    status.value = "error";
    message.value = t("verify.invalid");
    return;
  }
  try {
    await auth.verifyEmail(token);
    status.value = "ok";
  } catch (e) {
    status.value = "error";
    message.value = e instanceof ApiError ? e.message : t("verify.failed");
  }
});

function goDashboard() {
  void router.push("/dashboard");
}

async function goLoginAndResend() {
  if (!auth.isAuthenticated) {
    void router.push("/login");
    return;
  }
  try {
    await auth.resendVerification();
    toasts.success(t("verify.resentOk"));
  } catch {
    toasts.error(t("verify.resentFail"));
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard>
      <template v-if="status === 'verifying'">
        <h1>{{ t("verify.verifying") }}</h1>
        <p class="muted">{{ t("verify.pleaseWait") }}</p>
      </template>

      <template v-else-if="status === 'ok'">
        <h1>{{ t("verify.success") }}</h1>
        <p>{{ t("verify.successBody") }}</p>
        <Button :label="t('verify.toDashboard')" @click="goDashboard" />
      </template>

      <template v-else>
        <h1>{{ t("verify.failed") }}</h1>
        <p class="muted">{{ message }}</p>
        <div class="actions">
          <Button v-if="auth.isAuthenticated" :label="t('verify.resend')" severity="secondary" @click="goLoginAndResend" />
          <router-link to="/login">
            <Button :label="t('auth.login')" severity="secondary" text />
          </router-link>
        </div>
      </template>
    </AppCard>
  </div>
</template>

<style scoped>
.actions {
  display: flex;
  gap: 0.5rem;
}
</style>
