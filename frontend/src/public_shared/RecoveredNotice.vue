<script setup lang="ts">
/**
 * The permanent transparency banner on a public edit page: shown
 * whenever an organiser has recovered (re-minted) this submission's
 * secret link (``link_recovered_at`` non-null — never cleared). Shared
 * by all four mini-apps.
 */
import { computed } from "vue";
import { chromeStrings, type Locale } from "./strings";

const props = defineProps<{
  recoveredAt: string | null | undefined;
  locale: Locale;
}>();

const text = computed(() => {
  if (!props.recoveredAt) return null;
  const date = new Date(props.recoveredAt).toLocaleDateString(props.locale === "en" ? "en-GB" : "nl-NL", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return chromeStrings(props.locale).linkRecovered.replace("{date}", date);
});
</script>

<template>
  <div v-if="text" class="recovered-notice" role="note">
    <span class="recovered-icon" aria-hidden="true">🔑</span>
    <span>{{ text }}</span>
  </div>
</template>

<style scoped>
.recovered-notice {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid #e6c76a;
  border-radius: 8px;
  background: #fdf6e3;
  color: #6b5310;
  font-size: 0.875rem;
  line-height: 1.45;
}
.recovered-icon {
  flex-shrink: 0;
}
</style>
