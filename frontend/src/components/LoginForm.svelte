<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppInput from "@/components/AppInput.svelte";
import { t } from "@/i18n.svelte";
import { useToasts } from "@/lib/toasts";
import { isValidEmail } from "@/lib/validate";
import { requestLoginLink } from "@/stores/auth.svelte";

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
const { onsent }: { onsent?: () => void } = $props();

const toasts = useToasts();

let email = $state("");
let submitting = $state(false);
let sent = $state(false);

async function submit() {
  const trimmed = email.trim();
  if (!trimmed) {
    toasts.warn(t("auth.fillEmail"));
    return;
  }
  if (!isValidEmail(trimmed)) {
    toasts.warn(t("common.invalidEmail"));
    return;
  }
  submitting = true;
  try {
    await requestLoginLink(trimmed);
    sent = true;
    onsent?.();
  } catch {
    // Network or server error. The backend never throws on an unknown
    // email (200 is the privacy-preserving response), so anything here
    // is a genuine outage.
    toasts.error(t("auth.loginFailed"));
  } finally {
    submitting = false;
  }
}
</script>

{#if sent}
  <p class="muted">{t("auth.linkSentBody", { email })}</p>
{:else}
  <!-- Magic-link forms don't get a "save login" doorhanger from any
       browser: there is no password to store and no webauthn ceremony
       to bind to. The only autofill path that actually engages is
       Firefox's form history (the double-click dropdown of
       previously-typed values), which keys on ``name`` plus a
       recognised ``autocomplete`` field name. ``"email"`` is the right
       token for that; we deliberately don't claim
       ``"username webauthn"``, since neither side of that pair is doing
       any work. -->
  <form
    class="login-form"
    method="post"
    action=""
    novalidate
    onsubmit={(e) => {
      e.preventDefault();
      void submit();
    }}
  >
    <AppInput
      bind:value={email}
      type="email"
      name="email"
      placeholder={t("auth.email")}
      autocomplete="email"
      fluid
    />
    <AppButton type="submit" label={t("auth.sendLink")} loading={submitting} />
  </form>
{/if}

<style>
/* The address takes the room it needs and the button takes what it
 * needs; on a phone they stack. */
.login-form {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.login-form :global(.app-input) {
  flex: 1 1 auto;
}
/* The label is two words; let it keep its line rather than wrapping
 * into a two-line button next to a one-line field. */
.login-form :global(.app-btn) {
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
