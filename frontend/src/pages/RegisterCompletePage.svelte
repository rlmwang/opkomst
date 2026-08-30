<script lang="ts">
import AppButton from "@/components/AppButton.svelte";
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import AppInput from "@/components/AppInput.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { useToasts } from "@/lib/toasts";
import { completeRegistration } from "@/stores/auth.svelte";
import { go, route } from "@/router/navigation.svelte";

const toasts = useToasts();

const token = route.query.get("token") ?? "";
let name = $state("");
let submitting = $state(false);
let linkInvalid = $state(!token);

async function submit() {
  const trimmed = name.trim();
  if (!trimmed) {
    toasts.warn(t("auth.fillName"));
    return;
  }
  submitting = true;
  try {
    await completeRegistration(token, trimmed);
    void go("/", { replace: true });
  } catch (e) {
    // 410 means the token was used or expired between the page load and
    // the submit: the same "link expired" card the redeem flow uses,
    // with a route back to the landing page.
    if (e instanceof ApiError && e.status === 410) linkInvalid = true;
    else toasts.error(t("auth.completeFailed"));
  } finally {
    submitting = false;
  }
}
</script>

<AppHeader />
<div class="container-wide">
  {#if linkInvalid}
    <AppCard>
      <h1>{t("auth.linkExpiredTitle")}</h1>
      <p class="muted">{t("auth.linkExpired")}</p>
      <p><RouterLink to="/">{t("auth.requestNewLink")}</RouterLink></p>
    </AppCard>
  {:else}
    <AppCard>
      <h1>{t("auth.completeTitle")}</h1>
      <p class="muted">{t("auth.completeBody")}</p>
      <form
        class="stack"
        method="post"
        action=""
        novalidate
        onsubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <AppInput
          bind:value={name}
          name="name"
          placeholder={t("auth.name")}
          autocomplete="name"
          autofocus
          fluid
        />
        <AppButton type="submit" label={t("auth.completeSubmit")} loading={submitting} />
      </form>
    </AppCard>
  {/if}
</div>
