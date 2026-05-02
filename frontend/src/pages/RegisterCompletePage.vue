<script setup lang="ts">
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { ApiError } from "@/api/client";
import AppCard from "@/components/AppCard.vue";
import AppHeader from "@/components/AppHeader.vue";
import { useToasts } from "@/lib/toasts";
import { useAuthStore } from "@/stores/auth";

const { t } = useI18n();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const toasts = useToasts();

const token = ref("");
const name = ref("");
const submitting = ref(false);
const linkInvalid = ref(false);

onMounted(() => {
  const raw = (route.query.token as string | undefined) ?? "";
  if (!raw) {
    linkInvalid.value = true;
    return;
  }
  token.value = raw;
});

async function submit() {
  const trimmed = name.value.trim();
  if (!trimmed) {
    toasts.warn(t("auth.fillName"));
    return;
  }
  submitting.value = true;
  try {
    await auth.completeRegistration(token.value, trimmed);
    void router.replace("/events");
  } catch (e) {
    // 410 means the token was already used or expired between
    // page-load and submit — surface the same "link expired" card
    // the redeem flow uses, with a route back to /login.
    if (e instanceof ApiError && e.status === 410) {
      linkInvalid.value = true;
    } else {
      toasts.error(t("auth.completeFailed"));
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <AppHeader />
  <div class="container">
    <AppCard v-if="linkInvalid">
      <h1>{{ t("auth.linkExpiredTitle") }}</h1>
      <p class="muted">{{ t("auth.linkExpired") }}</p>
      <p>
        <router-link to="/login">{{ t("auth.requestNewLink") }}</router-link>
      </p>
    </AppCard>

    <AppCard v-else>
      <h1>{{ t("auth.completeTitle") }}</h1>
      <p class="muted">{{ t("auth.completeBody") }}</p>
      <form class="stack" method="post" action="" novalidate @submit.prevent="submit">
        <InputText
          v-model="name"
          name="name"
          :placeholder="t('auth.name')"
          autocomplete="name"
          autofocus
          fluid
        />
        <Button type="submit" :label="t('auth.completeSubmit')" :loading="submitting" />
      </form>
    </AppCard>
  </div>
</template>
