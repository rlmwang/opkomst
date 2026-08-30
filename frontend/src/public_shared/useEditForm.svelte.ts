/**
 * Dirty / revert / just-saved state for a public edit page, shared by all
 * the mini-apps so their edit-mode action bars behave identically.
 *
 * Given a ``snapshot`` that serialises the page's editable form and an
 * ``apply`` that restores it:
 * - ``captureBaseline()`` records the current form as the saved
 *   baseline. Call it right after the server prefill and after every
 *   successful save.
 * - ``dirty`` is true when the form differs from that baseline.
 * - ``revert()`` restores the form to the baseline (stay on the page).
 * - ``flashSaved()`` lights ``justSaved`` for a moment (the "Opgeslagen"
 *   state) so the bar can disable Save right after a save.
 *
 * ``snapshot`` must read the page's own ``$state`` so ``dirty``
 * re-evaluates as the user types; it should return a JSON-serialisable
 * value.
 */
export function useEditForm<T>(opts: { snapshot: () => T; apply: (snap: T) => void }) {
  let baseline = $state<string>("");
  let saved = $state(false);

  const dirty = $derived(baseline !== JSON.stringify(opts.snapshot()));

  function captureBaseline(): void {
    baseline = JSON.stringify(opts.snapshot());
  }

  function revert(): void {
    if (!baseline) return;
    opts.apply(JSON.parse(baseline) as T);
  }

  function flashSaved(): void {
    saved = true;
    window.setTimeout(() => (saved = false), 2000);
  }

  // Getters, because a plain property would hand the caller the value
  // this ran with rather than the one it has.
  return {
    get dirty() {
      return dirty;
    },
    get justSaved() {
      return saved;
    },
    captureBaseline,
    revert,
    flashSaved,
  };
}
