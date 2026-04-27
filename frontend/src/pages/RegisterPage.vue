<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const toasts = useToasts();

const email = ref("");
const name = ref("");
const password = ref("");
const submitting = ref(false);

async function submit() {
  const trimmedEmail = email.value.trim();
  const trimmedName = name.value.trim();
  if (!trimmedName) {
    toasts.warn(t("auth.fillName"));
    return;
  }
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
    await auth.register(trimmedEmail, password.value, trimmedName);
    void router.push("/dashboard");
  } catch (e) {
    // 409 is the only message worth surfacing specifically (email
    // taken); everything else collapses to a localised generic.
    const msg =
      e instanceof ApiError && e.status === 409
        ? t("auth.emailTaken")
        : t("auth.registerFailed");
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
      <h1>{{ t("auth.register") }}</h1>
      <p class="muted">{{ t("auth.registerHint") }}</p>
      <form class="stack" novalidate @submit.prevent="submit">
        <InputText v-model="name" :placeholder="t('auth.name')" fluid />
        <InputText v-model="email" type="email" :placeholder="t('auth.email')" autocomplete="email" fluid />
        <Password v-model="password" :placeholder="t('auth.passwordHint')" toggle-mask autocomplete="new-password" fluid />
        <Button type="submit" :label="t('auth.createAccount')" :loading="submitting" />
      </form>
      <p class="muted">
        {{ t("auth.hasAccount") }} <router-link to="/login">{{ t("auth.login") }}</router-link>
      </p>
    </AppCard>
  </div>
</template>
