<script setup lang="ts">
/** The respondent's magic edit link, shown once on the confirmation
 *  screen. The token lives only in this URL — there's no server-side
 *  way to recover it — so the copy is explicit that it can't be
 *  re-sent. One component for all three mini-apps. */
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
      <input class="link-field" type="text" :value="url" readonly @focus="(e) => (e.target as HTMLInputElement).select()" />
      <button type="button" class="btn-copy" @click="copy">
        {{ copied ? c.copied : c.copy }}
      </button>
    </div>
    <p class="warning">{{ c.editWarning }}</p>
  </div>
</template>

<style scoped>
.edit-link { gap: 0.625rem; }
.prompt { margin: 0; font-weight: 600; }
.link-row { display: flex; gap: 0.5rem; }
.link-field {
  flex: 1;
  min-width: 0;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-bg-subtle, var(--brand-surface));
  color: var(--brand-text);
  font-family: inherit;
  font-size: 0.9375rem;
}
.btn-copy {
  flex: none;
  border: 1px solid var(--brand-red);
  background: var(--brand-surface);
  color: var(--brand-red);
  font-weight: 600;
  font-size: 0.9375rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  cursor: pointer;
}
.btn-copy:hover { background: var(--brand-red); color: #fff; }
.warning { margin: 0; font-size: 0.8125rem; color: var(--brand-text-muted); }
</style>
