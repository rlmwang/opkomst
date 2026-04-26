<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { useToast } from "primevue/usetoast";
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const router = useRouter();
const toast = useToast();

const email = ref("");
const name = ref("");
const password = ref("");
const submitting = ref(false);

async function submit() {
  submitting.value = true;
  try {
    await auth.register(email.value, password.value, name.value);
    void router.push("/dashboard");
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : t("auth.registerFailed");
    toast.add({ severity: "error", summary: msg, life: 3000 });
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <div class="card stack">
      <h1>{{ t("auth.register") }}</h1>
      <p class="muted">{{ t("auth.registerHint") }}</p>
      <form class="stack" @submit.prevent="submit">
        <InputText v-model="name" :placeholder="t('auth.name')" required fluid />
        <InputText v-model="email" type="email" :placeholder="t('auth.email')" required autocomplete="email" fluid />
        <Password v-model="password" :placeholder="t('auth.passwordHint')" toggle-mask required autocomplete="new-password" fluid />
        <Button type="submit" :label="t('auth.createAccount')" :loading="submitting" />
      </form>
      <p class="muted">
        {{ t("auth.hasAccount") }} <router-link to="/login">{{ t("auth.login") }}</router-link>
      </p>
    </div>
  </div>
</template>
