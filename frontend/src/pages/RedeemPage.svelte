<script lang="ts">
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { t } from "@/i18n.svelte";
import { ApiError } from "@/api/client";
import { redeem } from "@/stores/auth.svelte";
import { go, route } from "@/router/navigation.svelte";

let error = $state<string | null>(null);

async function signIn() {
  const token = route.query.get("token") ?? "";
  if (!token) {
    error = t("auth.linkExpired");
    return;
  }
  try {
    await redeem(token);
    void go("/", { replace: true });
  } catch (e) {
    error =
      e instanceof ApiError && e.status === 410 ? t("auth.linkExpired") : t("auth.loginFailed");
  }
}
void signIn();
</script>

<AppHeader />
<div class="container-wide">
  {#if error}
    <AppCard>
      <h1>{t("auth.linkExpiredTitle")}</h1>
      <p class="muted">{error}</p>
      <p><RouterLink to="/">{t("auth.requestNewLink")}</RouterLink></p>
    </AppCard>
  {:else}
    <AppCard>
      <p class="muted">{t("auth.signingIn")}</p>
    </AppCard>
  {/if}
</div>
