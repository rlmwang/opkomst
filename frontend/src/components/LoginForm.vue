<script setup lang="ts">
import AppButton from "@/components/AppButton.vue";
import AppInput from "@/components/AppInput.vue";
import { ref } from "vue";
import { useI18n } from "@/i18n";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { useAuthStore } from "@/stores/auth";

/**
 * The magic-link door: an address, a button, and the "check your inbox"
 * state that replaces them.
 *
 * One component because it appears on both landing pages: under the
 * chapter grid on an organisation's public front page, and under the
 * tiles at the root. Signing in is the thing an organiser does there;
 * browsing is what everyone else does. The two must not drift.
 */

// Lets the host swap its own heading and intro for the sent state.
const emit = defineEmits<{ sent: [] }>();

const { t } = useI18n();
const auth = useAuthStore();
const toasts = useToasts();

const email = ref("");
const submitting = ref(false);
const sent = ref(false);

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
    emit("sent");
  } catch {
    // Network or server error — the backend never throws on an unknown
    // email (200 is the privacy-preserving response), so any error here
    // is a genuine outage.
    toasts.error(t("auth.loginFailed"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <p v-if="sent" class="muted">{{ t("auth.linkSentBody", { email }) }}</p>
  <!-- Magic-link forms don't get a "save login" doorhanger from any
       browser: there's no password to store and no webauthn ceremony to
       bind to. The only autofill path that actually engages is
       Firefox's form-history (the double-click dropdown of
       previously-typed values), which keys on ``name`` + a recognised
       ``autocomplete`` field-name. ``"email"`` is the right token for
       that; we deliberately don't claim ``"username webauthn"``, since
       neither side of that pair is doing any work. -->
  <form v-else class="login-form" method="post" action="" novalidate @submit.prevent="submit">
    <AppInput
      v-model="email"
      type="email"
      name="email"
      :placeholder="t('auth.email')"
      autocomplete="email"
      fluid
    />
    <AppButton type="submit" :label="t('auth.sendLink')" :loading="submitting" />
  </form>
</template>

<style scoped>
/* The address takes the room it needs and the button takes what it
 * needs; on a phone they stack. */
.login-form {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.login-form :deep(.app-input) {
  flex: 1 1 auto;
}
/* The label is two words; let it keep its line rather than wrapping
 * into a two-line button next to a one-line field. */
.login-form :deep(.app-btn) {
  flex: 0 0 auto;
  white-space: nowrap;
}
@media (max-width: 480px) {
  .login-form {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
