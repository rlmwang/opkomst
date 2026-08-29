<script lang="ts" module>
export interface ChoreDraft {
  id: string | null;
  name: string;
  description: string | null;
  cycle_slots: number[];
  people_per_shift: number;
  // Every chore always carries an emoji (seeded with DEFAULT_CHORE_EMOJI).
  emoji: string;
}
</script>

<script lang="ts">
/**
 * Editor for one chore on a roster. Shape mirrors the backend's
 * ``ChoreIn`` exactly so a parent collecting an array ships them as
 * ``chores`` without a transform. ``id`` is null for newly-added rows;
 * existing chores carry their server uuid so the diff-apply matches.
 *
 * The recurrence is edited via ``CycleGridPicker``, driven by the
 * roster-level ``periodWeeks``. Per-row move/delete mirror
 * ``QuestionEditor`` so both sit on the same ``useOrderedList`` parent.
 */
import AppButton from "@/components/AppButton.svelte";
import AppInput from "@/components/AppInput.svelte";
import CycleGridPicker from "@/components/CycleGridPicker.svelte";
import EmojiPicker from "@/components/EmojiPicker.svelte";
import NumberStepper from "@/components/NumberStepper.svelte";
import { t } from "@/i18n.svelte";

const {
  value,
  periodWeeks,
  canMoveUp,
  canMoveDown,
  onchange,
  ondelete,
  onmoveUp,
  onmoveDown,
}: {
  value: ChoreDraft;
  /** Roster cycle length; drives the number of week rows in the grid. */
  periodWeeks: number;
  canMoveUp: boolean;
  canMoveDown: boolean;
  /** The whole chore, with one field changed. The parent takes the
   *  replacement rather than the row writing itself back, because the
   *  list keeps an invariant across its rows: two chores never wear the
   *  same emoji. */
  onchange: (next: ChoreDraft) => void;
  ondelete: () => void;
  onmoveUp: () => void;
  onmoveDown: () => void;
} = $props();

function patch<K extends keyof ChoreDraft>(key: K, next: ChoreDraft[K]): void {
  onchange({ ...value, [key]: next });
}
</script>

<div class="chore-editor">
  <div class="header-row">
    <span class="emoji-slot">
      <EmojiPicker value={value.emoji} onselect={(e) => patch("emoji", e)} />
    </span>
    <AppInput
      value={value.name}
      placeholder={t("chore.edit.choreNamePlaceholder")}
      fluid
      oninput={(e) => patch("name", (e.currentTarget as HTMLInputElement).value)}
    />
    <div class="header-actions">
      <AppButton
        type="button"
        icon="arrow-up"
        size="small"
        severity="secondary"
        text
        disabled={!canMoveUp}
        ariaLabel={t("chore.edit.moveUp")}
        onclick={onmoveUp}
      />
      <AppButton
        type="button"
        icon="arrow-down"
        size="small"
        severity="secondary"
        text
        disabled={!canMoveDown}
        ariaLabel={t("chore.edit.moveDown")}
        onclick={onmoveDown}
      />
      <AppButton
        type="button"
        icon="trash"
        size="small"
        severity="secondary"
        text
        ariaLabel={t("chore.edit.deleteChore")}
        onclick={ondelete}
      />
    </div>
  </div>

  <AppInput
    value={value.description ?? ""}
    placeholder={t("chore.edit.choreDescriptionPlaceholder")}
    fluid
    oninput={(e) => {
      const v = (e.currentTarget as HTMLInputElement).value;
      patch("description", v ? v : null);
    }}
  />

  <CycleGridPicker
    bind:value={() => value.cycle_slots, (v) => patch("cycle_slots", v)}
    {periodWeeks}
  />

  <div class="people-row">
    <span class="field-label">{t("chore.edit.peoplePerShift")}</span>
    <NumberStepper
      bind:value={() => value.people_per_shift, (v) => patch("people_per_shift", v)}
      min={1}
      max={20}
      ariaLabel={t("chore.edit.peoplePerShift")}
    />
  </div>
</div>

<style>
.chore-editor {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 0.875rem 1rem;
  border: 1px solid var(--brand-border);
  border-radius: 8px;
  background: var(--brand-surface);
}
.header-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.emoji-slot {
  display: inline-flex;
  align-items: center;
}
.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.125rem;
}
.people-row {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  align-self: flex-start;
}
</style>
