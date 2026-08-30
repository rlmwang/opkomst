<script lang="ts">
import { locale, setLocale, type Locale } from "@/i18n.svelte";
import { tip } from "@/lib/tooltip";

// Switching fetches the other catalogue the first time, so this waits.
// The browser has it cached on every switch after that.
async function pick(l: Locale) {
  await setLocale(l);
}
</script>

<div class="lang-switcher">
  <button
    type="button"
    class="flag"
    class:active={locale() === "nl"}
    aria-label="Nederlands"
    use:tip={"Nederlands"}
    onclick={() => pick("nl")}
  >
    🇳🇱
  </button>
  <button
    type="button"
    class="flag"
    class:active={locale() === "en"}
    aria-label="English"
    use:tip={"English"}
    onclick={() => pick("en")}
  >
    🇬🇧
  </button>
</div>

<style>
.lang-switcher {
  display: flex;
  gap: 0.25rem;
  background: var(--brand-surface);
  border: 1px solid var(--brand-border);
  border-radius: 999px;
  padding: 0.25rem;
}
.flag {
  background: none;
  border: 2px solid transparent;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 999px;
  font-size: 1.1rem;
  line-height: 1;
  opacity: 0.4;
  filter: grayscale(0.6);
  transition: opacity 120ms ease, filter 120ms ease, border-color 120ms ease, background 120ms ease;
}
.flag:hover {
  opacity: 0.85;
  filter: grayscale(0.2);
}
.flag.active {
  opacity: 1;
  filter: none;
  background: var(--brand-bg);
  border-color: var(--brand-red);
  box-shadow: 0 0 0 1px var(--brand-red);
}
</style>
