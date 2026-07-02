import { computed, ref } from "vue";

/**
 * Dirty / revert / just-saved state for a public edit page, shared by all
 * four mini-apps so their edit-mode action bars behave identically.
 *
 * Given a ``snapshot`` that serialises the page's editable form and an
 * ``apply`` that restores it:
 * - ``captureBaseline()`` records the current form as the saved baseline —
 *   call it right after the server prefill and after every successful save.
 * - ``dirty`` is true when the form differs from that baseline.
 * - ``revert()`` restores the form to the baseline (stay on the page).
 * - ``flashSaved()`` lights ``justSaved`` for a moment (the "Opgeslagen"
 *   state) so the bar can disable Save right after a save.
 *
 * ``snapshot`` must read the reactive form refs so ``dirty`` re-evaluates
 * as the user types; it should return a JSON-serialisable value.
 */
export function useEditForm<T>(opts: { snapshot: () => T; apply: (snap: T) => void }) {
  const baseline = ref<string>("");
  const justSaved = ref(false);

  const dirty = computed(() => baseline.value !== JSON.stringify(opts.snapshot()));

  function captureBaseline(): void {
    baseline.value = JSON.stringify(opts.snapshot());
  }

  function revert(): void {
    if (!baseline.value) return;
    opts.apply(JSON.parse(baseline.value) as T);
  }

  function flashSaved(): void {
    justSaved.value = true;
    window.setTimeout(() => (justSaved.value = false), 2000);
  }

  return { dirty, justSaved, captureBaseline, revert, flashSaved };
}
