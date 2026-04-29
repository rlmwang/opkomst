<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();

const email = ref("");
const name = ref("");
const submitting = ref(false);
const sent = ref(false);

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
  submitting.value = true;
  try {
    await auth.register(trimmedEmail, trimmedName);
    sent.value = true;
  } catch {
    toasts.error(t("auth.registerFailed"));
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
      <h1>{{ t("auth.register") }}</h1>
      <p class="muted">{{ t("auth.registerHint") }}</p>
      <!-- See LoginPage for the explanation of the
           ``method="post"`` + ``name`` + ``autocomplete=
           "username email"`` combination — same Firefox/Chrome
           autofill story applies to register. -->
      <form class="stack" method="post" action="" novalidate @submit.prevent="submit">
        <InputText
          v-model="name"
          name="name"
          :placeholder="t('auth.name')"
          autocomplete="name"
          fluid
        />
        <InputText
          v-model="email"
          type="email"
          name="email"
          :placeholder="t('auth.email')"
          autocomplete="username email"
          fluid
        />
        <Button type="submit" :label="t('auth.sendLink')" :loading="submitting" />
      </form>
      <p class="muted">
        {{ t("auth.hasAccount") }} <router-link to="/login">{{ t("auth.login") }}</router-link>
      </p>
    </AppCard>
  </div>
</template>
