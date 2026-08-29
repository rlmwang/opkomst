<script lang="ts">
import BrandMark from "@/public_shared/BrandMark.svelte";
import LanguageSwitcher from "@/components/LanguageSwitcher.svelte";

/** The public header for pages that carry no page-specific identity
 * (the feedback form). Pages that do, an organisation's front page or a
 * chapter's agenda, use ``PublicIdentity`` in the same
 * ``.public-header`` row instead. */
</script>

<header class="public-header">
  <BrandMark publicLink />
  <LanguageSwitcher />
</header>
