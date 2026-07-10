<script setup lang="ts">
/** The respondent's magic edit link, shown once on the confirmation
 *  screen. The token lives only in this URL — there's no server-side
 *  way to recover it — so the copy is explicit that it can't be
 *  re-sent. One component for all mini-apps.
 *
 *  It renders as a fragment (no wrapper element), not a card: its three
 *  lines drop straight into the single ``PublicConfirmation`` card as
 *  direct children, so they share that card's one column ``gap`` and the
 *  vertical rhythm stays even. The copy button uses the same PrimeIcons
 *  glyphs as the organiser cards (inlined — public bundles ship no icon
 *  font) so the copy affordance is identical across the app. */
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
      <svg v-if="copied" viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path d="M9,18.25A.74.74,0,0,1,8.47,18l-5-5A.75.75,0,1,1,4.53,12L9,16.44,19.47,6A.75.75,0,0,1,20.53,7l-11,11A.74.74,0,0,1,9,18.25Z" /></svg>
      <svg v-else viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path d="M19.53,8,14,2.47a.75.75,0,0,0-.53-.22H11A2.75,2.75,0,0,0,8.25,5V6.25H7A2.75,2.75,0,0,0,4.25,9V19A2.75,2.75,0,0,0,7,21.75h7A2.75,2.75,0,0,0,16.75,19V17.75H17A2.75,2.75,0,0,0,19.75,15V8.5A.75.75,0,0,0,19.53,8ZM14.25,4.81l2.94,2.94H14.25Zm1,14.19A1.25,1.25,0,0,1,14,20.25H7A1.25,1.25,0,0,1,5.75,19V9A1.25,1.25,0,0,1,7,7.75H8.25V15A2.75,2.75,0,0,0,11,17.75h4.25ZM17,16.25H11A1.25,1.25,0,0,1,9.75,15V5A1.25,1.25,0,0,1,11,3.75h1.75V8.5a.76.76,0,0,0,.75.75h4.75V15A1.25,1.25,0,0,1,17,16.25Z" /></svg>
    </button>
  </div>
  <p class="warning">{{ c.editWarning }}</p>
</template>

<style scoped>
/* All three lines match the confirmation body: one size, regular weight,
 * muted. The link's own colour (brand red) and its bordered field are the
 * only emphasis — no competing bold text. */
.prompt,
.warning {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.45;
  color: var(--brand-text-muted);
}
.link-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  padding: 0.25rem 0.25rem 0.25rem 0.625rem;
  background: var(--brand-bg);
  border: 1px solid var(--brand-border);
  border-radius: 8px;
}
.link {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.9375rem;
  color: var(--brand-red);
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}
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
.copy-btn:hover {
  background: var(--brand-surface);
  color: var(--brand-red);
}
.copy-btn.copied {
  color: var(--brand-green);
}
</style>
