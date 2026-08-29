<script lang="ts">
import ChapterGrid from "@/components/ChapterGrid.svelte";
import LanguageSwitcher from "@/components/LanguageSwitcher.svelte";
import OrganiserDoor from "@/components/OrganiserDoor.svelte";
import PublicIdentity from "@/public_shared/PublicIdentity.svelte";
import { t } from "@/i18n.svelte";
import { brand } from "@/lib/branding";

/**
 * The organisation's public front page, at ``/{tenant}``.
 *
 * Its chapters, each linking to that chapter's agenda, which is where
 * "which Utrecht?" gets answered and what makes the agenda URLs
 * findable instead of passed around by hand. Shown to a visitor who is
 * not signed in; an organiser sees ``HomePage`` at the same path.
 */
interface ChapterEntry {
  name: string;
  slug: string;
  city: string | null;
}

const b = brand();
let chapters = $state<ChapterEntry[] | null>(null);
let failed = $state(false);

$effect(() => {
  void (async () => {
    try {
      const response = await fetch(`/api/v1/tenants/${encodeURIComponent(b.slug)}/chapters`);
      if (!response.ok) throw new Error(String(response.status));
      chapters = await response.json();
    } catch {
      failed = true;
    }
  })();
});
</script>

<!-- The same column as a chapter's agenda: the two public pages of an
     organisation are one surface, and a narrower front page reads as a
     different site. The header sits inside it, so the logo and the
     language toggle line up with the tiles under them. -->
<main class="container-wide stack">
  <header class="public-header">
    <PublicIdentity title={b.wordmark} />
    <LanguageSwitcher />
  </header>
  <p class="muted">{t("tenantIndex.lede")}</p>

  {#if failed}
    <p class="muted">{t("tenantIndex.failed")}</p>
  {:else if chapters !== null && chapters.length === 0}
    <p class="muted">{t("tenantIndex.none")}</p>
  {/if}

  {#if chapters && chapters.length > 0}
    <ChapterGrid {chapters} tenantSlug={b.slug} />
  {/if}

  <!-- Tiles first, because browsing is what most visitors came for,
       and the door under them for the few who came to organise
       (docs/design-personal-tenants.md). -->
  <OrganiserDoor />
</main>
