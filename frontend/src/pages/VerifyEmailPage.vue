<script setup lang="ts">
import Button from "primevue/button";
import { useToast } from "primevue/usetoast";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const auth = useAuthStore();
const toast = useToast();

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
    toast.add({ severity: "success", summary: t("verify.resentOk"), life: 3000 });
  } catch {
    toast.add({ severity: "error", summary: t("verify.resentFail"), life: 3000 });
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <div class="card stack">
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
    </div>
  </div>
</template>

<style scoped>
.actions {
  display: flex;
  gap: 0.5rem;
}
</style>
