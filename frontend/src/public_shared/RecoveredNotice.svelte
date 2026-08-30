<script lang="ts">
/**
 * The permanent transparency banner on a public edit page: shown
 * whenever an organiser has recovered (re-minted) this submission's
 * secret link (``link_recovered_at`` non-null — never cleared). Shared
 * by all four mini-apps.
 */
import { chromeStrings, type Locale } from "./strings";

const {
  recoveredAt,
  locale,
}: { recoveredAt: string | null | undefined; locale: Locale } = $props();

const text = $derived.by(() => {
  if (!recoveredAt) return null;
  const date = new Date(recoveredAt).toLocaleDateString(locale === "en" ? "en-GB" : "nl-NL", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return chromeStrings(locale).linkRecovered.replace("{date}", date);
});
</script>

{#if text}
  <div class="recovered-notice" role="note">
    <span class="recovered-icon" aria-hidden="true">🔑</span>
    <span>{text}</span>
  </div>
{/if}

<style>
.recovered-notice {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--brand-recovered-border);
  border-radius: 8px;
  background: var(--brand-recovered-bg);
  color: var(--brand-recovered-text);
  font-size: 0.875rem;
  line-height: 1.45;
}
.recovered-icon {
  flex-shrink: 0;
}
</style>
