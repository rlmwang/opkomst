<script setup lang="ts">
/** The respondent's magic edit link, shown once on the confirmation
 *  screen. The token lives only in this URL — there's no server-side
 *  way to recover it — so the copy is explicit that it can't be
 *  re-sent. One component for all three mini-apps.
 *
 *  Link + copy button mirror the organiser detail cards (a truncated
 *  link followed by a subtle icon-only copy button) so the styling is
 *  consistent across the app. The public bundles don't ship PrimeVue
 *  /primeicons, so the icons are inline SVGs. */
import { computed, ref } from "vue";
import { type Locale, chromeStrings } from "./strings";

const props = defineProps<{ url: string; locale: Locale }>();
const c = computed(() => chromeStrings(props.locale));

const copied = ref(false);

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.url);
  } catch {
    // Clipboard API unavailable (insecure context / older browser):
    // the link is still selectable on screen, so this is non-fatal.
    return;
  }
  copied.value = true;
  window.setTimeout(() => (copied.value = false), 2000);
}
</script>

<template>
  <div class="card stack edit-link">
    <p class="prompt">{{ c.editPrompt }}</p>
    <div class="link-row">
      <a class="link" :href="url" target="_blank" rel="noopener">{{ url }}</a>
      <button
        type="button"
        class="copy-btn"
        :class="{ copied }"
        :aria-label="copied ? c.copied : c.copy"
        :title="copied ? c.copied : c.copy"
        @click="copy"
      >
        <svg v-if="copied" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12" /></svg>
        <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
      </button>
    </div>
    <p class="warning">{{ c.editWarning }}</p>
  </div>
</template>

<style scoped>
.edit-link { gap: 0.625rem; }
.prompt { margin: 0; font-weight: 600; }
/* Mirrors the organiser detail card: truncated link + subtle icon
 * copy button. */
.link-row { display: flex; align-items: center; gap: 0.375rem; min-width: 0; }
.link {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--brand-red);
  text-decoration: none;
}
.link:hover { text-decoration: underline; }
.copy-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  background: none;
  color: var(--brand-text-muted);
  border-radius: 6px;
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.copy-btn:hover { background: var(--brand-bg); color: var(--brand-red); }
.copy-btn.copied { color: #1f7a3c; }
.warning { margin: 0; font-size: 0.8125rem; color: var(--brand-text-muted); }
</style>
