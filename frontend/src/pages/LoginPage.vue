<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const toasts = useToasts();

const email = ref("");
const submitting = ref(false);
const sent = ref(false);

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
  submitting.value = true;
  try {
    await auth.requestLoginLink(trimmedEmail);
    sent.value = true;
  } catch {
    // Network or server error — backend never throws on unknown
    // email (200 is the privacy-preserving response), so any error
    // here is a genuine outage.
    toasts.error(t("auth.loginFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard v-if="sent">
      <h1>{{ t("auth.linkSentTitle") }}</h1>
      <p class="muted">{{ t("auth.linkSentBody", { email }) }}</p>
    </AppCard>

    <AppCard v-else>
      <h1>{{ t("auth.login") }}</h1>
      <p class="muted">{{ t("auth.linkIntro") }}</p>
      <form class="stack" novalidate @submit.prevent="submit">
        <InputText v-model="email" type="email" :placeholder="t('auth.email')" autocomplete="email" fluid />
        <Button type="submit" :label="t('auth.sendLink')" :loading="submitting" />
      </form>
      <p class="muted">
        {{ t("auth.noAccount") }}
        <router-link to="/register">{{ t("auth.registerHere") }}</router-link>
      </p>
    </AppCard>
  </div>
</template>
