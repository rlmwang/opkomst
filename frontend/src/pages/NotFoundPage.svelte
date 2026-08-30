<script lang="ts">
import AppCard from "@/components/AppCard.svelte";
import AppHeader from "@/components/AppHeader.svelte";
import RouterLink from "@/router/RouterLink.svelte";
import { t } from "@/i18n.svelte";
</script>

<AppHeader />
<div class="container-wide">
  <AppCard stack={false}>
    <h1>{t("notFound.title")}</h1>
    <p>{t("notFound.body")}</p>
    <RouterLink to="/">{t("notFound.back")}</RouterLink>
  </AppCard>
</div>
