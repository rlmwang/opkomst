<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const toasts = useToasts();

const email = ref("");
const password = ref("");
const submitting = ref(false);

// An already-authenticated visitor on /login is just bouncing off
// the auth flow — send them straight to the events page. The same
// /dashboard target is the default post-submit redirect, so login
// always resolves to the events list regardless of how the user
// got here.
onMounted(() => {
  if (auth.isAuthenticated) void router.replace("/dashboard");
});

async function submit() {
  const trimmedEmail = email.value.trim();
  if (!trimmedEmail) {
    toasts.warn(t("auth.fillEmail"));
    return;
  }
  if (!isValidEmail(trimmedEmail)) {
    toasts.warn(t("common.invalidEmail"));
    return;
  }
  if (!password.value) {
    toasts.warn(t("auth.fillPassword"));
    return;
  }
  submitting.value = true;
  try {
    await auth.login(trimmedEmail, password.value);
    const next = (route.query.next as string) || "/dashboard";
    void router.push(next);
  } catch (e) {
    // Login failures all collapse to the same generic message — we
    // never reveal "no such email" vs "wrong password" anyway.
    const msg = e instanceof ApiError && e.status === 401 ? t("auth.loginFailed") : t("auth.loginFailed");
    toasts.error(msg);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard>
      <h1>{{ t("auth.login") }}</h1>
      <form class="stack" novalidate @submit.prevent="submit">
        <InputText v-model="email" type="email" :placeholder="t('auth.email')" autocomplete="email" fluid />
        <Password v-model="password" :placeholder="t('auth.password')" :feedback="false" toggle-mask autocomplete="current-password" fluid />
        <Button type="submit" :label="t('auth.login')" :loading="submitting" />
      </form>
      <p class="muted">
        {{ t("auth.noAccount") }}
        <router-link to="/register">{{ t("auth.registerHere") }}</router-link>
        — {{ t("auth.loginHint") }}
      </p>
    </AppCard>
  </div>
</template>
