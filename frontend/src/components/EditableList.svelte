<script lang="ts" generics="T">
import type { Snippet } from "svelte";

import AppButton from "@/components/AppButton.svelte";
import { t } from "@/i18n.svelte";

const {
  items,
  itemLabel,
  itemKey,
  loadingKey,
  readonly,
  row,
  add,
  onremove,
}: {
  /** The current items. */
  items: T[];
  /** How to render each item's label. */
  itemLabel: (item: T) => string;
  /** Stable per-item key. */
  itemKey: (item: T) => string;
  /** Key of the row whose remove button is mid-flight (waiting on a
   *  usage fetch before opening a confirm dialog, say). The matching
   *  trash button shows a spinner instead of the icon. */
  loadingKey?: string | null;
  /** Disable the trash button on every row. The list still renders the
   *  rows so non-mutators can read the data. */
  readonly?: boolean;
  row?: Snippet<[{ item: T; index: number }]>;
  add?: Snippet;
  onremove: (item: T) => void;
} = $props();
</script>

<div class="editable-list">
  {#each items as item, index (itemKey(item))}
    <div class="list-row">
      <div class="list-row-label">
        <!-- ``index`` is for rows whose value lives in a second array
             kept parallel to this one (a kompas option's direction). -->
        {#if row}
          {@render row({ item, index })}
        {:else}
          <span>{itemLabel(item)}</span>
        {/if}
      </div>
      <AppButton
        icon="trash"
        size="small"
        severity="secondary"
        text
        loading={loadingKey === itemKey(item)}
        disabled={readonly}
        ariaLabel={t("common.remove")}
        onclick={() => onremove(item)}
      />
    </div>
  {/each}
  <div class="add-row">{#if add}{@render add()}{/if}</div>
</div>

<style>
.editable-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.list-row-label {
  flex: 1;
  min-width: 0;
}
.add-row {
  display: flex;
  align-items: stretch;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
/* Inputs grow to fill the row; buttons (and other auxiliary
 * controls) keep their natural size. The previous ``> * { flex: 1 }``
 * stretched the trailing plus-button to 50% of the row width. */
.add-row :global(.app-input) {
  flex: 1;
  min-width: 0;
  width: 100%;
}
</style>
