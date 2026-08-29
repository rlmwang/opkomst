<script lang="ts">
/**
 * The edit-mode action bar shared by every public edit page. Withdraw sits
 * bottom-left, separated from Save + Revert bottom-right. Purely
 * presentational: the page owns save/revert/withdraw and (for withdraw)
 * its own confirm text. Labels come from the shared chrome strings so all
 * four entities read identically.
 *
 * Save is disabled with nothing pending or during the transient "saved"
 * flash; Revert is disabled with nothing pending.
 *
 * ``canEdit`` false drops Save and Revert entirely: the organiser has
 * closed the answers for changes, so there is nothing to save. Withdraw
 * stays, because taking your answers back is a different right and not
 * the organiser's to close.
 */
import { type Locale, chromeStrings } from "./strings";

const {
  dirty,
  saving,
  justSaved,
  locale,
  canWithdraw = true,
  canEdit = true,
  onsave,
  onrevert,
  onwithdraw,
}: {
  dirty: boolean;
  saving: boolean;
  justSaved: boolean;
  locale: Locale;
  /** Whether the withdraw button shows (default true). */
  canWithdraw?: boolean;
  /** Whether saving is offered at all (default true). */
  canEdit?: boolean;
  onsave: () => void;
  onrevert: () => void;
  onwithdraw: () => void;
} = $props();

const c = $derived(chromeStrings(locale));
</script>

<div class="edit-bar">
  {#if canWithdraw}
    <button type="button" class="bar-btn danger" disabled={saving} onclick={onwithdraw}>
      {c.withdraw}
    </button>
  {:else}
    <span></span>
  {/if}
  {#if canEdit}
    <div class="bar-right">
      <button type="button" class="bar-btn" disabled={saving || !dirty} onclick={onrevert}>
        {c.revert}
      </button>
      <button
        type="button"
        class="btn-primary"
        disabled={saving || justSaved || !dirty}
        onclick={onsave}
      >
        {justSaved ? c.saved : c.save}
      </button>
    </div>
  {:else}
    <span class="closed-note">{c.answersClosed}</span>
  {/if}
</div>

<style>
.closed-note {
  font-size: 0.875rem;
  color: var(--brand-text-muted);
}
.edit-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.bar-right {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}
/* Save is the shared ``.btn-primary`` (forms.css); Revert + Withdraw are
 * low-emphasis outline buttons defined here so the bar is self-contained. */
.bar-btn {
  font: inherit;
  cursor: pointer;
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-border);
  border-radius: 6px;
  background: var(--brand-surface);
  color: var(--brand-text);
}
.bar-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.bar-btn.danger {
  border-color: transparent;
  background: none;
  color: var(--brand-red);
}
.bar-btn.danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--brand-red) 8%, transparent);
}
</style>
